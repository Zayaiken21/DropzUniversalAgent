"""
database.py — Dropz Universal Agent
=====================================
Source of truth layout:
  • CEO login        → local SQLite only (no Supabase)
  • Client licenses  → Supabase public.client_licenses

Supabase table (run this SQL once in the Supabase SQL editor):
────────────────────────────────────────────────────────────────
create table if not exists public.client_licenses (
    name             text not null,
    token            text primary key,
    active           boolean not null default true,
    created_at       timestamptz not null default now(),
    -- Profile columns added via migration (run once):
    username         text,
    password_hash    text,
    password_set     boolean not null default false,
    password_updated_at  timestamptz,
    username_updated_at  timestamptz
);
create index if not exists idx_client_licenses_active
    on public.client_licenses(active);
create index if not exists idx_client_licenses_created_at
    on public.client_licenses(created_at desc);
alter table public.client_licenses enable row level security;

-- RLS policies (anon key is used by the desktop/web app)
drop policy if exists "dropz_client_licenses_select" on public.client_licenses;
drop policy if exists "dropz_client_licenses_insert" on public.client_licenses;
drop policy if exists "dropz_client_licenses_update" on public.client_licenses;
drop policy if exists "dropz_client_licenses_delete" on public.client_licenses;

create policy "dropz_client_licenses_select"
    on public.client_licenses for select using (true);
create policy "dropz_client_licenses_insert"
    on public.client_licenses for insert with check (true);
create policy "dropz_client_licenses_update"
    on public.client_licenses for update using (true) with check (true);
create policy "dropz_client_licenses_delete"
    on public.client_licenses for delete using (true);
────────────────────────────────────────────────────────────────

Works identically on:
  • Local dev (PyCharm + .env)
  • Streamlit Cloud  (st.secrets)
  • PyInstaller .exe build
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import re
import sqlite3
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from frontend.config import (
    BASE_DIR,
    SUPABASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
)

# ── constants ──────────────────────────────────────────────────────────────────

DB_PATH              = BASE_DIR / "dropz.db"
SUPABASE_TABLE       = "client_licenses"
TOKEN_LENGTH         = 15
PASSWORD_MIN_LENGTH  = 6
USERNAME_MIN_LENGTH  = 3
USERNAME_MAX_LENGTH  = 32
PBKDF2_ITERATIONS    = 260_000

# Columns that exist only after the profile migration has been applied
_PROFILE_COLS = frozenset({
    "username", "password_hash", "password_set",
    "password_updated_at", "username_updated_at",
})

# Full select string including profile columns
_FULL_SELECT = (
    "name,token,active,created_at,"
    "username,password_set,password_updated_at,username_updated_at"
)
_FULL_SELECT_WITH_HASH = _FULL_SELECT + ",password_hash"
# Legacy select for tables that haven't had the migration applied
_LEGACY_SELECT = "name,token,active,created_at"


# ── SQLite (CEO only) ──────────────────────────────────────────────────────────

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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            role          TEXT NOT NULL,
            token         TEXT UNIQUE,
            password_hash TEXT,
            active        INTEGER DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            message   TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


# ── CEO authentication (local SQLite only) ─────────────────────────────────────

def _get_ceo_secret() -> str:
    from frontend.config import CEO_SECRET_PHRASE
    return str(CEO_SECRET_PHRASE or "").strip()


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


def validate_ceo_password(password: str):
    conn = get_connection()
    c = conn.cursor()
    pw_hash = hashlib.sha256(str(password or "").strip().encode()).hexdigest()
    c.execute(
        "SELECT * FROM users WHERE role = 'ceo' AND password_hash = ?",
        (pw_hash,),
    )
    user = c.fetchone()
    conn.close()
    if user is None:
        return None
    row = dict(user)
    row["role"] = "ceo"
    row["name"] = row.get("name") or "CEO"
    return row


# ── Supabase plumbing ──────────────────────────────────────────────────────────

def _normalize_key(key: str) -> str:
    key = str(key or "").strip()
    if (key.startswith('"') and key.endswith('"')) or \
       (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key.rstrip(",").strip()


def _supabase_key(admin: bool = False) -> str:
    if admin and SUPABASE_SERVICE_ROLE_KEY:
        return _normalize_key(str(SUPABASE_SERVICE_ROLE_KEY))
    return _normalize_key(str(SUPABASE_ANON_KEY or ""))


def _supabase_available() -> bool:
    return bool(str(SUPABASE_URL or "").strip() and _supabase_key(False))


def _require_supabase():
    if not _supabase_available():
        raise RuntimeError(
            "Supabase is not configured. "
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to your .env file (local) "
            "or Streamlit Secrets (cloud)."
        )


def _supabase_headers(admin: bool = False) -> Dict[str, str]:
    key = _supabase_key(admin=admin)
    if not key:
        raise RuntimeError(
            "SUPABASE_ANON_KEY is missing. "
            "Add it to .env locally or to Streamlit Secrets online."
        )
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
        "Prefer":        "return=representation",
    }


def _supabase_rest_url(path: str) -> str:
    base = str(SUPABASE_URL or "").rstrip("/")
    return f"{base}/rest/v1/{path.lstrip('/')}"


def _supabase_request(
    method: str,
    path: str,
    *,
    admin: bool = False,
    **kwargs,
):
    import requests  # lazy import keeps startup fast

    if not _supabase_available():
        raise RuntimeError(
            "Supabase is not configured. "
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to .env or Streamlit Secrets."
        )

    extra_headers = kwargs.pop("headers", {}) or {}
    merged = _supabase_headers(admin=admin)
    merged.update(extra_headers)

    return requests.request(
        method,
        _supabase_rest_url(path),
        headers=merged,
        timeout=15,
        **kwargs,
    )


def _raise_supabase_error(
    action: str,
    response=None,
    exc: Exception | None = None,
):
    msg = f"Supabase {action} failed."
    if response is not None:
        msg += (
            f" Status {getattr(response, 'status_code', 'unknown')}: "
            f"{getattr(response, 'text', '')}"
        )
    if exc is not None:
        msg += f" Error: {exc}"
    raise RuntimeError(msg)


def _profile_columns_supported(response_text: str) -> bool:
    """
    Return False if the Supabase error text mentions any profile column
    that indicates the column does not exist yet.
    """
    text = str(response_text or "").lower()
    missing_signals = {
        "username", "password_hash", "password_set",
        "password_updated_at", "username_updated_at",
        "schema cache", "column",
    }
    return not any(sig in text for sig in missing_signals)


# ── Row normalisation ──────────────────────────────────────────────────────────

def _row_from_supabase(row: Dict[str, Any]) -> Dict[str, Any]:
    token = _normalize_token(row.get("token"))
    return {
        "id":                   token,
        "name":                 row.get("name") or "Client",
        "role":                 "client",
        "token":                token,
        # username defaults to token until the user creates their own
        "username":             row.get("username") or token,
        "active":               1 if bool(row.get("active", False)) else 0,
        "created_at":           str(row.get("created_at") or ""),
        "password_set":         1 if bool(row.get("password_set", False)) else 0,
        "password_hash":        str(row.get("password_hash") or ""),
        "password_updated_at":  str(row.get("password_updated_at") or ""),
        "username_updated_at":  str(row.get("username_updated_at") or ""),
    }


def _public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip sensitive fields and normalise for session state."""
    clean = dict(row or {})
    clean.pop("password_hash", None)
    clean["role"]         = "client"
    clean["id"]           = clean.get("token") or clean.get("username") or clean.get("name") or "client"
    clean["name"]         = clean.get("name") or clean.get("username") or "Client"
    clean["username"]     = clean.get("username") or clean.get("token") or ""
    clean["active"]       = 1 if bool(clean.get("active", True)) else 0
    clean["password_set"] = 1 if bool(clean.get("password_set", False)) else 0
    return clean


