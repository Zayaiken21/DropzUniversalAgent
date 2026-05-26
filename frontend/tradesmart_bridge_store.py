import base64
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional

import streamlit as st

STORE_PATH = Path("data/tradesmart_bridge_accounts.json")
KEY_PATH = Path("data/tradesmart_bridge.key")


def _ensure_data_dir() -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_crypto():
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except Exception:
        return None


def _get_key() -> bytes:
    _ensure_data_dir()
    Fernet = _get_crypto()
    if Fernet is None:
        return b""

    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()

    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


def _encrypt(value: str) -> str:
    if not value:
        return ""
    Fernet = _get_crypto()
    if Fernet is None:
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8")
    return Fernet(_get_key()).encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt(value: str) -> str:
    if not value:
        return ""
    Fernet = _get_crypto()
    try:
        if Fernet is None:
            return base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        return Fernet(_get_key()).decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def normalize_bridge_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    return url


def get_current_user_key(scope: str = "user") -> str:
    user = st.session_state.get("user")

    if isinstance(user, dict):
        raw = (
            user.get("id")
            or user.get("token")
            or user.get("name")
            or user.get("username")
            or user.get("email")
            or str(user)
        )
    else:
        raw = st.session_state.get("authenticated_user") or st.session_state.get("token") or scope

    digest = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:24]
    return f"user_{digest}"


def _read_store() -> Dict[str, Any]:
    _ensure_data_dir()
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_store(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_bridge_settings(user_key: str, bridge_url: str, bridge_token: str) -> None:
    data = _read_store()
    data[user_key] = {
        "bridge_url": normalize_bridge_url(bridge_url),
        "bridge_token_encrypted": _encrypt(bridge_token),
    }
    _write_store(data)


def load_bridge_settings(user_key: Optional[str] = None) -> Dict[str, str]:
    user_key = user_key or get_current_user_key()
    data = _read_store().get(user_key, {})
    return {
        "bridge_url": data.get("bridge_url", ""),
        "bridge_token": _decrypt(data.get("bridge_token_encrypted", "")),
    }


def mask_secret(value: str, left: int = 0, right: int = 4) -> str:
    if not value:
        return "Not saved"
    if len(value) <= right:
        return "*" * len(value)
    return f"{value[:left]}{'*' * max(4, len(value) - left - right)}{value[-right:]}"
