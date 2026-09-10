"""Drawing toolkit for the tutor UI, matching the wireframe design.

The design (`design/src/App.tsx`, a Figma Make React mock) is a warm, flat,
card-based interface: an off-white ground, white rounded cards, pastel accent
blocks, and Nunito set very heavy for the big numerals and letters. None of
that is reachable with OpenCV's Hershey fonts and square rectangles, so the
whole UI chrome is drawn with Pillow instead and composited back onto the BGR
webcam frame once per frame.

Usage:

    with Canvas(frame) as ui:        # frame is the BGR numpy array
        ui.card((x, y, w, h))
        ui.text("TEACH", (x + 16, y + 12), 12, WEIGHT_BOLD, INK)

Everything here is display-only. The classifier never sees these pixels.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- palette ---
# Straight from the design's `c` object. Kept as RGB hex because all drawing
# happens in Pillow; the frame is converted to RGB on the way in.
BG = "#F7F3EF"          # warm off-white ground
SURFACE = "#EFEBE5"     # deeper off-white for panels and bar tracks
WHITE = "#FFFFFF"
INK = "#111111"         # near-black text
INK_MID = "#555550"
INK_SOFT = "#999990"
INK_FAINT = "#CCCCC5"

YELLOW = "#FFE59A"
YELLOW_DK = "#C49A00"
PINK = "#FFBCC1"
PINK_DK = "#A03040"
MINT = "#B7E1D1"
MINT_DK = "#1A6B50"
SKY = "#A9D3FF"
SKY_DK = "#1A4A80"
TERRA = "#D4784E"
TERRA_FAINT = "#FAE8DC"

# Nunito's weight axis runs 200-1000; these are the steps the design uses.
WEIGHT_MEDIUM = 500
WEIGHT_SEMI = 600
WEIGHT_BOLD = 700
WEIGHT_XBOLD = 800
WEIGHT_BLACK = 900

_FONT_PATH = os.path.join("assets", "fonts", "Nunito-Variable.ttf")
# Ordered fallbacks, used only if the vendored Nunito is missing.
_FALLBACK_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)

_font_cache: dict[tuple[int, int], ImageFont.FreeTypeFont] = {}


def font(size, weight=WEIGHT_SEMI):
    """A cached Nunito face at `size` px and `weight` on the variable axis.

    Font objects are cached because Pillow re-reads and re-instances the face
    otherwise, and this runs on every frame.
    """
    key = (int(size), int(weight))
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    path = _FONT_PATH if os.path.exists(_FONT_PATH) else None
    if path is None:
        path = next((p for p in _FALLBACK_FONTS if os.path.exists(p)), None)

    if path is None:
        face = ImageFont.load_default()
    else:
        face = ImageFont.truetype(path, int(size))
        try:
            face.set_variation_by_axes([int(weight)])
        except Exception:
            # Static face (a fallback): no weight axis to set.
            pass

    _font_cache[key] = face
    return face


def _rgb(color):
    """Hex color -> an (r, g, b) tuple."""
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgba(color, alpha):
    """Hex color + 0-1 alpha -> an RGBA tuple Pillow can fill with."""
    return _rgb(color) + (int(round(alpha * 255)),)


def bgr(color):
    """Hex color -> a BGR tuple, for the frames cv2 fills directly."""
    r, g, b = _rgb(color)
    return (b, g, r)


def blend(color_a, color_b, t):
    """Mix two hex colors; t=0 gives a, t=1 gives b."""
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    out = []
    for i in (0, 2, 4):
        ca, cb = int(a[i:i + 2], 16), int(b[i:i + 2], 16)
        out.append(int(round(ca + (cb - ca) * float(np.clip(t, 0.0, 1.0)))))
    return "#%02X%02X%02X" % tuple(out)


def score_color(value):
    """Pastel accent for a 0-1 quality score: pink -> yellow -> mint."""
    if value < 0.5:
        return blend(PINK, YELLOW, value / 0.5)
    return blend(YELLOW, MINT, (value - 0.5) / 0.5)


# ----------------------------------------------------------------- canvas ---

class Canvas:
    """A Pillow drawing surface over one BGR frame.

    The frame is converted to RGB once on entry and written back on exit, so a
    whole screen costs one round trip rather than one per widget. Use it as a
    context manager; `flush()` is called for you.
    """

    def __init__(self, frame=None, size=None, background=None):
        self._frame = frame
        if frame is not None:
            self.image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        elif background is not None:
            # An opaque offscreen layer. Note that Pillow *replaces* alpha
            # rather than compositing it when drawing onto an RGBA image, so
            # anything translucent drawn on a transparent layer punches a hole
            # straight through it. Layers that should end up opaque must start
            # opaque, in RGB.
            self.image = Image.new("RGB", size, _rgb(background))
        else:
            # A standalone transparent layer, for chrome that can be drawn once
            # and composited on later frames.
            self.image = Image.new("RGBA", size, (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.flush()
        return False

    def flush(self):
        """Write the drawn image back into the original frame, in place."""
        if self._frame is None:
            return
        self._frame[:] = cv2.cvtColor(np.asarray(self.image), cv2.COLOR_RGB2BGR)

    def stamp(self, layer, xy=(0, 0)):
        """Composite a pre-rendered layer, honoring its alpha if it has one."""
        pos = (int(xy[0]), int(xy[1]))
        self.image.paste(layer, pos, layer if layer.mode == "RGBA" else None)

    # -- primitives --

    def rect(self, box, color, radius=0, alpha=1.0, outline=None, width=1):
        """Filled (optionally rounded, optionally translucent) rectangle.

        `box` is (x, y, w, h). Pillow wants (x0, y0, x1, y1) inclusive.
        """
        x, y, w, h = box
        xy = (x, y, x + w - 1, y + h - 1)
        fill = rgba(color, alpha) if color else None
        line = rgba(outline, alpha) if outline else None
        if radius > 0:
            self.draw.rounded_rectangle(xy, radius=radius, fill=fill,
                                        outline=line, width=width)
        else:
            self.draw.rectangle(xy, fill=fill, outline=line, width=width)

    def card(self, box, bg=WHITE, radius=16, alpha=1.0):
        """The design's flat card: rounded, filled, no shadow."""
        self.rect(box, bg, radius=radius, alpha=alpha)

    def text(self, s, xy, size, weight=WEIGHT_SEMI, color=INK, align="left",
             alpha=1.0, tracking=0.0):
        """Draw a single line and return its width in px.

        `align` positions the string horizontally about `xy[0]`: "left",
        "center" or "right". `tracking` adds per-character letter spacing, for
        the design's uppercase eyebrow labels.
        """
        face = font(size, weight)
        x, y = xy
        fill = rgba(color, alpha)

        if tracking:
            width = self.measure(s, size, weight, tracking)
            if align == "center":
                x -= width / 2
            elif align == "right":
                x -= width
            for ch in s:
                self.draw.text((x, y), ch, font=face, fill=fill)
                x += face.getlength(ch) + tracking
            return width

        width = face.getlength(s)
        if align == "center":
            x -= width / 2
        elif align == "right":
            x -= width
        self.draw.text((x, y), s, font=face, fill=fill)
        return width

    def measure(self, s, size, weight=WEIGHT_SEMI, tracking=0.0):
        """Rendered width of `s` in px."""
        face = font(size, weight)
        if tracking:
            return sum(face.getlength(ch) for ch in s) + tracking * max(len(s) - 1, 0)
        return face.getlength(s)

    def text_centered(self, s, box, size, weight=WEIGHT_SEMI, color=INK,
                      alpha=1.0):
        """Center a line on both axes inside (x, y, w, h) by its ink bounds.

        Optical centering matters for the huge single-letter glyphs: Nunito's
        line box carries far more space above a capital than below it, so
        centering on the font metrics leaves the letter visibly high.
        """
        x, y, w, h = box
        face = font(size, weight)
        left, top, right, bottom = face.getbbox(s)
        px = x + (w - (right - left)) / 2 - left
        py = y + (h - (bottom - top)) / 2 - top
        self.draw.text((px, py), s, font=face, fill=rgba(color, alpha))

    def eyebrow(self, s, xy, color=INK_FAINT):
        """The design's 10px uppercase label with wide tracking."""
        return self.text(s.upper(), xy, 10, WEIGHT_BOLD, color, tracking=1.5)

    def bar(self, box, value, color, track=SURFACE, radius=None):
        """Pill-shaped progress bar. `value` is 0-1 and is clamped."""
        x, y, w, h = box
        radius = h // 2 if radius is None else radius
        self.rect(box, track, radius=radius)
        filled = int(round(w * float(np.clip(value, 0.0, 1.0))))
        if filled >= 2:
            self.rect((x, y, max(filled, h), h), color, radius=radius)

    def chip(self, s, xy, bg, color, size=12, weight=WEIGHT_BOLD,
             pad_x=12, height=24, radius=None):
        """Pastel pill with a label. Returns its total width."""
        x, y = xy
        w = int(self.measure(s, size, weight) + pad_x * 2)
        radius = height // 2 if radius is None else radius
        self.rect((x, y, w, height), bg, radius=radius)
        self.text_centered(s, (x, y, w, height), size, weight, color)
        return w

    def tile(self, s, box, bg, color, size=16, weight=WEIGHT_BLACK, radius=12):
        """Rounded square holding one letter — word strips, recent letters."""
        self.rect(box, bg, radius=radius)
        self.text_centered(s, box, size, weight, color)

    def paste(self, image, xy, radius=0):
        """Composite an RGB/RGBA PIL image, optionally rounded-cornered."""
        if radius > 0:
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, image.size[0] - 1, image.size[1] - 1), radius=radius,
                fill=255)
            self.image.paste(image, (int(xy[0]), int(xy[1])), mask)
        else:
            self.image.paste(image, (int(xy[0]), int(xy[1])))

    def wrap(self, s, width, size, weight=WEIGHT_SEMI):
        """Greedy word-wrap `s` to `width` px. Returns a list of lines."""
        words, lines, line = s.split(), [], ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and self.measure(candidate, size, weight) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        return lines

    def paragraph(self, s, xy, width, size, weight=WEIGHT_SEMI, color=INK,
                  line_height=1.6):
        """Draw wrapped body copy. Returns the total height drawn."""
        step = size * line_height
        x, y = xy
        lines = self.wrap(s, width, size, weight)
        for i, line in enumerate(lines):
            self.text(line, (x, y + i * step), size, weight, color)
        return int(round(step * len(lines)))


