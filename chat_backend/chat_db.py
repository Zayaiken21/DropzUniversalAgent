import sqlite3
from pathlib import Path
from frontend.config import BASE_DIR

CHAT_DB_DIR = BASE_DIR / "chat_backend"
CHAT_DB_PATH = CHAT_DB_DIR / "chat.db"

def get_chat_connection():
    CHAT_DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_chat_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS chat_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        in_chat INTEGER DEFAULT 0,
        muted INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT DEFAULT 'main',
        user_name TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT,
        media_path TEXT,
        media_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    migrate_schema()

def migrate_schema():
    conn = get_chat_connection()
    c = conn.cursor()

    c.execute("PRAGMA table_info(chat_users)")
    user_cols = {r["name"] for r in c.fetchall()}
    user_alters = [
        ("in_chat", "ALTER TABLE chat_users ADD COLUMN in_chat INTEGER DEFAULT 0"),
        ("muted", "ALTER TABLE chat_users ADD COLUMN muted INTEGER DEFAULT 0"),
        ("status", "ALTER TABLE chat_users ADD COLUMN status TEXT DEFAULT 'active'"),
        ("last_seen", "ALTER TABLE chat_users ADD COLUMN last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col, ddl in user_alters:
        if col not in user_cols:
            c.execute(ddl)

    c.execute("PRAGMA table_info(chat_messages)")
    msg_cols = {r["name"] for r in c.fetchall()}
    msg_alters = [
        ("room_id", "ALTER TABLE chat_messages ADD COLUMN room_id TEXT DEFAULT 'main'"),
        ("media_path", "ALTER TABLE chat_messages ADD COLUMN media_path TEXT"),
        ("media_type", "ALTER TABLE chat_messages ADD COLUMN media_type TEXT"),
        ("created_at", "ALTER TABLE chat_messages ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col, ddl in msg_alters:
        if col not in msg_cols:
            c.execute(ddl)

    conn.commit()
    conn.close()

def upsert_user(name, role="client"):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM chat_users WHERE name = ?", (name,))
    row = c.fetchone()
    if row:
        c.execute(
            "UPDATE chat_users SET role = ?, active = 1, in_chat = 1, status = 'active', last_seen = CURRENT_TIMESTAMP WHERE name = ?",
            (role, name),
        )
    else:
        c.execute(
            "INSERT INTO chat_users (name, role, active, in_chat, status) VALUES (?, ?, 1, 1, 'active')",
            (name, role),
        )
    conn.commit()
    conn.close()

def set_user_presence(name, in_chat=1, status="active"):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE chat_users SET in_chat = ?, status = ?, last_seen = CURRENT_TIMESTAMP WHERE name = ?",
        (in_chat, status, name),
    )
    conn.commit()
    conn.close()

def set_user_muted(name, muted=0):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute("UPDATE chat_users SET muted = ? WHERE name = ?", (muted, name))
    conn.commit()
    conn.close()

def cleanup_inactive(minutes=2):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute(
        """
        UPDATE chat_users
        SET active = 0, in_chat = 0, status = 'idle'
        WHERE last_seen < datetime('now', ?)
        """,
        (f"-{minutes} minutes",),
    )
    conn.commit()
    conn.close()

def add_message(user_name, role, message=None, media_path=None, media_type=None, room_id="main"):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    message = message if message is not None else ""
    c.execute(
        """
        INSERT INTO chat_messages (room_id, user_name, role, message, media_path, media_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (room_id, user_name, role, message, media_path, media_type),
    )
    conn.commit()
    conn.close()

def get_messages(room_id="main", limit=300):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM chat_messages
        WHERE room_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (room_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_users():
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT name, role, active, in_chat, muted, status, last_seen
        FROM chat_users
        WHERE active = 1
        ORDER BY CASE status WHEN 'speaking' THEN 0 WHEN 'active' THEN 1 WHEN 'idle' THEN 2 ELSE 3 END, last_seen DESC
        """
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_online_count():
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chat_users WHERE active = 1")
    count = c.fetchone()[0]
    conn.close()
    return count

def prune_messages(keep=1000):
    migrate_schema()
    conn = get_chat_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chat_messages")
    total = c.fetchone()[0]
    if total > keep:
        cutoff = total - keep
        c.execute(
            "DELETE FROM chat_messages WHERE id IN (SELECT id FROM chat_messages ORDER BY id ASC LIMIT ?)",
            (cutoff,),
        )
    conn.commit()
    conn.close()

init_db()