"""Webcam loop for the ASL fingerspelling tutor.

This module owns the camera, the models, and nothing else about the UI: each
frame it detects the hand, classifies it, then hands the result to the current
tutor `Mode`, which decides what to draw and how to react to key presses. See
`src/tutor/modes.py` for the modes themselves.
"""

from collections import Counter, deque
import json
import os
import time

import cv2
import numpy as np

from .config import (
    CLASS_NAMES,
    CLASS_NAMES_PATH,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    MODEL_PATH,
    PREDICTION_HISTORY,
)
from .hand_tracking import HandTracker
from .preprocessing import preprocess_skeleton
from .skeleton import render_skeleton
from .tutor import theme
from .tutor.modes import HomeMode, camera_prompt
from .tutor.reference import ReferenceLibrary


def load_classifier(model_path=MODEL_PATH):
    """Load a trained Keras model if it exists."""
    if not os.path.exists(model_path):
        return None

    try:
        from tensorflow.keras.models import load_model
    except Exception:
        return None

    try:
        return load_model(model_path)
    except Exception:
        return None


def load_class_names(path=CLASS_NAMES_PATH):
    """Return the class-name list saved at train time, or the config fallback.

    The saved list is authoritative: its order matches the model's output
    neurons, which need not match the alphabetical CLASS_NAMES fallback.
    """
    if os.path.exists(path):
        try:
            with open(path) as fh:
                names = json.load(fh)
            if isinstance(names, list) and names:
                return names
        except Exception:
            pass
    return CLASS_NAMES


def smooth_prediction(history, label, confidence):
    """Smooth predictions across a short frame history."""
    history.append((label, confidence))

    if len(history) == 0:
        return label, confidence

    most_common_label, _ = Counter(item[0] for item in history).most_common(1)[0]
    matching_confidences = [item[1] for item in history if item[0] == most_common_label]
    average_confidence = float(np.mean(matching_confidences)) if matching_confidences else float(confidence)
    return most_common_label, average_confidence


def classify_hand(model, landmarks, prediction_history, class_names):
    """Render the hand skeleton and classify it.

    Returns (label, confidence, skeleton_rgb) or (None, None, None).
    """
    skeleton = render_skeleton(landmarks)
    batch = preprocess_skeleton(skeleton)
    if batch is None:
        return None, None, None

    prediction = model.predict(batch, verbose=0)[0]
    predicted_index = int(np.argmax(prediction))
    confidence = float(prediction[predicted_index])
    label = class_names[predicted_index] if 0 <= predicted_index < len(class_names) else "UNKNOWN"

    smoothed_label, smoothed_confidence = smooth_prediction(prediction_history, label, confidence)
    return smoothed_label, smoothed_confidence, skeleton


def _warn(frame, lines, y=40):
    """Print red warning lines in the top-left corner."""
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (20, y + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


def _save_session(mode):
    """Persist a mode's attempt log, if it keeps one."""
    session = getattr(mode, "session", None)
    if session is not None:
        session.save()


def open_camera(index=0, width=FRAME_WIDTH, height=FRAME_HEIGHT):
    """Open the webcam, or return None if it is unavailable.

    A denied camera permission looks the same as no camera at all, so this
    never raises: the app opens anyway and shows the "allow camera access"
    notice until one turns up.
    """
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def _inside(box, x, y):
    """Whether (x, y) falls inside an (x, y, w, h) box."""
    bx, by, bw, bh = box
    return bx <= x < bx + bw and by <= y < by + bh


def _blank_frame(width=FRAME_WIDTH, height=FRAME_HEIGHT):
    """A plain themed frame to draw on while there is no camera image."""
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = theme.bgr(theme.BG)
    return frame


def main():
    """Open the webcam and run the tutor loop."""
    model = load_classifier()
    class_names = load_class_names()
    hand_tracker = HandTracker()
    reference_library = ReferenceLibrary.load()
    prediction_history = deque(maxlen=PREDICTION_HISTORY)

    mode = HomeMode()

    window = "ASL Fingerspelling Tutor"
    cv2.namedWindow(window)

    # The UI is clickable as well as keyboard-driven. Clicks are queued by the
    # callback and drained in the loop, so handling runs on the main thread
    # against the regions the current frame actually drew.
    clicks = []

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))

    cv2.setMouseCallback(window, on_mouse)

    cap = open_camera()
    start_time = time.time()
    quitting = False

    while not quitting:
        frame = None
        if cap is not None:
            success, captured = cap.read()
            if success:
                frame = cv2.flip(captured, 1)
            else:
                # The camera went away mid-session (unplugged, or permission
                # revoked). Drop it and fall back to the notice.
                cap.release()
                cap = None

        camera_ready = frame is not None
        if frame is None:
            frame = _blank_frame()

        label, confidence = None, 0.0
        if camera_ready:
            # detect_for_video requires strictly increasing timestamps
            timestamp_ms = int((time.time() - start_time) * 1000)
            result = hand_tracker.detect(frame, timestamp_ms)
            hand_tracker.draw(frame, result)
            first_hand = hand_tracker.get_first_hand(result)

            if first_hand is None:
                # No hand this frame - drop the smoothing history so the
                # readout doesn't linger on a letter the user has stopped
                # signing.
                prediction_history.clear()
            elif model is not None:
                label, confidence, _skeleton = classify_hand(
                    model, first_hand, prediction_history, class_names
                )
                confidence = confidence or 0.0
        else:
            first_hand = None
            prediction_history.clear()

        # The current mode owns all state and all UI from here.
        mode.camera_ready = camera_ready
        mode.update(label, confidence, first_hand, reference_library)
        mode.render(frame)

        notice = None
        if not camera_ready:
            notice = camera_prompt(frame, hand_tracker.error_message)
        if model is None:
            _warn(frame, ["Warning: model file missing",
                          f"Expected: {MODEL_PATH}"])
        if reference_library is None:
            _warn(frame, ["Reference poses missing - no graded feedback",
                          "Run: python -m scripts.build_reference_poses"],
                  y=110)
        if camera_ready and not hand_tracker.available:
            lines = ["Hand tracking unavailable"]
            if hand_tracker.error_message:
                lines.append(hand_tracker.error_message[:70])
            _warn(frame, lines, y=180)

        cv2.imshow(window, frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q")):
            break
        if cap is None and key in (ord("r"), ord("R")):
            cap = open_camera()
            key = 255                      # consumed by the retry
        if key != 255:
            next_mode = mode.handle_key(key)
            if next_mode is not None:
                _save_session(mode)
                mode = next_mode

        while clicks:
            x, y = clicks.pop(0)
            if notice is not None:
                # The camera notice covers the screen, so only its own buttons
                # are live; everything behind it is hidden and must stay inert.
                if _inside(notice["quit"], x, y):
                    clicks.clear()
                    quitting = True
                    break
                if _inside(notice["retry"], x, y):
                    cap = open_camera()
                clicks.clear()
                break
            next_mode = mode.handle_click(x, y)
            if next_mode is not None:
                _save_session(mode)
                mode = next_mode
                clicks.clear()             # the new mode drew none of these

        # A closed window should quit rather than leave the loop spinning.
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            break

    _save_session(mode)
    hand_tracker.close()
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
