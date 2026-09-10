"""Render a hand skeleton in MediaPipe's default drawing style.

The `asl-alphabet-wireframes` dataset is made of MediaPipe hand-landmark
skeletons drawn on a black background. To classify a live webcam hand with a
model trained on that dataset, we must draw the detected landmarks in the *same*
style, then normalize position/scale identically for training and inference.

Colors below (RGB) were reverse-engineered from the dataset and match
MediaPipe's default hand landmark/connection styling.
"""

import cv2
import numpy as np

# --- MediaPipe default style colors (RGB) ---
_RED = (255, 48, 48)       # palm landmarks
_PEACH = (255, 229, 180)   # thumb
_PURPLE = (128, 64, 128)   # index
_YELLOW = (255, 204, 0)    # middle
_GREEN = (48, 255, 48)     # ring
_BLUE = (21, 101, 192)     # pinky
_GRAY = (128, 128, 128)    # palm connections
_WHITE = (255, 255, 255)

# Landmark index -> dot color
_PALM_LANDMARKS = (0, 1, 5, 9, 13, 17)
_FINGER_LANDMARKS = {
    _PEACH: (2, 3, 4),
    _PURPLE: (6, 7, 8),
    _YELLOW: (10, 11, 12),
    _GREEN: (14, 15, 16),
    _BLUE: (18, 19, 20),
}

# Connection (start, end) grouped by drawing color
_PALM_CONNECTIONS = ((0, 1), (0, 5), (5, 9), (9, 13), (13, 17), (0, 17))
_FINGER_CONNECTIONS = {
    _PEACH: ((1, 2), (2, 3), (3, 4)),
    _PURPLE: ((5, 6), (6, 7), (7, 8)),
    _YELLOW: ((9, 10), (10, 11), (11, 12)),
    _GREEN: ((13, 14), (14, 15), (15, 16)),
    _BLUE: ((17, 18), (18, 19), (19, 20)),
}


def _landmark_color(idx):
    if idx in _PALM_LANDMARKS:
        return _RED
    for color, idxs in _FINGER_LANDMARKS.items():
        if idx in idxs:
            return color
    return _RED


# Feedback ramp, in the wireframe design's pastel accents (see
# design/src/App.tsx): mint reads as "this joint is right", yellow as "close",
# pink as "wrong". Kept here as literals rather than importing the tutor's
# theme module, so this file stays free of UI dependencies.
_MINT = (183, 225, 209)
_FB_YELLOW = (255, 229, 154)
_PINK = (255, 188, 193)


def error_color(error, lo=0.10, hi=0.45):
    """Map a per-joint distance to a mint -> yellow -> pink RGB color.

    `lo` is the intra-class noise floor (anything under it is "right") and
    `hi` is roughly the distance to a different letter. Used for the tutor's
    per-finger feedback, never for the classifier input.
    """
    t = float(np.clip((error - lo) / max(hi - lo, 1e-6), 0.0, 1.0))
    a, b, f = (_MINT, _FB_YELLOW, t / 0.5) if t < 0.5 else (
        _FB_YELLOW, _PINK, (t - 0.5) / 0.5)
    return tuple(int(round(ca + (cb - ca) * f)) for ca, cb in zip(a, b))


