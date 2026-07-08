"""
Camera capture wrapper lifecycle logic.
"""
import cv2

def open_camera(device_idx: int, width: int, height: int):
    """Acquires a handle to the OpenCV capture interface."""
    print(f"Opening camera on index {device_idx} ...")
    cap = cv2.VideoCapture(device_idx)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        print("Camera is now ON.")
    else:
        print(f"ERROR: Camera {device_idx} could not be opened.")
    return cap

def release_camera(cap):
    """Releases active video capture handles and clears overlays."""
    if cap is not None:
        if cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        print("Camera released.")

def get_frame(cap, flip_horizontal: bool = True):
    """Reads frame and optionally applies mirrors."""
    success, frame = cap.read()
    if success and flip_horizontal:
        frame = cv2.flip(frame, 1)
    return success, frame
