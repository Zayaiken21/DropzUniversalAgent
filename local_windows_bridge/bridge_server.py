import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

load_dotenv()

BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "change-me")
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MT5_PATH = os.getenv("MT5_PATH", "")
MT5_LOGIN = os.getenv("MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

ALLOWED_SYMBOL = "XAUUSD"

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
        raise HTTPException(status_code=500, detail=f"MetaTrader5 package is not available on this Windows PC: {exc}")


def initialize_mt5():
    global _connected
    mt5 = get_mt5()

    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH

    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        kwargs["login"] = int(MT5_LOGIN)
        kwargs["password"] = MT5_PASSWORD
        kwargs["server"] = MT5_SERVER

    ok = mt5.initialize(**kwargs)
    if not ok:
        raise HTTPException(status_code=500, detail=f"MT5 initialization failed: {mt5.last_error()}")

    symbol_ok = mt5.symbol_select(ALLOWED_SYMBOL, True)
    if not symbol_ok:
        raise HTTPException(status_code=500, detail=f"Could not select {ALLOWED_SYMBOL}. Check your broker symbol name.")

    _connected = True
    return mt5


def account_payload(mt5):
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
    }


class ConnectRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL


class TradeRequest(BaseModel):
    symbol: str = ALLOWED_SYMBOL
    direction: str
    volume: float
    stop_loss: float = 0
    take_profit: float = 0
    comment: str = "TradeSmart Agent"


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
        "magic": 777001,
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
    if payload.get("retcode") != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(status_code=500, detail=f"Trade rejected: {payload}")

    return {
        "status": "filled",
        "symbol": ALLOWED_SYMBOL,
        "direction": direction,
        "volume": req.volume,
        "result": payload,
    }


if __name__ == "__main__":
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
