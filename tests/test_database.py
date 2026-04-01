"""
tests/test_database.py
Unit tests for the Database abstraction layer (SQLite backend).
Run: pytest tests/ -v
"""

import os
import sys
import tempfile
import pytest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Point to a temp DB for testing
os.environ["DB_BACKEND"] = "sqlite"


@pytest.fixture
def db(tmp_path):
    """Create a fresh in-memory/temp Database instance for each test."""
    os.environ["SQLITE_PATH"] = str(tmp_path / "test.db")
    from backend.database import Database
    instance = Database()
    yield instance


class TestUsers:
    def test_upsert_and_get(self, db):
        db.upsert_user("Alice Smith", "/path/encodings.pkl")
        users = db.get_all_users()
        assert len(users) == 1
        assert users[0]["name"] == "Alice Smith"

    def test_upsert_idempotent(self, db):
        db.upsert_user("Bob Jones")
        db.upsert_user("Bob Jones", "/updated/path")
        users = db.get_all_users()
        assert len(users) == 1
        assert users[0]["encoding_path"] == "/updated/path"


class TestAccessLogs:
    def test_log_entry(self, db):
        row_id = db.log_entry(
            session_id="sess-001",
            name="Alice",
            is_known=True,
            entry_time=datetime.now(),
        )
        assert row_id > 0
        logs = db.get_recent_logs(10)
        assert len(logs) == 1
        assert logs[0]["name"] == "Alice"
        assert logs[0]["status"] == "INSIDE"

    def test_log_exit(self, db):
        db.log_entry("sess-002", "Bob", True, datetime.now())
        db.log_exit("sess-002", datetime.now(), 42.5)
        logs = db.get_recent_logs(10)
        bob = next(l for l in logs if l["name"] == "Bob")
        assert bob["status"] == "OUTSIDE"
        assert abs(bob["duration_sec"] - 42.5) < 0.1

    def test_currently_inside(self, db):
        db.log_entry("s1", "Alice", True, datetime.now())
        db.log_entry("s2", "Bob",   True, datetime.now())
        db.log_exit("s2", datetime.now(), 10.0)
        inside = db.get_currently_inside()
        names = [r["name"] for r in inside]
        assert "Alice" in names
        assert "Bob" not in names

    def test_unknown_face_logging(self, db):
        db.log_entry("s3", "Unknown-ABC123", False, datetime.now(), "/data/unknown/snap.jpg")
        unknowns = db.get_unknown_faces()
        assert len(unknowns) == 1
        assert not unknowns[0]["is_known"]

    def test_search_by_name(self, db):
        db.log_entry("s4", "Carol", True, datetime.now())
        db.log_entry("s5", "Dave",  True, datetime.now())
        results = db.search_logs(name="Carol")
        assert len(results) == 1
        assert results[0]["name"] == "Carol"

    def test_search_by_status(self, db):
        db.log_entry("s6", "Eve",   True, datetime.now())
        db.log_entry("s7", "Frank", True, datetime.now())
        db.log_exit("s7", datetime.now(), 5.0)
        inside  = db.search_logs(status="INSIDE")
        outside = db.search_logs(status="OUTSIDE")
        assert all(r["status"] == "INSIDE"  for r in inside)
        assert all(r["status"] == "OUTSIDE" for r in outside)

    def test_stats(self, db):
        db.log_entry("s8", "Alice",            True,  datetime.now())
        db.log_entry("s9", "Unknown-XYZ",      False, datetime.now())
        stats = db.get_stats()
        assert stats["total_events"] == 2
        assert stats["currently_inside"] == 2
        assert stats["unknown_faces"] == 1

    def test_suggested_id_update(self, db):
        db.log_entry("s10", "Unknown-TTT", False, datetime.now())
        db.update_suggested_id("s10", "Possible: John Doe (simulated)")
        logs = db.get_recent_logs(5)
        row = next(l for l in logs if l["session_id"] == "s10")
        assert "John Doe" in row["suggested_id"]
