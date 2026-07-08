import asyncio
import json
import math
import os
import sys
import platform
import time
import traceback
import cv2

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# ─── Diagnostic banner: always print exactly which interpreter is running ────
# This alone resolves most "mediapipe missing" cases, because the #1 cause is
# running this script with a different Python than the one mediapipe was
# pip-installed into (very common on Windows with multiple Python installs).
print("=" * 70)
print(f"Python executable : {sys.executable}")
print(f"Python version    : {platform.python_version()} ({platform.architecture()[0]})")
print("=" * 70)

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    MEDIAPIPE_AVAILABLE = True
    print(f"mediapipe OK      : version {mp.__version__}, loaded from {mp.__file__}")
    print("  Using the modern Tasks API (mediapipe.tasks.python.vision.HandLandmarker).")
    print("  Note: current mediapipe releases removed the old 'mediapipe.solutions' API")
    print("  entirely, so this engine no longer depends on it.")
except (ImportError, AttributeError) as e:
    MEDIAPIPE_AVAILABLE = False
    print("WARNING: mediapipe failed to import. Running in simulation mode (no gestures).")
    print(f"  Reason: {e}")
    print("  Full traceback:")
    traceback.print_exc()
    print()
    print("  Most likely causes, in order of probability:")
    print(f"  1. mediapipe is not installed for THIS interpreter ({sys.executable}).")
    print(f"     Fix: {sys.executable} -m pip install --upgrade mediapipe")
    print(f"  2. Your Python version ({platform.python_version()}) has no mediapipe wheel.")
    print("     mediapipe requires Python 3.9-3.12 (64-bit). If you're on 3.13+ or 32-bit,")
    print("     install a supported Python version and recreate your virtual environment.")
    print("  3. Installed in a different venv/conda env than the one running this script.")
    print("     Check with: pip show mediapipe   (run using the SAME python you use to")
    print("     launch this script, e.g. 'python gesture_engine.py')")
print("=" * 70)

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("WARNING: 'websockets' not installed. WebSocket broadcasting disabled.")

# ─── Config ──────────────────────────────────────────────────────────────────
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
        # The new Tasks API needs an external .task model file (the old
        # mp.solutions.hands API used to bundle this automatically).
        # Downloaded once, then cached locally next to this script.
        "path": "hand_landmarker.task",
        "download_url": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
    }
}

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
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
    """Return a local path to hand_landmarker.task, downloading it on first run.

    The new mediapipe Tasks API needs this external model file (the old
    mp.solutions.hands API didn't need this — it was bundled in the package).
    """
    model_cfg = CONFIG["mediapipe_model"]
    model_path = model_cfg["path"]
    if not os.path.isabs(model_path):
        model_path = os.path.join(os.path.dirname(__file__), model_path)

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


# ─── Global State ────────────────────────────────────────────────────────────
CONNECTED_CLIENTS: set = set()

# Engine operating mode: "idle" or "active"
ENGINE_MODE = "idle"
LAST_ACTIVITY_TIME = time.time()


def set_engine_mode(mode: str):
    global ENGINE_MODE, LAST_ACTIVITY_TIME
    if mode == ENGINE_MODE:
        return
    ENGINE_MODE = mode
    LAST_ACTIVITY_TIME = time.time()
    print(f"Engine mode → {mode.upper()}")


class HandTrackerState:
    def __init__(self):
        self.coords_history = []
        self.last_gesture_time = 0
        self.last_state = "open"
        self.state_hold_start = 0.0  # when current state began
        self.hand_detected = False
        self.last_classified_gesture = None


tracker_state = HandTrackerState()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def calculate_distance(pt1, pt2):
    return math.sqrt((pt1.x - pt2.x) ** 2 + (pt1.y - pt2.y) ** 2 + (pt1.z - pt2.z) ** 2)


async def broadcast_event(event_dict: dict):
    global LAST_ACTIVITY_TIME
    LAST_ACTIVITY_TIME = time.time()

    if not WEBSOCKETS_AVAILABLE:
        print(f"[WS-off] {json.dumps(event_dict)}")
        return

    if CONNECTED_CLIENTS:
        message = json.dumps(event_dict)
        for ws in list(CONNECTED_CLIENTS):
            try:
                await ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                CONNECTED_CLIENTS.discard(ws)
            except Exception as e:
                print(f"WS send error: {e}")


