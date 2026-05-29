import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

load_dotenv()

BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "change-me")
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MT5_PATH = os.getenv("MT5_PATH", "")

ALLOWED_SYMBOL = "XAUUSD"
MAGIC = 777001

app = FastAPI(title="TradeSmart Windows MT5 Bridge")
_connected = False


class MT5Profile(BaseModel):
    login: Optional[int | str] = None
    password: str = ""
    server: str = ""
    terminal_path: str = ""
    timeout: int = 8000
    portable: bool = False


class ConnectRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    profile: Optional[MT5Profile] = None


class TradeRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    direction: str
    volume: float
    stop_loss: float = 0
    take_profit: float = 0
    comment: str = "TradeSmart Agent"
    profile: Optional[MT5Profile] = None


class CloseRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    ticket: int
    volume: Optional[float] = None
    deviation: int = 30
    comment: str = "TradeSmart Close"
    profile: Optional[MT5Profile] = None


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
        raise HTTPException(status_code=500, detail=f"MetaTrader5 package is not available on this Windows PC: {exc}")


def _clean_profile(profile: Optional[MT5Profile]) -> Dict[str, Any]:
    profile = profile or MT5Profile()
    login_raw = str(profile.login or "").strip()
    login = "".join(ch for ch in login_raw if ch.isdigit())
    timeout = int(profile.timeout or 8000)
    timeout = max(5000, min(timeout, 20000))
    return {
        "login": login,
        "password": str(profile.password or "").strip(),
        "server": str(profile.server or "").replace("\u00a0", " ").strip().strip('"').strip("'"),
        "terminal_path": str(profile.terminal_path or MT5_PATH or "").strip().strip('"').strip("'"),
        "timeout": timeout,
        "portable": bool(profile.portable),
    }


def _account_payload(mt5) -> Optional[Dict[str, Any]]:
    info = mt5.account_info()
    if info is None:
        return None
    data = info._asdict()
    return {
        "login": data.get("login"),
        "server": data.get("server"),
        "balance": data.get("balance"),
        "equity": data.get("equity"),
        "currency": data.get("currency"),
        "leverage": data.get("leverage"),
        "trade_allowed": data.get("trade_allowed"),
    }


def initialize_mt5(profile: Optional[MT5Profile] = None):
    global _connected
    mt5 = get_mt5()
    cleaned = _clean_profile(profile)

    login = cleaned["login"]
    password = cleaned["password"]
    server = cleaned["server"]
    terminal_path = cleaned["terminal_path"]
    timeout = cleaned["timeout"]

    if not login or not password or not server:
        raise HTTPException(status_code=400, detail="Missing selected MT5 login, password, or server.")

    login_int = int(login)

    try:
        mt5.shutdown()
    except Exception:
        pass

    kwargs: Dict[str, Any] = {"timeout": timeout, "portable": cleaned["portable"]}
    if terminal_path:
        kwargs["path"] = terminal_path

    ok = mt5.initialize(**kwargs)
    if not ok:
        raise HTTPException(status_code=500, detail=f"MT5 initialization failed: {mt5.last_error()}")

    account = mt5.account_info()
    if account is not None:
        data = account._asdict()
        if str(data.get("login", "")).strip() == str(login_int):
            mt5.symbol_select(ALLOWED_SYMBOL, True)
            _connected = True
            return mt5

    login_ok = mt5.login(login_int, password=password, server=server, timeout=timeout)
    if not login_ok:
        account = mt5.account_info()
        if account is not None:
            data = account._asdict()
            if str(data.get("login", "")).strip() == str(login_int):
                mt5.symbol_select(ALLOWED_SYMBOL, True)
                _connected = True
                return mt5

        err = mt5.last_error()
        mt5.shutdown()
        raise HTTPException(
            status_code=401,
            detail=(
                f"MT5 connection failed for {login} on {server}: {err}. "
                "The selected Demo/Live profile was sent to MT5. If MT5 is open on the correct Demo account, "
                "this bridge will now accept that session; otherwise verify the exact Demo server name."
            ),
        )

    account = mt5.account_info()
    if account is None:
        err = mt5.last_error()
        mt5.shutdown()
        raise HTTPException(status_code=500, detail=f"MT5 account_info failed after login: {err}")

    data = account._asdict()
    if str(data.get("login", "")).strip() != str(login_int):
        wrong = data.get("login", "unknown")
        mt5.shutdown()
        raise HTTPException(status_code=401, detail=f"MT5 opened the wrong account. Expected {login}, but terminal is on {wrong}.")

    symbol_ok = mt5.symbol_select(ALLOWED_SYMBOL, True)
    if not symbol_ok:
        raise HTTPException(status_code=500, detail=f"Could not select {ALLOWED_SYMBOL}. Check your broker symbol name.")

    _connected = True
    return mt5