def _sqlite_row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return None


# ── Token and username helpers ─────────────────────────────────────────────────

def _normalize_token(token: Any) -> str:
    return str(token or "").strip().upper()


def _normalize_username(username: Any) -> str:
    return str(username or "").strip()


def _normalize_identifier(identifier: Any) -> str:
    return str(identifier or "").strip()


def _generate_token() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(TOKEN_LENGTH))


def _unique_token(existing_check) -> str:
    for _ in range(50):
        token = _generate_token()
        if not existing_check(token):
            return token
    return _generate_token()


# ── Password helpers ───────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    password = str(password or "")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    password    = str(password or "")
    stored_hash = str(stored_hash or "")
    if not stored_hash:
        return False
    try:
        method, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if method != "pbkdf2_sha256":
            return False
        actual   = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        expected = bytes.fromhex(digest_hex)
        return hmac.compare_digest(actual, expected)
    except Exception:
        # Legacy SHA-256 fallback (pre-PBKDF2 hashes)
        legacy = hashlib.sha256(password.strip().encode()).hexdigest()
        return hmac.compare_digest(legacy, stored_hash)


def _validate_password_strength(password: str) -> tuple[bool, str]:
    password = str(password or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if password.strip() != password:
        return False, "Password cannot start or end with spaces."
    return True, ""


def _validate_username(username: str) -> tuple[bool, str]:
    username = _normalize_username(username)
    if len(username) < USERNAME_MIN_LENGTH:
        return False, f"Username must be at least {USERNAME_MIN_LENGTH} characters."
    if len(username) > USERNAME_MAX_LENGTH:
        return False, f"Username must be {USERNAME_MAX_LENGTH} characters or less."
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", username):
        return False, "Username can only use letters, numbers, dots, underscores, and hyphens."
    return True, ""


# ── Supabase read helpers ──────────────────────────────────────────────────────

def _select_client_by_token(
    token: str,
    include_password: bool = True,
) -> Optional[Dict[str, Any]]:
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return None

    select = _FULL_SELECT_WITH_HASH if include_password else _FULL_SELECT
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true&select={select}&limit=1",
    )

    if response.status_code == 200:
        rows = response.json()
        return _row_from_supabase(rows[0]) if rows else None

    # Graceful degradation: profile columns not yet migrated
    if response.status_code in (400, 404) and not _profile_columns_supported(response.text):
        fallback = _supabase_request(
            "GET",
            f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true"
            f"&select={_LEGACY_SELECT}&limit=1",
        )
        if fallback.status_code == 200:
            rows = fallback.json()
            return _row_from_supabase(rows[0]) if rows else None
        _raise_supabase_error("select token (legacy)", response=fallback)

    _raise_supabase_error("select token", response=response)


