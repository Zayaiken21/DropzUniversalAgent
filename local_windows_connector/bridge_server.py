from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
import uvicorn

load_dotenv()

BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "change-me").strip()
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1").strip()
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MT5_PATH = os.getenv("MT5_PATH", "").strip()
ALLOWED_SYMBOL = "XAUUSD"
MAGIC = 777001

RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_REQUESTS = 60
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(title="TradeSmart Safe Windows MT5 Bridge", version="1.0.1")


class MT5Profile(BaseModel):
    login: int | str
    password: str
    server: str
    terminal_path: str = ""
    timeout: int = 60000
    portable: bool = False


class ConnectRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    profile: Optional[MT5Profile] = None


class TradeRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    direction: str
    volume: float = Field(gt=0)
    stop_loss: float = 0
    take_profit: float = 0
    comment: str = "TradeSmart Agent"
    profile: Optional[MT5Profile] = None


class CloseRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    ticket: int
    profile: Optional[MT5Profile] = None


class RatesRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    timeframe: str = "M1"
    count: int = 100
    profile: Optional[MT5Profile] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))


def _audit(event: str, payload: Dict[str, Any] | None = None) -> None:
    try:
        safe = dict(payload or {})
        if "password" in safe:
            safe["password"] = "***"
        Path("logs").mkdir(exist_ok=True)
        with Path("logs/tradesmart_bridge_audit.log").open("a", encoding="utf-8") as fh:
            fh.write(json_dumps({"ts": _now(), "event": event, "payload": safe}) + "\n")
    except Exception:
        pass


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
        raise HTTPException(status_code=429, detail="Bridge rate limit reached.")
    bucket.append(now)


def _require_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bridge token.")
    supplied = authorization.replace("Bearer ", "", 1).strip()
    if not BRIDGE_TOKEN or supplied != BRIDGE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid bridge token.")


def _require_symbol(symbol: str) -> None:
    if str(symbol or "").upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD is allowed.")


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"MetaTrader5 is not available on this Windows PC. Install MetaTrader5 in the connector Python environment. Details: {exc}",
        )


def _initialize(profile: Optional[MT5Profile] = None):
    mt5 = _mt5()

    try:
        mt5.shutdown()
    except Exception:
        pass

    kwargs: Dict[str, Any] = {}

    if MT5_PATH:
        kwargs["path"] = MT5_PATH

    if profile:
        if profile.terminal_path:
            kwargs["path"] = profile.terminal_path
        kwargs.update(
            {
                "login": int(profile.login),
                "password": profile.password,
                "server": profile.server,
                "timeout": int(profile.timeout or 60000),
                "portable": bool(profile.portable),
            }
        )

    ok = mt5.initialize(**kwargs)
    if not ok:
        raise HTTPException(status_code=500, detail=f"MT5 initialization failed: {mt5.last_error()}")

    if not mt5.symbol_select(ALLOWED_SYMBOL, True):
        raise HTTPException(status_code=500, detail=f"Could not select {ALLOWED_SYMBOL}. Check broker symbol name.")

    return mt5


def _asdict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)
    except Exception:
        return {}


def _account(mt5) -> Dict[str, Any]:
    info = mt5.account_info()
    if info is None:
        return {}
    data = info._asdict()
    return {
        "login": data.get("login"),
        "server": data.get("server"),
        "balance": data.get("balance"),
        "equity": data.get("equity"),
        "profit": data.get("profit"),
        "margin": data.get("margin"),
        "margin_free": data.get("margin_free"),
        "currency": data.get("currency"),
        "leverage": data.get("leverage"),
        "trade_allowed": data.get("trade_allowed"),
    }


def _positions(mt5) -> list[Dict[str, Any]]:
    raw = mt5.positions_get(symbol=ALLOWED_SYMBOL)
    if raw is None:
        return []
    return [_asdict(p) for p in raw]


def _orders(mt5) -> list[Dict[str, Any]]:
    raw = mt5.orders_get(symbol=ALLOWED_SYMBOL)
    if raw is None:
        return []
    return [_asdict(o) for o in raw]


def _rates(mt5, timeframe: str = "M1", count: int = 100) -> list[Dict[str, Any]]:
    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
    }
    tf = timeframe_map.get(str(timeframe or "M1").upper(), mt5.TIMEFRAME_M1)
    raw = mt5.copy_rates_from_pos(ALLOWED_SYMBOL, tf, 0, max(1, min(int(count or 100), 500)))
    if raw is None:
        return []
    rows = []
    names = getattr(getattr(raw, "dtype", None), "names", None)
    for row in raw:
        if names:
            rows.append({str(name): row[name].item() if hasattr(row[name], "item") else row[name] for name in names})
        else:
            rows.append(_asdict(row))
    rows.sort(key=lambda item: int(item.get("time", 0) or 0))
    return rows


def _deals(mt5, days: int = 30) -> list[Dict[str, Any]]:
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=max(1, min(int(days or 30), 365)))
    raw = mt5.history_deals_get(from_dt, to_dt)
    deals: list[Dict[str, Any]] = []
    if raw is not None:
        for deal in raw:
            data = _asdict(deal)
            if str(data.get("symbol", "")).upper() == ALLOWED_SYMBOL:
                deals.append(data)
    deals.sort(key=lambda d: int(d.get("time", 0) or 0), reverse=True)
    return deals


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
    return {"ok": True, "bridge": "TradeSmart", "symbol": ALLOWED_SYMBOL, "ts": _now()}


