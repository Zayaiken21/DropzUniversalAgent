from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BUY = "BUY"
SELL = "SELL"
CLOSE = "CLOSE"
HOLD = "HOLD"

SYMBOL_DEFAULT = "XAUUSD"
DRAW_ENV = "TRADESMART_MT5_BRIDGE_FILE"
DRAW_JSON1 = "TradeSmart_AI_DrawCommands.json1"
DRAW_JSONL = "TradeSmart_AI_DrawCommands.jsonl"
DEBUG_FILE = "TradeSmart_AI_Debug_LastSignal.json"

TIMEFRAMES = ["H4", "M15", "M1"]
TF_BARS = {"H4": 260, "M15": 420, "M1": 800}


def f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def symbol_from_context(context: Dict[str, Any]) -> str:
    return str(context.get("symbol") or (context.get("profile") or {}).get("symbol") or SYMBOL_DEFAULT)


def normalize_candle(candle: Any) -> Dict[str, Any]:
    if isinstance(candle, dict):
        return candle
    out: Dict[str, Any] = {}
    for key in ("time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"):
        try:
            out[key] = candle[key]
        except Exception:
            try:
                out[key] = getattr(candle, key)
            except Exception:
                pass
    return out


def mt5_rates(symbol: str) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        import MetaTrader5 as mt5
    except Exception:
        return out

    try:
        mt5.initialize()
    except Exception:
        pass

    tf_map = {
        "M1": getattr(mt5, "TIMEFRAME_M1", None),
        "M15": getattr(mt5, "TIMEFRAME_M15", None),
        "H4": getattr(mt5, "TIMEFRAME_H4", None),
    }

    for tf, tf_const in tf_map.items():
        if tf_const is None:
            continue
        try:
            raw = mt5.copy_rates_from_pos(symbol, tf_const, 0, TF_BARS[tf])
        except Exception:
            raw = None
        if raw is None:
            continue

        rows: List[Dict[str, Any]] = []
        for r in raw:
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

        # Non-repaint: remove current forming candle.
        if len(rows) > 2:
            rows = rows[:-1]
        out[tf] = rows

    return out


