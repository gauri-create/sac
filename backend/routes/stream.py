"""
backend/routes/stream.py
MJPEG video stream endpoint for the live camera feed in the dashboard.
"""

import time
import logging
from flask import Blueprint, Response, current_app

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)

PLACEHOLDER_JPEG = None


def _get_placeholder() -> bytes:
    """Return a minimal JPEG for when the camera is not active."""
    global PLACEHOLDER_JPEG
    if PLACEHOLDER_JPEG is None:
        try:
            import cv2
            import numpy as np
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "Camera Not Active", (160, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (80, 80, 80), 2)
            _, buf = cv2.imencode(".jpg", img)
            PLACEHOLDER_JPEG = buf.tobytes()
        except Exception:
            # Minimal valid 1x1 black JPEG (hard-coded fallback)
            PLACEHOLDER_JPEG = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
                b"\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07"
                b"\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13"
                b"\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c"
                b"(7),01444\x1f'9=82<.342\x1e\x1e#$' )100\xff\xc0\x00\x0b\x08"
                b"\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01"
                b"\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
                b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01"
                b"\x01\x00\x00?\x00\xf5\x07\xff\xd9"
            )
    return PLACEHOLDER_JPEG


def _generate_frames():
    """Generator that yields MJPEG frames."""
    while True:
        frame = current_app.config.get("LATEST_FRAME")
        if frame is None:
            frame = _get_placeholder()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.04)  # ~25 fps cap


@stream_bp.route("/video_feed")
def video_feed():
    """MJPEG stream consumed by the <img> tag in the dashboard."""
    return Response(
        _generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
