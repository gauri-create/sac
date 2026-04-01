"""
backend/database.py
Database abstraction supporting SQLite (local) and MySQL (production).
Handles schema creation, CRUD operations for users and access logs.
"""

import os
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_BACKEND   = os.getenv("DB_BACKEND", "sqlite")
SQLITE_PATH  = os.getenv("SQLITE_PATH", "data/access_logs.db")

MYSQL_HOST   = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT   = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER   = os.getenv("MYSQL_USER", "root")
MYSQL_PASS   = os.getenv("MYSQL_PASS", "")
MYSQL_DB     = os.getenv("MYSQL_DB", "secure_entry")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    encoding_path TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    is_known      INTEGER NOT NULL DEFAULT 0,
    entry_time    DATETIME,
    exit_time     DATETIME,
    duration_sec  REAL,
    status        TEXT    NOT NULL DEFAULT 'INSIDE',
    image_path    TEXT,
    suggested_id  TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_logs_name        ON access_logs(name);
CREATE INDEX IF NOT EXISTS idx_logs_entry_time  ON access_logs(entry_time);
CREATE INDEX IF NOT EXISTS idx_logs_status      ON access_logs(status);
"""


class Database:
    """
    Thread-safe database wrapper.
    Uses check_same_thread=False for SQLite; connection pooling for MySQL.
    """

    def __init__(self, db_path: str = SQLITE_PATH):
        self._backend = DB_BACKEND
        self._db_path = db_path
        self._connection = None
        self._init_connection()
        self._create_schema()

    def _init_connection(self):
        if self._backend == "sqlite":
            import sqlite3
            # Use the db_path passed in (absolute path from app factory)
            db_file = self._db_path
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                db_file,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL;")
            logger.info("SQLite connected: %s", db_file)

        elif self._backend == "mysql":
            try:
                import mysql.connector
                self._connection = mysql.connector.connect(
                    host=MYSQL_HOST,
                    port=MYSQL_PORT,
                    user=MYSQL_USER,
                    password=MYSQL_PASS,
                    database=MYSQL_DB,
                    autocommit=False,
                )
                logger.info("MySQL connected: %s@%s/%s", MYSQL_USER, MYSQL_HOST, MYSQL_DB)
            except ImportError:
                raise RuntimeError(
                    "mysql-connector-python not installed. "
                    "Run: pip install mysql-connector-python"
                )
        else:
            raise ValueError(f"Unknown DB_BACKEND: {self._backend}")

    @contextmanager
    def _cursor(self):
        """Yield a cursor and auto-commit/rollback."""
        cur = self._connection.cursor()
        try:
            yield cur
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()

    def _create_schema(self):
        """Create tables if they don't exist."""
        with self._cursor() as cur:
            if self._backend == "mysql":
                mysql_schema = SCHEMA_SQL.replace(
                    "INTEGER PRIMARY KEY AUTOINCREMENT",
                    "INT AUTO_INCREMENT PRIMARY KEY",
                ).replace("REAL", "FLOAT")
                for stmt in mysql_schema.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cur.execute(stmt)
            else:
                cur.executescript(SCHEMA_SQL)
        logger.info("Schema initialized.")

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def upsert_user(self, name: str, encoding_path: str = "") -> int:
        sql = """
            INSERT INTO users (name, encoding_path)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET encoding_path=excluded.encoding_path
        """
        if self._backend == "mysql":
            sql = """
                INSERT INTO users (name, encoding_path) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE encoding_path=VALUES(encoding_path)
            """
        with self._cursor() as cur:
            cur.execute(sql, (name, encoding_path))
            return cur.lastrowid

    def get_all_users(self) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM users ORDER BY name")
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Access Logs — Write
    # ------------------------------------------------------------------

    def log_entry(
        self,
        session_id: str,
        name: str,
        is_known: bool,
        entry_time: datetime,
        image_path: Optional[str] = None,
    ) -> int:
        ph = "?" if self._backend == "sqlite" else "%s"
        sql = f"""
            INSERT INTO access_logs
                (session_id, name, is_known, entry_time, status, image_path)
            VALUES ({ph},{ph},{ph},{ph},'INSIDE',{ph})
        """
        with self._cursor() as cur:
            cur.execute(
                sql,
                (
                    session_id,
                    name,
                    int(is_known),
                    entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                    image_path,
                ),
            )
            return cur.lastrowid

    def log_exit(
        self,
        session_id: str,
        exit_time: datetime,
        duration_sec: float,
    ):
        ph = "?" if self._backend == "sqlite" else "%s"
        sql = f"""
            UPDATE access_logs
            SET exit_time={ph}, duration_sec={ph}, status='OUTSIDE'
            WHERE session_id={ph} AND status='INSIDE'
        """
        with self._cursor() as cur:
            cur.execute(
                sql,
                (
                    exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                    round(duration_sec, 1),
                    session_id,
                ),
            )

    def update_suggested_id(self, session_id: str, suggested: str):
        ph = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE access_logs SET suggested_id={ph} WHERE session_id={ph}",
                (suggested, session_id),
            )

    # ------------------------------------------------------------------
    # Access Logs — Read
    # ------------------------------------------------------------------

    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM access_logs ORDER BY entry_time DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_logs_by_name(self, name: str) -> List[Dict]:
        ph = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"SELECT * FROM access_logs WHERE name LIKE {ph} ORDER BY entry_time DESC",
                (f"%{name}%",),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_logs_by_date(self, date_str: str) -> List[Dict]:
        ph = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"SELECT * FROM access_logs WHERE DATE(entry_time)={ph} ORDER BY entry_time DESC",
                (date_str,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_currently_inside(self) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM access_logs WHERE status='INSIDE' ORDER BY entry_time DESC"
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_unknown_faces(self, limit: int = 30) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM access_logs
                WHERE is_known=0
                ORDER BY entry_time DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM access_logs")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE status='INSIDE'")
            inside = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE is_known=0")
            unknown = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT name) FROM access_logs WHERE is_known=1")
            known_people = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM access_logs WHERE DATE(entry_time)=DATE('now')"
            )
            today = cur.fetchone()[0]
        return {
            "total_events": total,
            "currently_inside": inside,
            "unknown_faces": unknown,
            "known_people": known_people,
            "today_events": today,
        }

    def search_logs(
        self,
        name: Optional[str] = None,
        date: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        conditions = []
        params = []
        ph = "?" if self._backend == "sqlite" else "%s"

        if name:
            conditions.append(f"name LIKE {ph}")
            params.append(f"%{name}%")
        if date:
            conditions.append(f"DATE(entry_time)={ph}")
            params.append(date)
        if status:
            conditions.append(f"status={ph}")
            params.append(status.upper())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        sql = f"""
            SELECT * FROM access_logs
            {where}
            ORDER BY entry_time DESC
            LIMIT {ph}
        """
        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
