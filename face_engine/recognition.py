"""
face_engine/recognition.py
Match detected faces against known encodings.
Manages per-person session state: entry time, exit detection, dedup cooldown.
"""

import os
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import face_recognition
import numpy as np

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.50
EXIT_TIMEOUT_SEC     = 5.0
LOG_COOLDOWN_SEC     = 30.0


@dataclass
class PersonSession:
    """Tracks one continuous visit of a single identity."""
    name: str
    entry_time: float = field(default_factory=time.time)
    last_seen: float  = field(default_factory=time.time)
    exited: bool      = False
    snapshot_path: Optional[str] = None
    session_id: str   = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def touch(self):
        self.last_seen = time.time()

    def duration_seconds(self) -> float:
        end = time.time() if not self.exited else self.last_seen
        return end - self.entry_time


@dataclass
class RecognitionResult:
    name: str
    is_known: bool
    confidence: float
    face_location: Tuple
    snapshot_path: Optional[str] = None
    session_id: Optional[str]    = None


class FaceRecognizer:
    """
    Core recognition engine.

    Workflow per frame:
        1. Compute encodings for detected faces.
        2. Compare against known encodings via L2 distance.
        3. Assign name (known) or generate Unknown-<id> (unknown).
        4. Manage session state: open new session on entry,
           mark exit after EXIT_TIMEOUT_SEC of absence.
    """

    def __init__(
        self,
        known_encodings: List[np.ndarray],
        known_names: List[str],
        unknown_faces_dir: str = "data/unknown_faces",
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        exit_timeout: float = EXIT_TIMEOUT_SEC,
        log_cooldown: float = LOG_COOLDOWN_SEC,
    ):
        self.known_encodings      = known_encodings
        self.known_names          = known_names
        self.unknown_faces_dir    = unknown_faces_dir
        self.confidence_threshold = confidence_threshold
        self.exit_timeout         = exit_timeout
        self.log_cooldown         = log_cooldown

        self._active_sessions: Dict[str, PersonSession] = {}
        self._last_logged: Dict[str, float] = {}
        # Store encodings for unknown faces to provide consistency
        self._unknown_encodings: Dict[str, np.ndarray] = {}

        os.makedirs(unknown_faces_dir, exist_ok=True)

    def process_frame(
        self,
        frame: np.ndarray,
        face_locations: List[Tuple],
        rgb_small: np.ndarray,
        scale_factor: float,
    ) -> Tuple[List[RecognitionResult], List[PersonSession]]:
        """
        Process a single frame: encode faces, match against known, manage sessions.

        Returns:
            results: Recognition result per detected face.
            exited_sessions: Sessions that just transitioned to exited.
        """
        results: List[RecognitionResult] = []

        if not face_locations:
            exited = self._check_exits(set())
            return results, exited

        # Scale locations down for encoding on the small frame
        small_locations = [
            (
                int(top * scale_factor),
                int(right * scale_factor),
                int(bottom * scale_factor),
                int(left * scale_factor),
            )
            for (top, right, bottom, left) in face_locations
        ]

        encodings = face_recognition.face_encodings(rgb_small, small_locations)

        current_names_in_frame = set()

        for encoding, location in zip(encodings, face_locations):
            name, confidence, is_known = self._match_encoding(encoding)

            snapshot_path = None
            if not is_known:
                snapshot_path = self._save_unknown_snapshot(frame, location, name)
                # Store encoding for future consistency matching
                if name not in self._unknown_encodings:
                    self._unknown_encodings[name] = encoding

            session = self._update_session(name, snapshot_path)
            current_names_in_frame.add(name)

            results.append(
                RecognitionResult(
                    name=name,
                    is_known=is_known,
                    confidence=confidence,
                    face_location=location,
                    snapshot_path=snapshot_path,
                    session_id=session.session_id,
                )
            )

        exited_sessions = self._check_exits(current_names_in_frame)
        return results, exited_sessions

    def _match_encoding(
        self, encoding: np.ndarray
    ) -> Tuple[str, float, bool]:
        """Compare encoding against all known encodings."""
        if not self.known_encodings:
            unknown_id = self._assign_unknown_id(encoding)
            return unknown_id, 1.0, False

        distances = face_recognition.face_distance(self.known_encodings, encoding)
        best_idx  = int(np.argmin(distances))
        best_dist = float(distances[best_idx])

        if best_dist <= self.confidence_threshold:
            return self.known_names[best_idx], best_dist, True

        unknown_id = self._assign_unknown_id(encoding)
        return unknown_id, best_dist, False

    def _generate_unknown_id(self) -> str:
        return f"Unknown-{str(uuid.uuid4())[:6].upper()}"

    def _assign_unknown_id(self, encoding: np.ndarray) -> str:
        """
        Try to assign a consistent Unknown-ID for repeat appearances
        of the same unrecognized face within this session.
        """
        for name, stored_enc in self._unknown_encodings.items():
            dist = float(face_recognition.face_distance([stored_enc], encoding)[0])
            if dist < 0.45:
                return name
        return self._generate_unknown_id()

    def _update_session(
        self, name: str, snapshot_path: Optional[str]
    ) -> PersonSession:
        if name in self._active_sessions:
            session = self._active_sessions[name]
            if session.exited:
                new_session = PersonSession(name=name, snapshot_path=snapshot_path)
                self._active_sessions[name] = new_session
                logger.info("Re-entry detected: %s", name)
                return new_session
            session.touch()
            return session

        session = PersonSession(name=name, snapshot_path=snapshot_path)
        self._active_sessions[name] = session
        logger.info("Entry: %s (session %s)", name, session.session_id)
        return session

    def _check_exits(self, current_names: set) -> List[PersonSession]:
        now = time.time()
        exited = []
        for name, session in list(self._active_sessions.items()):
            if session.exited:
                continue
            if name not in current_names:
                if now - session.last_seen > self.exit_timeout:
                    session.exited = True
                    logger.info(
                        "Exit: %s after %.1fs (session %s)",
                        name,
                        session.duration_seconds(),
                        session.session_id,
                    )
                    exited.append(session)
        return exited

    def should_log(self, name: str) -> bool:
        """Dedup guard: prevent log spam for the same person."""
        now = time.time()
        last = self._last_logged.get(name, 0)
        if now - last >= self.log_cooldown:
            self._last_logged[name] = now
            return True
        return False

    def get_active_sessions(self) -> Dict[str, PersonSession]:
        return {
            name: s
            for name, s in self._active_sessions.items()
            if not s.exited
        }

    def _save_unknown_snapshot(
        self, frame: np.ndarray, location: Tuple, name: str
    ) -> Optional[str]:
        try:
            top, right, bottom, left = location
            pad = 20
            h, w = frame.shape[:2]
            t = max(0, top - pad)
            b = min(h, bottom + pad)
            l = max(0, left - pad)
            r = min(w, right + pad)
            crop = frame[t:b, l:r]
            if crop.size == 0:
                return None
            ts = int(time.time())
            filename = os.path.join(self.unknown_faces_dir, f"{name}_{ts}.jpg")
            cv2.imwrite(filename, crop)
            return filename
        except Exception as e:
            logger.error("Failed to save snapshot: %s", e)
            return None

    @staticmethod
    def result_color(result: RecognitionResult) -> Tuple[int, int, int]:
        """BGR color: green=known, red=unknown."""
        return (0, 200, 0) if result.is_known else (0, 0, 220)

    @staticmethod
    def result_label(result: RecognitionResult) -> str:
        conf_pct = int((1.0 - result.confidence) * 100)
        if result.is_known:
            return f"{result.name} ({conf_pct}%)"
        return result.name
