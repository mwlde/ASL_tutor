"""Small wrapper around MediaPipe Hands for webcam inference."""

"""Hand tracker using MediaPipe Tasks API.

This implementation uses the MediaPipe Tasks Python API (HandLandmarker)
when available and reports a clear `error_message` when it is not. The
class provides simple drawing and bbox extraction helpers for the live
inference loop.
"""

import os
from typing import Optional, Tuple, List

import cv2

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
except Exception as exc:  # pragma: no cover - environment dependent
    mp = None
    mp_tasks = None
    mp_vision = None
    MEDIAPIPE_TASKS_ERROR = exc
else:
    MEDIAPIPE_TASKS_ERROR = None

from .config import HAND_LANDMARKER_MODEL_PATH, NUM_HANDS, MIN_DETECTION_CONFIDENCE, MIN_TRACKING_CONFIDENCE


class HandTracker:
    """HandLandmarker wrapper using the Tasks API.

    Attributes
    - available: whether a Tasks-based landmarker is ready
    - error_message: a human-readable error if unavailable
    """

    def __init__(self, model_path: str = HAND_LANDMARKER_MODEL_PATH):
        self.model_path = model_path
        self.available = False
        self.error_message = None
        self._detector = None

        if mp is None or mp_tasks is None or mp_vision is None:
            self.error_message = f"MediaPipe Tasks unavailable: {MEDIAPIPE_TASKS_ERROR}"
            return

        if not os.path.exists(self.model_path):
            self.error_message = f"Hand landmarker model missing: {self.model_path}"
            return

        try:
            BaseOptions = mp_tasks.BaseOptions
            HandLandmarker = mp_vision.HandLandmarker
            HandLandmarkerOptions = mp_vision.HandLandmarkerOptions
            RunningMode = mp_vision.RunningMode

            base_options = BaseOptions(model_asset_path=self.model_path)
            options = HandLandmarkerOptions(
                base_options=base_options,
                running_mode=RunningMode.VIDEO,
                num_hands=NUM_HANDS,
                min_hand_detection_confidence=float(MIN_DETECTION_CONFIDENCE),
                min_tracking_confidence=float(MIN_TRACKING_CONFIDENCE),
            )

            self._detector = HandLandmarker.create_from_options(options)
            self.available = True
        except Exception as exc:  # pragma: no cover - environment dependent
            self.error_message = f"Failed to initialize HandLandmarker: {exc}"
            self._detector = None

    def is_available(self) -> bool:
        return self.available

    def detect(self, frame, timestamp_ms: int):
        """Detect hands in a BGR OpenCV frame and return a HandLandmarkerResult.

        The Tasks API expects an `mp.Image` (SRGB) and a monotonically
        increasing timestamp in milliseconds for VIDEO running mode.
        """
        if not self.available or self._detector is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        return self._detector.detect_for_video(mp_image, timestamp_ms)

    def get_first_hand(self, result):
        """Return the first hand's landmark list, or None.

        In the Tasks API `result.hand_landmarks` is a list (one entry per
        detected hand); each entry is itself a list of NormalizedLandmark
        objects exposing `.x`, `.y`, `.z` in normalized [0, 1] coordinates.
        """
        if result is None:
            return None

        landmarks = getattr(result, "hand_landmarks", None)
        if not landmarks:
            return None

        return landmarks[0]

    # Live-hand styling, matching the tutor's wireframe design: near-black ink
    # underneath and warm off-white on top, so the skeleton stays legible over
    # a bright wall or a dark room without borrowing an accent color that the
    # panel uses to mean something.
    _INK = (17, 17, 17)
    _LIGHT = (239, 243, 247)

    _CONNECTIONS = (
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17),
    )

    def draw(self, frame, result):
        """Draw landmarks and a lightweight skeleton on the frame."""
        landmarks = getattr(result, "hand_landmarks", None)
        if not landmarks:
            return

        h, w = frame.shape[:2]
        for hand in landmarks:
            pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand]

            for color, thickness in ((self._INK, 6), (self._LIGHT, 2)):
                for a, b in self._CONNECTIONS:
                    if a < len(pts) and b < len(pts):
                        cv2.line(frame, pts[a], pts[b], color, thickness,
                                 cv2.LINE_AA)
            for p in pts:
                cv2.circle(frame, p, 5, self._INK, -1, cv2.LINE_AA)
                cv2.circle(frame, p, 3, self._LIGHT, -1, cv2.LINE_AA)

    def extract_bbox(self, frame, hand_landmarks):
        """Compute a padded bbox from a landmarks list (normalized coordinates)."""
        if not hand_landmarks:
            return None

        h, w = frame.shape[:2]
        xs = [float(lm.x) for lm in hand_landmarks]
        ys = [float(lm.y) for lm in hand_landmarks]

        if not xs or not ys:
            return None

        x_min = int(min(xs) * w)
        y_min = int(min(ys) * h)
        x_max = int(max(xs) * w)
        y_max = int(max(ys) * h)

        pad_x = int(0.15 * (x_max - x_min + 1))
        pad_y = int(0.15 * (y_max - y_min + 1))

        x_min = max(0, x_min - pad_x)
        y_min = max(0, y_min - pad_y)
        x_max = min(w - 1, x_max + pad_x)
        y_max = min(h - 1, y_max + pad_y)

        return x_min, y_min, x_max, y_max

    def close(self):
        try:
            if self._detector:
                self._detector.close()
        except Exception:
            pass
