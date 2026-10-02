"""Redraw the Maptology logo mark and favicon with clean geometry.

The mark (folded map, network nodes, check) is drawn here from coordinates,
so strokes are even and edges are sharp. The "Maptology" wordmark is kept
from the existing maptology.png, below the mark.

    python3 build/make_logo.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "maptology.png")
FAVICON = os.path.join(ROOT, "favicon.png")

DARK = (4, 63, 71, 255)
TEAL = (32, 146, 173, 255)
PAPER = (255, 255, 255, 255)

# Mark coordinates are on a 1000 x 1000 grid.
GRID = 1000
SS = 4  # drawn this many times larger, then reduced, for smooth edges

XS = (150, 383, 617, 850)        # left edge, two folds, right edge
TOP = (300, 190, 300, 190)       # zigzag top edge at each x
BOTTOM = (860, 750, 860, 750)    # zigzag bottom edge at each x

STROKE = 44
NODE_R = 88
NODE_INNER_R = 46
CHECK = [(345, 520), (465, 640), (700, 375)]
CHECK_W = 78
CHECK_OUTLINE = 22

# Nodes, and the point inside or on the map each one connects to.
NODES = [
    ((140, 140), (345, 520)),   # top left, into the check
    ((745, 90), (680, 270)),    # top right, onto the top edge
    ((XS[3], 610), (700, 560)), # right edge, inward
    ((XS[0], BOTTOM[0]), (290, 655)),  # bottom left corner, inward
]

# Short fold creases, one from the top and one from the bottom.
FOLDS = [
    ((XS[1], TOP[1]), (XS[1], 345)),
    ((XS[2], BOTTOM[2]), (XS[2], 705)),
]


def _round_line(draw, points, width, fill, s):
    pts = [(x * s, y * s) for x, y in points]
    draw.line(pts, fill=fill, width=int(width * s), joint="curve")
    r = width * s / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _circle(draw, center, r, fill, s):
    x, y = center[0] * s, center[1] * s
    draw.ellipse((x - r * s, y - r * s, x + r * s, y + r * s), fill=fill)


def draw_mark(size, stroke_scale=1.0, folds=True):
    """The mark alone on a transparent square, `size` pixels across.

    The fold creases can be left out for small sizes, where they only blur
    into the check.
    """
    s = size * SS / GRID
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = STROKE * stroke_scale

    outline = ([(x, t) for x, t in zip(XS, TOP)]
               + [(x, b) for x, b in reversed(list(zip(XS, BOTTOM)))])
    d.polygon([(x * s, y * s) for x, y in outline], fill=PAPER)

    for node, target in NODES:
        _round_line(d, [node, target], w, DARK, s)
    for a, b in (FOLDS if folds else []):
        _round_line(d, [a, b], w, DARK, s)
    _round_line(d, outline + [outline[0]], w, DARK, s)

    _round_line(d, CHECK, CHECK_W + 2 * CHECK_OUTLINE * stroke_scale, DARK, s)
    _round_line(d, CHECK, CHECK_W, TEAL, s)

    for node, _ in NODES:
        _circle(d, node, NODE_R * (1 + 0.15 * (stroke_scale - 1)), DARK, s)
        _circle(d, node, NODE_INNER_R, TEAL, s)

    return img.resize((size, size), Image.LANCZOS)


def build_logo():
    old = Image.open(LOGO).convert("RGBA")
    w, h = old.size
    word_top = 500  # the wordmark starts below this row in the original
    word = old.crop((0, word_top, w, h))

    mark_size = 500
    mark = draw_mark(mark_size)
    bbox = mark.getbbox()
    mark = mark.crop(bbox)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(mark, ((w - mark.width) // 2, max(0, word_top - 10 - mark.height)), mark)
    out.alpha_composite(word, (0, word_top))
    out.save(LOGO)


def build_favicon(size=256):
    # Heavier strokes so the mark still reads at 16 and 32 pixels.
    mark = draw_mark(size * 2, stroke_scale=1.35, folds=False)
    mark = mark.crop(mark.getbbox())
    side = int(max(mark.size) * 1.06)
    canvas = Image.new("RGBA", (side, side), PAPER)
    canvas.alpha_composite(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    canvas.resize((size, size), Image.LANCZOS).convert("RGB").save(FAVICON)


if __name__ == "__main__":
    build_logo()
    build_favicon()
