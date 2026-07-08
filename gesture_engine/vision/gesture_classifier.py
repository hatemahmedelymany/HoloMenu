"""
Pure-function MediaPipe hand landmarks classifier logic.
"""
import math
import time
from gesture_engine.config.settings import CONFIG
from gesture_engine.state import tracker_state


def calculate_distance(pt1, pt2):
    """Euclidean distance solver between points."""
    return math.sqrt((pt1.x - pt2.x) ** 2 + (pt1.y - pt2.y) ** 2 + (pt1.z - pt2.z) ** 2)


def analyze_gestures(landmarks) -> tuple[str | None, str]:
    """Classifies a list of 21 MediaPipe landmarks into a recognized gesture.

    This function is pure and does not import cv2 or websockets.
    """
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
