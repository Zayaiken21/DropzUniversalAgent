from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
    return dict(obj)


def initialize_mt5():
    """Initialize MT5 on the Windows machine only."""
    global _connected
    mt5 = get_mt5()

    kwargs: Dict[str, Any] = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH

    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        kwargs["login"] = int(MT5_LOGIN)
        kwargs["password"] = MT5_PASSWORD
        kwargs["server"] = MT5_SERVER

    try:
        mt5.shutdown()
    except Exception:
        pass

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


def _order_payload(order: Any) -> Dict[str, Any]:
    return _asdict(order)


def _deal_payload(deal: Any) -> Dict[str, Any]:
    return _asdict(deal)


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
    ticket: int
    symbol: str = ALLOWED_SYMBOL
    volume: Optional[float] = None
    deviation: int = 30
    comment: str = "TradeSmart Close"


class RatesRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    timeframe: str = "M1"
    count: int = 100


@app.get("/status")
def status(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = get_mt5()
    info = mt5.account_info()
    return {
        "connected": info is not None,
        "symbol": ALLOWED_SYMBOL,
        "account": account_payload(mt5) if info is not None else None,
    }


@app.post("/connect")
def connect(req: ConnectRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="This bridge only allows XAUUSD.")
    mt5 = initialize_mt5()
    return {
        "connected": True,
        "symbol": ALLOWED_SYMBOL,
        "account": account_payload(mt5),
    }


@app.post("/disconnect")
def disconnect(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    global _connected
    mt5 = get_mt5()
    mt5.shutdown()
    _connected = False
    return {"connected": False, "message": "Disconnected from MT5."}


@app.get("/account")
def account(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    return {"account": account_payload(mt5), "symbol": ALLOWED_SYMBOL}


@app.get("/positions")
def positions(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    raw = mt5.positions_get(symbol=ALLOWED_SYMBOL)
    return {
        "symbol": ALLOWED_SYMBOL,
        "positions": [] if raw is None else [_position_payload(p) for p in raw],
        "account": account_payload(mt5),
    }


@app.get("/orders")
def orders(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    raw = mt5.orders_get(symbol=ALLOWED_SYMBOL)
    return {
        "symbol": ALLOWED_SYMBOL,
        "orders": [] if raw is None else [_order_payload(o) for o in raw],
        "account": account_payload(mt5),
    }


@app.get("/history")
def history(days: int = 30, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=max(1, min(int(days or 30), 365)))
    raw = mt5.history_deals_get(from_dt, to_dt)
    deals: List[Dict[str, Any]] = []
    if raw is not None:
        for deal in raw:
            data = _deal_payload(deal)
            if str(data.get("symbol", "")).upper() == ALLOWED_SYMBOL:
                deals.append(data)
    deals.sort(key=lambda d: int(d.get("time", 0) or 0), reverse=True)
    return {
        "symbol": ALLOWED_SYMBOL,
        "deals": deals[:100],
        "account": account_payload(mt5),
    }


@app.post("/rates")
def rates(req: RatesRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD is allowed.")

    mt5 = initialize_mt5()
    timeframe_name = str(req.timeframe or "M1").upper()
    timeframe = getattr(mt5, f"TIMEFRAME_{timeframe_name}", mt5.TIMEFRAME_M1)

    raw = mt5.copy_rates_from_pos(ALLOWED_SYMBOL, timeframe, 0, int(req.count or 100))
    rows = []
    if raw is not None:
        for r in raw:
            try:
                rows.append({
                    "time": int(r["time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "tick_volume": int(r["tick_volume"]),
                    "spread": int(r["spread"]),
                    "real_volume": int(r["real_volume"]),
                })
            except Exception:
                rows.append(dict(r))
    return {"symbol": ALLOWED_SYMBOL, "timeframe": timeframe_name, "rates": rows}


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
    account_info = mt5.account_info()
    if terminal is not None and terminal._asdict().get("trade_allowed") is False:
        raise HTTPException(status_code=403, detail="MT5 AutoTrading is disabled in the terminal.")
    if account_info is not None and account_info._asdict().get("trade_allowed") is False:
        raise HTTPException(status_code=403, detail="Trading is disabled for this MT5 account.")

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
    }

    filling_modes = [
        getattr(mt5, "ORDER_FILLING_IOC", None),
        getattr(mt5, "ORDER_FILLING_FOK", None),
        getattr(mt5, "ORDER_FILLING_RETURN", None),
    ]

    if req.stop_loss > 0:
        request["sl"] = float(req.stop_loss)
    if req.take_profit > 0:
        request["tp"] = float(req.take_profit)

    last_payload: Dict[str, Any] = {}
    for filling in [m for m in filling_modes if m is not None]:
        request["type_filling"] = filling
        result = mt5.order_send(request)
        if result is None:
            last_payload = {"message": f"order_send failed: {mt5.last_error()}", "request": request}
            continue

        payload = result._asdict()
        last_payload = payload
        if payload.get("retcode") == mt5.TRADE_RETCODE_DONE:
            return {
                "status": "filled",
                "ok": True,
                "symbol": ALLOWED_SYMBOL,
                "direction": direction,
                "volume": req.volume,
                "account": account_payload(mt5),
                "result": payload,
            }

    raise HTTPException(status_code=500, detail=f"Trade rejected: {last_payload}")


@app.post("/close_position")
def close_position(req: CloseRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5()

    positions = mt5.positions_get(ticket=int(req.ticket))
    if not positions:
        raise HTTPException(status_code=404, detail=f"Position {req.ticket} was not found.")

    pos = positions[0]
    data = pos._asdict()
    symbol = str(data.get("symbol") or ALLOWED_SYMBOL)
    if symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="Only XAUUSD positions can be closed.")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {symbol}.")

    pos_type = int(data.get("type", 0) or 0)
    volume = float(req.volume or data.get("volume") or 0)
    close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(req.ticket),
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "price": price,
        "deviation": int(req.deviation or 30),
        "magic": MAGIC,
        "comment": req.comment[:28],
        "type_time": mt5.ORDER_TIME_GTC,
    }

    filling_modes = [
        getattr(mt5, "ORDER_FILLING_IOC", None),
        getattr(mt5, "ORDER_FILLING_FOK", None),
        getattr(mt5, "ORDER_FILLING_RETURN", None),
    ]

    last_payload: Dict[str, Any] = {}
    for filling in [m for m in filling_modes if m is not None]:
        request["type_filling"] = filling
        result = mt5.order_send(request)
        if result is None:
            last_payload = {"message": f"close order_send failed: {mt5.last_error()}", "request": request}
            continue

        payload = result._asdict()
        last_payload = payload
        if payload.get("retcode") == mt5.TRADE_RETCODE_DONE:
            return {
                "status": "closed",
                "ok": True,
                "symbol": symbol,
                "ticket": req.ticket,
                "account": account_payload(mt5),
                "result": payload,
            }

    raise HTTPException(status_code=500, detail=f"Close rejected: {last_payload}")


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
