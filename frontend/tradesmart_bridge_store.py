import base64
import hashlib
import json
import os
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

    env_key = (
        os.getenv("TRADESMART_BRIDGE_FERNET_KEY")
        or os.getenv("TRADESMART_MASTER_KEY")
        or ""
    ).strip()
    if env_key:
        return env_key.encode("utf-8")

    try:
        secret_key = str(st.secrets.get("TRADESMART_BRIDGE_FERNET_KEY", "") or st.secrets.get("TRADESMART_MASTER_KEY", "") or "").strip()
        if secret_key:
            return secret_key.encode("utf-8")
    except Exception:
        pass

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
    return (url or "").strip().rstrip("/")


def _secret_or_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return str(value).strip()
    try:
        for name in names:
            value = st.secrets.get(name, "")
            if value:
                return str(value).strip()
    except Exception:
        pass
    return ""


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
    """
    Load per-user saved bridge settings, with automatic fallback to env/secrets.

    This is what makes the bridge automatic when you add:
      TRADESMART_BRIDGE_URL
      TRADESMART_BRIDGE_TOKEN
    to Streamlit secrets or .env.
    """
    user_key = user_key or get_current_user_key()
    data = _read_store().get(user_key, {})

    saved_url = normalize_bridge_url(data.get("bridge_url", ""))
    saved_token = _decrypt(data.get("bridge_token_encrypted", ""))

    auto_url = normalize_bridge_url(_secret_or_env("TRADESMART_BRIDGE_URL", "BRIDGE_URL"))
    auto_token = _secret_or_env("TRADESMART_BRIDGE_TOKEN", "BRIDGE_TOKEN")

    return {
        "bridge_url": saved_url or auto_url,
        "bridge_token": saved_token or auto_token,
    }


def mask_secret(value: str, left: int = 0, right: int = 4) -> str:
    if not value:
        return "Not saved"
    if len(value) <= right:
        return "*" * len(value)
    return f"{value[:left]}{'*' * max(4, len(value) - left - right)}{value[-right:]}"
