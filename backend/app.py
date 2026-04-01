"""
backend/app.py
Flask application factory.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import Database
from backend.routes.api import api_bp
from backend.routes.stream import stream_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Resolve project root relative to this file so paths always work
PROJECT_ROOT = Path(__file__).parent.parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "frontend" / "templates"),
        static_folder=str(PROJECT_ROOT / "frontend" / "static"),
    )
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Ensure required runtime directories exist
    (PROJECT_ROOT / "data" / "unknown_faces").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data" / "known_faces").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "models").mkdir(parents=True, exist_ok=True)

    # Shared state
    db = Database(db_path=str(PROJECT_ROOT / "data" / "access_logs.db"))
    app.config["DB"] = db
    app.config["CAMERA_ACTIVE"] = False
    app.config["LATEST_FRAME"] = None
    app.config["SYSTEM_STATUS"] = "idle"
    app.config["PROJECT_ROOT"] = str(PROJECT_ROOT)

    app.register_blueprint(api_bp,    url_prefix="/api")
    app.register_blueprint(stream_bp, url_prefix="/stream")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/unknown_faces/<path:filename>")
    def serve_unknown_face(filename):
        return send_from_directory(
            str(PROJECT_ROOT / "data" / "unknown_faces"),
            filename,
        )

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5050))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    logger.info("Starting AI Secure Entry on http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
