# ⬡ SecureEye — AI Secure Entry System

> Real-time face recognition access control with a live web dashboard.
> Production-structured · Modular · Portfolio-ready.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Local Setup](#local-setup)
5. [Adding Known Faces](#adding-known-faces)
6. [Running the System](#running-the-system)
7. [Dashboard Guide](#dashboard-guide)
8. [Database Schema](#database-schema)
9. [Entry/Exit Tracking Logic](#entryexit-tracking-logic)
10. [Configuration Reference](#configuration-reference)
11. [Deployment Guide](#deployment-guide)
12. [Extending the System](#extending-the-system)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                      SECUREEYE SYSTEM                    │
│                                                          │
│  Webcam ──► FaceDetector ──► FaceRecognizer              │
│                  │                  │                    │
│            (OpenCV HOG)     (face_recognition)           │
│                  │                  │                    │
│                  └──────┬───────────┘                    │
│                         │                                │
│                   SessionTracker                         │
│                    (entry/exit)                          │
│                         │                                │
│                    Database (SQLite/MySQL)                │
│                         │                                │
│              Flask REST API (/api/*)                      │
│                         │                                │
│           Browser Dashboard (HTML+CSS+JS)                │
│           + MJPEG stream (/stream/video_feed)            │
└──────────────────────────────────────────────────────────┘
```

**Design decisions:**
- **HOG model** (not CNN) for CPU-only deployments — fast and reliable on commodity hardware.
- **Frame skipping** (process every 2nd frame) for better FPS with negligible accuracy loss.
- **SQLite WAL mode** for concurrent reads from Flask while the camera thread writes.
- **MJPEG** stream via multipart HTTP — works in all browsers with no WebSocket complexity.
- **Session-based dedup** — one DB row per continuous visit, not per detected frame.

---

## Project Structure

```
ai_secure_entry/
│
├── face_engine/               # ML / vision module
│   ├── __init__.py
│   ├── detection.py           # OpenCV face location + FPS management
│   ├── encoding.py            # Build & cache 128-d face encodings
│   └── recognition.py        # Match faces, manage sessions, save snapshots
│
├── backend/                   # Web server module
│   ├── __init__.py
│   ├── app.py                 # Flask app factory
│   ├── database.py            # SQLite/MySQL abstraction layer
│   └── routes/
│       ├── __init__.py
│       ├── api.py             # REST endpoints + background camera thread
│       └── stream.py         # MJPEG video stream
│
├── frontend/                  # Dashboard UI
│   ├── templates/
│   │   └── index.html         # Single-page dashboard
│   └── static/
│       ├── css/dashboard.css  # Industrial cyberpunk design
│       ├── js/dashboard.js    # Live polling, table rendering, controls
│       └── img/
│           └── unknown_placeholder.svg
│
├── data/
│   ├── known_faces/           # <Name>/ subdirs with .jpg/.png images
│   │   └── Alice_Smith/
│   │       ├── photo1.jpg
│   │       └── photo2.jpg
│   ├── unknown_faces/         # Auto-saved snapshots of unrecognized faces
│   └── access_logs.db         # SQLite database (auto-created)
│
├── models/
│   └── encodings.pkl          # Cached face encodings (auto-built)
│
├── scripts/
│   ├── run.py                 # Main launcher
│   └── add_person.py          # Register new faces from CLI
│
├── docs/
│   └── deployment.md          # Cloud deployment guide
│
├── requirements.txt
├── .env.example
├── Procfile                   # Heroku/Render
├── render.yaml                # Render.com deployment spec
└── README.md
```

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | 3.11 recommended |
| CMake | ≥ 3.18 | Required to compile dlib |
| C++ compiler | GCC 9+ / MSVC 2019+ / Xcode CLT | For dlib build |
| Webcam | Any | USB or built-in |

### Install system dependencies

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install -y cmake build-essential libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev python3-dev
```

**macOS:**
```bash
xcode-select --install
brew install cmake
```

**Windows:**
- Install [Visual Studio Build Tools 2022](https://visualstudio.microsoft.com/downloads/) with C++ workload
- Install [CMake](https://cmake.org/download/)

---

## Local Setup

### 1. Clone / download the project

```bash
cd ai_secure_entry
```

### 2. Create virtual environment

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** `dlib` compiles from source and takes 2–5 minutes. This is normal.

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your settings (optional for local use)
```

### 5. Add known faces (see next section), then run:

```bash
python scripts/run.py
```

Open **http://localhost:5050** in your browser.

---

## Adding Known Faces

### Method A: Manual folder structure

Create a subdirectory under `data/known_faces/` named with the person's name (underscores for spaces). Add at least **2–5 clear photos** per person for better accuracy.

```
data/known_faces/
    Alice_Smith/
        front.jpg
        slight_angle.jpg
    Bob_Jones/
        photo1.jpg
```

Then rebuild encodings:
```bash
python scripts/run.py --encode
```

### Method B: CLI helper script

```bash
python scripts/add_person.py "Alice Smith" /path/to/alice1.jpg /path/to/alice2.jpg
```

This copies the images and rebuilds encodings automatically.

### Method C: Dashboard button

On the **Known Users** tab, click **⟳ Rebuild Encodings** after manually adding images to the folder structure.

### Photo guidelines for best accuracy

| Do ✓ | Avoid ✗ |
|------|---------|
| Well-lit, front-facing | Dark / backlit photos |
| Clear face, no obstruction | Sunglasses, heavy hats |
| Multiple angles (2–5 photos) | Single blurry photo |
| JPG or PNG, ≥ 200×200px | Tiny thumbnails |

---

## Running the System

### Dashboard only (no camera — useful for viewing DB data)
```bash
python scripts/run.py
```

### Dashboard + auto-start camera
```bash
python scripts/run.py --camera
```

### Rebuild encodings from dataset, then exit
```bash
python scripts/run.py --encode
```

### Camera loop only (headless, no web UI)
```bash
python scripts/run.py --camera-only
```

### Camera control via dashboard
1. Open http://localhost:5050
2. Click **▶ START** on the Overview tab to begin recognition
3. Click **■ STOP** to halt the camera

---

## Dashboard Guide

### Overview Tab
- **Stats row** — live counts of total events, currently inside, today's events, unknown faces, known people.
- **Live Feed** — MJPEG stream with annotated bounding boxes. Green box = known person. Red box = unknown.
- **Currently Inside** — real-time list of people currently in frame / recently seen.
- **Recent Activity** — last 20 events (entry/exit/unknown) with timestamps and duration.

### Access Logs Tab
- Full searchable table: filter by **name**, **date**, or **status** (Inside/Outside).
- Columns: Name, Status badge, Entry time, Exit time, Duration, Type (Known/Unknown).

### Unknown Faces Tab
- Photo gallery of all unrecognized faces with timestamps.
- **Suggest Identity** button triggers the mock AI enrichment hook (replace with real API in production).

### Known Users Tab
- List of all registered users from the `users` table.
- **⟳ Rebuild Encodings** — regenerates `models/encodings.pkl` from the `data/known_faces/` dataset.

---

## Database Schema

### `users` table
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT UNIQUE | Display name |
| `encoding_path` | TEXT | Path to source images |
| `created_at` | DATETIME | Registration time |

### `access_logs` table
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `session_id` | TEXT | UUID per continuous visit |
| `name` | TEXT | Person's name or Unknown-XXXXXX |
| `is_known` | INTEGER | 1 = known, 0 = unknown |
| `entry_time` | DATETIME | First frame detected |
| `exit_time` | DATETIME | Last frame seen + timeout |
| `duration_sec` | REAL | Seconds spent inside |
| `status` | TEXT | INSIDE or OUTSIDE |
| `image_path` | TEXT | Snapshot path (unknowns only) |
| `suggested_id` | TEXT | AI-enriched identity (optional) |
| `created_at` | DATETIME | Row creation time |

**Indexes:** `name`, `entry_time`, `status` — ensures fast dashboard queries even with large log tables.

---

## Entry/Exit Tracking Logic

This is the core engineering challenge. Here's how it works:

```
Frame 1: Alice detected → new PersonSession created, entry_time = now
Frame 2: Alice detected → session.last_seen updated (touch)
Frame 3: Alice NOT detected → timer starts (exit_timeout countdown)
...
Frame 8: Still not detected → elapsed > EXIT_TIMEOUT_SEC (5s default)
         → session.exited = True
         → DB: UPDATE exit_time, duration_sec, status='OUTSIDE'
```

### Key parameters (tunable in `recognition.py`):

| Constant | Default | Effect |
|----------|---------|--------|
| `CONFIDENCE_THRESHOLD` | 0.50 | L2 distance cutoff. Lower = stricter. |
| `EXIT_TIMEOUT_SEC` | 5.0 | Seconds before person is marked exited |
| `LOG_COOLDOWN_SEC` | 30.0 | Min seconds before re-logging same person |

### Duplicate prevention

- Each continuous visit gets one `session_id` (UUID).
- `should_log()` enforces a cooldown — prevents log spam if recognition flickers.
- Re-entry after exit correctly creates a **new session row** in the DB.

### Multiple faces

The recognizer processes all faces in a single frame simultaneously. Each face gets its own `PersonSession`, identified independently.

---

## Configuration Reference

All settings are in `.env` (copy from `.env.example`):

```
SECRET_KEY        Flask secret key
PORT              Web server port (default: 5050)
FLASK_DEBUG       0 = production, 1 = hot-reload
CAMERA_INDEX      Webcam index (0 = default)
DB_BACKEND        sqlite or mysql
SQLITE_PATH       Path to SQLite file
MYSQL_HOST/PORT/USER/PASS/DB  MySQL connection (if DB_BACKEND=mysql)
```

---

## Deployment Guide

### Option 1: Render.com (recommended free tier)

1. Push to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set **Build Command:** `pip install -r requirements.txt`
4. Set **Start Command:** `gunicorn -w 2 -b 0.0.0.0:$PORT backend.app:create_app()`
5. Add environment variables from `.env.example`

> **Note:** Cloud deployments don't have webcam access. Use `--camera-only` on a local machine and point it at a remote DB (MySQL) while the dashboard runs on the cloud.

### Option 2: Heroku

```bash
heroku create secureeye-app
heroku config:set SECRET_KEY=your-secret DB_BACKEND=sqlite
git push heroku main
```

### Option 3: AWS EC2 / DigitalOcean Droplet

```bash
# On server
git clone <repo> && cd ai_secure_entry
pip install -r requirements.txt
gunicorn -w 4 -b 0.0.0.0:5050 --timeout 120 "backend.app:create_app()"

# With nginx reverse proxy (recommended)
# Point /stream/ location to pass proxy with long timeout:
# proxy_read_timeout 3600;
```

### Hybrid architecture (recommended for production)

```
Local machine (has webcam):           Cloud server (public URL):
  python scripts/run.py               Flask dashboard
  --camera-only                  ←──  MySQL database (shared)
  DB_BACKEND=mysql                    nginx + gunicorn
  MYSQL_HOST=<cloud-ip>
```

Both the camera machine and the cloud server point to the **same MySQL instance**. The camera machine writes logs; the dashboard reads and displays them.

---

## Extending the System

### Replace mock identity lookup with real API
Edit `backend/routes/api.py` → `_mock_identity_lookup()`. Add your vetted API call there.

### Add email/SMS alerts for unknown faces
Hook into `_camera_loop()` after `log_entry()` — send notification when `is_known=False`.

### Switch to CNN model for better accuracy (GPU)
In `detection.py` constructor: `FaceDetector(model="cnn")`. Requires CUDA + dlib built with CUDA support.

### Add door lock GPIO control (Raspberry Pi)
In `recognition.py → _update_session()`, trigger GPIO output when a known face is confirmed.

### REST API usage examples

```bash
# Get live stats
curl http://localhost:5050/api/stats

# Get recent logs
curl http://localhost:5050/api/logs?limit=20

# Search by name
curl "http://localhost:5050/api/logs?name=Alice"

# Search by date
curl "http://localhost:5050/api/logs?date=2024-01-15"

# Get currently inside
curl http://localhost:5050/api/logs/inside

# Start camera
curl -X POST http://localhost:5050/api/camera/start

# Rebuild encodings
curl -X POST http://localhost:5050/api/encodings/rebuild
```