def render_skeleton(landmarks, size=400, margin=0.15, joint_errors=None):
    """Draw the 21 hand landmarks as a MediaPipe-style skeleton on black.

    `landmarks` is a list of 21 objects exposing normalized `.x`/`.y` (the
    Tasks-API hand). Landmarks are re-normalized to their own bounding box so
    the skeleton fills a `margin`-padded square canvas, matching the crop-to-
    content normalization used at train time. Returns an RGB uint8 image.

    `joint_errors` is an optional (21,) array of per-landmark distances from a
    reference pose; when given, landmark dots are tinted green-to-red by error
    instead of MediaPipe's fixed palette. This is display-only feedback — the
    classifier is always fed the untinted default rendering, which is what it
    was trained on.
    """
    xs = np.array([lm.x for lm in landmarks], dtype=np.float32)
    ys = np.array([lm.y for lm in landmarks], dtype=np.float32)

    # Fit the hand into a centered square that preserves aspect ratio.
    span = max(xs.max() - xs.min(), ys.max() - ys.min(), 1e-6)
    usable = size * (1.0 - 2 * margin)
    cx = (xs.min() + xs.max()) / 2.0
    cy = (ys.min() + ys.max()) / 2.0
    px = ((xs - cx) / span * usable + size / 2.0).astype(int)
    py = ((ys - cy) / span * usable + size / 2.0).astype(int)
    pts = list(zip(px.tolist(), py.tolist()))

    canvas = np.zeros((size, size, 3), dtype=np.uint8)

    # Line thickness / dot radius scaled to canvas size (tuned to dataset look).
    palm_th = max(2, round(size * 0.0075))
    finger_th = max(1, round(size * 0.005))
    radius = max(2, round(size * 0.011))

    # The canvas is kept in RGB order; cv2 just writes the raw byte tuples we
    # pass, and everything downstream (PIL, TF, inference) reads it as RGB.
    def line(a, b, color, th):
        cv2.line(canvas, pts[a], pts[b], color, th, cv2.LINE_AA)

    for a, b in _PALM_CONNECTIONS:
        line(a, b, _GRAY, palm_th)
    for color, conns in _FINGER_CONNECTIONS.items():
        for a, b in conns:
            line(a, b, color, finger_th)

    for idx, p in enumerate(pts):
        if joint_errors is not None:
            color = error_color(float(joint_errors[idx]))
        else:
            color = _landmark_color(idx)
        cv2.circle(canvas, p, radius + 1, _WHITE, -1, cv2.LINE_AA)
        cv2.circle(canvas, p, radius, color, -1, cv2.LINE_AA)

    return canvas


def crop_to_content(image, pad_frac=0.08):
    """Tight-crop non-black content and square-pad it.

    Applied identically to dataset images and live renders so the model never
    has to learn absolute position or scale. Returns an RGB uint8 image; if the
    frame is essentially empty it is returned unchanged.
    """
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    ys, xs = np.where(gray > 25)
    if len(xs) == 0:
        return image

    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    crop = image[y0:y1 + 1, x0:x1 + 1]

    h, w = crop.shape[:2]
    side = max(h, w)
    pad = int(side * pad_frac)
    canvas = np.zeros((side + 2 * pad, side + 2 * pad, 3), dtype=image.dtype)
    oy = pad + (side - h) // 2
    ox = pad + (side - w) // 2
    canvas[oy:oy + h, ox:ox + w] = crop
    return canvas


# --- Tutor overlays (drawn on the live BGR webcam frame, not the CNN input) ---

# All connections as (start, end) pairs, for the flat single-color ghost.
_ALL_CONNECTIONS = _PALM_CONNECTIONS + tuple(
    conn for conns in _FINGER_CONNECTIONS.values() for conn in conns
)


def landmark_pixels(landmarks, frame_shape):
    """Tasks-API landmarks -> (21, 2) float array of pixel coordinates."""
    h, w = frame_shape[:2]
    return np.array([[lm.x * w, lm.y * h] for lm in landmarks], dtype=np.float32)


def project_pose(normalized_pose, live_landmarks, frame_shape, mirrored=False):
    """Place a normalized reference pose onto the live hand, in pixels.

    The reference is wrist-centered and scale-normalized, so it is rescaled by
    the live hand's own RMS wrist distance and translated to the live wrist —
    the ghost then sits on the user's hand at their hand's size, and only the
    finger geometry differs. `mirrored` re-flips the reference when the live
    hand matched it mirrored (see reference.per_joint_distances).

    The fit is done in MediaPipe's normalized coordinate space, the same space
    the reference poses were averaged in, and only converted to pixels at the
    end. Fitting in pixels instead would stretch the ghost by the frame's
    aspect ratio and it would not sit on a correctly-signed hand.
    """
    h, w = frame_shape[:2]
    live = np.array([[lm.x, lm.y] for lm in live_landmarks], dtype=np.float32)
    wrist = live[0]
    centered = live - wrist
    scale = float(np.sqrt(np.mean(np.sum(centered ** 2, axis=1))))

    ref = np.asarray(normalized_pose, dtype=np.float32).copy()
    if mirrored:
        ref = ref * np.array([-1.0, 1.0], dtype=np.float32)
    return (ref * scale + wrist) * np.array([w, h], dtype=np.float32)


