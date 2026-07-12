"""
Configuration dictionary loading and MediaPipe model management.
"""
import os
import json

CONFIG = {
    "camera": {
        "device_index": 0, "width": 640, "height": 480,
        "idle_fps": 6, "active_fps": 30, "auto_recovery_delay": 5.0,
        "show_debug_window": True
    },
    "websocket": {"host": "127.0.0.1", "port": 8766},
    "interaction": {
        "dwell_click_seconds": 1.3,
        "click_cooldown_ms": 800,
        "click_method": "dwell"
    },
    "order": {
        "inactivity_timeout_seconds": 75,
        "order_complete_return_to_idle_seconds": 8
    },
    "gesture_thresholds": {
        "cooldown_seconds": 0.6,
        "min_hold_seconds": 0.25,
        "min_tracking_confidence": 0.7,
        "swipe": {"min_distance_x": 0.15, "max_distance_y": 0.08, "max_time_frames": 20, "min_velocity": 0.015},
        "pinch": {"threshold_distance": 0.06},
        "thumbs_up": {"thumb_ip_tip_angle": 150.0}
    },
    "mediapipe_model": {
        "path": "hand_landmarker.task",
        "download_url": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
    }
}

# Override from config.json if present (relative to current file's parent's parent directory)
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            file_config = json.load(f)
            for section in file_config:
                if section in CONFIG:
                    CONFIG[section].update(file_config[section])
        print("Loaded configuration from config.json")
    except Exception as e:
        print(f"Error reading config.json: {e}. Using defaults.")


def ensure_model_downloaded() -> str:
    """Return a local path to hand_landmarker.task, downloading it on first run."""
    model_cfg = CONFIG["mediapipe_model"]
    model_path = model_cfg["path"]
    if not os.path.isabs(model_path):
        # Place model in root directory relative to current config package
        model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), model_path)

    if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
        return model_path

    print(f"Hand landmark model not found at {model_path}")
    print(f"Downloading it once from {model_cfg['download_url']} ...")
    try:
        import urllib.request
        urllib.request.urlretrieve(model_cfg["download_url"], model_path)
        print(f"Model downloaded successfully to {model_path}")
    except Exception as e:
        print(f"ERROR: could not auto-download the model file: {e}")
        print(f"  Manual fix: download {model_cfg['download_url']}")
        print(f"  and save it as: {model_path}")
        raise
    return model_path

# Hard Safeguard Check
ENV = os.getenv("ENV", "development")
DISABLE_WS_AUTH = os.getenv("DISABLE_WS_AUTH", "false").lower() in ("true", "1", "yes")

# Also check top-level config.json properties if present
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            file_config = json.load(f)
            if "DISABLE_WS_AUTH" in file_config:
                val = file_config["DISABLE_WS_AUTH"]
                if isinstance(val, bool):
                    DISABLE_WS_AUTH = val
                elif isinstance(val, str):
                    DISABLE_WS_AUTH = val.lower() in ("true", "1", "yes")
            if "websocket" in file_config and "disable_auth" in file_config["websocket"]:
                val = file_config["websocket"]["disable_auth"]
                if isinstance(val, bool):
                    DISABLE_WS_AUTH = val
                elif isinstance(val, str):
                    DISABLE_WS_AUTH = val.lower() in ("true", "1", "yes")
    except Exception:
        pass

if ENV == "production" and DISABLE_WS_AUTH:
    raise RuntimeError("Cannot disable WebSocket auth in production")

