# frontend/license_client.py
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import uuid
from pathlib import Path
from typing import Any, Dict

import requests

APP_DATA_DIR = Path(os.getenv("DROPZ_APP_DATA_DIR", Path.home() / ".dropz_universal_agent"))
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

LICENSE_FILE = APP_DATA_DIR / "license.json"


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


def get_license_endpoint() -> str:
    # Example:
    # https://gzondcztcusuwyksoyvp.supabase.co/functions/v1/validate-license
    return _secret_or_env("DROPZ_LICENSE_ENDPOINT", "").rstrip("/")


def get_device_id() -> str:
    raw = "|".join(
        [
            platform.node(),
            platform.system(),
            platform.machine(),
            socket.gethostname(),
            str(uuid.getnode()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def save_license_token(token: str, payload: Dict[str, Any] | None = None) -> None:
    data = {
        "token": str(token or "").strip(),
        "device_id": get_device_id(),
        "last_validation": payload or {},
    }
    LICENSE_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def load_license_token() -> str:
    if not LICENSE_FILE.exists():
        return ""
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        return str(data.get("token") or "").strip()
    except Exception:
        return ""


def clear_license_token() -> None:
    try:
        LICENSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def validate_license(token: str) -> Dict[str, Any]:
    endpoint = get_license_endpoint()
    token = str(token or "").strip()

    if not endpoint:
        return {
            "ok": False,
            "valid": False,
            "message": "License endpoint is not configured.",
        }

    if not token:
        return {
            "ok": False,
            "valid": False,
            "message": "License token is required.",
        }

    try:
        response = requests.post(
            endpoint,
            json={"token": token, "device_id": get_device_id()},
            timeout=12,
        )
        try:
            data = response.json()
        except Exception:
            data = {"ok": False, "valid": False, "message": response.text}

        if response.status_code >= 400:
            data.setdefault("ok", False)
            data.setdefault("valid", False)
            data.setdefault("message", f"License server error: {response.status_code}")
            return data

        if data.get("valid"):
            save_license_token(token, data)

        return data

    except requests.RequestException as exc:
        return {
            "ok": False,
            "valid": False,
            "message": f"Could not reach license server: {exc}",
        }


def is_license_valid_cached() -> bool:
    token = load_license_token()
    if not token:
        return False
    result = validate_license(token)
    return bool(result.get("valid"))
