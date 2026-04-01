"""
tests/test_api.py
Integration tests for Flask API endpoints.
Uses Flask test client — no real camera or network required.
"""

import os
import sys
import json
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["DB_BACKEND"] = "sqlite"


@pytest.fixture
def client(tmp_path):
    os.environ["SQLITE_PATH"] = str(tmp_path / "test_api.db")
    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealthAndStats:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["status"] == "ok"

    def test_stats_empty_db(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["total_events"] == 0
        assert data["currently_inside"] == 0


class TestLogs:
    def test_logs_empty(self, client):
        r = client.get("/api/logs")
        assert r.status_code == 200
        assert json.loads(r.data) == []

    def test_logs_inside_empty(self, client):
        r = client.get("/api/logs/inside")
        assert r.status_code == 200
        assert json.loads(r.data) == []

    def test_logs_unknown_empty(self, client):
        r = client.get("/api/logs/unknown")
        assert r.status_code == 200
        assert json.loads(r.data) == []


class TestCameraAPI:
    def test_camera_status_default(self, client):
        r = client.get("/api/camera/status")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["active"] is False

    def test_camera_stop_when_idle(self, client):
        r = client.post("/api/camera/stop")
        assert r.status_code == 200


class TestUsers:
    def test_users_empty(self, client):
        r = client.get("/api/users")
        assert r.status_code == 200
        assert json.loads(r.data) == []


class TestSuggestIdentity:
    def test_suggest_no_data(self, client):
        r = client.post(
            "/api/suggest_identity",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "suggested_identity" in data

    def test_suggest_with_image_path(self, client):
        r = client.post(
            "/api/suggest_identity",
            data=json.dumps({"image_path": "data/unknown_faces/Unknown-ABC_1700000.jpg"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "Unknown-ABC" in data["suggested_identity"]


class TestDashboard:
    def test_index_serves_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"SecureEye" in r.data
