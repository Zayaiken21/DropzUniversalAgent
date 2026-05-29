from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

load_dotenv()

BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "change-me")
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MT5_PATH = os.getenv("MT5_PATH", "")
MT5_LOGIN = os.getenv("MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

ALLOWED_SYMBOL = "XAUUSD"
MAGIC = 777001

app = FastAPI(title="TradeSmart Windows MT5 Bridge")
_connected = False


def require_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bridge token.")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != BRIDGE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid bridge token.")


def get_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"MetaTrader5 package is not available on this Windows PC: {exc}",
        )


def _asdict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if isinstance(obj, dict):
        return obj
    try:
        names = getattr(getattr(obj, "dtype", None), "names", None)
        if names:
            return {str(name): _native(obj[name]) for name in names}
    except Exception:
        pass
    try:
        return dict(obj)
    except Exception:
        return {}


def _native(value: Any) -> Any:
    try:
        if hasattr(value, "item"):
            return value.item()
    except Exception:
        pass
    return value


def initialize_mt5():
    """Initialize MT5 on the Windows machine only."""
    global _connected
    mt5 = get_mt5()

    kwargs: Dict[str, Any] = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH

    # Optional: if these are not set, bridge uses the already-open MT5 terminal session.
    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        kwargs["login"] = int(MT5_LOGIN)
        kwargs["password"] = MT5_PASSWORD
        kwargs["server"] = MT5_SERVER

    ok = mt5.initialize(**kwargs)
    if not ok:
        raise HTTPException(status_code=500, detail=f"MT5 initialization failed: {mt5.last_error()}")

    symbol_ok = mt5.symbol_select(ALLOWED_SYMBOL, True)
    if not symbol_ok:
        raise HTTPException(
            status_code=500,
            detail=f"Could not select {ALLOWED_SYMBOL}. Check your broker symbol name.",
        )

    _connected = True
    return mt5


def account_payload(mt5) -> Optional[Dict[str, Any]]:
    info = mt5.account_info()
    if info is None:
        return None
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


def _position_payload(position: Any) -> Dict[str, Any]:
    data = _asdict(position)
    return {
        **data,
        "symbol": data.get("symbol"),
        "ticket": data.get("ticket"),
        "time": data.get("time"),
        "time_msc": data.get("time_msc"),
        "type": data.get("type"),
        "volume": data.get("volume"),
        "price_open": data.get("price_open"),
        "price_current": data.get("price_current"),
        "profit": data.get("profit"),
        "magic": data.get("magic"),
        "comment": data.get("comment"),
    }


def _rates_payload(rates: Any) -> list[Dict[str, Any]]:
    if rates is None:
        return []
    rows = []
    for row in rates:
        data = _asdict(row)
        if data:
            rows.append({k: _native(v) for k, v in data.items()})
    rows.sort(key=lambda item: int(item.get("time", 0) or 0))
    return rows


class ConnectRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL


class TradeRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    direction: str
    volume: float
    stop_loss: float = 0
    take_profit: float = 0
    comment: str = "TradeSmart Agent"
    deviation: int = 30


class CloseRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    ticket: int
    volume: Optional[float] = None
    deviation: int = 30


class RatesRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    timeframe: str = "M1"
    count: int = 100


