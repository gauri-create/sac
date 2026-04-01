"""
tests/test_recognition.py
Unit tests for session management in FaceRecognizer.
Uses mock encodings so no real camera or dlib is needed.
"""

import sys
import time
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from face_engine.recognition import FaceRecognizer, PersonSession


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_recognizer(exit_timeout=0.2, cooldown=0.0) -> FaceRecognizer:
    """Return a recognizer with fake encodings for Alice and Bob."""
    alice_enc = np.zeros(128, dtype=np.float64)   # encoding "0 vector" = Alice
    bob_enc   = np.ones(128, dtype=np.float64) * 0.5
    return FaceRecognizer(
        known_encodings=[alice_enc, bob_enc],
        known_names=["Alice", "Bob"],
        unknown_faces_dir="/tmp/test_unknown",
        confidence_threshold=0.50,
        exit_timeout=exit_timeout,
        log_cooldown=cooldown,
    )


# ── Session creation tests ───────────────────────────────────────────────────

class TestSessionCreation:
    def test_new_session_on_first_detection(self):
        rec = make_recognizer()
        # Simulate _update_session being called directly
        session = rec._update_session("Alice", None)
        assert session.name == "Alice"
        assert not session.exited
        assert "Alice" in rec._active_sessions

    def test_touch_on_repeated_detection(self):
        rec = make_recognizer()
        s1 = rec._update_session("Alice", None)
        t_before = s1.last_seen
        time.sleep(0.05)
        s2 = rec._update_session("Alice", None)
        assert s1 is s2  # same session object
        assert s2.last_seen > t_before

    def test_reentry_creates_new_session(self):
        rec = make_recognizer(exit_timeout=0.1)
        s1 = rec._update_session("Bob", None)
        # Force exit
        s1.exited = True
        s2 = rec._update_session("Bob", None)
        assert s1 is not s2
        assert not s2.exited


# ── Exit detection tests ─────────────────────────────────────────────────────

class TestExitDetection:
    def test_exit_after_timeout(self):
        rec = make_recognizer(exit_timeout=0.1)
        rec._update_session("Alice", None)
        time.sleep(0.15)
        exited = rec._check_exits(current_names=set())
        assert len(exited) == 1
        assert exited[0].name == "Alice"

    def test_no_exit_while_in_frame(self):
        rec = make_recognizer(exit_timeout=0.3)
        rec._update_session("Alice", None)
        time.sleep(0.05)
        exited = rec._check_exits(current_names={"Alice"})
        assert len(exited) == 0

    def test_no_double_exit(self):
        rec = make_recognizer(exit_timeout=0.1)
        rec._update_session("Alice", None)
        time.sleep(0.15)
        rec._check_exits(set())             # first call → exits
        exited2 = rec._check_exits(set())   # second call → already marked
        assert len(exited2) == 0

    def test_multiple_people_partial_exit(self):
        rec = make_recognizer(exit_timeout=0.1)
        rec._update_session("Alice", None)
        rec._update_session("Bob",   None)
        time.sleep(0.15)
        # Bob stays visible
        exited = rec._check_exits(current_names={"Bob"})
        names = [s.name for s in exited]
        assert "Alice" in names
        assert "Bob"   not in names


# ── Dedup guard tests ────────────────────────────────────────────────────────

class TestLogCooldown:
    def test_should_log_first_time(self):
        rec = make_recognizer(cooldown=10.0)
        assert rec.should_log("Alice") is True

    def test_should_not_log_within_cooldown(self):
        rec = make_recognizer(cooldown=10.0)
        rec.should_log("Alice")
        assert rec.should_log("Alice") is False

    def test_should_log_after_cooldown(self):
        rec = make_recognizer(cooldown=0.05)
        rec.should_log("Alice")
        time.sleep(0.1)
        assert rec.should_log("Alice") is True


# ── Matching tests ───────────────────────────────────────────────────────────

class TestMatching:
    def test_known_match(self):
        rec = make_recognizer()
        alice_enc = np.zeros(128, dtype=np.float64)
        name, dist, is_known = rec._match_encoding(alice_enc)
        assert name == "Alice"
        assert is_known is True
        assert dist < 0.5

    def test_unknown_face(self):
        rec = make_recognizer()
        random_enc = np.random.rand(128).astype(np.float64) * 10
        name, dist, is_known = rec._match_encoding(random_enc)
        assert not is_known
        assert name.startswith("Unknown-")

    def test_empty_encodings_returns_unknown(self):
        rec = FaceRecognizer([], [], "/tmp", exit_timeout=5.0, log_cooldown=0.0)
        name, dist, is_known = rec._match_encoding(np.zeros(128))
        assert not is_known
        assert dist == 1.0


# ── Active sessions ──────────────────────────────────────────────────────────

class TestActiveSessions:
    def test_get_active_excludes_exited(self):
        rec = make_recognizer()
        rec._update_session("Alice", None)
        s = rec._update_session("Bob", None)
        s.exited = True
        active = rec.get_active_sessions()
        assert "Alice" in active
        assert "Bob" not in active
