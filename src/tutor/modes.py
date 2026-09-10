"""Tutor mode state machine.

Each mode is a small class that owns its own panel rendering and key handling.
The main webcam loop in `src/live_inference.py` holds a current Mode, calls
`update()` each frame with the latest model output and landmarks, then calls
`render()` to draw the interface and forwards key presses through
`handle_key()`.

Modes:
    HomeMode       - full-screen menu, picks one of the three tutor modes
    TeachMode      - target letter with ghost overlay + per-joint feedback
    PracticeMode   - free signing, CNN prediction + geometric closeness
    SpellWordMode  - target word, hold each sign for DWELL_SECONDS to commit

The look follows the wireframe design in `design/src/App.tsx`: a dark icon
rail on the left, the live camera in the middle, and a warm off-white panel of
rounded cards on the right. `theme.py` holds the palette and the drawing
primitives; this module is only layout and state.

All modes assume the frame is already flipped and the CNN + reference library
results have been computed by the caller. They only decide what to draw and
what state to update; they don't run inference themselves.
"""

from __future__ import annotations

import random
import time
from collections import deque
from pathlib import Path

from PIL import Image

from ..config import (
    CNN_THRESHOLD,
    DWELL_SECONDS,
    GEO_THRESHOLD,
    PANEL_WIDTH,
    RAIL_WIDTH,
    TEACH_HOLD_FRAMES,
    WORDS_PATH,
)
from ..skeleton import draw_joint_errors, render_ghost, render_pose_card
from . import theme as t
from .reference import worst_fingers
from .session import Session

WORDS_PATH = Path(WORDS_PATH)

# ------- letters -------
SUPPORTED_LETTERS = list("ABCDEFGHIKLMNOPQRSTUVWXY")  # 24, no J/Z

# ------- layout -------
PAD = 16              # panel padding, and the padding inside every card
GAP = 10              # vertical space between cards
RADIUS = 16           # card corner radius
BTN_H = 40
STRIP_H = 64          # spell-a-word progress strip


def _panel_box(frame):
    """(x, y, w, h) of the right-hand panel, below any top strip."""
    h, w = frame.shape[:2]
    return (w - PANEL_WIDTH, 0, PANEL_WIDTH, h)


# ------- shared chrome -------

_NAV = (("home", "Home", ord("h")), ("teach", "Teach", ord("1")),
        ("practice", "Practice", ord("2")), ("spell", "Spell", ord("3")))


def _nav_icon(ui, kind, box, color):
    """One 18x18 rail glyph, drawn from primitives."""
    x, y, w, h = box
    d = ui.draw
    fill = t.rgba(color, 1.0)
    if kind == "home":
        d.polygon([(x + w / 2, y), (x, y + h * 0.45), (x + w * 0.16, y + h * 0.45),
                   (x + w * 0.16, y + h), (x + w * 0.84, y + h),
                   (x + w * 0.84, y + h * 0.45), (x + w, y + h * 0.45)], fill=fill)
    elif kind == "teach":
        d.rounded_rectangle((x, y + 1, x + w, y + h * 0.66), radius=3, fill=fill)
        d.rounded_rectangle((x + w * 0.36, y + h * 0.76, x + w * 0.64, y + h),
                            radius=2, fill=fill)
    elif kind == "practice":
        d.ellipse((x, y, x + w, y + h), outline=fill, width=2)
        d.ellipse((x + w * 0.32, y + h * 0.32, x + w * 0.68, y + h * 0.68), fill=fill)
    else:  # spell
        for i, frac in enumerate((1.0, 0.58, 0.75)):
            yy = y + 2 + i * (h - 4) / 2
            d.rounded_rectangle((x, yy - 1, x + w * frac, yy + 1), radius=1, fill=fill)


