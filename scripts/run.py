#!/usr/bin/env python3
"""
scripts/run.py
Single-command launcher.

Usage:
    python scripts/run.py                 # Web dashboard only (no camera)
    python scripts/run.py --camera        # Camera + web dashboard
    python scripts/run.py --encode        # (Re)build face encodings and exit
    python scripts/run.py --camera-only   # Camera loop, no web server (headless)
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is always on the path regardless of CWD
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Also change CWD to project root so relative paths resolve correctly
os.chdir(PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("launcher")


def build_encodings():
    from face_engine.encoding import EncodingManager
    mgr = EncodingManager(
        known_faces_dir=PROJECT_ROOT / "data" / "known_faces",
        encodings_path=PROJECT_ROOT / "models" / "encodings.pkl",
    )
    n = mgr.build_encodings(force_rebuild=True)
    logger.info("Done. %d identit%s encoded.", n, "y" if n == 1 else "ies")


def run_dashboard(start_camera: bool = False):
    from backend.app import create_app
    app = create_app()
    port = int(os.getenv("PORT", 5050))

    if start_camera:
        import threading
        from backend.routes.api import _camera_loop, _stop_event
        _stop_event.clear()
        t = threading.Thread(
            target=_camera_loop,
            args=(app, _stop_event),
            daemon=True,
            name="CameraThread",
        )
        t.start()
        app.config["CAMERA_ACTIVE"] = True
        app.config["SYSTEM_STATUS"] = "running"
        logger.info("Camera thread auto-started.")

    logger.info("Dashboard at http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


def run_camera_only():
    """Headless mode: run recognition loop, log to DB, no web server."""
    from backend.app import create_app
    from backend.routes.api import _camera_loop, _stop_event
    app = create_app()
    with app.app_context():
        _camera_loop(app, _stop_event)


def main():
    p = argparse.ArgumentParser(description="SecureEye AI Entry System")
    p.add_argument("--encode",      action="store_true", help="Build face encodings and exit")
    p.add_argument("--camera",      action="store_true", help="Auto-start camera with dashboard")
    p.add_argument("--camera-only", dest="camera_only", action="store_true",
                   help="Camera loop only (no web server)")
    args = p.parse_args()

    if args.encode:
        build_encodings()
    elif args.camera_only:
        run_camera_only()
    else:
        run_dashboard(start_camera=args.camera)


if __name__ == "__main__":
    main()