@app.get("/status")
def status(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    positions = mt5.positions_get(symbol=ALLOWED_SYMBOL) or []
    return {
        "connected": mt5.account_info() is not None,
        "symbol": ALLOWED_SYMBOL,
        "account": account_payload(mt5),
        "positions": [_position_payload(p) for p in positions],
        "open_positions_count": len(positions),
    }


@app.post("/connect")
def connect(req: ConnectRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="This bridge only allows XAUUSD.")
    mt5 = initialize_mt5()
    positions = mt5.positions_get(symbol=ALLOWED_SYMBOL) or []
    return {
        "connected": True,
        "symbol": ALLOWED_SYMBOL,
        "account": account_payload(mt5),
        "positions": [_position_payload(p) for p in positions],
        "open_positions_count": len(positions),
    }


@app.post("/disconnect")
def disconnect(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    global _connected
    mt5 = get_mt5()
    mt5.shutdown()
    _connected = False
    return {"connected": False, "message": "Disconnected from MT5."}


@app.get("/positions")
def positions(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    raw = mt5.positions_get(symbol=ALLOWED_SYMBOL) or []
    return {"symbol": ALLOWED_SYMBOL, "positions": [_position_payload(p) for p in raw], "count": len(raw)}


@app.get("/orders")
def orders(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    raw = mt5.orders_get(symbol=ALLOWED_SYMBOL) or []
    return {"symbol": ALLOWED_SYMBOL, "orders": [_asdict(o) for o in raw], "count": len(raw)}


@app.post("/rates")
def rates(req: RatesRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD is allowed.")
    mt5 = initialize_mt5()
    tf = str(req.timeframe or "M1").upper()
    timeframe = getattr(mt5, f"TIMEFRAME_{tf}", mt5.TIMEFRAME_M1)
    count = max(1, min(int(req.count or 100), 1000))
    raw = mt5.copy_rates_from_pos(ALLOWED_SYMBOL, timeframe, 0, count)
    return {"symbol": ALLOWED_SYMBOL, "timeframe": tf, "rates": _rates_payload(raw), "count": len(raw) if raw is not None else 0}


@app.post("/place_trade")
def place_trade(req: TradeRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)

    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD is allowed.")

    direction = req.direction.upper()
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Direction must be BUY or SELL.")

    if req.volume <= 0:
        raise HTTPException(status_code=400, detail="Volume must be greater than 0.")

    mt5 = initialize_mt5()

    terminal = mt5.terminal_info()
    account = mt5.account_info()
    if terminal is not None and getattr(terminal, "trade_allowed", True) is False:
        raise HTTPException(status_code=403, detail="MT5 Algo Trading is disabled in the terminal.")
    if account is not None and getattr(account, "trade_allowed", True) is False:
        raise HTTPException(status_code=403, detail="Trading is disabled for this MT5 account. Use the main trading password, not investor/read-only mode.")

    tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {ALLOWED_SYMBOL}.")

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": ALLOWED_SYMBOL,
        "volume": float(req.volume),
        "type": order_type,
        "price": price,
        "deviation": int(req.deviation or 30),
        "magic": MAGIC,
        "comment": req.comment[:28],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if req.stop_loss > 0:
        request["sl"] = float(req.stop_loss)
    if req.take_profit > 0:
        request["tp"] = float(req.take_profit)

    result = mt5.order_send(request)
    if result is None:
        raise HTTPException(status_code=500, detail=f"order_send failed: {mt5.last_error()}")

    payload = result._asdict()
    ok_codes = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008)}
    if payload.get("retcode") not in ok_codes:
        raise HTTPException(status_code=500, detail=f"Trade rejected: {payload}")

    return {
        "status": "filled",
        "symbol": ALLOWED_SYMBOL,
        "direction": direction,
        "volume": req.volume,
        "result": payload,
        "account": account_payload(mt5),
    }


@app.post("/close_position")
def close_position(req: CloseRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD is allowed.")

    mt5 = initialize_mt5()
    positions = mt5.positions_get(symbol=ALLOWED_SYMBOL) or []
    target = None
    for pos in positions:
        data = _position_payload(pos)
        if str(data.get("ticket")) == str(req.ticket):
            target = data
            break

    if not target:
        raise HTTPException(status_code=404, detail=f"Position {req.ticket} was not found.")

    tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {ALLOWED_SYMBOL}.")

    pos_type = int(target.get("type", 0) or 0)
    close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    close_price = tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask
    volume = float(req.volume or target.get("volume") or 0.01)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(req.ticket),
        "symbol": ALLOWED_SYMBOL,
        "volume": volume,
        "type": close_type,
        "price": close_price,
        "deviation": int(req.deviation or 30),
        "magic": MAGIC,
        "comment": "TradeSmart Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        raise HTTPException(status_code=500, detail=f"close order_send failed: {mt5.last_error()}")

    payload = result._asdict()
    ok_codes = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008)}
    if payload.get("retcode") not in ok_codes:
        raise HTTPException(status_code=500, detail=f"Close rejected: {payload}")

    return {
        "status": "closed",
        "symbol": ALLOWED_SYMBOL,
        "ticket": req.ticket,
        "volume": volume,
        "result": payload,
        "account": account_payload(mt5),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
