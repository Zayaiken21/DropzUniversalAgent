from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
import uvicorn

load_dotenv()

RELAY_TOKEN = os.getenv("RELAY_TOKEN", "change-this-relay-admin-token").strip()
FERNET_KEY = os.getenv("TRADESMART_RELAY_FERNET_KEY", "").strip()
STORE_FILE = Path(os.getenv("TRADESMART_RELAY_STORE", "data/tradesmart_bridge_registry.enc"))
PAIRING_FILE = Path(os.getenv("TRADESMART_PAIRING_STORE", "data/tradesmart_pairing_codes.enc"))

RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_REQUESTS = 120
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(title="TradeSmart Bridge Relay", version="1.0.0")


class PairingCodeRequest(BaseModel):
    user_key: str = Field(min_length=1)


class RegisterBridgeRequest(BaseModel):
    user_key: str = ""
    pairing_code: str = ""
    bridge_url: str
    bridge_token: str


class LookupBridgeRequest(BaseModel):
    user_key: str = Field(min_length=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    global FERNET_KEY
    if not FERNET_KEY:
        STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        key_file = STORE_FILE.parent / ".relay_fernet.key"
        if key_file.exists():
            FERNET_KEY = key_file.read_text().strip()
        else:
            FERNET_KEY = Fernet.generate_key().decode()
            key_file.write_text(FERNET_KEY)
    return Fernet(FERNET_KEY.encode())


def _read_enc(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = _fernet().decrypt(path.read_bytes()).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def _write_enc(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet().encrypt(json.dumps(data, default=str).encode("utf-8")))


def _require_relay_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing relay token.")
    supplied = authorization.replace("Bearer ", "", 1).strip()
    if supplied != RELAY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid relay token.")


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request) -> None:
    key = _client_key(request)
    now = time.time()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Relay rate limit reached.")
    bucket.append(now)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    _rate_limit(request)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return {"ok": True, "relay": "TradeSmart", "ts": _now()}


@app.post("/create_pairing_code")
def create_pairing_code(req: PairingCodeRequest, authorization: Optional[str] = Header(None)):
    _require_relay_token(authorization)

    import secrets
    code = secrets.token_urlsafe(18)
    data = _read_enc(PAIRING_FILE)
    data[code] = {
        "user_key": req.user_key,
        "created_at": _now(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        "used": False,
    }
    _write_enc(PAIRING_FILE, data)
    return {"ok": True, "pairing_code": code, "expires_in_minutes": 20}


@app.post("/register_bridge")
def register_bridge(req: RegisterBridgeRequest, authorization: Optional[str] = Header(None)):
    # Supports either relay admin token OR one-time pairing code.
    authorized_by_admin = False
    try:
        _require_relay_token(authorization)
        authorized_by_admin = True
    except HTTPException:
        authorized_by_admin = False

    user_key = req.user_key.strip()

    if not authorized_by_admin:
        pairings = _read_enc(PAIRING_FILE)
        pairing = pairings.get(req.pairing_code)
        if not pairing:
            raise HTTPException(status_code=403, detail="Invalid pairing code.")
        if pairing.get("used"):
            raise HTTPException(status_code=403, detail="Pairing code already used.")
        if datetime.fromisoformat(pairing["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Pairing code expired.")
        user_key = pairing.get("user_key", "")
        pairing["used"] = True
        pairing["used_at"] = _now()
        pairings[req.pairing_code] = pairing
        _write_enc(PAIRING_FILE, pairings)

    if not user_key:
        raise HTTPException(status_code=400, detail="Missing user key.")

    if not req.bridge_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Bridge URL must be HTTPS.")

    registry = _read_enc(STORE_FILE)
    registry[user_key] = {
        "bridge_url": req.bridge_url.rstrip("/"),
        "bridge_token": req.bridge_token,
        "updated_at": _now(),
    }
    _write_enc(STORE_FILE, registry)
    return {"ok": True, "registered": True, "user_key": user_key, "bridge_url": req.bridge_url.rstrip("/")}


@app.post("/get_bridge")
def get_bridge(req: LookupBridgeRequest, authorization: Optional[str] = Header(None)):
    _require_relay_token(authorization)
    registry = _read_enc(STORE_FILE)
    bridge = registry.get(req.user_key)
    if not bridge:
        return {"ok": False, "message": "No bridge registered for this user."}
    return {
        "ok": True,
        "bridge_url": bridge.get("bridge_url"),
        "bridge_token": bridge.get("bridge_token"),
        "updated_at": bridge.get("updated_at"),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("RELAY_HOST", "0.0.0.0"), port=int(os.getenv("RELAY_PORT", "8010")))