def render_ghost(frame, normalized_pose, live_landmarks, mirrored=False,
                 alpha=0.42, color=(255, 255, 255), halo=(17, 17, 17)):
    """Draw a reference pose over the live hand at low alpha, in place.

    Colors are BGR (this draws on the webcam frame, unlike render_skeleton).
    The pose is stroked twice — a dark `halo` underneath, then `color` on top —
    so the ghost stays readable against a bright wall or a dark room, which a
    single flat stroke does not.

    Returns the projected (21, 2) pixel array so callers can reuse it.
    """
    pts = project_pose(normalized_pose, live_landmarks, frame.shape, mirrored)
    ipts = [(int(round(x)), int(round(y))) for x, y in pts]

    layer = frame.copy()
    for a, b in _ALL_CONNECTIONS:
        cv2.line(layer, ipts[a], ipts[b], halo, 7, cv2.LINE_AA)
    for a, b in _ALL_CONNECTIONS:
        cv2.line(layer, ipts[a], ipts[b], color, 3, cv2.LINE_AA)
    for p in ipts:
        cv2.circle(layer, p, 6, halo, -1, cv2.LINE_AA)
        cv2.circle(layer, p, 4, color, -1, cv2.LINE_AA)

    cv2.addWeighted(layer, alpha, frame, 1.0 - alpha, 0, frame)
    return pts


def draw_joint_errors(frame, live_landmarks, joint_errors, radius=9):
    """Ring each live landmark in green-to-red by its distance from reference.

    Drawn on the webcam frame so the learner sees *which* joints are wrong,
    rather than only a single closeness number.
    """
    pts = landmark_pixels(live_landmarks, frame.shape)
    for idx, (x, y) in enumerate(pts):
        r, g, b = error_color(float(joint_errors[idx]))
        cv2.circle(frame, (int(round(x)), int(round(y))), radius,
                   (b, g, r), 2, cv2.LINE_AA)


def render_pose_card(normalized_pose, width, height, mirrored=False,
                     bg=(239, 235, 229), stroke=(17, 17, 17), margin=0.07):
    """Draw a reference pose as a standalone illustration, in RGB.

    This is what fills the tutor's "how to sign" card. The wireframe design
    mocked that card with a stock photo of a hand; a rendered reference pose is
    both honest (it is the exact shape the learner is scored against) and free
    of any network fetch in the webcam loop. Callers should cache the result
    per letter — the geometry never changes.
    """
    pose = np.asarray(normalized_pose, dtype=np.float32).copy()
    if mirrored:
        pose = pose * np.array([-1.0, 1.0], dtype=np.float32)

    # Fit the pose into the box, preserving aspect ratio.
    lo, hi = pose.min(axis=0), pose.max(axis=0)
    span = float(max((hi - lo).max(), 1e-6))
    usable = min(width, height) * (1.0 - 2 * margin)
    center = (lo + hi) / 2.0
    pts = (pose - center) / span * usable + np.array([width / 2.0, height / 2.0],
                                                     dtype=np.float32)
    ipts = [(int(round(x)), int(round(y))) for x, y in pts]

    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:] = bg
    for a, b in _ALL_CONNECTIONS:
        cv2.line(canvas, ipts[a], ipts[b], stroke, 3, cv2.LINE_AA)
    for p in ipts:
        cv2.circle(canvas, p, 5, stroke, -1, cv2.LINE_AA)
    return canvas