def mortarboard(ui, box, color):
    """A graduation cap, drawn to fill `box`: board, cap, and tassel."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    fill = rgba(color, 1.0)

    board = w * 0.40          # half-width of the flat top
    ui.draw.polygon([(cx, cy - h * 0.24), (cx + board, cy - h * 0.06),
                     (cx, cy + h * 0.12), (cx - board, cy - h * 0.06)],
                    fill=fill)

    # The cap below it, drawn as the band that shows under the board.
    cap = w * 0.20
    ui.draw.polygon([(cx - cap, cy - h * 0.01), (cx + cap, cy - h * 0.01),
                     (cx + cap, cy + h * 0.16), (cx, cy + h * 0.25),
                     (cx - cap, cy + h * 0.16)], fill=fill)

    # Tassel: down the right edge of the board, ending in a knot.
    tx = cx + board * 0.80
    ui.draw.line([(tx, cy - h * 0.04), (tx, cy + h * 0.18)], fill=fill,
                 width=max(1, int(w * 0.05)))
    knot = max(1.5, w * 0.07)
    ui.draw.ellipse((tx - knot, cy + h * 0.16 - knot,
                     tx + knot, cy + h * 0.16 + knot), fill=fill)



def _bezier(p0, p1, p2, p3, steps):
    """Sample a cubic bezier as a list of (x, y) points."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return out


# The organic decoration from the design's <Blob>, as the control points of its
# SVG path (viewBox 200x200, translated by 100,100 — so these are already
# centered on the origin and range roughly -80..80).
_BLOB_START = (47, -65)
_BLOB_CURVES = (
    ((59, -55), (66, -39), (70, -23)), ((74, -6), (74, 11), (68, 27)),
    ((62, 43), (50, 57), (36, 65)), ((21, 73), (4, 75), (-14, 71)),
    ((-32, 67), (-51, 57), (-63, 42)), ((-74, 27), (-79, 7), (-76, -12)),
    ((-73, -31), (-63, -49), (-48, -60)), ((-33, -72), (-14, -77), (3, -77)),
    ((20, -78), (35, -75), (47, -65)),
)


def blob_points(center, size):
    """The blob outline scaled to `size` px across and centered on `center`."""
    scale = size / 200.0
    pts, cursor = [], _BLOB_START
    for c1, c2, end in _BLOB_CURVES:
        pts.extend(_bezier(cursor, c1, c2, end, 12)[1:])
        cursor = end
    return [(center[0] + x * scale, center[1] + y * scale) for x, y in pts]
