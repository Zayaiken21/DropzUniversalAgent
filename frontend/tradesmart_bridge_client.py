from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import requests

ALLOWED_SYMBOL = "XAUUSD"


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


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _streamlit_user_key() -> str:
    """
    Stable production user key.

    This mirrors the TradeSmart page user lookup, but also allows a forced
    connector key for local testing or packaged connector pairing.

    Production options:
      1. Best: set TRADESMART_USER_KEY after pairing/install.
      2. Normal app: derives from st.session_state["user"].
      3. Local dev fallback: default, only when enabled.
    """
    forced = _secret_or_env("TRADESMART_USER_KEY", "").strip()
    if forced:
        return forced

    try:
        import streamlit as st

        user = st.session_state.get("user")
        if isinstance(user, dict):
            for field in ("id", "token", "email", "username", "name", "role"):
                value = user.get(field)
                if value not in (None, ""):
                    return f"user_{value}"

        value = st.session_state.get("authenticated_user") or st.session_state.get("role")
        if value not in (None, ""):
            return str(value)

    except Exception:
        pass

    if _secret_or_env("TRADESMART_ALLOW_DEFAULT_BRIDGE_FALLBACK", "false").lower() in {"1", "true", "yes", "on"}:
        return "default"

    return "default"


def _relay_config() -> Tuple[str, str]:
    relay_url = _secret_or_env("TRADESMART_RELAY_URL", "").rstrip("/")
    relay_token = _secret_or_env("TRADESMART_RELAY_TOKEN", "")
    return relay_url, relay_token


def _relay_lookup(user_key: str) -> Dict[str, str]:
    relay_url, relay_token = _relay_config()

    if not relay_url or not relay_token:
        return {}

    try:
        response = requests.post(
            f"{relay_url}/get_bridge",
            headers=_headers(relay_token),
            json={"user_key": user_key},
            timeout=12,
        )

        try:
            data = response.json()
        except Exception:
            data = {"message": response.text}

        if response.status_code >= 400 or not data.get("ok"):
            return {}

        bridge_url = str(data.get("bridge_url") or "").strip().rstrip("/")
        bridge_token = str(data.get("bridge_token") or "").strip()

        if not bridge_url or not bridge_token:
            return {}

        return {
            "bridge_url": bridge_url,
            "bridge_token": bridge_token,
            "user_key": user_key,
            "updated_at": data.get("updated_at", ""),
        }

    except Exception:
        return {}


def resolve_bridge_settings(settings: Dict[str, Any] | None = None) -> Dict[str, str]:
    settings = dict(settings or {})
    user_key = str(settings.get("user_key") or _streamlit_user_key()).strip() or "default"

    # 1. Explicit bridge settings, if the user still saved them manually.
    bridge_url = str(settings.get("bridge_url") or settings.get("windows_bridge_url") or "").strip().rstrip("/")
    bridge_token = str(settings.get("bridge_token") or settings.get("windows_bridge_token") or "").strip()

    # 2. Production relay lookup.
    if not bridge_url or not bridge_token:
        relay = _relay_lookup(user_key)
        bridge_url = bridge_url or relay.get("bridge_url", "")
        bridge_token = bridge_token or relay.get("bridge_token", "")

    # 3. Optional local-dev fallback only.
    if (not bridge_url or not bridge_token) and _secret_or_env("TRADESMART_ALLOW_DIRECT_BRIDGE_ENV", "false").lower() in {"1", "true", "yes", "on"}:
        bridge_url = bridge_url or _secret_or_env("TRADESMART_BRIDGE_URL", "").rstrip("/")
        bridge_token = bridge_token or _secret_or_env("TRADESMART_BRIDGE_TOKEN", "")

    # Never allow placeholder URLs.
    bad_markers = ("your-tunnel", "your-vps", "YOUR-", "example.com")
    if any(marker in bridge_url for marker in bad_markers):
        bridge_url = ""

    return {
        "bridge_url": bridge_url,
        "bridge_token": bridge_token,
        "user_key": user_key,
    }


def _profile_payload(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "login": settings.get("login"),
        "password": settings.get("password"),
        "server": settings.get("server"),
        "terminal_path": settings.get("terminal_path", ""),
        "timeout": int(settings.get("timeout", 60000) or 60000),
        "portable": bool(settings.get("portable", False)),
    }


def bridge_request(
    settings: Dict[str, Any],
    endpoint: str,
    payload: Dict[str, Any] | None = None,
    timeout: int = 12,
) -> Tuple[bool, Dict[str, Any]]:
    resolved = resolve_bridge_settings(settings)
    bridge_url = resolved.get("bridge_url", "")
    bridge_token = resolved.get("bridge_token", "")

    if not bridge_url or not bridge_token:
        return False, {
            "ok": False,
            "message": (
                "Could not find your MT5 connector. Start the TradeSmart Connector on the Windows MT5 computer. "
                f"Lookup user key: {resolved.get('user_key', 'unknown')}"
            ),
            "user_key": resolved.get("user_key", "unknown"),
        }

    try:
        url = f"{bridge_url}{endpoint}"
        if payload is None:
            response = requests.get(url, headers=_headers(bridge_token), timeout=timeout)
        else:
            response = requests.post(url, headers=_headers(bridge_token), json=payload, timeout=timeout)

        try:
            data = response.json()
        except Exception:
            data = {"message": response.text}

        if response.status_code >= 400:
            return False, {
                "ok": False,
                "message": data.get("detail") or data.get("message") or response.text,
                "raw": data,
            }

        return True, data

    except requests.exceptions.RequestException as exc:
        return False, {
            "ok": False,
            "message": f"Could not reach the Windows Bridge at {bridge_url}: {exc}",
        }


def connect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(
        settings,
        "/connect",
        payload={"symbol": ALLOWED_SYMBOL, "profile": _profile_payload(settings)},
        timeout=25,
    )


def disconnect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/disconnect", payload={}, timeout=10)


def get_bridge_status(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/status", payload=None, timeout=10)


def get_bridge_positions(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/positions", payload=None, timeout=10)


def get_bridge_orders(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/orders", payload=None, timeout=10)


def get_bridge_history(settings: Dict[str, Any], days: int = 30) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, f"/history?days={int(days)}", payload=None, timeout=15)


def get_bridge_rates(settings: Dict[str, Any], timeframe: str = "M1", count: int = 120) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(
        settings,
        "/rates",
        payload={"symbol": ALLOWED_SYMBOL, "timeframe": timeframe, "count": int(count)},
        timeout=15,
    )


def place_xauusd_order(settings: Dict[str, Any], signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    payload = {
        "symbol": ALLOWED_SYMBOL,
        "direction": signal.get("direction") or signal.get("action"),
        "volume": float(signal.get("volume", 0)),
        "stop_loss": float(signal.get("stop_loss", signal.get("sl", 0)) or 0),
        "take_profit": float(signal.get("take_profit", signal.get("tp", 0)) or 0),
        "comment": str(signal.get("reason", "TradeSmart Agent"))[:28],
        "profile": _profile_payload(settings),
    }
    return bridge_request(settings, "/place_trade", payload=payload, timeout=25)


def close_xauusd_position(settings: Dict[str, Any], ticket: int) -> Tuple[bool, Dict[str, Any]]:
    payload = {
        "symbol": ALLOWED_SYMBOL,
        "ticket": int(ticket),
        "profile": _profile_payload(settings),
    }
    return bridge_request(settings, "/close_position", payload=payload, timeout=25)
