from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import requests

ALLOWED_SYMBOL = "XAUUSD"


def _streamlit_secret(name: str, default: str = "") -> str:
    """Read Streamlit secrets safely without requiring Streamlit outside the app."""
    try:
        import streamlit as st

        value = st.secrets.get(name, default)
        return str(value or "").strip()
    except Exception:
        return str(default or "").strip()


def _auto_bridge_defaults() -> Dict[str, str]:
    """
    Automatic bridge fallback.

    Priority:
    1. Values passed in settings/profile.
    2. Per-user saved bridge settings from frontend.tradesmart_bridge_store.
    3. Streamlit secrets / environment variables.

    This lets TradeSmart keep calling connect_bridge(profile) without needing
    bridge_url/bridge_token inside the MT5 profile itself.
    """
    return {
        "bridge_url": (
            os.getenv("TRADESMART_BRIDGE_URL")
            or os.getenv("BRIDGE_URL")
            or _streamlit_secret("TRADESMART_BRIDGE_URL")
            or _streamlit_secret("BRIDGE_URL")
            or ""
        ).strip().rstrip("/"),
        "bridge_token": (
            os.getenv("TRADESMART_BRIDGE_TOKEN")
            or os.getenv("BRIDGE_TOKEN")
            or _streamlit_secret("TRADESMART_BRIDGE_TOKEN")
            or _streamlit_secret("BRIDGE_TOKEN")
            or ""
        ).strip(),
    }


def _load_saved_bridge_settings() -> Dict[str, str]:
    try:
        from frontend.tradesmart_bridge_store import load_bridge_settings

        saved = load_bridge_settings()
        if isinstance(saved, dict):
            return {
                "bridge_url": str(saved.get("bridge_url") or "").strip().rstrip("/"),
                "bridge_token": str(saved.get("bridge_token") or "").strip(),
            }
    except Exception:
        pass
    return {"bridge_url": "", "bridge_token": ""}


def resolve_bridge_settings(settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Merge MT5 profile/settings with the automatic bridge config.

    Keep the original profile fields too so callers do not lose mode/login/server.
    """
    settings = dict(settings or {})
    saved = _load_saved_bridge_settings()
    defaults = _auto_bridge_defaults()

    bridge_url = (
        str(settings.get("bridge_url") or "").strip().rstrip("/")
        or saved.get("bridge_url", "")
        or defaults.get("bridge_url", "")
    )
    bridge_token = (
        str(settings.get("bridge_token") or "").strip()
        or saved.get("bridge_token", "")
        or defaults.get("bridge_token", "")
    )

    settings["bridge_url"] = bridge_url
    settings["bridge_token"] = bridge_token
    return settings


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def bridge_request(
    settings: Dict[str, Any] | None,
    endpoint: str,
    payload: Dict[str, Any] | None = None,
    timeout: int = 12,
) -> Tuple[bool, Dict[str, Any]]:
    resolved = resolve_bridge_settings(settings)

    bridge_url = (resolved.get("bridge_url") or "").strip().rstrip("/")
    token = (resolved.get("bridge_token") or "").strip()

    if not bridge_url or not token:
        return False, {
            "message": (
                "Windows Bridge URL and API token are not available. "
                "Add TRADESMART_BRIDGE_URL and TRADESMART_BRIDGE_TOKEN to Streamlit secrets/env, "
                "or save them in Settings."
            )
        }

    url = f"{bridge_url}{endpoint}"
    try:
        if payload is None:
            response = requests.get(url, headers=_headers(token), timeout=timeout)
        else:
            response = requests.post(url, headers=_headers(token), json=payload, timeout=timeout)

        try:
            data = response.json()
        except Exception:
            data = {"message": response.text}

        if response.status_code >= 400:
            message = data.get("detail") or data.get("message") or response.text
            if isinstance(message, (dict, list)):
                message = str(message)
            data["message"] = str(message)
            return False, data

        return True, data

    except requests.exceptions.RequestException as exc:
        return False, {"message": f"Could not reach the Windows Bridge at {bridge_url}: {exc}"}


def connect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/connect", payload={"symbol": ALLOWED_SYMBOL}, timeout=20)


def disconnect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/disconnect", payload={}, timeout=10)


def get_bridge_status(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/status", payload=None, timeout=8)


def get_bridge_positions(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/positions", payload=None, timeout=10)


def get_bridge_orders(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/orders", payload=None, timeout=10)


def get_bridge_rates(settings: Dict[str, Any], timeframe: str = "M1", count: int = 100) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(
        settings,
        "/rates",
        payload={"symbol": ALLOWED_SYMBOL, "timeframe": timeframe, "count": count},
        timeout=12,
    )


def place_xauusd_order(settings: Dict[str, Any], signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    payload = {
        "symbol": ALLOWED_SYMBOL,
        "direction": signal.get("direction") or signal.get("action"),
        "volume": float(signal.get("volume", 0)),
        "stop_loss": float(signal.get("stop_loss", signal.get("sl", 0)) or 0),
        "take_profit": float(signal.get("take_profit", signal.get("tp", 0)) or 0),
        "comment": str(signal.get("reason", "TradeSmart Agent"))[:28],
    }
    return bridge_request(settings, "/place_trade", payload=payload, timeout=20)


def close_xauusd_position(settings: Dict[str, Any], ticket: int, volume: float | None = None) -> Tuple[bool, Dict[str, Any]]:
    payload: Dict[str, Any] = {"symbol": ALLOWED_SYMBOL, "ticket": int(ticket)}
    if volume is not None:
        payload["volume"] = float(volume)
    return bridge_request(settings, "/close_position", payload=payload, timeout=20)
