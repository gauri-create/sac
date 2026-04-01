"""
face_engine/detection.py
Real-time face detection using OpenCV + face_recognition.
Handles frame preprocessing, face location detection, and FPS optimization.
"""

import cv2
import face_recognition
import numpy as np
import time
from typing import List, Tuple


class FaceDetector:
    """
    Handles real-time face detection with adaptive frame skipping
    to maintain acceptable FPS on commodity hardware.
    """

    def __init__(self, scale_factor: float = 0.5, model: str = "hog"):
        """
        Args:
            scale_factor: Resize frame before detection (0.25–1.0). Lower = faster.
            model: 'hog' (CPU, fast) or 'cnn' (GPU, accurate).
        """
        self.scale_factor = scale_factor
        self.model = model  # 'hog' recommended for CPU-only deployments
        self._frame_count = 0
        self._process_every_n = 2  # Process every Nth frame to save CPU
        self._last_locations: List[Tuple] = []
        self._last_fps_check = time.time()
        self._fps = 0.0

    def preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Downscale + convert BGR→RGB for face_recognition library.
        face_recognition expects RGB; OpenCV gives BGR.
        """
        small = cv2.resize(
            frame,
            (0, 0),
            fx=self.scale_factor,
            fy=self.scale_factor,
        )
        return cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

    def detect_faces(
        self, frame: np.ndarray
    ) -> Tuple[List[Tuple[int, int, int, int]], np.ndarray]:
        """
        Detect all face bounding boxes in the given frame.

        Returns:
            face_locations: List of (top, right, bottom, left) in ORIGINAL frame coords.
            rgb_small: Preprocessed small frame (for encoding step — avoids double resize).
        """
        self._frame_count += 1

        rgb_small = self.preprocess_frame(frame)

        # Skip detection on intermediate frames; reuse last known locations
        if self._frame_count % self._process_every_n == 0:
            raw_locations = face_recognition.face_locations(
                rgb_small, model=self.model
            )
            # Scale locations back to original frame coordinates
            inv = 1.0 / self.scale_factor
            self._last_locations = [
                (
                    int(top * inv),
                    int(right * inv),
                    int(bottom * inv),
                    int(left * inv),
                )
                for (top, right, bottom, left) in raw_locations
            ]

        self._update_fps()
        return self._last_locations, rgb_small

    def _update_fps(self):
        now = time.time()
        elapsed = now - self._last_fps_check
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_check = now

    @property
    def fps(self) -> float:
        return round(self._fps, 1)

    def draw_boxes(
        self,
        frame: np.ndarray,
        face_locations: List[Tuple],
        labels: List[str],
        colors: List[Tuple[int, int, int]],
    ) -> np.ndarray:
        """
        Draw bounding boxes and name labels on the frame.

        Args:
            frame: Original BGR frame.
            face_locations: List of (top, right, bottom, left).
            labels: Name strings aligned with face_locations.
            colors: BGR tuples aligned with face_locations.
        Returns:
            Annotated frame copy.
        """
        output = frame.copy()
        for (top, right, bottom, left), label, color in zip(
            face_locations, labels, colors
        ):
            # Box
            cv2.rectangle(output, (left, top), (right, bottom), color, 2)

            # Label background
            (text_w, text_h), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_DUPLEX, 0.6, 1
            )
            cv2.rectangle(
                output,
                (left, bottom - text_h - 10),
                (left + text_w + 6, bottom),
                color,
                cv2.FILLED,
            )
            cv2.putText(
                output,
                label,
                (left + 3, bottom - 5),
                cv2.FONT_HERSHEY_DUPLEX,
                0.6,
                (255, 255, 255),
                1,
            )

        # FPS overlay
        cv2.putText(
            output,
            f"FPS: {self.fps}",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        return output
