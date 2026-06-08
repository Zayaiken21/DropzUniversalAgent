import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from .chat_time import iso_utc_now, utc_now
from .chat_utils import DB_PATH, ensure_dirs


def _conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=8000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


@contextmanager
def get_db():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'client',
            muted INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT UNIQUE NOT NULL,
            token TEXT NOT NULL,
            token_type TEXT DEFAULT 'client',
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL DEFAULT 'main',
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'client',
            message TEXT,
            media_path TEXT,
            media_type TEXT,
            created_at TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS presence (
            user_name TEXT PRIMARY KEY,
            role TEXT DEFAULT 'client',
            status TEXT DEFAULT 'active',
            muted INTEGER DEFAULT 0,
            last_seen TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_room_id_id ON messages(room_id, id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_presence_last_seen ON presence(last_seen)")


def upsert_user(user_name, role="client"):
    now = iso_utc_now()
    with get_db() as db:
        db.execute("""
        INSERT INTO users(user_name, role, muted, active, created_at, updated_at)
        VALUES(?, ?, 0, 1, ?, ?)
        ON CONFLICT(user_name) DO UPDATE SET
            role=excluded.role,
            active=1,
            updated_at=excluded.updated_at
        """, (user_name, role, now, now))
        db.execute("""
        INSERT INTO presence(user_name, role, status, muted, last_seen)
        VALUES(?, ?, 'active', COALESCE((SELECT muted FROM users WHERE user_name=?), 0), ?)
        ON CONFLICT(user_name) DO UPDATE SET
            role=excluded.role,
            status='active',
            last_seen=excluded.last_seen
        """, (user_name, role, user_name, now))


def set_user_presence(user_name, role="client", status="active", muted=None):
    now = iso_utc_now()
    with get_db() as db:
        if muted is None:
            row = db.execute("SELECT muted FROM users WHERE user_name=?", (user_name,)).fetchone()
            muted = int(row["muted"]) if row else 0
        db.execute("""
        INSERT INTO presence(user_name, role, status, muted, last_seen)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(user_name) DO UPDATE SET
            role=excluded.role,
            status=excluded.status,
            muted=excluded.muted,
            last_seen=excluded.last_seen
        """, (user_name, role, status, int(muted), now))


def set_user_muted(user_name, muted):
    now = iso_utc_now()
    with get_db() as db:
        db.execute("UPDATE users SET muted=?, updated_at=? WHERE user_name=?", (int(muted), now, user_name))
        db.execute("UPDATE presence SET muted=?, last_seen=? WHERE user_name=?", (int(muted), now, user_name))


def add_message(user_name, role, message, media_path=None, media_type=None, room_id="main"):
    now = iso_utc_now()
    with get_db() as db:
        cur = db.execute("""
        INSERT INTO messages(room_id, user_name, role, message, media_path, media_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (room_id, user_name, role, message, media_path, media_type, now))
        return cur.lastrowid


def get_messages(room_id="main", limit=120):
    with get_db() as db:
        rows = db.execute("""
        SELECT * FROM messages
        WHERE room_id=?
        ORDER BY id DESC
        LIMIT ?
        """, (room_id, int(limit))).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_latest_message_id(room_id="main"):
    with get_db() as db:
        row = db.execute("SELECT MAX(id) AS max_id FROM messages WHERE room_id=?", (room_id,)).fetchone()
        return int(row["max_id"] or 0)


def prune_messages(keep=2500):
    with get_db() as db:
        db.execute("""
        DELETE FROM messages
        WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?)
        """, (int(keep),))


def cleanup_inactive(seconds=30):
    cutoff = (utc_now() - timedelta(seconds=seconds)).isoformat()
    with get_db() as db:
        db.execute("UPDATE presence SET status='offline' WHERE last_seen < ?", (cutoff,))


def get_active_users(limit=30):
    with get_db() as db:
        rows = db.execute("""
        SELECT user_name AS name, role, status, muted, last_seen
        FROM presence
        WHERE status != 'offline'
        ORDER BY last_seen DESC
        LIMIT ?
        """, (int(limit),)).fetchall()
        return [dict(r) for r in rows]


def get_online_count():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS c FROM presence WHERE status != 'offline'").fetchone()
        return int(row["c"] if row else 0)


def ensure_user_token(user_name, token, token_type="client"):
    now = iso_utc_now()
    with get_db() as db:
        db.execute("""
        INSERT INTO user_tokens(user_name, token, token_type, active, created_at, updated_at)
        VALUES(?, ?, ?, 1, ?, ?)
        ON CONFLICT(user_name) DO UPDATE SET
            token=excluded.token,
            token_type=excluded.token_type,
            active=1,
            updated_at=excluded.updated_at
        """, (user_name, token, token_type, now, now))


def validate_user_token(user_name, token):
    with get_db() as db:
        row = db.execute("SELECT token, active FROM user_tokens WHERE user_name=? LIMIT 1", (user_name,)).fetchone()
        return bool(row and row["active"] == 1 and row["token"] == token)
