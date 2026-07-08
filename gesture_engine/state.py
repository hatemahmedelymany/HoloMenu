"""
Shared mutable engine state: tracker state, active mode, and active clients.
"""
import time

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
