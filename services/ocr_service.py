"""OCR Service — image bytes → words with mm positions"""
import io, logging
import cv2, numpy as np, pytesseract
from PIL import Image
import config
from models.schemas import OCRWord

log = logging.getLogger(__name__)


def _deskew(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    _, binary = cv2.threshold(cv2.GaussianBlur(gray, (5,5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 100: return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45: angle += 90
    elif angle > 45: angle -= 90
    if abs(angle) < 0.5 or abs(angle) > 15: return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
    return cv2.adaptiveThreshold(cv2.fastNlMeansDenoising(gray, h=10),
                                  255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)


async def process_document(file_bytes: bytes, dpi: int = None, min_conf: float = 60.0):
    dpi = dpi or config.SCAN_DPI
    arr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        pil = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    h, w = img.shape[:2]
    proc = _preprocess(_deskew(img))
    data = pytesseract.image_to_data(proc, config="--psm 3 --oem 3", output_type=pytesseract.Output.DICT)

    words = []
    for i in range(len(data["text"])):
        t, c = data["text"][i].strip(), float(data["conf"][i])
        if not t or c < min_conf: continue
        words.append(OCRWord(
            text=t,
            x_mm=round(config.px_to_mm(int(data["left"][i]), dpi), 3),
            y_mm=round(config.px_to_mm(int(data["top"][i]), dpi), 3),
            width_mm=round(config.px_to_mm(int(data["width"][i]), dpi), 3),
            height_mm=round(config.px_to_mm(int(data["height"][i]), dpi), 3),
            confidence=round(c, 1),
        ))

    full = " ".join(d.strip() for d in data["text"] if d.strip())
    log.info(f"OCR: {len(words)} words at {dpi} DPI")
    return words, full, w, h


def group_into_lines(words: list[OCRWord], tol_mm: float = 2.0) -> list[dict]:
    if not words: return []
    lines, cur_y, cur = [], None, []
    for w in sorted(words, key=lambda x: (x.y_mm, x.x_mm)):
        if cur_y is None or abs(w.y_mm - cur_y) > tol_mm:
            if cur: lines.append({"y_mm": cur_y, "x_mm": cur[0].x_mm, "text": " ".join(x.text for x in cur)})
            cur_y, cur = w.y_mm, [w]
        else:
            cur.append(w)
    if cur: lines.append({"y_mm": cur_y, "x_mm": cur[0].x_mm, "text": " ".join(x.text for x in cur)})
    return lines
