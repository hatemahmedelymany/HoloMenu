"""
MediaPipe hand landmarker Tasks API load and validation hooks.
"""
import traceback
from gesture_engine.config.settings import CONFIG, ensure_model_downloaded

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    MEDIAPIPE_AVAILABLE = True
except (ImportError, AttributeError) as e:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    mp_vision = None
    print("WARNING: mediapipe failed to import. Running in simulation mode (no gestures).")
    print(f"  Reason: {e}")
    traceback.print_exc()


def create_hand_landmarker():
    """Builds and returns hand landmarker core listener config."""
    if not MEDIAPIPE_AVAILABLE:
        return None
    model_path = ensure_model_downloaded()
    options = mp_vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
        min_hand_presence_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
        min_tracking_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
    )
    return mp_vision.HandLandmarker.create_from_options(options)
