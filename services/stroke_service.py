"""Stroke Service — glyph image → normalized stroke paths"""
import cv2, numpy as np, logging
from skimage.morphology import skeletonize
from scipy.interpolate import splprep, splev

log = logging.getLogger(__name__)


def _walk_skeleton(skel: np.ndarray) -> list[list[tuple]]:
    pixels = set(zip(*np.where(skel)))
    if not pixels: return []
    visited = np.zeros_like(skel, dtype=bool)

    def nbrs(y, x):
        return [(y+dy, x+dx) for dy in [-1,0,1] for dx in [-1,0,1]
                if (dy or dx) and (y+dy, x+dx) in pixels and not visited[y+dy, x+dx]]

    endpoints = [(y,x) for y,x in pixels
                 if sum(1 for dy in [-1,0,1] for dx in [-1,0,1]
                        if (dy or dx) and (y+dy, x+dx) in pixels) == 1]
    starts = endpoints or [next(iter(pixels))]

    strokes = []
    for s in starts:
        if visited[s]: continue
        stack, path = [s], []
        while stack:
            cy, cx = stack[-1]
            if visited[cy, cx]: stack.pop(); continue
            visited[cy, cx] = True
            path.append((cx, cy))
            ns = nbrs(cy, cx)
            if ns: stack.append(ns[0])
            else: stack.pop()
        if len(path) >= 3: strokes.append(path)
    return strokes


def _smooth(pts):
    if len(pts) < 4: return [[float(p[0]), float(p[1])] for p in pts]
    xs, ys = zip(*pts)
    try:
        tck, _ = splprep([xs, ys], s=len(pts)*2, k=min(3, len(pts)-1))
        sx, sy = splev(np.linspace(0, 1, max(len(pts), 20)), tck)
        return [[round(float(x), 4), round(float(y), 4)] for x, y in zip(sx, sy)]
    except Exception:
        return [[float(p[0]), float(p[1])] for p in pts]


def extract_strokes(image_bytes: bytes) -> tuple[list[dict], float]:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None: raise ValueError("Cannot decode image")

    blur = cv2.GaussianBlur(img, (3,3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    k = np.ones((2,2), np.uint8)
    binary = cv2.morphologyEx(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    skel = skeletonize(binary.astype(bool)).astype(np.uint8)

    raw = _walk_skeleton(skel)
    if not raw: return [], 0.6

    all_x = [p[0] for s in raw for p in s]
    all_y = [p[1] for s in raw for p in s]
    sx, sy = (max(all_x)-min(all_x)) or 1, (max(all_y)-min(all_y)) or 1
    mx, my = min(all_x), min(all_y)

    normalized = [{"pen":"down","points":[[round((p[0]-mx)/sx,4), round((p[1]-my)/sy,4)] for p in _smooth(s)]} for s in raw]
    return normalized, round(sx/sy, 4)


def measure_style(sample_bytes: bytes) -> dict:
    arr = np.frombuffer(sample_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    blur = cv2.GaussianBlur(img, (5,5), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    lines = cv2.HoughLines(cv2.Canny(binary, 50, 150), 1, np.pi/180, 30)
    slant = 0.0
    if lines is not None:
        angles = [np.degrees(t)-90 for _,t in lines[:,0] if -45 < np.degrees(t)-90 < 45]
        if angles: slant = round(float(np.median(angles)), 2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bys = [float(y+h) for c in contours for x,y,w,h in [cv2.boundingRect(c)] if w>5 and h>5]
    waver = round(min(max(float(np.std(bys))*25.4/300, 0.1), 2.0), 3) if len(bys) > 3 else 0.3
    return {"slant_deg": slant, "baseline_waver": waver}
