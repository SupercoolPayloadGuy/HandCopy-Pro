"""
calligraphr_service.py
======================
Parses a filled-in Calligraphr template sheet.

Calligraphr templates are a grid of equal-sized boxes, each containing
one handwritten character.  We:
  1. Find all the boxes by detecting the grid rectangles
  2. Sort them left-to-right, top-to-bottom
  3. Map them to the character list in the order Calligraphr uses
  4. Extract strokes from each box crop

Supported: the standard Calligraphr "Basic Latin" template (A4 or Letter).
The character order matches Calligraphr's default template exactly.
"""

import cv2
import numpy as np
import logging
from services.stroke_service import extract_strokes

log = logging.getLogger(__name__)

# Default Calligraphr template character order (Basic Latin sheet)
# Matches exactly the order boxes appear left→right, top→bottom
CALLIGRAPHR_ORDER = list(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    ".,!?-:;'\"()@#$%&"
)


def _find_glyph_boxes(img: np.ndarray) -> list[tuple[int,int,int,int]]:
    """
    Find the character boxes in a Calligraphr sheet.
    Returns list of (x, y, w, h) sorted top→bottom, left→right.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()

    # Calligraphr boxes have clear borders — threshold and find rectangles
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    # Dilate to connect border lines
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(binary, k, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_area = img.shape[0] * img.shape[1]
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        # Box must be reasonably sized (not too small, not the whole image)
        if area < img_area * 0.001 or area > img_area * 0.1:
            continue
        # Must be roughly square-ish (character boxes are ~square or slightly tall)
        ratio = w / h
        if ratio < 0.4 or ratio > 2.5:
            continue
        # Minimum size filter
        if w < 30 or h < 30:
            continue
        boxes.append((x, y, w, h))

    if not boxes:
        return []

    # Cluster by similar sizes — find the most common box size
    widths = sorted([b[2] for b in boxes])
    median_w = widths[len(widths)//2]
    median_h = sorted([b[3] for b in boxes])[len(boxes)//2]

    # Keep only boxes close to median size (±40%)
    filtered = [b for b in boxes
                if abs(b[2] - median_w) < median_w * 0.4
                and abs(b[3] - median_h) < median_h * 0.4]

    # Sort: top-to-bottom first, then left-to-right within each row
    row_height = median_h * 0.6
    filtered.sort(key=lambda b: (round(b[1] / row_height), b[0]))

    log.info(f"Calligraphr: found {len(filtered)} boxes (median size {median_w}×{median_h}px)")
    return filtered


def _crop_box(img: np.ndarray, x: int, y: int, w: int, h: int, padding: int = 6) -> np.ndarray:
    """Crop a single box from the sheet, with a small inset to remove borders."""
    h_img, w_img = img.shape[:2]
    x1 = max(0, x + padding)
    y1 = max(0, y + padding)
    x2 = min(w_img, x + w - padding)
    y2 = min(h_img, y + h - padding)
    return img[y1:y2, x1:x2]


def parse_calligraphr_sheet(
    image_bytes: bytes,
    character_order: list[str] = None,
) -> dict[str, tuple[list[dict], float]]:
    """
    Parse a filled Calligraphr sheet image.

    Returns:
        dict mapping character → (strokes, width_ratio)
        Only includes characters where strokes were successfully extracted.
    """
    order = character_order or CALLIGRAPHR_ORDER

    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")

    boxes = _find_glyph_boxes(img)
    if not boxes:
        raise ValueError(
            "No character boxes found. Make sure you upload the filled Calligraphr sheet "
            "(not a blank template), scanned straight and well-lit."
        )

    results = {}
    skipped = []

    for i, (x, y, w, h) in enumerate(boxes):
        if i >= len(order):
            break
        char = order[i]
        crop = _crop_box(img, x, y, w, h)
        crop_bytes = cv2.imencode(".png", crop)[1].tobytes()
        try:
            strokes, width_ratio = extract_strokes(crop_bytes)
            if strokes:
                results[char] = (strokes, width_ratio)
            else:
                skipped.append(char)
        except Exception as e:
            log.warning(f"Skipped '{char}': {e}")
            skipped.append(char)

    if skipped:
        log.info(f"Skipped {len(skipped)} empty/unreadable boxes: {''.join(skipped)}")

    log.info(f"Calligraphr: extracted {len(results)} glyphs from {len(boxes)} boxes")
    return results