def get_timeframes(context: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    raw = context.get("timeframes") or context.get("timeframe_rates") or {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            key = str(key).upper()
            if key in TIMEFRAMES:
                rows = [normalize_candle(c) for c in list(value or [])]
                out[key] = rows[:-1] if len(rows) > 2 else rows

    for key in ("rates", "closed_rates", "candles", "m1_rates", "rates_m1", "bars"):
        if context.get(key) and "M1" not in out:
            rows = [normalize_candle(c) for c in list(context.get(key) or [])]
            rows = [r for r in rows if r]
            rows.sort(key=lambda x: int(x.get("time", 0) or 0))
            out["M1"] = rows[:-1] if len(rows) > 2 else rows

    direct = mt5_rates(symbol_from_context(context))
    for tf, rows in direct.items():
        if rows:
            out[tf] = rows

    return out


def candle_direction(c: Dict[str, Any]) -> str:
    if f(c.get("close")) > f(c.get("open")):
        return BUY
    if f(c.get("close")) < f(c.get("open")):
        return SELL
    return HOLD


def confirmed_swings(rates: List[Dict[str, Any]], left: int = 3, right: int = 3, max_bars: int = 300) -> List[Dict[str, Any]]:
    # Confirmed-only pivots. The right-side requirement prevents repainting.
    candles = list(rates or [])[-max_bars:]
    swings: List[Dict[str, Any]] = []
    if len(candles) < left + right + 1:
        return swings

    for i in range(left, len(candles) - right):
        c = candles[i]
        high = f(c.get("high"))
        low = f(c.get("low"))
        window_left = candles[i-left:i]
        window_right = candles[i+1:i+1+right]

        if all(high > f(x.get("high")) for x in window_left + window_right):
            swings.append({"type": "high", "price": high, "time": int(c.get("time", 0) or 0), "index": i})
        if all(low < f(x.get("low")) for x in window_left + window_right):
            swings.append({"type": "low", "price": low, "time": int(c.get("time", 0) or 0), "index": i})
    return swings


def latest_swing(swings: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    for s in reversed(swings):
        if s.get("type") == kind:
            return s
    return None


def bias_from_pair(high: Optional[Dict[str, Any]], low: Optional[Dict[str, Any]], last_close: float) -> str:
    if not high or not low:
        return HOLD
    # If last confirmed low came after high and price pushes up, bullish retracement context.
    if int(low.get("time", 0)) > int(high.get("time", 0)) and last_close > f(low["price"]):
        return BUY
    if int(high.get("time", 0)) > int(low.get("time", 0)) and last_close < f(high["price"]):
        return SELL
    return BUY if last_close > (f(high["price"]) + f(low["price"])) / 2 else SELL


def ote_zone(low: float, high: float, direction: str) -> Dict[str, float]:
    low = f(low); high = f(high)
    if high <= low:
        return {}
    rng = high - low
    if direction == BUY:
        return {"62": high - rng * 0.62, "705": high - rng * 0.705, "79": high - rng * 0.79}
    if direction == SELL:
        return {"62": low + rng * 0.62, "705": low + rng * 0.705, "79": low + rng * 0.79}
    return {}


def in_zone(price: float, zone: Dict[str, float]) -> bool:
    vals = [f(v) for v in zone.values() if f(v) > 0]
    return bool(vals) and min(vals) <= price <= max(vals)


def avg_volume(rates: List[Dict[str, Any]], period: int = 30) -> float:
    sample = list(rates or [])[-period:]
    if not sample:
        return 0.0
    return sum(f(c.get("tick_volume") or c.get("real_volume")) for c in sample) / len(sample)


def volume_confirm(rates: List[Dict[str, Any]], direction: str) -> bool:
    if len(rates) < 10:
        return False
    last = rates[-1]
    av = avg_volume(rates[:-1], 30)
    vol = f(last.get("tick_volume") or last.get("real_volume"))
    return av > 0 and vol >= av * 1.15 and candle_direction(last) == direction


def make_signal(action: str, reason: str, confidence: float, context: Dict[str, Any], data: Optional[Dict[str, Any]] = None, close_ticket: Any = None) -> Dict[str, Any]:
    action = str(action or HOLD).upper()
    if action not in (BUY, SELL, CLOSE, HOLD):
        action = HOLD

    rules = context.get("rules") or {}
    data = data or {}

    return {
        "enabled": True,
        "active": True,
        "valid": True,
        "strategy": "xauusd_m1_candle_strategy",
        "name": "xauusd_m1_candle_strategy",
        "symbol": symbol_from_context(context),
        "volume": f(rules.get("volume") or rules.get("trade_volume") or context.get("volume"), 0.01),
        "action": action,
        "signal": action,
        "trade_signal": action,
        "direction": action,
        "side": action,
        "mt5_action": action,
        "mt5_order_type": action,
        "order_type": action,
        "should_trade": action in (BUY, SELL),
        "execute": action in (BUY, SELL),
        "should_execute": action in (BUY, SELL),
        "should_close": action == CLOSE,
        "close_ticket": close_ticket,
        "confidence": max(0.0, min(f(confidence), 1.0)),
        "reason": reason,
        "thought": reason,
        "data": data,
    }


def h4_m15_structure(context: Dict[str, Any]) -> Dict[str, Any]:
    tfs = get_timeframes(context)
    h4 = tfs.get("H4", [])
    m15 = tfs.get("M15", [])
    m1 = tfs.get("M1", [])

    last_close = f((m1 or m15 or h4)[-1].get("close")) if (m1 or m15 or h4) else 0.0

    h4_swings = confirmed_swings(h4, 3, 3, 260)
    m15_swings = confirmed_swings(m15, 3, 3, 420)

    h4_high = latest_swing(h4_swings, "high")
    h4_low = latest_swing(h4_swings, "low")
    m15_high = latest_swing(m15_swings, "high")
    m15_low = latest_swing(m15_swings, "low")

    direction = bias_from_pair(h4_high, h4_low, last_close)
    if direction == HOLD:
        direction = bias_from_pair(m15_high, m15_low, last_close)

    ote_pair_high = m15_high or h4_high
    ote_pair_low = m15_low or h4_low
    zone = ote_zone(f(ote_pair_low.get("price")) if ote_pair_low else 0.0, f(ote_pair_high.get("price")) if ote_pair_high else 0.0, direction)

    return {
        "tfs": tfs,
        "last_close": last_close,
        "direction": direction,
        "h4_high": h4_high,
        "h4_low": h4_low,
        "m15_high": m15_high,
        "m15_low": m15_low,
        "ote_high": ote_pair_high,
        "ote_low": ote_pair_low,
        "ote_zone": zone,
        "inside_ote": in_zone(last_close, zone),
    }


def position_age_candles(position: Dict[str, Any], rates: List[Dict[str, Any]]) -> int:
    open_time = int(position.get("time", 0) or 0)
    if not open_time:
        return 0
    return len([c for c in rates if int(c.get("time", 0) or 0) > open_time])


def position_in_profit(position: Dict[str, Any], rates: List[Dict[str, Any]]) -> bool:
    if position.get("profit") is not None:
        return f(position.get("profit")) > 0
    if not rates:
        return False
    entry = f(position.get("price_open") or position.get("open_price") or position.get("entry_price"))
    close = f(rates[-1].get("close"))
    pos_type = int(position.get("type", 0) or 0)
    return close > entry if pos_type == 0 else close < entry


def build_decision(context: Dict[str, Any]) -> Dict[str, Any]:
    s = h4_m15_structure(context)
    m1 = s["tfs"].get("M1", [])
    m15 = s["tfs"].get("M15", [])
    rates = m1 or m15

    if not rates:
        return make_signal(HOLD, "HOLD: no closed candles available.", 0.0, context, data=s)

    positions = context.get("positions") or context.get("open_positions") or []
    if positions:
        p = positions[0]
        age = position_age_candles(p, m1 or rates)
        profit = position_in_profit(p, m1 or rates)
        ticket = p.get("ticket")
        close = f((m1 or rates)[-1]["close"])
        pos_type = int(p.get("type", 0) or 0)

        target = s["h4_high"] if pos_type == 0 else s["h4_low"]
        if target:
            tp = f(target["price"])
            if (pos_type == 0 and close >= tp) or (pos_type == 1 and close <= tp):
                return make_signal(CLOSE, "CLOSE: H4 liquidity target reached.", 1.0, context, close_ticket=ticket, data=s)

        if profit and age >= 7:
            return make_signal(CLOSE, f"CLOSE: profit after {age} closed M1 candles.", 1.0, context, close_ticket=ticket, data=s)
        if not profit and age >= 4:
            return make_signal(CLOSE, f"CLOSE: not in profit after {age} closed M1 candles.", 1.0, context, close_ticket=ticket, data=s)

        return make_signal(HOLD, f"HOLD: tracking open trade, candles_open={age}, in_profit={profit}.", 0.0, context, data=s)

    direction = s["direction"]
    if direction not in (BUY, SELL):
        return make_signal(HOLD, "HOLD: H4/M15 structure not clear.", 0.0, context, data=s)

    score = 1.0
    reasons = [f"{direction}: H4 external liquidity + M15 internal structure"]

    if s["inside_ote"]:
        score += 1.0
        reasons.append("price inside real OTE 62-79 zone")

    if volume_confirm(m1 or m15, direction):
        score += 0.75
        reasons.append("volume confirms execution direction")

    last_dir = candle_direction((m1 or m15)[-1])
    if last_dir == direction:
        score += 0.5
        reasons.append("last closed execution candle agrees")

    min_score = f((context.get("rules") or {}).get("min_confluence_score"), 1.0)
    action = direction if score >= min_score else HOLD
    return make_signal(action, "; ".join(reasons), min(score / 3.25, 1.0), context, data=s)


def draw_paths() -> List[Path]:
    raw = os.environ.get(DRAW_ENV)
    if raw:
        p = Path(raw)
        paths = [p]
        paths.append(p.with_suffix(".jsonl" if p.suffix.lower() == ".json1" else ".json1"))
        return paths
    cwd = Path.cwd()
    return [cwd / DRAW_JSON1, cwd / DRAW_JSONL]


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def build_draw_commands(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    s = (decision or {}).get("data") or h4_m15_structure(context)
    now = int(time.time())
    future = now + 60 * 24
    cmds: List[Dict[str, Any]] = [{"type": "clear_all"}]

    def seg(name: str, price: float, color: str, text: str, width: int = 2):
        if price <= 0:
            return
        cmds.append({"type": "segment", "name": name, "time1": now, "price1": price, "time2": future, "price2": price, "color": color, "width": width})
        cmds.append({"type": "text", "name": f"{name}_TXT", "time": future, "price": price, "color": color, "text": text})

    h4_high = s.get("h4_high")
    h4_low = s.get("h4_low")
    m15_high = s.get("m15_high")
    m15_low = s.get("m15_low")

    if h4_low:
        seg("TS_H4_EXTERNAL_LOW", f(h4_low["price"]), "green", f"H4 external sell-side liquidity {f(h4_low['price']):.2f}", 3)
    if h4_high:
        seg("TS_H4_EXTERNAL_HIGH", f(h4_high["price"]), "red", f"H4 external buy-side liquidity {f(h4_high['price']):.2f}", 3)
    if m15_low:
        seg("TS_M15_INTERNAL_LOW", f(m15_low["price"]), "green", f"M15 internal range low {f(m15_low['price']):.2f}", 2)
    if m15_high:
        seg("TS_M15_INTERNAL_HIGH", f(m15_high["price"]), "red", f"M15 internal range high {f(m15_high['price']):.2f}", 2)

    direction = s.get("direction", HOLD)
    zone = s.get("ote_zone") or {}
    if zone and direction in (BUY, SELL):
        for key, color in (("62", "yellow"), ("705", "blue"), ("79", "yellow")):
            price = f(zone.get(key))
            seg(f"TS_REAL_OTE_{key}", price, color, f"Real OTE {key} {direction} {price:.2f}", 1)

    if decision:
        action = decision.get("action", HOLD)
        reason = str(decision.get("reason", ""))[:140]
        last = f(s.get("last_close"))
        color = "green" if action == BUY else "red" if action == SELL else "yellow"
        cmds.append({"type": "text", "name": "TS_DECISION_REASON", "time": now, "price": last, "color": color, "text": f"{action}: {reason}"})

    return cmds


def write_draws(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> int:
    commands = build_draw_commands(context, decision)
    payload = {"version": 4, "source": "TradeSmartAI", "updated": time.time(), "command_count": len(commands), "commands": commands}
    for p in draw_paths():
        write_json(p, payload)
    return len(commands)


def write_debug(context: Dict[str, Any], result: Dict[str, Any], command_count: int) -> None:
    base = draw_paths()[0].parent
    write_json(base / DEBUG_FILE, {"updated": time.time(), "action": result.get("action"), "reason": result.get("reason"), "command_count": command_count, "data": result.get("data", {})})
