import sqlite3
import os
import hashlib
import secrets
from datetime import datetime
from pathlib import Path

from frontend.config import DATABASE_URL, BASE_DIR

DB_PATH = BASE_DIR / "dropz.db"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        token TEXT UNIQUE,
        password_hash TEXT,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

def _get_ceo_secret():
    secret = os.getenv("CEO_SECRET_PHRASE")
    if not secret:
        try:
            import streamlit as st
            secret = st.secrets.get("CEO_SECRET_PHRASE", "")
        except Exception:
            secret = ""
    return (secret or "").strip()

def create_ceo_user():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role = 'ceo'")
    if c.fetchone() is None:
        from frontend.config import CEO_SECRET_PHRASE
        secret = _get_ceo_secret() or (CEO_SECRET_PHRASE or "").strip()
        if not secret:
            conn.close()
            return
        password_hash = hashlib.sha256(secret.encode()).hexdigest()
        c.execute(
            "INSERT INTO users (name, role, password_hash, active) VALUES (?, ?, ?, ?)",
            ("CEO", "ceo", password_hash, 1)
        )
        conn.commit()
    conn.close()

def generate_client_token(name, num_tokens=1):
    conn = get_connection()
    c = conn.cursor()
    tokens = []
    for _ in range(num_tokens):
        token = secrets.token_urlsafe(11)[:15]
        c.execute(
            "INSERT INTO users (name, role, token, active) VALUES (?, ?, ?, ?)",
            (name, "client", token, 1)
        )
        tokens.append(token)
    conn.commit()
    conn.close()
    return tokens

def validate_ceo_password(password):
    conn = get_connection()
    c = conn.cursor()
    password_hash = hashlib.sha256(password.strip().encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE role = 'ceo' AND password_hash = ?", (password_hash,))
    user = c.fetchone()
    conn.close()
    return user

def validate_token(token):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE token = ? AND active = 1", (token.strip(),))
    user = c.fetchone()
    conn.close()
    return user

def cancel_token(token):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET active = 0 WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def delete_user_by_token(token):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def cancel_all_client_tokens():
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET active = 0 WHERE role = 'client'")
    conn.commit()
    conn.close()

def get_all_client_tokens():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role = 'client' ORDER BY created_at DESC")
    users = c.fetchall()
    conn.close()
    return users

def get_active_token_count():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'client' AND active = 1")
    count = c.fetchone()[0]
    conn.close()
    return count

init_db()
create_ceo_user()

def frontend_database():
    return None