# ─── Gesture Analysis (ACTIVE mode only) ─────────────────────────────────────

def analyze_gestures(landmarks):
    global tracker_state
    now = time.time()

    wrist       = landmarks[0]
    index_tip   = landmarks[8]
    index_mcp   = landmarks[5]
    middle_tip  = landmarks[12]
    middle_mcp  = landmarks[9]
    ring_tip    = landmarks[16]
    ring_mcp    = landmarks[13]
    pinky_tip   = landmarks[20]
    pinky_mcp   = landmarks[17]
    thumb_tip   = landmarks[4]
    thumb_ip    = landmarks[3]
    thumb_mcp   = landmarks[2]

    palm_ref_x = index_mcp.x
    palm_ref_y = index_mcp.y

    tracker_state.coords_history.append((palm_ref_x, palm_ref_y, now))
    max_history = CONFIG["gesture_thresholds"]["swipe"]["max_time_frames"] * 2
    if len(tracker_state.coords_history) > max_history:
        tracker_state.coords_history.pop(0)

    fingers_folded = [
        index_tip.y  > index_mcp.y,
        middle_tip.y > middle_mcp.y,
        ring_tip.y   > ring_mcp.y,
        pinky_tip.y  > pinky_mcp.y,
    ]

    pinch_dist = calculate_distance(thumb_tip, index_tip)
    is_pinch = pinch_dist < CONFIG["gesture_thresholds"]["pinch"]["threshold_distance"]

    is_thumb_up = (
        thumb_tip.y < thumb_ip.y and
        thumb_ip.y  < thumb_mcp.y and
        all(fingers_folded)
    )

    current_state = "open"
    if is_pinch:
        current_state = "pinch"
    elif is_thumb_up:
        current_state = "thumbs_up"
    elif all(fingers_folded):
        current_state = "fist"

    state_changed = current_state != tracker_state.last_state
    prev_state = tracker_state.last_state
    prev_hold_duration = now - tracker_state.state_hold_start

    if state_changed:
        tracker_state.state_hold_start = now  # reset hold timer on state change
    tracker_state.last_state = current_state

    cooldown = CONFIG["gesture_thresholds"]["cooldown_seconds"]
    min_hold = CONFIG["gesture_thresholds"].get("min_hold_seconds", 0.25)
    on_cooldown = (now - tracker_state.last_gesture_time) < cooldown

    actions_triggered = []

    # Only emit a gesture if the PREVIOUS state was held long enough
    # This prevents OPEN_PALM from firing on every brief hand-open transition
    if state_changed and not on_cooldown and prev_hold_duration >= min_hold:
        if current_state == "fist":        actions_triggered.append("CLOSED_FIST")
        elif current_state == "open":      actions_triggered.append("OPEN_PALM")
        elif current_state == "pinch":     actions_triggered.append("PINCH")
        elif current_state == "thumbs_up": actions_triggered.append("THUMBS_UP")

    # Swipe detection
    if current_state == "open" and not on_cooldown and len(tracker_state.coords_history) >= 5:
        swipe_cfg = CONFIG["gesture_thresholds"]["swipe"]
        lookback_len = min(len(tracker_state.coords_history), swipe_cfg["max_time_frames"])
        old_pt = tracker_state.coords_history[-lookback_len]
        new_pt = tracker_state.coords_history[-1]
        dx = new_pt[0] - old_pt[0]
        dy = new_pt[1] - old_pt[1]
        dt = new_pt[2] - old_pt[2]

        if dt > 0.05 and abs(dy) < swipe_cfg["max_distance_y"]:
            if dx < -swipe_cfg["min_distance_x"]:
                actions_triggered.append("SWIPE_LEFT")
            elif dx > swipe_cfg["min_distance_x"]:
                actions_triggered.append("SWIPE_RIGHT")

    if actions_triggered:
        tracker_state.last_gesture_time = now
        tracker_state.last_classified_gesture = actions_triggered[0]
        if "SWIPE_LEFT" in actions_triggered or "SWIPE_RIGHT" in actions_triggered:
            tracker_state.coords_history.clear()
        return actions_triggered[0], current_state

    return None, current_state


# ─── Inactivity Watchdog ─────────────────────────────────────────────────────

