"""
backend/routes/api.py
All REST API endpoints for the dashboard and system control.
"""

import os
import threading
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)

_camera_thread = None
_stop_event    = threading.Event()


def _db():
    return current_app.config["DB"]


def _project_root() -> Path:
    return Path(current_app.config.get("PROJECT_ROOT", Path(__file__).parent.parent.parent))


def _serialize_log(row: dict) -> dict:
    """Ensure datetime fields are strings for JSON serialization."""
    for key in ("entry_time", "exit_time", "created_at"):
        if key in row and row[key] and not isinstance(row[key], str):
            row[key] = str(row[key])
    # Ensure None values become null-friendly strings
    for key in ("exit_time", "suggested_id", "image_path"):
        if row.get(key) is None:
            row[key] = None
    return row


# ── Stats ────────────────────────────────────────────────────────────────────
@api_bp.route("/stats")
def stats():
    return jsonify(_db().get_stats())


# ── Logs ─────────────────────────────────────────────────────────────────────
@api_bp.route("/logs")
def logs():
    limit  = int(request.args.get("limit", 50))
    name   = request.args.get("name")
    date   = request.args.get("date")
    status = request.args.get("status")

    if name or date or status:
        rows = _db().search_logs(name=name, date=date, status=status, limit=limit)
    else:
        rows = _db().get_recent_logs(limit=limit)

    return jsonify([_serialize_log(r) for r in rows])


@api_bp.route("/logs/today")
def logs_today():
    today = datetime.now().strftime("%Y-%m-%d")
    rows  = _db().get_logs_by_date(today)
    return jsonify([_serialize_log(r) for r in rows])


@api_bp.route("/logs/inside")
def logs_inside():
    rows = _db().get_currently_inside()
    return jsonify([_serialize_log(r) for r in rows])


@api_bp.route("/logs/unknown")
def logs_unknown():
    limit = int(request.args.get("limit", 30))
    rows  = _db().get_unknown_faces(limit=limit)
    return jsonify([_serialize_log(r) for r in rows])


# ── Users ────────────────────────────────────────────────────────────────────
@api_bp.route("/users")
def users():
    return jsonify(_db().get_all_users())


# ── Camera control ───────────────────────────────────────────────────────────
@api_bp.route("/camera/start", methods=["POST"])
def camera_start():
    global _camera_thread, _stop_event

    if current_app.config.get("CAMERA_ACTIVE"):
        return jsonify({"status": "already_running"})

    _stop_event.clear()
    # Pass a frozen copy of the app object for thread safety
    app_obj = current_app._get_current_object()
    _camera_thread = threading.Thread(
        target=_camera_loop,
        args=(app_obj, _stop_event),
        daemon=True,
        name="CameraThread",
    )
    _camera_thread.start()
    current_app.config["CAMERA_ACTIVE"] = True
    current_app.config["SYSTEM_STATUS"] = "running"
    logger.info("Camera thread started.")
    return jsonify({"status": "started"})


@api_bp.route("/camera/stop", methods=["POST"])
def camera_stop():
    global _stop_event
    _stop_event.set()
    current_app.config["CAMERA_ACTIVE"] = False
    current_app.config["SYSTEM_STATUS"] = "idle"
    logger.info("Camera thread stop requested.")
    return jsonify({"status": "stopped"})


@api_bp.route("/camera/status")
def camera_status():
    return jsonify({
        "active": current_app.config.get("CAMERA_ACTIVE", False),
        "status": current_app.config.get("SYSTEM_STATUS", "idle"),
    })


# ── Rebuild encodings ────────────────────────────────────────────────────────
@api_bp.route("/encodings/rebuild", methods=["POST"])
def rebuild_encodings():
    import sys
    proj_root = str(_project_root())
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)

    from face_engine.encoding import EncodingManager
    mgr = EncodingManager(
        known_faces_dir=_project_root() / "data" / "known_faces",
        encodings_path=_project_root() / "models" / "encodings.pkl",
    )
    count = mgr.build_encodings(force_rebuild=True)
    return jsonify({"status": "ok", "identities": count})