@app.get("/status")
def status(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = get_mt5()
    info = mt5.account_info()
    return {
        "connected": info is not None,
        "symbol": ALLOWED_SYMBOL,
        "account": _account_payload(mt5) if info is not None else None,
        "positions": _positions_payload(mt5) if info is not None else [],
    }


@app.post("/connect")
def connect(req: ConnectRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.symbol.upper() != ALLOWED_SYMBOL:
        raise HTTPException(status_code=400, detail="This bridge only allows XAUUSD.")
    mt5 = initialize_mt5(req.profile)
    return {
        "connected": True,
        "symbol": ALLOWED_SYMBOL,
        "account": _account_payload(mt5),
        "positions": _positions_payload(mt5),
    }


@app.post("/disconnect")
def disconnect(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    global _connected
    mt5 = get_mt5()
    mt5.shutdown()
    _connected = False
    return {"connected": False, "message": "Disconnected from MT5."}


def _positions_payload(mt5):
    raw = mt5.positions_get(symbol=ALLOWED_SYMBOL)
    if raw is None:
        return []
    out = []
    for p in raw:
        data = p._asdict() if hasattr(p, "_asdict") else dict(p)
        out.append(data)
    return out


@app.get("/positions")
def positions(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = get_mt5()
    return {"symbol": ALLOWED_SYMBOL, "positions": _positions_payload(mt5), "account": _account_payload(mt5)}


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

    mt5 = initialize_mt5(req.profile)

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
        "deviation": 30,
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
    success_codes = {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}
    if payload.get("retcode") not in success_codes:
        raise HTTPException(status_code=500, detail=f"Trade rejected: {payload}")

    return {
        "status": "filled",
        "symbol": ALLOWED_SYMBOL,
        "direction": direction,
        "volume": req.volume,
        "result": payload,
        "account": _account_payload(mt5),
        "positions": _positions_payload(mt5),
    }


@app.post("/close_position")
def close_position(req: CloseRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    mt5 = initialize_mt5(req.profile)

    target = None
    for pos in _positions_payload(mt5):
        if str(pos.get("ticket")) == str(req.ticket):
            target = pos
            break

    if target is None:
        raise HTTPException(status_code=404, detail=f"Position {req.ticket} was not found.")

    tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"No tick data for {ALLOWED_SYMBOL}.")

    pos_type = int(target.get("type", 0) or 0)
    close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    close_price = tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(target.get("ticket")),
        "symbol": ALLOWED_SYMBOL,
        "volume": float(req.volume or target.get("volume") or 0.01),
        "type": close_type,
        "price": close_price,
        "deviation": int(req.deviation or 30),
        "magic": MAGIC,
        "comment": req.comment[:28],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        raise HTTPException(status_code=500, detail=f"close order_send failed: {mt5.last_error()}")

    payload = result._asdict()
    success_codes = {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}
    if payload.get("retcode") not in success_codes:
        raise HTTPException(status_code=500, detail=f"Close rejected: {payload}")

    return {"status": "closed", "result": payload, "account": _account_payload(mt5), "positions": _positions_payload(mt5)}


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
