import sqlite3
import os
import hashlib
import random
import string
from pathlib import Path
from typing import Any, Dict, List, Optional

from frontend.config import (
    DATABASE_URL,
    BASE_DIR,
    SUPABASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
)

DB_PATH = BASE_DIR / "dropz.db"
SUPABASE_TABLE = "client_licenses"
TOKEN_LENGTH = 15


# ============================================================
# SQLite fallback
# ============================================================

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


# ============================================================
# Shared helpers
# ============================================================

def _secret_or_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()

    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        if value not in (None, ""):
            return str(value).strip()
    except Exception:
        pass

    return default


def _get_ceo_secret():
    secret = _secret_or_env("CEO_SECRET_PHRASE", "")
    return (secret or "").strip()


def _supabase_available() -> bool:
    return bool(SUPABASE_URL and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY))


def _supabase_headers(admin: bool = False) -> Dict[str, str]:
    # Public distributed builds should normally use anon + RLS policies.
    # Private CEO builds may use service role if you intentionally put it in .env.
    key = SUPABASE_SERVICE_ROLE_KEY if admin and SUPABASE_SERVICE_ROLE_KEY else SUPABASE_ANON_KEY
    key = key or SUPABASE_SERVICE_ROLE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_rest_url(path: str) -> str:
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1/{path.lstrip('/')}"


def _supabase_request(method: str, path: str, *, admin: bool = False, **kwargs):
    import requests

    if not _supabase_available():
        raise RuntimeError("Supabase is not configured. SUPABASE_URL/SUPABASE_ANON_KEY missing.")

    headers = kwargs.pop("headers", {})
    merged = _supabase_headers(admin=admin)
    merged.update(headers)

    response = requests.request(
        method,
        _supabase_rest_url(path),
        headers=merged,
        timeout=15,
        **kwargs,
    )
    return response


def _report_supabase_error(action: str, response=None, exc: Exception | None = None) -> None:
    message = f"Supabase {action} failed."
    if response is not None:
        message += f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')}"
    if exc is not None:
        message += f" Error: {exc}"

    # Keep app from crashing, but make the issue visible in logs/UI.
    print(message)
    try:
        import streamlit as st
        st.error(message)
    except Exception:
        pass


def _token_row(token: str, name: str = "Client", active: bool = True, created_at: str = "") -> Dict[str, Any]:
    return {
        "id": token,
        "name": name or "Client",
        "role": "client",
        "token": token,
        "active": 1 if active else 0,
        "created_at": created_at or "",
    }


def _sqlite_row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return None


def _normalize_token(token: Any) -> str:
    return str(token or "").strip().upper()


def _generate_token() -> str:
    # Original Dropz-style token: exactly 15 random uppercase letters/numbers.
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(TOKEN_LENGTH))


def _unique_token(existing_check) -> str:
    for _ in range(50):
        token = _generate_token()
        if not existing_check(token):
            return token
    return _generate_token()


# ============================================================
# CEO login stays local and unchanged
# ============================================================

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


