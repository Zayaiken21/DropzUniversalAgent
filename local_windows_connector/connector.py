from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)

BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "").strip()
RELAY_URL = os.getenv("RELAY_URL", "").strip().rstrip("/")
RELAY_TOKEN = os.getenv("RELAY_TOKEN", "").strip()
PAIRING_CODE = os.getenv("PAIRING_CODE", "").strip()
USER_KEY = os.getenv("TRADESMART_USER_KEY", "").strip()
NGROK_PATH = os.getenv("NGROK_PATH", "ngrok").strip()
REGISTER_INTERVAL_SECONDS = int(os.getenv("REGISTER_INTERVAL_SECONDS", "30"))

if not BRIDGE_TOKEN:
    BRIDGE_TOKEN = secrets.token_urlsafe(32)
    set_key(str(ENV_FILE), "BRIDGE_TOKEN", BRIDGE_TOKEN)


def _run_bridge() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bridge_server:app", "--host", BRIDGE_HOST, "--port", str(BRIDGE_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _run_ngrok() -> subprocess.Popen:
    return subprocess.Popen(
        [NGROK_PATH, "http", str(BRIDGE_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _get_ngrok_url() -> Optional[str]:
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=4)
        data = response.json()
        for tunnel in data.get("tunnels", []):
            url = tunnel.get("public_url", "")
            if url.startswith("https://"):
                return url.rstrip("/")
    except Exception:
        return None
    return None


def _register_bridge(url: str) -> bool:
    if not RELAY_URL:
        print("RELAY_URL is missing in .env. Connector is running, but it cannot auto-register.")
        return False

    payload: Dict[str, Any] = {
        "user_key": USER_KEY,
        "pairing_code": PAIRING_CODE,
        "bridge_url": url,
        "bridge_token": BRIDGE_TOKEN,
    }

    headers = {"Content-Type": "application/json"}
    if RELAY_TOKEN:
        headers["Authorization"] = f"Bearer {RELAY_TOKEN}"

    try:
        response = requests.post(f"{RELAY_URL}/register_bridge", headers=headers, json=payload, timeout=12)
        if response.status_code >= 400:
            print("Bridge registration failed:", response.status_code, response.text)
            return False
        print("Bridge registered:", url)
        return True
    except Exception as exc:
        print("Bridge registration error:", exc)
        return False


def main() -> None:
    print("Starting TradeSmart Bridge...")
    bridge_proc = _run_bridge()
    time.sleep(3)

    print("Starting ngrok tunnel...")
    ngrok_proc = _run_ngrok()

    last_url = ""
    last_register = 0.0

    try:
        while True:
            url = _get_ngrok_url()
            now = time.time()

            if url and (url != last_url or now - last_register >= REGISTER_INTERVAL_SECONDS):
                print("Tunnel URL:", url)
                _register_bridge(url)
                last_url = url
                last_register = now

            if bridge_proc.poll() is not None:
                print("Bridge stopped. Restarting...")
                bridge_proc = _run_bridge()

            if ngrok_proc.poll() is not None:
                print("ngrok stopped. Restarting...")
                ngrok_proc = _run_ngrok()

            time.sleep(5)

    except KeyboardInterrupt:
        print("Stopping TradeSmart Connector...")

    finally:
        for proc in (bridge_proc, ngrok_proc):
            try:
                proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
