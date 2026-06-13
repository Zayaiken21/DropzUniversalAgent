import sqlite3
import hashlib
import random
import string
from typing import Any, Dict, List, Optional

from frontend.config import (
    BASE_DIR,
    SUPABASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
    supabase_config_status,
)

DB_PATH = BASE_DIR / "dropz.db"
SUPABASE_TABLE = "client_licenses"
TOKEN_LENGTH = 15


# ============================================================
# SQLite local system kept for CEO login only
# Client token source of truth is Supabase.
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
# Helpers
# ============================================================

def _get_ceo_secret() -> str:
    from frontend.config import CEO_SECRET_PHRASE
    return str(CEO_SECRET_PHRASE or "").strip()


def _normalize_key(key: str) -> str:
    key = str(key or "").strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key.rstrip(",").strip()


def _supabase_key(admin: bool = False) -> str:
    # Keep your current logic: service role can be added later, but anon-only works now.
    if admin and SUPABASE_SERVICE_ROLE_KEY:
        return _normalize_key(SUPABASE_SERVICE_ROLE_KEY)
    return _normalize_key(SUPABASE_ANON_KEY)


def _supabase_available() -> bool:
    return bool(str(SUPABASE_URL or "").strip() and _supabase_key(False))


def _supabase_headers(admin: bool = False) -> Dict[str, str]:
    key = _supabase_key(admin=admin)
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is missing. Add it to .env locally and Streamlit Secrets online.")

    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_rest_url(path: str) -> str:
    return f"{str(SUPABASE_URL).rstrip('/')}/rest/v1/{path.lstrip('/')}"


def _supabase_request(method: str, path: str, *, admin: bool = False, **kwargs):
    import requests

    if not _supabase_available():
        raise RuntimeError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env or Streamlit Secrets.")

    headers = kwargs.pop("headers", {}) or {}
    merged = _supabase_headers(admin=admin)
    merged.update(headers)

    return requests.request(
        method,
        _supabase_rest_url(path),
        headers=merged,
        timeout=15,
        **kwargs,
    )


def test_supabase_connection() -> tuple[bool, str]:
    """Safe visible connection test for the CEO settings page."""
    try:
        response = _supabase_request(
            "GET",
            f"{SUPABASE_TABLE}?select=token&limit=1",
            admin=False,
        )
        if response.status_code == 200:
            return True, "Supabase connected."
        return False, f"Status {response.status_code}: {response.text}"
    except Exception as exc:
        return False, str(exc)


def get_supabase_debug_status() -> dict:
    status = supabase_config_status()
    ok, msg = test_supabase_connection()
    status["SUPABASE_CONNECTION_OK"] = ok
    status["SUPABASE_CONNECTION_MESSAGE"] = msg
    return status


def _raise_supabase_error(action: str, response=None, exc: Exception | None = None):
    message = f"Supabase {action} failed."
    if response is not None:
        message += f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')}"
    if exc is not None:
        message += f" Error: {exc}"

    raise RuntimeError(message)


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
        secret = _get_ceo_secret()
        if not secret:
            conn.close()
            return
        password_hash = hashlib.sha256(secret.encode()).hexdigest()
        c.execute(
            "INSERT INTO users (name, role, password_hash, active) VALUES (?, ?, ?, ?)",
            ("CEO", "ceo", password_hash, 1),
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
# Client token functions — Supabase source of truth
# Same process locally, packaged, and Streamlit Cloud.
# ============================================================

def _require_supabase():
    if not _supabase_available():
        raise RuntimeError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env or Streamlit Secrets.")


def _supabase_token_exists(token: str) -> bool:
    _require_supabase()
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?token=eq.{token}&select=token&limit=1",
        admin=False,
    )
    if response.status_code == 200:
        return bool(response.json())
    _raise_supabase_error("check token", response=response)


def generate_client_token(name, num_tokens=1):
    _require_supabase()
    name = str(name or "Client").strip() or "Client"
    amount = int(num_tokens or 1)
    tokens: List[str] = []
    payload = []

    for _ in range(amount):
        token = _unique_token(_supabase_token_exists)
        payload.append({"name": name, "token": token, "active": True})
        tokens.append(token)

    response = _supabase_request(
        "POST",
        SUPABASE_TABLE,
        admin=False,
        json=payload,
    )

    if response.status_code in (200, 201):
        return tokens

    _raise_supabase_error("insert token", response=response)


def validate_token(token):
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return None

    path = f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true&select=name,token,active,created_at&limit=1"
    response = _supabase_request("GET", path, admin=False)

    if response.status_code == 200:
        rows = response.json()
        if not rows:
            return None
        row = rows[0]
        return _token_row(
            token=row.get("token", token),
            name=row.get("name") or "Client",
            active=bool(row.get("active", True)),
            created_at=str(row.get("created_at") or ""),
        )

    _raise_supabase_error("validate token", response=response)


def cancel_token(token):
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return False

    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}",
        admin=False,
        json={"active": False},
    )
    if response.status_code in (200, 204):
        return True
    _raise_supabase_error("cancel token", response=response)


def delete_user_by_token(token):
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return False

    # This fully deletes the token row from Supabase. Existing logic preserved.
    response = _supabase_request(
        "DELETE",
        f"{SUPABASE_TABLE}?token=eq.{token}",
        admin=False,
        headers={"Prefer": "return=minimal"},
    )
    if response.status_code in (200, 202, 204):
        return True
    _raise_supabase_error("delete token", response=response)


def cancel_all_client_tokens():
    _require_supabase()
    # Keeps existing cancel-all behavior: deactivate all active tokens.
    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?active=eq.true",
        admin=False,
        json={"active": False},
    )
    if response.status_code in (200, 204):
        return True
    _raise_supabase_error("cancel all tokens", response=response)


def get_all_client_tokens():
    _require_supabase()
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
    _raise_supabase_error("list tokens", response=response)


def get_active_token_count():
    _require_supabase()
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?active=eq.true&select=token",
        admin=False,
        headers={"Prefer": "count=exact"},
    )
    if response.status_code == 200:
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            return int(content_range.rsplit("/", 1)[-1])
        return len(response.json())
    _raise_supabase_error("active token count", response=response)


init_db()
create_ceo_user()


def frontend_database():
    return None