async def inactivity_watchdog():
    """Broadcasts session_timeout if no activity for configured duration in ACTIVE mode."""
    timeout_secs = CONFIG["order"]["inactivity_timeout_seconds"]
    while True:
        await asyncio.sleep(5)
        if ENGINE_MODE == "active":
            idle_for = time.time() - LAST_ACTIVITY_TIME
            if idle_for >= timeout_secs:
                print(f"Inactivity timeout after {idle_for:.0f}s — broadcasting session_timeout")
                await broadcast_event({"event": "session_timeout", "idle_seconds": int(idle_for)})
                set_engine_mode("idle")


# ─── Camera / Recognition Loop ───────────────────────────────────────────────

async def run_recognition_engine():
    device_idx = CONFIG["camera"]["device_index"]
    width      = CONFIG["camera"]["width"]
    height     = CONFIG["camera"]["height"]

    # Camera is intentionally NOT opened here. It only turns on when the
    # customer clicks "Start Order" (mode -> active) and turns off again
    # when the order is confirmed, cancelled, or times out (mode -> idle).
    cap = None

    hand_landmarker = None
    if MEDIAPIPE_AVAILABLE:
        model_path = ensure_model_downloaded()
        options = mp_vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
            min_hand_presence_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
            min_tracking_confidence=CONFIG["gesture_thresholds"]["min_tracking_confidence"],
        )
        hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)
        print("HandLandmarker initialized (Tasks API, VIDEO running mode).")
    vision_start_time = time.time()

    print("HoloMenu gesture engine started. Mode: IDLE (camera OFF until an order starts)")

    fps_start_time = time.time()
    fps_counter = 0
    last_broadcast_mode = None
    health_last_broadcast = 0.0
    camera_ok = False

    try:
        while True:
            await asyncio.sleep(0.001)

            # ── Mode transition: open/close the camera exactly here ──────────
            if ENGINE_MODE != last_broadcast_mode:
                await broadcast_event({"event": "engine_mode", "mode": ENGINE_MODE})

                if ENGINE_MODE == "active":
                    tracker_state.coords_history.clear()
                    tracker_state.hand_detected = False
                    if cap is None or not cap.isOpened():
                        print(f"Opening camera on index {device_idx} (order started)...")
                        cap = cv2.VideoCapture(device_idx)
                        if cap.isOpened():
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                            print("Camera is now ON.")
                        else:
                            print(f"ERROR: Camera {device_idx} could not be opened.")

                elif ENGINE_MODE == "idle":
                    if cap is not None:
                        if cap.isOpened():
                            cap.release()
                        cap = None
                        cv2.destroyAllWindows()
                        print("Camera released — order ended (confirmed / cancelled / timed out).")
                    tracker_state.hand_detected = False
                    tracker_state.coords_history.clear()

                last_broadcast_mode = ENGINE_MODE

            # ── IDLE: no camera open, just idle-poll and report health ───────
            if ENGINE_MODE == "idle":
                camera_ok = False
                now = time.time()
                if (now - health_last_broadcast) >= 5.0:
                    health_last_broadcast = now
                    await broadcast_event({
                        "event": "health_status",
                        "camera_ok": camera_ok,
                        "mediapipe_ok": MEDIAPIPE_AVAILABLE,
                        "hand_detected": False,
                        "mode": ENGINE_MODE,
                        "last_gesture": tracker_state.last_classified_gesture,
                    })
                await asyncio.sleep(1.0 / CONFIG["camera"]["idle_fps"])
                continue

            # ── ACTIVE from here on — camera should be open ───────────────────
            target_fps = CONFIG["camera"]["active_fps"]

            # Camera auto-recovery (only while an order is actually active)
            if cap is None or not cap.isOpened():
                await asyncio.sleep(CONFIG["camera"]["auto_recovery_delay"])
                cap = cv2.VideoCapture(device_idx)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    print(f"Camera re-opened on index {device_idx}")
                continue

            success, frame = cap.read()
            if not success:
                print("Frame grab failed — recovering...")
                cap.release()
                cap = None
                continue

            fps_counter += 1
            now = time.time()
            if (now - fps_start_time) >= 5.0:
                current_fps = fps_counter / 5.0
                print(f"[{ENGINE_MODE.upper()}] {current_fps:.1f} FPS | Clients: {len(CONNECTED_CLIENTS)}")
                fps_counter = 0
                fps_start_time = now

            # Broadcast health status every 5 seconds
            camera_ok = cap is not None and cap.isOpened()
            if (now - health_last_broadcast) >= 5.0:
                health_last_broadcast = now
                await broadcast_event({
                    "event": "health_status",
                    "camera_ok": camera_ok,
                    "mediapipe_ok": MEDIAPIPE_AVAILABLE,
                    "hand_detected": tracker_state.hand_detected,
                    "mode": ENGINE_MODE,
                    "last_gesture": tracker_state.last_classified_gesture,
                })

            # Flip camera frame horizontally if configured
            if CONFIG["camera"].get("flip_horizontal", True):
                frame = cv2.flip(frame, 1)

            # Full MediaPipe recognition (mode is guaranteed "active" here)
            if MEDIAPIPE_AVAILABLE and hand_landmarker:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = int((time.time() - vision_start_time) * 1000)
                results = hand_landmarker.detect_for_video(mp_image, timestamp_ms)

                if results.hand_landmarks:
                    hand_landmarks = results.hand_landmarks[0]  # list of 21 NormalizedLandmark

                    if not tracker_state.hand_detected:
                        tracker_state.hand_detected = True
                        print("Hand detected: Tracking active")

                    # Draw landmarks if debug window is enabled (manual draw —
                    # the new Tasks API's drawing_utils has a different signature
                    # than the old one, so we draw simple dots directly instead).
                    if CONFIG["camera"].get("show_debug_window", False):
                        try:
                            h, w = frame.shape[:2]
                            for lm in hand_landmarks:
                                cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 4, (0, 240, 255), -1)
                        except Exception:
                            pass

                    fingertip   = hand_landmarks[8]
                    index_mcp   = hand_landmarks[5]
                    pointer_x   = index_mcp.x
                    pointer_y   = index_mcp.y

                    # Invert X coordinate if configured
                    if CONFIG["camera"].get("invert_x", False):
                        pointer_x = 1.0 - pointer_x

                    gesture, hand_state = analyze_gestures(hand_landmarks)

                    await broadcast_event({
                        "event":       "pointer",
                        "x":           pointer_x,
                        "y":           pointer_y,
                        "fingertip_x": fingertip.x,
                        "fingertip_y": fingertip.y,
                        "state":       hand_state,
                    })

                    if gesture:
                        print(f"Gesture: {gesture}")
                        await broadcast_event({
                            "event":     "gesture",
                            "gesture":   gesture,
                            "confidence": 0.95,
                            "hand":      "single",
                            "timestamp": int(time.time()),
                        })
                else:
                    if tracker_state.hand_detected:
                        tracker_state.hand_detected = False
                        print("Hand lost: Tracking inactive")
                    tracker_state.coords_history.clear()

            # Render debug window if enabled
            if CONFIG["camera"].get("show_debug_window", False) and cap is not None:
                cv2.imshow("HoloMenu Gesture Debug", frame)
                cv2.waitKey(1)
            else:
                cv2.destroyAllWindows()

            # FPS throttle
            elapsed = time.time() - now
            sleep_time = max(1.0 / target_fps - elapsed, 0)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        print("Vision loop shutting down...")
    finally:
        if cap is not None:
            if cap.isOpened():
                cap.release()
            cap = None
        if hand_landmarker:
            hand_landmarker.close()


# ─── WebSocket Handler ───────────────────────────────────────────────────────

async def ws_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    print(f"WS client connected: {websocket.remote_address}")

    # Send current mode to newly connected client
    await websocket.send(json.dumps({"event": "engine_mode", "mode": ENGINE_MODE}))

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                # Client can request mode change
                if data.get("cmd") == "start_order":
                    set_engine_mode("active")
                    await broadcast_event({"event": "engine_mode", "mode": "active"})
                elif data.get("cmd") == "end_session":
                    set_engine_mode("idle")
                    await broadcast_event({"event": "engine_mode", "mode": "idle"})
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        print(f"WS client error: {e}")
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        print(f"WS client disconnected: {websocket.remote_address}")


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    if not WEBSOCKETS_AVAILABLE:
        print("ERROR: Install websockets: pip install websockets")
        return

    host = CONFIG["websocket"]["host"]
    port = CONFIG["websocket"]["port"]

    server = await websockets.serve(ws_handler, host, port, reuse_address=True)
    print(f"WebSocket server on ws://{host}:{port}")

    await asyncio.gather(
        run_recognition_engine(),
        inactivity_watchdog(),
    )
    await server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGesture engine shut down gracefully.")