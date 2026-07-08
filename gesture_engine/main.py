"""
Gesture Engine Entrypoint. Wires vision capture, Landmarking, classification, and WS transit.
"""
import asyncio
import json
import time
import sys
import platform
import cv2

from gesture_engine.config.settings import CONFIG
import gesture_engine.state as engine_state
from gesture_engine.state import tracker_state, set_engine_mode

from gesture_engine.vision.camera import open_camera, release_camera, get_frame
from gesture_engine.vision.hand_landmarker import create_hand_landmarker, MEDIAPIPE_AVAILABLE, mp
from gesture_engine.vision.gesture_classifier import analyze_gestures

from gesture_engine.transport.websocket_server import ws_handler, broadcast_event, WEBSOCKETS_AVAILABLE

# Diagonal diagnostic banner
print("=" * 70)
print(f"Python executable : {sys.executable}")
print(f"Python version    : {platform.python_version()} ({platform.architecture()[0]})")
print("=" * 70)
if MEDIAPIPE_AVAILABLE:
    print("MediaPipe HandLandmarker Tasks API loaded successfully.")
else:
    print("WARNING: Running in simulation mode (MediaPipe not loaded).")
print("=" * 70)


async def inactivity_watchdog():
    """Broadcasts session_timeout if no activity for configured duration in ACTIVE mode."""
    timeout_secs = CONFIG["order"]["inactivity_timeout_seconds"]
    while True:
        await asyncio.sleep(5)
        if engine_state.ENGINE_MODE == "active":
            idle_for = time.time() - engine_state.LAST_ACTIVITY_TIME
            if idle_for >= timeout_secs:
                print(f"Inactivity timeout after {idle_for:.0f}s — broadcasting session_timeout")
                await broadcast_event({"event": "session_timeout", "idle_seconds": int(idle_for)})
                set_engine_mode("idle")


async def run_recognition_engine():
    device_idx = CONFIG["camera"]["device_index"]
    width      = CONFIG["camera"]["width"]
    height     = CONFIG["camera"]["height"]

    cap = None
    hand_landmarker = create_hand_landmarker()
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
            if engine_state.ENGINE_MODE != last_broadcast_mode:
                await broadcast_event({"event": "engine_mode", "mode": engine_state.ENGINE_MODE})

                if engine_state.ENGINE_MODE == "active":
                    tracker_state.coords_history.clear()
                    tracker_state.hand_detected = False
                    if cap is None or not cap.isOpened():
                        cap = open_camera(device_idx, width, height)

                elif engine_state.ENGINE_MODE == "idle":
                    if cap is not None:
                        release_camera(cap)
                        cap = None
                    tracker_state.hand_detected = False
                    tracker_state.coords_history.clear()

                last_broadcast_mode = engine_state.ENGINE_MODE

            # ── IDLE: no camera open, just idle-poll and report health ───────
            if engine_state.ENGINE_MODE == "idle":
                camera_ok = False
                now = time.time()
                if (now - health_last_broadcast) >= 5.0:
                    health_last_broadcast = now
                    await broadcast_event({
                        "event": "health_status",
                        "camera_ok": camera_ok,
                        "mediapipe_ok": MEDIAPIPE_AVAILABLE,
                        "hand_detected": False,
                        "mode": engine_state.ENGINE_MODE,
                        "last_gesture": tracker_state.last_classified_gesture,
                    })
                await asyncio.sleep(1.0 / CONFIG["camera"]["idle_fps"])
                continue

            # ── ACTIVE from here on — camera should be open ───────────────────
            target_fps = CONFIG["camera"]["active_fps"]

            # Camera auto-recovery (only while an order is actually active)
            if cap is None or not cap.isOpened():
                await asyncio.sleep(CONFIG["camera"]["auto_recovery_delay"])
                cap = open_camera(device_idx, width, height)
                continue

            # Get frame
            flip_horizontal = CONFIG["camera"].get("flip_horizontal", True)
            success, frame = get_frame(cap, flip_horizontal)
            if not success:
                print("Frame grab failed — recovering...")
                release_camera(cap)
                cap = None
                continue

            fps_counter += 1
            now = time.time()
            if (now - fps_start_time) >= 5.0:
                current_fps = fps_counter / 5.0
                print(f"[{engine_state.ENGINE_MODE.upper()}] {current_fps:.1f} FPS | Clients: {len(engine_state.CONNECTED_CLIENTS)}")
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
                    "mode": engine_state.ENGINE_MODE,
                    "last_gesture": tracker_state.last_classified_gesture,
                })

            # Full MediaPipe recognition
            if MEDIAPIPE_AVAILABLE and hand_landmarker:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = int((time.time() - vision_start_time) * 1000)
                results = hand_landmarker.detect_for_video(mp_image, timestamp_ms)

                if results.hand_landmarks:
                    hand_landmarks = results.hand_landmarks[0]

                    if not tracker_state.hand_detected:
                        tracker_state.hand_detected = True
                        print("Hand detected: Tracking active")

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

            # Render debug window
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
            release_camera(cap)
            cap = None
        if hand_landmarker:
            hand_landmarker.close()


async def main():
    if not WEBSOCKETS_AVAILABLE:
        print("ERROR: Install websockets: pip install websockets")
        return

    host = CONFIG["websocket"]["host"]
    port = CONFIG["websocket"]["port"]

    import websockets
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
