from typing import Dict, Any, Tuple
import requests

ALLOWED_SYMBOL = "XAUUSD"


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def bridge_request(settings: Dict[str, str], endpoint: str, payload: Dict[str, Any] | None = None, timeout: int = 12) -> Tuple[bool, Dict[str, Any]]:
    bridge_url = (settings.get("bridge_url") or "").strip().rstrip("/")
    token = settings.get("bridge_token") or ""

    if not bridge_url or not token:
        return False, {"message": "Windows Bridge URL and API token are not saved."}

    try:
        if payload is None:
            response = requests.get(f"{bridge_url}{endpoint}", headers=_headers(token), timeout=timeout)
        else:
            response = requests.post(f"{bridge_url}{endpoint}", headers=_headers(token), json=payload, timeout=timeout)

        try:
            data = response.json()
        except Exception:
            data = {"message": response.text}

        if response.status_code >= 400:
            return False, data

        return True, data
    except requests.exceptions.RequestException as exc:
        return False, {"message": f"Could not reach the Windows Bridge: {exc}"}


def connect_bridge(settings: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/connect", payload={"symbol": ALLOWED_SYMBOL}, timeout=20)


def disconnect_bridge(settings: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/disconnect", payload={}, timeout=10)


def get_bridge_status(settings: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
    return bridge_request(settings, "/status", payload=None, timeout=8)


def place_xauusd_order(settings: Dict[str, str], signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    payload = {
        "symbol": ALLOWED_SYMBOL,
        "direction": signal.get("direction") or signal.get("action"),
        "volume": float(signal.get("volume", 0)),
        "stop_loss": float(signal.get("stop_loss", 0) or 0),
        "take_profit": float(signal.get("take_profit", 0) or 0),
        "comment": signal.get("reason", "TradeSmart Agent")[:28],
    }
    return bridge_request(settings, "/place_trade", payload=payload, timeout=20)