# ── Suggest identity ─────────────────────────────────────────────────────────
@api_bp.route("/suggest_identity", methods=["POST"])
def suggest_identity():
    data       = request.get_json(silent=True) or {}
    image_path = data.get("image_path", "")
    session_id = data.get("session_id", "")

    suggestion = _mock_identity_lookup(image_path)

    if session_id:
        _db().update_suggested_id(session_id, suggestion)

    return jsonify({"suggested_identity": suggestion})


def _mock_identity_lookup(image_path: str) -> str:
    if image_path:
        basename = Path(image_path).stem
        return f"Possible match: {basename} (confidence: simulated)"
    return "No suggestion available"


# ── Background camera loop ───────────────────────────────────────────────────
def _camera_loop(app, stop_event: threading.Event):
    """
    Runs in a daemon thread. Reads frames, runs face recognition,
    writes results to DB, updates app.config['LATEST_FRAME'] for MJPEG.
    """
    import sys
    import time

    proj_root = app.config.get("PROJECT_ROOT", str(Path(__file__).parent.parent.parent))
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)

    try:
        import cv2
        from face_engine.detection   import FaceDetector
        from face_engine.encoding    import EncodingManager
        from face_engine.recognition import FaceRecognizer
    except ImportError as e:
        logger.error("Import error in camera loop: %s", e)
        app.config["SYSTEM_STATUS"] = "error"
        app.config["CAMERA_ACTIVE"] = False
        return

    with app.app_context():
        db = app.config["DB"]
        root = Path(proj_root)

        enc_mgr = EncodingManager(
            known_faces_dir=root / "data" / "known_faces",
            encodings_path=root / "models" / "encodings.pkl",
        )
        try:
            enc_mgr.build_encodings()
        except Exception as e:
            logger.error("Failed to load encodings: %s", e)
            app.config["SYSTEM_STATUS"] = "error"
            return

        known_encodings, known_names = enc_mgr.get_data()
        detector   = FaceDetector(scale_factor=0.5, model="hog")
        recognizer = FaceRecognizer(
            known_encodings,
            known_names,
            unknown_faces_dir=str(root / "data" / "unknown_faces"),
        )

        cam_index = int(os.getenv("CAMERA_INDEX", "0"))
        cap = cv2.VideoCapture(cam_index)
        if not cap.isOpened():
            logger.error("Cannot open camera index %d", cam_index)
            app.config["SYSTEM_STATUS"] = "error"
            app.config["CAMERA_ACTIVE"] = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        logger.info("Camera loop running (index=%d).", cam_index)

        logged_entries = set()

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                logger.warning("Frame read failed — retrying.")
                time.sleep(0.1)
                continue

            face_locations, rgb_small = detector.detect_faces(frame)

            results, exited_sessions = recognizer.process_frame(
                frame, face_locations, rgb_small, detector.scale_factor
            )

            for result in results:
                sid = result.session_id
                if sid and sid not in logged_entries:
                    if recognizer.should_log(result.name):
                        db.log_entry(
                            session_id=sid,
                            name=result.name,
                            is_known=result.is_known,
                            entry_time=datetime.now(),
                            image_path=result.snapshot_path,
                        )
                        if result.is_known:
                            db.upsert_user(result.name)
                        logged_entries.add(sid)

            for session in exited_sessions:
                db.log_exit(
                    session_id=session.session_id,
                    exit_time=datetime.now(),
                    duration_sec=session.duration_seconds(),
                )

            labels = [FaceRecognizer.result_label(r) for r in results]
            colors = [FaceRecognizer.result_color(r)  for r in results]
            annotated = detector.draw_boxes(frame, face_locations, labels, colors)

            status_text = f"System: ACTIVE | Faces: {len(results)}"
            cv2.putText(annotated, status_text, (10, annotated.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 255), 1)

            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            app.config["LATEST_FRAME"] = jpeg.tobytes()

        cap.release()
        logger.info("Camera loop terminated.")