def _select_client_by_username(
    username: str,
    include_password: bool = True,
) -> Optional[Dict[str, Any]]:
    _require_supabase()
    username = _normalize_username(username)
    if not username:
        return None

    select = _FULL_SELECT_WITH_HASH if include_password else _FULL_SELECT
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?username=eq.{username}&active=eq.true&select={select}&limit=1",
    )

    if response.status_code == 200:
        rows = response.json()
        return _row_from_supabase(rows[0]) if rows else None

    if response.status_code in (400, 404) and not _profile_columns_supported(response.text):
        # Profile columns not yet added — username login not possible yet
        return None

    _raise_supabase_error("select username", response=response)


def _select_client_by_identifier(
    identifier: str,
    include_password: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Try token first (covers first-time logins), then username.
    This means a user can always fall back to their original access code.
    """
    identifier = _normalize_identifier(identifier)
    if not identifier:
        return None
    token_user = _select_client_by_token(identifier, include_password=include_password)
    if token_user:
        return token_user
    return _select_client_by_username(identifier, include_password=include_password)


def _supabase_token_exists(token: str) -> bool:
    _require_supabase()
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?token=eq.{token}&select=token&limit=1",
    )
    if response.status_code == 200:
        return bool(response.json())
    _raise_supabase_error("check token exists", response=response)


def _username_exists(username: str, current_token: str = "") -> bool:
    user = _select_client_by_username(username, include_password=False)
    if not user:
        return False
    # Allow the current user to keep their own username
    if current_token and _normalize_token(user.get("token")) == _normalize_token(current_token):
        return False
    return True


# ── Public client-license functions ───────────────────────────────────────────

def generate_client_token(name: str, num_tokens: int = 1) -> list[str] | str:
    """
    Create one or more new client license tokens in Supabase.
    Returns a list of token strings (or a single string when num_tokens=1).
    """
    _require_supabase()
    name   = str(name or "Client").strip() or "Client"
    amount = max(1, int(num_tokens or 1))
    tokens: List[str] = []
    payload = []

    for _ in range(amount):
        token = _unique_token(_supabase_token_exists)
        tokens.append(token)
        payload.append({
            "name":         name,
            "token":        token,
            # username defaults to the token so validate_client_login works
            # immediately on first use without a migration guard
            "username":     token,
            "active":       True,
            "password_set": False,
            "password_hash": None,
        })

    response = _supabase_request("POST", SUPABASE_TABLE, json=payload)

    if response.status_code in (200, 201):
        return tokens[0] if amount == 1 else tokens

    # Graceful legacy insert (table before profile column migration)
    if response.status_code in (400, 404) and not _profile_columns_supported(response.text):
        legacy_payload = [{"name": name, "token": t, "active": True} for t in tokens]
        legacy_resp = _supabase_request("POST", SUPABASE_TABLE, json=legacy_payload)
        if legacy_resp.status_code in (200, 201):
            return tokens[0] if amount == 1 else tokens
        _raise_supabase_error("insert token (legacy)", response=legacy_resp)

    _raise_supabase_error("insert token", response=response)


def validate_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate that a token exists and is active (used by password reset).
    Returns the public user dict or None.
    """
    user = _select_client_by_token(token, include_password=False)
    return _public_user(user) if user else None


def validate_client_login(
    username_or_token: str,
    password: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Client login rules (in order):
      1. Identifier lookup — token or username, both work.
      2. If no password is set yet → first-time login, route to profile setup.
      3. If password is set but none provided → tell UI password is required.
      4. Verify PBKDF2 password → success or None.
    """
    user = _select_client_by_identifier(username_or_token, include_password=True)
    if not user:
        return None

    # First-time login: no password configured
    if not bool(user.get("password_set")) or not user.get("password_hash"):
        user["login_ok"]               = True
        user["requires_profile_setup"] = True
        user["requires_password_setup"] = True
        return _public_user(user)

    # Known user, password not supplied in form
    if password in (None, ""):
        user["login_ok"]          = False
        user["password_required"] = True
        return _public_user(user)

    # Verify password
    if _verify_password(str(password), str(user.get("password_hash") or "")):
        user["login_ok"]               = True
        user["requires_profile_setup"] = False
        return _public_user(user)

    return None


def set_client_profile(
    token: str,
    username: str,
    new_password: str,
) -> Dict[str, Any]:
    """
    First-time activation: sets the username and password for a new client.
    The original token remains the license key (never changes).
    """
    _require_supabase()
    token    = _normalize_token(token)
    username = _normalize_username(username)

    ok, msg = _validate_username(username)
    if not ok:
        raise RuntimeError(msg)

    ok, msg = _validate_password_strength(new_password)
    if not ok:
        raise RuntimeError(msg)

    user = _select_client_by_token(token, include_password=False)
    if not user:
        raise RuntimeError("Invalid or expired access code.")

    if _username_exists(username, current_token=token):
        raise RuntimeError("That username is already taken. Please choose another.")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "username":             username,
        "password_hash":        _hash_password(new_password),
        "password_set":         True,
        "password_updated_at":  now,
        "username_updated_at":  now,
    }

    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true",
        json=payload,
    )

    if response.status_code in (200, 204):
        updated = _select_client_by_token(token, include_password=False)
        return _public_user(
            updated or {**user, "username": username, "password_set": True}
        )

    _raise_supabase_error("set username and password", response=response)



def reset_client_username_with_token(token: str, new_username: str) -> Dict[str, Any]:
    """
    Username reset using the original client access code.
    The password is unchanged. The original token remains the permanent license key.
    """
    _require_supabase()
    token = _normalize_token(token)
    new_username = _normalize_username(new_username)

    ok, msg = _validate_username(new_username)
    if not ok:
        raise RuntimeError(msg)

    user = _select_client_by_token(token, include_password=False)
    if not user:
        raise RuntimeError("Invalid or expired access code.")

    if _username_exists(new_username, current_token=token):
        raise RuntimeError("That username is already taken. Please choose another.")

    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true",
        json={
            "username": new_username,
            "username_updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    if response.status_code in (200, 204):
        updated = _select_client_by_token(token, include_password=False)
        return _public_user(updated or {**user, "username": new_username})

    _raise_supabase_error("reset username", response=response)


def reset_client_profile_with_token(
    token: str,
    new_username: str | None = None,
    new_password: str | None = None,
) -> Dict[str, Any]:
    """
    Reset username and/or password using the original client access code.
    Leave either value blank/None to keep it unchanged.
    """
    _require_supabase()
    token = _normalize_token(token)
    user = _select_client_by_token(token, include_password=False)
    if not user:
        raise RuntimeError("Invalid or expired access code.")

    payload: Dict[str, Any] = {}
    new_username = _normalize_username(new_username)

    if new_username:
        ok, msg = _validate_username(new_username)
        if not ok:
            raise RuntimeError(msg)
        if _username_exists(new_username, current_token=token):
            raise RuntimeError("That username is already taken. Please choose another.")
        payload["username"] = new_username
        payload["username_updated_at"] = datetime.now(timezone.utc).isoformat()

    if new_password not in (None, ""):
        ok, msg = _validate_password_strength(str(new_password))
        if not ok:
            raise RuntimeError(msg)
        payload["password_hash"] = _hash_password(str(new_password))
        payload["password_set"] = True
        payload["password_updated_at"] = datetime.now(timezone.utc).isoformat()

    if not payload:
        raise RuntimeError("Enter a new username, a new password, or both.")

    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true",
        json=payload,
    )

    if response.status_code in (200, 204):
        updated = _select_client_by_token(token, include_password=False)
        return _public_user(updated or {**user, **payload})

    _raise_supabase_error("reset username/password", response=response)


def set_client_password(token: str, new_password: str) -> Dict[str, Any]:
    """Change a client's password only. Username is unchanged."""
    _require_supabase()
    token = _normalize_token(token)

    ok, msg = _validate_password_strength(new_password)
    if not ok:
        raise RuntimeError(msg)

    user = _select_client_by_token(token, include_password=False)
    if not user:
        raise RuntimeError("Invalid or expired access code.")

    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}&active=eq.true",
        json={
            "password_hash":       _hash_password(new_password),
            "password_set":        True,
            "password_updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    if response.status_code in (200, 204):
        updated = _select_client_by_token(token, include_password=False)
        return _public_user(updated or user)

    _raise_supabase_error("set password", response=response)


def reset_client_password_with_token(token: str, new_password: str) -> Dict[str, Any]:
    """
    Password reset using the original client access code.
    Username is preserved; only the password is replaced.
    """
    return set_client_password(token, new_password)


def cancel_token(token: str) -> bool:
    """Mark a single token as inactive (soft delete)."""
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return False
    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?token=eq.{token}",
        json={"active": False},
    )
    if response.status_code in (200, 204):
        return True
    _raise_supabase_error("cancel token", response=response)


def delete_user_by_token(token: str) -> bool:
    """Hard-delete a client license row from Supabase."""
    _require_supabase()
    token = _normalize_token(token)
    if not token:
        return False
    response = _supabase_request(
        "DELETE",
        f"{SUPABASE_TABLE}?token=eq.{token}",
        headers={"Prefer": "return=minimal"},
    )
    if response.status_code in (200, 202, 204):
        return True
    _raise_supabase_error("delete token", response=response)


def cancel_all_client_tokens() -> bool:
    """Mark all active tokens as inactive."""
    _require_supabase()
    response = _supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?active=eq.true",
        json={"active": False},
    )
    if response.status_code in (200, 204):
        return True
    _raise_supabase_error("cancel all tokens", response=response)


