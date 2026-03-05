"""G-code Service — text blocks + strokes → robot motion"""
import math, random, logging
import config

log = logging.getLogger(__name__)


def _slant(pts, deg, h):
    if abs(deg) < 0.1: return pts
    sh = math.tan(math.radians(deg))
    return [[p[0] + sh*(1.0-p[1])*h, p[1]] for p in pts]


def _scale(pts, ox, oy, h, wr):
    cw = h * wr
    return [[round(ox + p[0]*cw, 4), round(oy + p[1]*h, 4)] for p in pts]


def _waver(y, waver, seed):
    return y + random.Random(seed).gauss(0, waver*0.3)


def block_to_gcode(block, glyph_map, slant=0.0, spacing=1.0, word_sp=2.5, waver=0.3, h=None):
    h  = h  or config.CHAR_HEIGHT_MM
    fr = config.DEFAULT_FEED
    rr = config.RAPID_FEED
    pd, pu = config.PEN_DOWN_CMD, config.PEN_UP_CMD

    lines = [f"; '{block['text'][:40]}' at ({block['x_mm']:.1f},{block['y_mm']:.1f})mm", pu]
    cx, cy = block["x_mm"], block["y_mm"]
    line_h = h * 1.8
    max_x  = block["x_mm"] + block.get("max_width_mm", 170.0)

    for wi, word in enumerate(block["text"].split(" ")):
        if cx > block["x_mm"] and cx + sum(h*glyph_map.get(c,{}).get("width_ratio",0.6)*spacing for c in word) > max_x:
            cx = block["x_mm"]; cy += line_h

        for ci, ch in enumerate(word):
            gd = glyph_map.get(ch)
            if ch == " " or gd is None:
                cx += h * (word_sp/10) * spacing; continue
            wr  = gd.get("width_ratio", 0.6)
            yy  = _waver(cy, waver, hash(f"{block['text']}{wi}{ci}") & 0xFFFF)
            for stroke in gd["strokes"]:
                pts = _scale(_slant(stroke["points"], slant, h), cx, yy, h, wr)
                if not pts: continue
                lines += [pu, f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} F{rr}"]
                if stroke.get("pen","down") == "down":
                    lines.append(pd)
                    for p in pts[1:]: lines.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F{fr}")
            cx += h * wr * spacing
        cx += h * (word_sp/10) * spacing

    lines.append(pu)
    return lines


def compile_gcode(text_blocks: list[dict], glyph_map: dict, profile: dict) -> str:
    header = [
        "; === Handwriting Robot G-code ===",
        f"; {len(text_blocks)} block(s)",
        "G21", "G90", config.PEN_UP_CMD, "G28 X Y", "",
    ]
    body = []
    for b in text_blocks:
        body += block_to_gcode(b, glyph_map,
                               slant=profile.get("slant_deg",0.0),
                               spacing=profile.get("letter_spacing",1.0),
                               word_sp=profile.get("word_spacing",2.5),
                               waver=profile.get("baseline_waver",0.3),
                               h=b.get("char_height_mm") or None)
        body.append("")
    footer = [config.PEN_UP_CMD, "G0 X0 Y0 F3000", "M2"]
    return "\n".join(header + body + footer)