def _render_rail(ui, frame, active, height=None, mode=None):
    """The dark icon rail down the left edge, with the active mode lit.

    Pass `mode` to register the icons as clickable; each stands for the key
    that reaches the same screen.
    """
    h = height if height is not None else frame.shape[0]
    ui.rect((0, 0, RAIL_WIDTH, h), t.INK)

    # Logo mark: a yellow rounded tile holding a dark graduation cap.
    lx, ly, size = (RAIL_WIDTH - 36) // 2, 20, 36
    ui.rect((lx, ly, size, size), t.YELLOW, radius=12)
    t.mortarboard(ui, (lx, ly, size, size), t.INK)

    y = ly + size + 20
    for kind, _label, key in _NAV:
        selected = kind == active
        box = ((RAIL_WIDTH - 44) // 2, y, 44, 44)
        if selected:
            ui.rect(box, t.WHITE, radius=14, alpha=0.12)
        _nav_icon(ui, kind, ((RAIL_WIDTH - 18) // 2, y + 13, 18, 18),
                  t.WHITE if selected else t.INK_SOFT)
        if mode is not None:
            mode.hit(box, key)
        y += 48

    # Help sits apart from the four destinations, at the foot of the rail.
    help_box = ((RAIL_WIDTH - 44) // 2, h - 64, 44, 44)
    ui.rect(help_box, t.WHITE, radius=14, alpha=0.10)
    ui.text_centered("?", help_box, 20, t.WEIGHT_BLACK, t.WHITE)
    if mode is not None:
        mode.hit(help_box, ord("?"))


def _mixed_label(ui, normal, bold, xy):
    """The design's two-tone panel heading: "Teach a letter"."""
    x, y = xy
    x += ui.text(f"{normal} ", (x, y), 14, t.WEIGHT_MEDIUM, t.INK_SOFT)
    ui.text(bold, (x, y), 14, t.WEIGHT_XBOLD, t.INK)


def _button(ui, box, label, badge, variant="default", mode=None, key=None):
    """Pill button with a keybinding badge, in one of the design's variants.

    Pass `mode` to make it clickable: the region is registered against `key`
    (defaulting to the badge letter), so clicking it runs exactly what pressing
    that key runs.
    """
    x, y, w, h = box
    if mode is not None:
        mode.hit(box, key if key is not None else ord(badge.lower()[:1]))
    badge_box = (x + 12, y + (h - 24) // 2, 24, 24)

    if variant == "ghost":
        # No plate at all: just the key and the label, in muted ink.
        ui.text(f"{badge}   {label}", (x + 14, y + (h - 19) // 2), 13,
                t.WEIGHT_BOLD, t.INK_SOFT)
        return

    if variant == "primary":
        ui.rect(box, t.INK, radius=14)
        ui.rect(badge_box, t.WHITE, radius=8, alpha=0.15)
        text_color, badge_fg = t.WHITE, t.WHITE
    else:
        ui.rect(box, t.WHITE, radius=14, outline=t.INK_FAINT, width=2)
        ui.rect(badge_box, t.SURFACE, radius=8)
        text_color, badge_fg = t.INK, t.INK_SOFT

    ui.text_centered(badge, badge_box, 10, t.WEIGHT_XBOLD, badge_fg)
    ui.text(label, (x + 48, y + (h - 19) // 2), 14, t.WEIGHT_BOLD, text_color)


def _stat(ui, xy, value, label):
    """A number over its caption, for the small tally cards."""
    x, y = xy
    ui.text(value, (x, y), 24, t.WEIGHT_BLACK, t.INK)
    ui.text(label, (x, y + 30), 10, t.WEIGHT_SEMI, t.INK_SOFT)


def _divider_row(ui, x, y, w, left, right_letter, right_pct):
    """The card footer that reports what the CNN currently sees."""
    ui.rect((x, y, w, 1), t.SURFACE)
    ui.text(left, (x, y + 12), 11, t.WEIGHT_SEMI, t.INK_SOFT)
    if right_letter:
        pct_w = ui.measure(right_pct, 11, t.WEIGHT_SEMI)
        ui.text(right_pct, (x + w, y + 14), 11, t.WEIGHT_SEMI, t.INK_SOFT,
                align="right")
        ui.text(right_letter, (x + w - pct_w - 6, y + 11), 14, t.WEIGHT_XBOLD,
                t.INK, align="right")
    else:
        ui.text("no hand", (x + w, y + 12), 11, t.WEIGHT_SEMI, t.INK_FAINT,
                align="right")


class _Stack:
    """Top-down card layout inside the panel, with a bottom-pinned footer."""

    def __init__(self, box, top_pad=PAD):
        x, y, w, h = box
        self.x = x + PAD
        self.w = w - PAD * 2
        self.y = y + top_pad
        self.bottom = y + h - PAD

    def place(self, height, gap=GAP):
        """Reserve `height` px and return the (x, y, w, h) box for it."""
        box = (self.x, self.y, self.w, height)
        self.y += height + gap
        return box

    def pin(self, height, gap=GAP):
        """Reserve `height` px at the bottom of the panel instead."""
        self.bottom -= height
        box = (self.x, self.bottom, self.w, height)
        self.bottom -= gap
        return box


# ------- reference art -------

_pose_card_cache: dict[tuple[str, int, int], Image.Image] = {}


def _pose_image(ref_lib, letter, width, height):
    """Cached "how to sign" illustration for one letter, or None."""
    if ref_lib is None or letter not in ref_lib.poses:
        return None
    key = (letter, width, height)
    cached = _pose_card_cache.get(key)
    if cached is None:
        cached = Image.fromarray(
            render_pose_card(ref_lib.poses[letter], width, height))
        _pose_card_cache[key] = cached
    return cached


def _target_card(ui, box, letter, ref_lib, eyebrow="Target letter"):
    """Target letter beside its reference hand shape, in one card.

    The design pairs a letter card with a landscape photo card. A rendered
    reference pose is portrait-shaped line art rather than a photo, so it would
    swim in a full-width landscape card; setting it next to the glyph fills the
    card properly and costs less vertical space, which the panel is short of.
    """
    x, y, w, h = box
    ui.card(box, t.WHITE, radius=RADIUS)
    ui.eyebrow(eyebrow, (x + PAD, y + PAD))

    art = int(h - PAD * 2 - 10)
    image = _pose_image(ref_lib, letter, art, art)
    if image is not None:
        ax = x + w - PAD - art
        ui.rect((ax, y + PAD + 10, art, art), t.SURFACE, radius=12)
        ui.paste(image, (ax, y + PAD + 10), radius=12)
        ui.text("how to sign", (ax + art / 2, y + h - PAD - 2), 9,
                t.WEIGHT_BOLD, t.INK_FAINT, align="center", tracking=1.0)
        glyph_w = w - PAD * 2 - art - 10
    else:
        glyph_w = w - PAD * 2

    ui.text_centered(letter, (x + PAD, y + PAD + 14, glyph_w, h - PAD * 2 - 20),
                     72, t.WEIGHT_BLACK, t.INK)


# ------- help modal + camera notice -------

HELP_TITLE = "What this is"

HELP_SECTIONS = (
    ("What it does",
     "A tutor for the American Sign Language fingerspelling alphabet. Pick a "
     "letter, copy the shape with your hand, and get told which fingers are "
     "off until you have it."),
    ("Why it needs your camera",
     "The whole thing works by watching the shape of your hand, so it needs "
     "the webcam to see it. The video is read frame by frame on this computer "
     "and thrown away immediately — nothing is recorded, saved, or uploaded, "
     "and there is no network connection involved."),
    ("How it grades you",
     "Two things look at your hand at once. A trained classifier decides "
     "whether the sign is right at all, and a geometric comparison against a "
     "stored reference pose fills the match bar and colors each knuckle by "
     "how far off it is."),
    ("What is missing",
     "J and Z are left out: they are the two letters made with movement "
     "rather than a held shape, and this app only reads still hand shapes."),
)


def _render_help(ui, mode, frame):
    """Full-screen explainer, opened by the rail's ? button or the ? key."""
    h, w = frame.shape[:2]
    ui.rect((0, 0, w, h), t.INK, alpha=0.55)

    cw, ch = 680, 540
    cx, cy = (w - cw) // 2, (h - ch) // 2
    ui.card((cx, cy, cw, ch), t.BG, radius=20)

    ui.eyebrow("About this app", (cx + 40, cy + 36))
    ui.text(HELP_TITLE, (cx + 40, cy + 54), 30, t.WEIGHT_BLACK, t.INK)

    y = cy + 104
    for heading, body in HELP_SECTIONS:
        ui.text(heading, (cx + 40, y), 13, t.WEIGHT_XBOLD, t.TERRA)
        y += 22
        y += ui.paragraph(body, (cx + 40, y), cw - 80, 12, t.WEIGHT_MEDIUM,
                          t.INK_MID)
        y += 14

    ui.rect((cx + 40, y, cw - 80, 1), t.INK_FAINT)
    y += 16
    ui.text("1 2 3 switch modes  ·  H home  ·  N next  ·  R random  "
            "·  S skip  ·  Q quit", (cx + 40, y), 11, t.WEIGHT_SEMI,
            t.INK_SOFT)

    close = (cx + cw - 40 - 150, cy + ch - 40 - BTN_H, 150, BTN_H)
    _button(ui, close, "Got it", "?", "primary", mode=mode, key=ord("?"))


def camera_prompt(frame, error_message=None):
    """Full-screen "we need the camera" notice, drawn over whatever is behind.

    Shown by the webcam loop whenever no frames are arriving — no camera
    attached, or the permission was never granted or has been revoked.

    Returns the "retry" and "quit" button boxes so the loop can route clicks to
    them. They are not registered on the current mode: this notice blocks the
    screen, and a click landing on a button hidden behind it would surprise.
    """
    h, w = frame.shape[:2]
    with t.Canvas(frame) as ui:
        ui.rect((0, 0, w, h), t.BG, alpha=0.94)

        cw, ch = 620, 300
        cx, cy = (w - cw) // 2, (h - ch) // 2
        ui.card((cx, cy, cw, ch), t.WHITE, radius=20)

        icon = (cx + cw // 2 - 26, cy + 34, 52, 52)
        ui.rect(icon, t.YELLOW, radius=16)
        ui.text_centered("!", icon, 30, t.WEIGHT_BLACK, t.YELLOW_DK)

        ui.text("Please allow camera access", (cx + cw / 2, cy + 104), 24,
                t.WEIGHT_BLACK, t.INK, align="center")
        body = ("The tutor reads the shape of your hand from the webcam, so it "
                "cannot register your movement without it. Allow camera access "
                "for this app, then press R to try again. Nothing is recorded "
                "or uploaded — frames are read and discarded as they arrive.")
        lines = ui.wrap(body, cw - 120, 13, t.WEIGHT_MEDIUM)
        for i, line in enumerate(lines):
            ui.text(line, (cx + cw / 2, cy + 146 + i * 22), 13, t.WEIGHT_MEDIUM,
                    t.INK_MID, align="center")

        if error_message:
            ui.text(error_message[:78], (cx + cw / 2, cy + ch - 84), 10,
                    t.WEIGHT_SEMI, t.INK_FAINT, align="center")

        retry = (cx + cw / 2 - 160, cy + ch - 64, 160, BTN_H)
        quit_box = (cx + cw / 2 + 10, cy + ch - 64, 120, BTN_H)
        _button(ui, retry, "Try again", "R", "primary")
        _button(ui, quit_box, "Quit", "Q")
    return {"retry": retry, "quit": quit_box}


def _camera_note(ui, box, ready):
    """The allow-the-camera line, or a quiet confirmation once it is running."""
    if ready:
        ui.card(box, t.MINT, radius=box[3] // 2)
        ui.text_centered("Camera on — frames are read here and discarded.",
                         box, 12, t.WEIGHT_BOLD, t.MINT_DK)
    else:
        ui.card(box, t.YELLOW, radius=box[3] // 2)
        ui.text_centered(
            "Please allow camera access so the app can register your movement.",
            box, 12, t.WEIGHT_BOLD, t.YELLOW_DK)


# ------- base class -------

class Mode:
    """Base tutor mode.

    Subclasses implement `_render()`; the public `render()` wraps it so the
    click map is rebuilt every frame and the help modal draws on top.
    """
    name = "base"
    nav = "home"

    def __init__(self):
        # Clickable regions for this frame: [((x, y, w, h), key), ...]. Every
        # region maps to the key it stands for, so a click and its keystroke
        # always take the same path through handle_key().
        self._hits = []
        self.show_help = False
        # Set by the webcam loop each frame; drives the "allow camera" notice.
        self.camera_ready = False

    def update(self, cnn_label, cnn_conf, landmarks, ref_lib):
        """Called each frame with the latest model output.

        cnn_label:  str or None
        cnn_conf:   float in [0, 1]
        landmarks:  Tasks-API landmark list or None if no hand
        ref_lib:    ReferenceLibrary instance or None if not loaded
        """
        pass

    def hit(self, box, key):
        """Register a clickable region standing in for `key`."""
        self._hits.append((box, key))

    def render(self, frame):
        """Draw the mode, then the help modal if it is open."""
        self._hits = []
        self._render(frame)
        if self.show_help:
            # The modal owns every click while it is up; anything registered
            # behind it would otherwise still be pressable.
            self._hits = []
            with t.Canvas(frame) as ui:
                _render_help(ui, self, frame)

    def _render(self, frame):
        """Draw whatever UI this mode wants onto frame."""
        pass

    def handle_click(self, x, y):
        """Route a click to whichever key its region stands for."""
        for (bx, by, bw, bh), key in reversed(self._hits):
            if bx <= x < bx + bw and by <= y < by + bh:
                return self.handle_key(key)
        return None

    def handle_key(self, key):
        """Return a new Mode to switch to, or None to stay.

        Modal handling lives here so it cannot be skipped: subclasses override
        `_handle_key`, which is only reached once the help overlay is closed.
        """
        if self.show_help:
            # Any key dismisses the modal; nothing behind it should react.
            self.show_help = False
            return None
        if key in (ord("?"), ord("/")):
            self.show_help = True
            return None
        return self._handle_key(key)

    def _handle_key(self, key):
        """Mode-specific keys. The rail shows all four destinations at once,
        so 1/2/3/H jump between modes from anywhere, not only from home."""
        if key in (ord("1"), ord("2"), ord("3"), ord("h"), ord("H")):
            target = {ord("1"): TeachMode, ord("2"): PracticeMode,
                      ord("3"): SpellWordMode}.get(key, HomeMode)
            return None if isinstance(self, target) and target is HomeMode else target()
        return None


# ------- Home -------

class HomeMode(Mode):
    name = "home"
    nav = "home"

    _CARDS = (
        ("teach", "Teach", "a letter",
         "Step through each letter with live feedback and a hand reference.",
         t.YELLOW, t.YELLOW_DK),
        ("practice", "Practice", "free signing",
         "Sign freely and see how the model reads your hand in real time.",
         t.MINT, t.MINT_DK),
        ("spell", "Spell", "a word",
         "Hold each letter sign until it commits, then move to the next one.",
         t.SKY, t.SKY_DK),
    )

    def __init__(self):
        super().__init__()
        self._layer = None
        self._layer_size = None
        self._boxes = []          # click regions baked with the layer
        self._note_box = (0, 0, 0, 0)   # slot the camera note is drawn into

    def _render(self, frame):
        h, w = frame.shape[:2]
        # The menu itself never changes, so it is drawn once into a layer and
        # stamped on. Only the camera note below it varies frame to frame.
        if self._layer is None or self._layer_size != (w, h):
            self._boxes = []
            self._layer = self._build_layer(w, h)
            self._layer_size = (w, h)
        for box, key in self._boxes:
            self.hit(box, key)

        with t.Canvas(frame) as ui:
            ui.stamp(self._layer)
            _camera_note(ui, self._note_box, self.camera_ready)

    def _build_layer(self, w, h):
        """Draw the whole static home screen into a reusable layer."""
        # Opaque: this is a title screen, not a heads-up display over the
        # camera, and a washed-out live feed behind the menu reads as noise.
        ui = t.Canvas(size=(w, h), background=t.BG)
        _render_rail(ui, None, self.nav, height=h)
        rail_y = 20 + 36 + 20
        for i, (_kind, _label, key) in enumerate(_NAV):
            self._boxes.append((((RAIL_WIDTH - 44) // 2, rail_y + i * 48, 44, 44),
                                key))
        self._boxes.append((((RAIL_WIDTH - 44) // 2, h - 64, 44, 44), ord("?")))

        # Home has no panel, so the content centers on everything right
        # of the rail rather than on the narrower camera column.
        cx = RAIL_WIDTH + (w - RAIL_WIDTH) // 2

        # Organic decorations from the design.
        for color, center, size, alpha in (
            (t.YELLOW, (w - 150, 90), 320, 0.55),
            (t.MINT, (RAIL_WIDTH + 140, h - 110), 260, 0.45),
            (t.PINK, (w - 230, h - 150), 180, 0.30),
            (t.TERRA_FAINT, (RAIL_WIDTH + 90, 130), 200, 0.70),
        ):
            ui.draw.polygon(t.blob_points(center, size),
                            fill=t.rgba(color, alpha))

        y = 48
        ui.text("WELCOME", (cx, y), 10, t.WEIGHT_BOLD, t.INK_FAINT,
                align="center", tracking=2.0)
        y += 22
        ui.text("ASL Fingerspelling", (cx, y), 38, t.WEIGHT_BLACK, t.INK,
                align="center")
        y += 44
        ui.text("Tutor", (cx, y), 38, t.WEIGHT_BLACK, t.TERRA, align="center")
        y += 54

        # Reserved for the camera note, which is the one part of this screen
        # that changes and so is drawn per-frame rather than baked in.
        self._note_box = (cx - 250, y, 500, 36)
        y += 48

        for line in ("Learn the 24 static letters at your own pace.",
                     "Every sign gets clearer with a little practice."):
            ui.text(line, (cx, y), 13, t.WEIGHT_MEDIUM, t.INK_MID,
                    align="center")
            y += 22

        y += 14
        card_w = 380
        card_x = cx - card_w // 2
        for i, (_id, title, sub, desc, chip_bg, chip_fg) in enumerate(self._CARDS):
            box = (card_x, y, card_w, 92)
            self._boxes.append((box, ord(str(i + 1))))
            ui.card(box, t.WHITE, radius=RADIUS)
            bx = card_x + 20
            chip_w = ui.chip(title, (bx, y + 16), chip_bg, chip_fg, size=12)
            ui.text(sub, (bx + chip_w + 8, y + 20), 13, t.WEIGHT_SEMI,
                    t.INK_MID)
            ui.text(f"[{i + 1}]", (card_x + card_w - 20, y + 20), 12,
                    t.WEIGHT_XBOLD, t.INK_FAINT, align="right")
            ui.paragraph(desc, (bx, y + 50), card_w - 40, 12,
                         t.WEIGHT_MEDIUM, t.INK_SOFT)
            y += 92 + 10

        help_box = (cx - 92, y + 4, 184, 34)
        self._boxes.append((help_box, ord("?")))
        ui.rect(help_box, t.WHITE, radius=12, outline=t.INK_FAINT, width=2)
        ui.text_centered("?   What is this?", help_box, 12, t.WEIGHT_BOLD,
                         t.INK_MID)

        ui.text("J and Z are motion signs and are not included in this version.",
                (cx, h - 62), 11, t.WEIGHT_MEDIUM, t.INK_FAINT, align="center")
        ui.text("[Q] quit", (cx, h - 40), 11, t.WEIGHT_BOLD, t.INK_FAINT,
                align="center")
        return ui.image


# ------- Teach -------

class TeachMode(Mode):
    name = "teach"
    nav = "teach"

    def __init__(self, letters=None):
        super().__init__()
        self.queue = list(letters) if letters else list(SUPPORTED_LETTERS)
        random.shuffle(self.queue)
        self.order = list(self.queue)          # for the progress grid
        self.target = self.queue.pop(0)
        self.last_score = 0.0
        self.last_worst = []
        self.last_cnn_label = None
        self.last_cnn_conf = 0.0
        # Kept for the on-frame overlay: the live hand, its per-joint errors,
        # and the reference pose to ghost over it.
        self.last_landmarks = None
        self.last_dists = None
        self.last_mirrored = False
        self.last_ref_pose = None
        self.ref_lib = None
        self.pass_history = deque(maxlen=TEACH_HOLD_FRAMES)
        self.session = Session(mode="teach")
        self.completed = False

    @property
    def done_count(self):
        return len(self.order) - len(self.queue) - (0 if self.completed else 1)

    def _next_letter(self, passed=True):
        self.session.record(self.target, passed=passed,
                            score=self.last_score if passed else 0.0)
        if not self.queue:
            self.completed = True
            return
        self.target = self.queue.pop(0)
        self.pass_history.clear()

    def update(self, cnn_label, cnn_conf, landmarks, ref_lib):
        self.last_cnn_label = cnn_label
        self.last_cnn_conf = cnn_conf or 0.0
        self.ref_lib = ref_lib
        if landmarks is not None and ref_lib is not None and self.target in ref_lib.poses:
            score, dists, mirrored = ref_lib.score(landmarks, self.target)
            self.last_score = score
            self.last_worst = worst_fingers(dists, top=2)
            self.last_landmarks = landmarks
            self.last_dists = dists
            self.last_mirrored = mirrored
            self.last_ref_pose = ref_lib.poses[self.target]
        else:
            self.last_score = 0.0
            self.last_worst = []
            self.last_landmarks = None
            self.last_dists = None
            self.last_ref_pose = None

        passed = (cnn_label == self.target
                  and self.last_cnn_conf >= CNN_THRESHOLD
                  and self.last_score >= GEO_THRESHOLD)
        self.pass_history.append(passed)
        if (len(self.pass_history) == self.pass_history.maxlen
                and all(self.pass_history)):
            self._next_letter()

    def _coaching(self):
        """One line of feedback keyed off how close the current hand is."""
        if self.last_landmarks is None:
            return ("Hold your hand up in front of the camera to get started.",
                    t.SURFACE, t.INK_MID)
        if self.last_score >= 0.9:
            return ("That is the shape. Hold it steady for a moment.",
                    t.MINT, t.MINT_DK)
        if self.last_worst:
            fingers = " and ".join(self.last_worst)
            return (f"Try adjusting your {fingers} — everything else is close.",
                    t.YELLOW, t.YELLOW_DK)
        return ("Keep going, you are getting closer.", t.YELLOW, t.YELLOW_DK)

    def _render_overlay(self, frame):
        """Ghost the target pose onto the live hand and color the bad joints."""
        if self.last_landmarks is None or self.last_ref_pose is None:
            return
        render_ghost(frame, self.last_ref_pose, self.last_landmarks,
                     mirrored=self.last_mirrored)
        if self.last_dists is not None:
            draw_joint_errors(frame, self.last_landmarks, self.last_dists)

    def _render_complete(self, ui, frame):
        stack = _Stack(_panel_box(frame))
        _mixed_label(ui, "Alphabet", "complete", (stack.x, stack.y))
        stack.y += 30

        box = stack.place(190)
        ui.card(box, t.MINT, radius=RADIUS)
        ui.text("Well done.", (box[0] + box[2] / 2, box[1] + 32), 26,
                t.WEIGHT_BLACK, t.MINT_DK, align="center")
        ui.paragraph(
            "You worked through all 24 letters. That kind of persistence is "
            "exactly how signs become second nature.",
            (box[0] + 20, box[1] + 78), box[2] - 40, 12, t.WEIGHT_MEDIUM,
            t.INK_MID)

        attempts = self.session.attempts
        accuracy = self.session.accuracy
        ui.text(f"{attempts} letters - {accuracy:.0%} first-try",
                (stack.x, stack.y + 4), 12, t.WEIGHT_SEMI, t.INK_SOFT)

        _button(ui, stack.pin(BTN_H), "Return home", "H", "primary", mode=self)

    def _render(self, frame):
        if not self.completed:
            self._render_overlay(frame)

        with t.Canvas(frame) as ui:
            panel = _panel_box(frame)
            ui.rect(panel, t.SURFACE)
            _render_rail(ui, frame, self.nav, mode=self)

            if self.completed:
                self._render_complete(ui, frame)
                return

            stack = _Stack(panel)
            _mixed_label(ui, "Teach", "a letter", (stack.x, stack.y))
            stack.y += 30

            _target_card(ui, stack.place(150), self.target, self.ref_lib)

            # Match + CNN readout
            box = stack.place(92)
            ui.card(box, t.WHITE, radius=RADIUS)
            bx, by, bw = box[0] + PAD, box[1] + PAD, box[2] - PAD * 2
            ui.bar((bx, by + 2, bw, 10), self.last_score,
                   t.score_color(self.last_score))
            ui.text(f"Match — {self.last_score:.0%}", (bx, by + 18), 11,
                    t.WEIGHT_SEMI, t.INK_SOFT)
            _divider_row(ui, bx, by + 40, bw, "CNN read", self.last_cnn_label,
                         f"{self.last_cnn_conf:.0%}")

            # Coaching
            copy, bg, fg = self._coaching()
            box = stack.place(72)
            ui.card(box, bg, radius=RADIUS)
            ui.paragraph(copy, (box[0] + PAD, box[1] + PAD), box[2] - PAD * 2,
                         12, t.WEIGHT_BOLD, fg)

            # Progress grid
            done = self.done_count
            box = stack.place(104)
            ui.card(box, t.WHITE, radius=RADIUS)
            ui.eyebrow(f"Progress - {done} / {len(self.order)}",
                       (box[0] + PAD, box[1] + PAD))
            # 12 x 22px tiles + 2px gaps is 286px, inside the card's 292px of
            # inner width (the card is 324 wide, less PAD on each side).
            tile, gap, per_row = 22, 2, 12
            gx0, gy0 = box[0] + PAD, box[1] + PAD + 24
            for i, letter in enumerate(self.order):
                col, row = i % per_row, i // per_row
                tx = gx0 + col * (tile + gap)
                ty = gy0 + row * (tile + gap)
                if i < done:
                    bg_c, fg_c = t.MINT, t.MINT_DK
                elif i == done:
                    bg_c, fg_c = t.INK, t.WHITE
                else:
                    bg_c, fg_c = t.SURFACE, t.INK_FAINT
                ui.tile(letter, (tx, ty, tile, tile), bg_c, fg_c, size=10,
                        radius=8)

            # Controls, pinned to the bottom
            _button(ui, stack.pin(BTN_H), "Go home", "H", "ghost", mode=self)
            _button(ui, stack.pin(BTN_H), "Random letter", "R", mode=self)
            _button(ui, stack.pin(BTN_H), "Next letter", "N", "primary", mode=self)

    def _handle_key(self, key):
        if key in (ord("n"), ord("N")):
            self._next_letter(passed=False)
            return None
        if key in (ord("r"), ord("R")):
            self.target = random.choice(SUPPORTED_LETTERS)
            self.pass_history.clear()
            return None
        return super()._handle_key(key)


# ------- Practice -------

class PracticeMode(Mode):
    name = "practice"
    nav = "practice"

    def __init__(self):
        super().__init__()
        self.last_cnn_label = None
        self.last_cnn_conf = 0.0
        self.last_best_letter = None
        self.last_best_score = 0.0
        self.last_landmarks = None
        self.recent = deque(maxlen=5)
        self.session = Session(mode="practice")

    def update(self, cnn_label, cnn_conf, landmarks, ref_lib):
        self.last_cnn_label = cnn_label
        self.last_cnn_conf = cnn_conf or 0.0
        self.last_landmarks = landmarks
        if landmarks is not None and ref_lib is not None:
            self.last_best_letter, self.last_best_score = ref_lib.best_match(landmarks)
        else:
            self.last_best_letter, self.last_best_score = None, 0.0
        if cnn_label and self.last_cnn_conf >= CNN_THRESHOLD:
            if not self.recent or self.recent[-1] != cnn_label:
                self.recent.append(cnn_label)
                self.session.record(cnn_label, passed=True,
                                    score=self.last_best_score)

    def _mean_closeness(self):
        """Average geometric closeness across the letters logged this session."""
        scores = [r["score"] for r in self.session.records]
        return sum(scores) / len(scores) if scores else 0.0

    def _render(self, frame):
        with t.Canvas(frame) as ui:
            panel = _panel_box(frame)
            ui.rect(panel, t.SURFACE)
            _render_rail(ui, frame, self.nav, mode=self)

            stack = _Stack(panel)
            _mixed_label(ui, "Practice", "free signing", (stack.x, stack.y))
            stack.y += 30

            confident = (self.last_cnn_label is not None
                         and self.last_cnn_conf >= CNN_THRESHOLD)

            # What the CNN sees
            box = stack.place(168)
            ui.card(box, t.WHITE, radius=RADIUS)
            ui.eyebrow("CNN sees", (box[0] + PAD, box[1] + PAD))
            glyph = self.last_cnn_label or "-"
            ui.text_centered(glyph, (box[0], box[1] + 30, box[2], 72), 68,
                             t.WEIGHT_BLACK, t.INK if confident else t.INK_FAINT)
            bx, bw = box[0] + PAD, box[2] - PAD * 2
            ui.bar((bx, box[1] + 116, bw, 10), self.last_cnn_conf,
                   t.MINT if confident else t.YELLOW)
            ui.text(f"Confidence — {self.last_cnn_conf:.0%}",
                    (bx, box[1] + 132), 11, t.WEIGHT_SEMI, t.INK_SOFT)

            # What the geometry says
            box = stack.place(128)
            ui.card(box, t.YELLOW, radius=RADIUS)
            ui.eyebrow("Geometry match", (box[0] + PAD, box[1] + PAD),
                       color=t.YELLOW_DK)
            ui.text(self.last_best_letter or "-", (box[0] + PAD, box[1] + 34),
                    40, t.WEIGHT_BLACK, t.INK)
            ui.text("nearest shape", (box[0] + PAD + 48, box[1] + 56), 11,
                    t.WEIGHT_MEDIUM, t.INK_MID)
            bx, bw = box[0] + PAD, box[2] - PAD * 2
            ui.bar((bx, box[1] + 88, bw, 10), self.last_best_score, t.YELLOW_DK,
                   track=t.WHITE)
            ui.text(f"Closeness — {self.last_best_score:.0%}",
                    (bx, box[1] + 104), 11, t.WEIGHT_SEMI, t.YELLOW_DK)

            # Recent letters
            box = stack.place(100)
            ui.card(box, t.WHITE, radius=RADIUS)
            ui.eyebrow("Recent letters", (box[0] + PAD, box[1] + PAD))
            tile = 40
            for i in range(5):
                tx = box[0] + PAD + i * (tile + 8)
                ty = box[1] + PAD + 20
                letter = self.recent[i] if i < len(self.recent) else ""
                ui.tile(letter, (tx, ty, tile, tile), t.SURFACE, t.INK, size=16)

            # Encouragement
            box = stack.place(72)
            ui.card(box, t.MINT, radius=RADIUS)
            copy = ("Looking good — keep going and watch your confidence "
                    "scores climb." if confident else
                    "Sign anything you like. Both readouts update live.")
            ui.paragraph(copy, (box[0] + PAD, box[1] + PAD), box[2] - PAD * 2,
                         12, t.WEIGHT_BOLD, t.MINT_DK)

            # Session tally
            box = stack.place(80)
            ui.card(box, t.WHITE, radius=RADIUS)
            ui.eyebrow("This session", (box[0] + PAD, box[1] + PAD))
            _stat(ui, (box[0] + PAD, box[1] + 34), str(self.session.attempts),
                  "letters signed")
            _stat(ui, (box[0] + box[2] / 2 + 10, box[1] + 34),
                  f"{self._mean_closeness():.0%}", "avg closeness")

            _button(ui, stack.pin(BTN_H), "Go home", "H", mode=self)


# ------- SpellWord -------

def _load_words(path=WORDS_PATH):
    if not path.exists():
        return ["HELLO", "WATER", "FRIEND", "SMILE", "LEARN"]
    words = []
    for line in path.read_text().splitlines():
        w = line.strip().upper()
        if w and all(c in SUPPORTED_LETTERS for c in w):
            words.append(w)
    return words or ["HELLO"]


class SpellWordMode(Mode):
    name = "spell"
    nav = "spell"

    def __init__(self, word=None, words=None):
        super().__init__()
        self.words = list(words) if words else _load_words()
        self.word = word or random.choice(self.words)
        self.index = 0
        self.dwell_start = None
        self.last_cnn_label = None
        self.last_cnn_conf = 0.0
        self.ref_lib = None
        self.completed = False
        self.start_time = time.time()
        self.elapsed = 0.0
        self.session = Session(mode="spell")

    @property
    def target(self):
        return self.word[self.index] if self.index < len(self.word) else None

    def _advance(self, passed, score=0.0):
        self.session.record(self.target, passed=passed, score=score)
        self.index += 1
        self.dwell_start = None
        if self.index >= len(self.word):
            self.completed = True
            self.elapsed = time.time() - self.start_time

    def update(self, cnn_label, cnn_conf, landmarks, ref_lib):
        self.last_cnn_label = cnn_label
        self.last_cnn_conf = cnn_conf or 0.0
        self.ref_lib = ref_lib
        if self.completed or self.target is None:
            return

        matches = (cnn_label == self.target
                   and self.last_cnn_conf >= CNN_THRESHOLD)
        now = time.time()
        if matches:
            if self.dwell_start is None:
                self.dwell_start = now
            elif now - self.dwell_start >= DWELL_SECONDS:
                self._advance(passed=True, score=self.last_cnn_conf)
        else:
            self.dwell_start = None

    def _render_strip(self, ui, frame):
        """Full-width word progress strip across the top of the content area."""
        w = frame.shape[1]
        x0 = RAIL_WIDTH
        ui.rect((x0, 0, w - x0, STRIP_H), t.WHITE)
        ui.text("SPELL", (x0 + 20, STRIP_H // 2 - 6), 10, t.WEIGHT_BOLD,
                t.INK_FAINT, tracking=1.5)

        tile, gap = 40, 8
        tx = x0 + 90
        for i, letter in enumerate(self.word):
            if i < self.index:
                bg_c, fg_c = t.MINT, t.MINT_DK
            elif i == self.index and not self.completed:
                bg_c, fg_c = t.YELLOW, t.YELLOW_DK
            else:
                bg_c, fg_c = t.SURFACE, t.INK_FAINT
            ui.tile(letter, (tx, (STRIP_H - tile) // 2, tile, tile), bg_c, fg_c,
                    size=20)
            tx += tile + gap

        if self.completed:
            ui.text("All done — great work.", (w - PANEL_WIDTH - 24,
                                               STRIP_H // 2 - 8), 12,
                    t.WEIGHT_XBOLD, t.MINT_DK, align="right")

    def _render_complete(self, ui, stack):
        _mixed_label(ui, "Spell", "complete", (stack.x, stack.y))
        stack.y += 30

        box = stack.place(210)
        ui.card(box, t.MINT, radius=RADIUS)
        cx = box[0] + box[2] / 2
        ui.text("Brilliant.", (cx, box[1] + 26), 26, t.WEIGHT_BLACK, t.MINT_DK,
                align="center")
        ui.text(f"{self.elapsed:.1f}s", (cx, box[1] + 64), 44, t.WEIGHT_BLACK,
                t.INK, align="center")
        ui.paragraph(
            "You spelled the whole word without stopping. That is real progress.",
            (box[0] + 20, box[1] + 130), box[2] - 40, 12, t.WEIGHT_MEDIUM,
            t.INK_MID)

        _button(ui, stack.pin(BTN_H), "Return home", "H", "primary", mode=self)

    def _render(self, frame):
        with t.Canvas(frame) as ui:
            x, _, w, h = _panel_box(frame)
            panel = (x, STRIP_H, w, h - STRIP_H)
            ui.rect(panel, t.SURFACE)
            _render_rail(ui, frame, self.nav, mode=self)
            self._render_strip(ui, frame)

            stack = _Stack(panel)
            if self.completed:
                self._render_complete(ui, stack)
                return

            _mixed_label(ui, "Spell", "a word", (stack.x, stack.y))
            stack.y += 30

            _target_card(ui, stack.place(150), self.target, self.ref_lib,
                         eyebrow="Sign this next")

            # Dwell + CNN readout
            dwell = 0.0
            if self.dwell_start is not None:
                dwell = min(1.0, (time.time() - self.dwell_start) / DWELL_SECONDS)
            box = stack.place(92)
            ui.card(box, t.WHITE, radius=RADIUS)
            bx, by, bw = box[0] + PAD, box[1] + PAD, box[2] - PAD * 2
            ui.bar((bx, by + 2, bw, 10), dwell, t.SKY)
            label = ("Keep holding — committing…" if dwell > 0
                     else f"Hold the sign for {DWELL_SECONDS:.1f}s to commit")
            ui.text(label, (bx, by + 18), 11, t.WEIGHT_SEMI, t.INK_SOFT)
            _divider_row(ui, bx, by + 40, bw, "CNN read", self.last_cnn_label,
                         f"{self.last_cnn_conf:.0%}")

            # Coaching
            box = stack.place(72)
            ui.card(box, t.SKY, radius=RADIUS)
            ui.paragraph(
                "Hold steady and the letter will commit on its own. Take your time.",
                (box[0] + PAD, box[1] + PAD), box[2] - PAD * 2, 12,
                t.WEIGHT_BOLD, t.SKY_DK)

            # Where you are in the word
            box = stack.place(80)
            ui.card(box, t.WHITE, radius=RADIUS)
            ui.eyebrow("This word", (box[0] + PAD, box[1] + PAD))
            _stat(ui, (box[0] + PAD, box[1] + 34),
                  f"{self.index + 1}/{len(self.word)}", "letter")
            _stat(ui, (box[0] + box[2] / 2 + 10, box[1] + 34),
                  f"{time.time() - self.start_time:.0f}s", "elapsed")

            _button(ui, stack.pin(BTN_H), "Go home", "H", "ghost", mode=self)
            _button(ui, stack.pin(BTN_H), "Skip this letter", "S", mode=self)

    def _handle_key(self, key):
        if not self.completed and key in (ord("s"), ord("S")):
            self._advance(passed=False)
            return None
        return super()._handle_key(key)