def validate_ceo_password(password):
    conn = get_connection()
    c = conn.cursor()
    password_hash = hashlib.sha256(str(password or "").strip().encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE role = 'ceo' AND password_hash = ?", (password_hash,))
    user = c.fetchone()
    conn.close()
    return user


# ============================================================
# Client token functions — Supabase first, SQLite fallback
# ============================================================

def _supabase_token_exists(token: str) -> bool:
    try:
        response = _supabase_request(
            "GET",
            f"{SUPABASE_TABLE}?token=eq.{token}&select=token",
            admin=True,
        )
        return response.status_code == 200 and bool(response.json())
    except Exception:
        return False


def generate_client_token(name, num_tokens=1):
    name = str(name or "Client").strip() or "Client"
    amount = int(num_tokens or 1)
    tokens: List[str] = []

    if _supabase_available():
        try:
            payload = []
            for _ in range(amount):
                token = _unique_token(_supabase_token_exists)
                payload.append({"name": name, "token": token, "active": True})
                tokens.append(token)

            response = _supabase_request(
                "POST",
                SUPABASE_TABLE,
                admin=True,
                json=payload,
            )

            if response.status_code in (200, 201):
                return tokens

            _report_supabase_error("insert token", response=response)
            return []
        except Exception as exc:
            _report_supabase_error("insert token", exc=exc)
            return []

    # Local fallback only when Supabase is not configured.
    conn = get_connection()
    c = conn.cursor()

    def local_exists(t: str) -> bool:
        c.execute("SELECT 1 FROM users WHERE token = ?", (t,))
        return c.fetchone() is not None

    for _ in range(amount):
        token = _unique_token(local_exists)
        c.execute(
            "INSERT INTO users (name, role, token, active) VALUES (?, ?, ?, ?)",
            (name, "client", token, 1)
        )
        tokens.append(token)

    conn.commit()
    conn.close()
    return tokens


def validate_token(token):
    token = _normalize_token(token)
    if not token:
        return None

    if _supabase_available():
        try:
            path = f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true&select=name,token,active,created_at"
            response = _supabase_request("GET", path, admin=False)

            if response.status_code == 200:
                rows = response.json()
                if rows:
                    row = rows[0]
                    return _token_row(
                        token=row.get("token", token),
                        name=row.get("name") or "Client",
                        active=bool(row.get("active", True)),
                        created_at=str(row.get("created_at") or ""),
                    )
                return None

            _report_supabase_error("validate token", response=response)
            return None
        except Exception as exc:
            _report_supabase_error("validate token", exc=exc)
            return None

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE token = ? AND active = 1", (token,))
    user = c.fetchone()
    conn.close()
    return _sqlite_row_to_dict(user)


def cancel_token(token):
    token = _normalize_token(token)
    if not token:
        return False

    if _supabase_available():
        try:
            response = _supabase_request(
                "PATCH",
                f"{SUPABASE_TABLE}?token=eq.{token}",
                admin=True,
                json={"active": False},
            )
            if response.status_code in (200, 204):
                return True
            _report_supabase_error("cancel token", response=response)
            return False
        except Exception as exc:
            _report_supabase_error("cancel token", exc=exc)
            return False

    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET active = 0 WHERE token = ?", (token,))
    conn.commit()
    changed = c.rowcount > 0
    conn.close()
    return changed


def delete_user_by_token(token):
    token = _normalize_token(token)
    if not token:
        return False

    if _supabase_available():
        try:
            response = _supabase_request(
                "DELETE",
                f"{SUPABASE_TABLE}?token=eq.{token}",
                admin=True,
                headers={"Prefer": "return=minimal"},
            )
            if response.status_code in (200, 202, 204):
                return True
            _report_supabase_error("delete token", response=response)
            return False
        except Exception as exc:
            _report_supabase_error("delete token", exc=exc)
            return False

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE token = ?", (token,))
    conn.commit()
    changed = c.rowcount > 0
    conn.close()
    return changed


def cancel_all_client_tokens():
    if _supabase_available():
        try:
            # Keeps old cancel-all behavior as deactivate.
            response = _supabase_request(
                "PATCH",
                f"{SUPABASE_TABLE}?active=eq.true",
                admin=True,
                json={"active": False},
            )
            if response.status_code in (200, 204):
                return True
            _report_supabase_error("cancel all tokens", response=response)
            return False
        except Exception as exc:
            _report_supabase_error("cancel all tokens", exc=exc)
            return False

    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET active = 0 WHERE role = 'client'")
    conn.commit()
    conn.close()
    return True


def get_all_client_tokens():
    if _supabase_available():
        try:
            response = _supabase_request(
                "GET",
                f"{SUPABASE_TABLE}?select=name,token,active,created_at&order=created_at.desc",
                admin=False,
            )
            if response.status_code == 200:
                rows = response.json()
                return [
                    _token_row(
                        token=row.get("token"),
                        name=row.get("name") or "Client",
                        active=bool(row.get("active", False)),
                        created_at=str(row.get("created_at") or ""),
                    )
                    for row in rows
                    if row.get("token")
                ]
            _report_supabase_error("list tokens", response=response)
            return []
        except Exception as exc:
            _report_supabase_error("list tokens", exc=exc)
            return []

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role = 'client' ORDER BY created_at DESC")
    users = [_sqlite_row_to_dict(row) for row in c.fetchall()]
    conn.close()
    return [u for u in users if u]


def get_active_token_count():
    if _supabase_available():
        try:
            response = _supabase_request(
                "GET",
                f"{SUPABASE_TABLE}?active=eq.true&select=token",
                admin=True,
                headers={"Prefer": "count=exact"},
            )
            if response.status_code == 200:
                content_range = response.headers.get("content-range", "")
                if "/" in content_range:
                    return int(content_range.rsplit("/", 1)[-1])
                return len(response.json())
            _report_supabase_error("active token count", response=response)
            return 0
        except Exception as exc:
            _report_supabase_error("active token count", exc=exc)
            return 0

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
