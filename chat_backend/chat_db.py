import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = Path("dropz.db")

def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT UNIQUE NOT NULL,
            token TEXT NOT NULL,
            token_type TEXT DEFAULT 'client',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'client',
            message TEXT,
            media_path TEXT,
            media_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS presence (
            user_name TEXT PRIMARY KEY,
            role TEXT DEFAULT 'client',
            status TEXT DEFAULT 'active',
            muted INTEGER DEFAULT 0,
            in_call INTEGER DEFAULT 0,
            speaking INTEGER DEFAULT 0,
            screen_sharing INTEGER DEFAULT 0,
            last_seen TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

def upsert_user(user_name, role):
    with get_db() as db:
        db.execute("""
        INSERT INTO users(user_name, role, updated_at)
        VALUES(?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_name) DO UPDATE SET
            role=excluded.role,
            updated_at=CURRENT_TIMESTAMP
        """, (user_name, role))
        db.execute("""
        INSERT INTO presence(user_name, role, status, last_seen)
        VALUES(?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(user_name) DO UPDATE SET
            role=excluded.role,
            status='active',
            last_seen=CURRENT_TIMESTAMP
        """, (user_name, role))

def set_user_presence(user_name, active=1, status="active", muted=0, in_call=0, speaking=0, screen_sharing=0):
    with get_db() as db:
        db.execute("""
        INSERT INTO presence(user_name, status, muted, in_call, speaking, screen_sharing, last_seen)
        VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_name) DO UPDATE SET
            status=excluded.status,
            muted=excluded.muted,
            in_call=excluded.in_call,
            speaking=excluded.speaking,
            screen_sharing=excluded.screen_sharing,
            last_seen=CURRENT_TIMESTAMP
        """, (user_name, status, muted, in_call, speaking, screen_sharing))

def mark_user_offline(user_name):
    with get_db() as db:
        db.execute("UPDATE presence SET status='offline', last_seen=CURRENT_TIMESTAMP WHERE user_name=?", (user_name,))

def set_user_muted(user_name, muted):
    with get_db() as db:
        db.execute("UPDATE users SET muted=?, updated_at=CURRENT_TIMESTAMP WHERE user_name=?", (muted, user_name))
        db.execute("UPDATE presence SET muted=?, last_seen=CURRENT_TIMESTAMP WHERE user_name=?", (muted, user_name))

def add_message(user_name, role, message, media_path=None, media_type=None, room_id="main"):
    with get_db() as db:
        db.execute("""
        INSERT INTO messages(room_id, user_name, role, message, media_path, media_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (room_id, user_name, role, message, media_path, media_type))

def get_messages(room_id="main", limit=300):
    with get_db() as db:
        rows = db.execute("""
        SELECT * FROM messages
        WHERE room_id=?
        ORDER BY id DESC
        LIMIT ?
        """, (room_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

def prune_messages(keep=2000):
    with get_db() as db:
        db.execute("""
        DELETE FROM messages
        WHERE id NOT IN (
            SELECT id FROM messages ORDER BY id DESC LIMIT ?
        )
        """, (keep,))

def cleanup_inactive(minutes=1):
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("UPDATE presence SET status='offline' WHERE last_seen < ?", (cutoff,))

def get_active_users():
    with get_db() as db:
        rows = db.execute("""
        SELECT user_name as name, role, status, muted, in_call, speaking, screen_sharing, last_seen
        FROM presence
        WHERE status != 'offline'
        ORDER BY last_seen DESC
        """).fetchall()
        return [dict(r) for r in rows]

def get_online_count():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS c FROM presence WHERE status != 'offline'").fetchone()
        return row["c"] if row else 0