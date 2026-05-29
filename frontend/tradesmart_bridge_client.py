import os
import requests

RELAY_URL = os.getenv("TRADESMART_RELAY_URL", "").strip()
RELAY_TOKEN = os.getenv("TRADESMART_RELAY_TOKEN", "").strip()


def _relay_lookup(user_key: str):
    if not RELAY_URL or not RELAY_TOKEN:
        return None

    try:
        r = requests.post(
            f"{RELAY_URL}/resolve_bridge",
            json={
                "user_key": user_key,
                "relay_token": RELAY_TOKEN,
            },
            timeout=10,
        )

        if r.status_code != 200:
            return None

        data = r.json()

        if not data.get("ok"):
            return None

        return data

    except Exception:
        return None


def connect_bridge(profile: dict):
    user_key = "default"

    relay = _relay_lookup(user_key)

    if not relay:
        return False, {
            "message": (
                "Could not find your MT5 connector. "
                "Start the local Windows connector first."
            )
        }

    bridge_url = relay.get("bridge_url")
    bridge_token = relay.get("bridge_token")

    try:
        r = requests.post(
            f"{bridge_url}/connect",
            json={
                "token": bridge_token,
                "profile": profile,
            },
            timeout=20,
        )

        return r.status_code == 200, r.json()

    except Exception as exc:
        return False, {"message": str(exc)}


def get_bridge_status(profile: dict):
    user_key = "default"

    relay = _relay_lookup(user_key)

    if not relay:
        return False, {
            "message": "Connector offline."
        }

    bridge_url = relay.get("bridge_url")
    bridge_token = relay.get("bridge_token")

    try:
        r = requests.post(
            f"{bridge_url}/status",
            json={
                "token": bridge_token,
                "profile": profile,
            },
            timeout=15,
        )

        return r.status_code == 200, r.json()

    except Exception as exc:
        return False, {"message": str(exc)}


def disconnect_bridge(profile: dict):
    user_key = "default"

    relay = _relay_lookup(user_key)

    if not relay:
        return False, {
            "message": "Connector offline."
        }

    bridge_url = relay.get("bridge_url")
    bridge_token = relay.get("bridge_token")

    try:
        r = requests.post(
            f"{bridge_url}/disconnect",
            json={
                "token": bridge_token,
                "profile": profile,
            },
            timeout=15,
        )

        return r.status_code == 200, r.json()

    except Exception as exc:
        return False, {"message": str(exc)}