@app.get("/status")
def status(request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    mt5 = _mt5()
    account = mt5.account_info()
    return {
        "ok": True,
        "connected": account is not None,
        "symbol": ALLOWED_SYMBOL,
        "account": _account(mt5) if account is not None else {},
        "positions": _positions(mt5) if account is not None else [],
        "orders": _orders(mt5) if account is not None else [],
        "ts": _now(),
    }


@app.post("/connect")
def connect(req: ConnectRequest, request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    _require_symbol(req.symbol)
    mt5 = _initialize(req.profile)
    payload = {
        "ok": True,
        "connected": True,
        "symbol": ALLOWED_SYMBOL,
        "account": _account(mt5),
        "positions": _positions(mt5),
        "orders": _orders(mt5),
        "ts": _now(),
    }
    _audit("connect", {"account": payload["account"]})
    return payload


@app.post("/disconnect")
def disconnect(request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    mt5 = _mt5()
    mt5.shutdown()
    _audit("disconnect")
    return {"ok": True, "connected": False, "message": "Disconnected from MT5.", "ts": _now()}


@app.get("/positions")
def positions(request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    mt5 = _mt5()
    return {"ok": True, "symbol": ALLOWED_SYMBOL, "positions": _positions(mt5), "account": _account(mt5), "ts": _now()}


@app.get("/orders")
def orders(request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    mt5 = _mt5()
    return {"ok": True, "symbol": ALLOWED_SYMBOL, "orders": _orders(mt5), "account": _account(mt5), "ts": _now()}


@app.get("/history")
def history(days: int = 30, request: Request = None, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    mt5 = _initialize(None)
    return {"ok": True, "symbol": ALLOWED_SYMBOL, "deals": _deals(mt5, days), "account": _account(mt5), "ts": _now()}


@app.post("/rates")
def rates(req: RatesRequest, request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    _require_symbol(req.symbol)
    mt5 = _initialize(req.profile)
    return {
        "ok": True,
        "symbol": ALLOWED_SYMBOL,
        "timeframe": req.timeframe,
        "rates": _rates(mt5, req.timeframe, req.count),
        "account": _account(mt5),
        "ts": _now(),
    }


@app.post("/place_trade")
def place_trade(req: TradeRequest, request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    _require_symbol(req.symbol)

    direction = str(req.direction).upper()
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Direction must be BUY or SELL.")

    mt5 = _initialize(req.profile)

    terminal = mt5.terminal_info()
    account = mt5.account_info()
    if terminal is not None and not getattr(terminal, "trade_allowed", True):
        raise HTTPException(status_code=403, detail="MT5 Algo Trading is disabled in the terminal.")
    if account is not None and not getattr(account, "trade_allowed", True):
        raise HTTPException(status_code=403, detail="This MT5 account is read-only or trading is disabled.")

    tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {ALLOWED_SYMBOL}.")

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = float(tick.ask if direction == "BUY" else tick.bid)

    request_payload = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": ALLOWED_SYMBOL,
        "volume": float(req.volume),
        "type": order_type,
        "price": price,
        "deviation": 30,
        "magic": MAGIC,
        "comment": str(req.comment or "TradeSmart Agent")[:28],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if req.stop_loss > 0:
        request_payload["sl"] = float(req.stop_loss)
    if req.take_profit > 0:
        request_payload["tp"] = float(req.take_profit)

    result = mt5.order_send(request_payload)
    if result is None:
        raise HTTPException(status_code=500, detail=f"order_send failed: {mt5.last_error()}")

    data = result._asdict()
    retcode = int(data.get("retcode", 0) or 0)
    ok_codes = {int(mt5.TRADE_RETCODE_DONE), int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
    if retcode not in ok_codes:
        _audit("trade_rejected", {"retcode": retcode, "direction": direction, "volume": req.volume})
        raise HTTPException(status_code=500, detail=f"Trade rejected. Retcode: {retcode}. Result: {data}")

    payload = {
        "ok": True,
        "status": "filled",
        "symbol": ALLOWED_SYMBOL,
        "direction": direction,
        "volume": req.volume,
        "account": _account(mt5),
        "positions": _positions(mt5),
        "result": data,
        "ts": _now(),
    }
    _audit("trade_filled", {"direction": direction, "volume": req.volume, "result": data})
    return payload


@app.post("/close_position")
def close_position(req: CloseRequest, request: Request, authorization: Optional[str] = Header(None)):
    _require_token(authorization)
    _require_symbol(req.symbol)
    mt5 = _initialize(req.profile)

    target = None
    for p in _positions(mt5):
        if str(p.get("ticket")) == str(req.ticket):
            target = p
            break

    if target is None:
        raise HTTPException(status_code=404, detail=f"Position {req.ticket} was not found.")

    tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {ALLOWED_SYMBOL}.")

    pos_type = int(target.get("type", 0) or 0)
    close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = float(tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask)

    request_payload = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(req.ticket),
        "symbol": ALLOWED_SYMBOL,
        "volume": float(target.get("volume", 0.01) or 0.01),
        "type": close_type,
        "price": price,
        "deviation": 30,
        "magic": MAGIC,
        "comment": "TradeSmart Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request_payload)
    if result is None:
        raise HTTPException(status_code=500, detail=f"close order_send failed: {mt5.last_error()}")

    data = result._asdict()
    retcode = int(data.get("retcode", 0) or 0)
    ok_codes = {int(mt5.TRADE_RETCODE_DONE), int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
    if retcode not in ok_codes:
        raise HTTPException(status_code=500, detail=f"Close rejected. Retcode: {retcode}. Result: {data}")

    _audit("position_closed", {"ticket": req.ticket, "result": data})
    return {"ok": True, "message": "Position closed.", "account": _account(mt5), "positions": _positions(mt5), "result": data, "ts": _now()}


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