def get_all_client_tokens() -> List[Dict[str, Any]]:
    """Return all client license rows for the CEO settings page."""
    _require_supabase()

    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?select={_FULL_SELECT}&order=created_at.desc",
    )

    if response.status_code == 200:
        return [
            _public_user(_row_from_supabase(row))
            for row in response.json()
            if row.get("token")
        ]

    # Legacy: profile columns not yet added
    if response.status_code in (400, 404) and not _profile_columns_supported(response.text):
        legacy_resp = _supabase_request(
            "GET",
            f"{SUPABASE_TABLE}?select={_LEGACY_SELECT}&order=created_at.desc",
        )
        if legacy_resp.status_code == 200:
            return [
                _public_user({
                    "token":        row.get("token"),
                    "username":     row.get("token"),
                    "name":         row.get("name") or "Client",
                    "active":       bool(row.get("active", False)),
                    "created_at":   str(row.get("created_at") or ""),
                    "password_set": False,
                })
                for row in legacy_resp.json()
                if row.get("token")
            ]
        _raise_supabase_error("list tokens (legacy)", response=legacy_resp)

    _raise_supabase_error("list tokens", response=response)


def get_active_token_count() -> int:
    """Return the count of active client licenses."""
    _require_supabase()
    response = _supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?active=eq.true&select=token",
        headers={"Prefer": "count=exact"},
    )
    if response.status_code == 200:
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            return int(content_range.rsplit("/", 1)[-1])
        return len(response.json())
    _raise_supabase_error("active token count", response=response)


# ── Boot-time init ─────────────────────────────────────────────────────────────

init_db()
create_ceo_user()


def frontend_database():
    """Shim for any import that expects this symbol."""
    return None
