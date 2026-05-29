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

TIMEFRAMES = ["H4", "M15", "M5", "M1"]
TF_BARS = {"H4": 260, "M15": 420, "M5": 360, "M1": 500}
TF_WEIGHT = {"H4": 3.0, "M15": 2.0, "M5": 1.25, "M1": 1.0}
SWING_DEPTH = 3


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
    if candle is None:
        return {}
    if isinstance(candle, dict):
        return candle
    out: Dict[str, Any] = {}
    for key in ("time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume", "volume"):
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
        "M5": getattr(mt5, "TIMEFRAME_M5", None),
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

        # Non-repaint: remove forming candle.
        if len(rows) > 2:
            rows = rows[:-1]
        out[tf] = rows

    return out


def get_timeframes(context: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    raw = context.get("timeframes") or context.get("timeframe_rates") or {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            tf = str(key).upper()
            if tf in TIMEFRAMES:
                rows = [normalize_candle(c) for c in list(value or [])]
                rows = [r for r in rows if r]
                rows.sort(key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows[:-1] if len(rows) > 2 else rows

    aliases = {
        "M1": ("rates", "closed_rates", "candles", "m1_rates", "rates_m1", "bars"),
        "M5": ("m5_rates", "rates_m5"),
        "M15": ("m15_rates", "rates_m15"),
        "H4": ("h4_rates", "rates_h4"),
    }
    for tf, keys in aliases.items():
        if tf in out:
            continue
        for key in keys:
            if context.get(key):
                rows = [normalize_candle(c) for c in list(context.get(key) or [])]
                rows = [r for r in rows if r]
                rows.sort(key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows[:-1] if len(rows) > 2 else rows
                break

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


def candle_volume(c: Dict[str, Any]) -> float:
    return f(c.get("tick_volume") or c.get("real_volume") or c.get("volume"), 0.0)


def avg_volume(rates: List[Dict[str, Any]], period: int = 30) -> float:
    sample = list(rates or [])[-period:]
    if not sample:
        return 0.0
    return sum(candle_volume(c) for c in sample) / len(sample)


def volume_confirm(rates: List[Dict[str, Any]], direction: str) -> bool:
    if len(rates) < 12 or direction not in (BUY, SELL):
        return False
    last = rates[-1]
    av = avg_volume(rates[:-1], 30)
    vol = candle_volume(last)
    return av > 0 and vol >= av * 1.15 and candle_direction(last) == direction


def confirmed_swings(rates: List[Dict[str, Any]], left: int = SWING_DEPTH, right: int = SWING_DEPTH, max_bars: int = 500) -> List[Dict[str, Any]]:
    candles = list(rates or [])[-max_bars:]
    swings: List[Dict[str, Any]] = []

    if len(candles) < left + right + 1:
        return swings

    for i in range(left, len(candles) - right):
        c = candles[i]
        high = f(c.get("high"))
        low = f(c.get("low"))
        left_side = candles[i - left:i]
        right_side = candles[i + 1:i + 1 + right]

        if all(high > f(x.get("high")) for x in left_side + right_side):
            swings.append({"type": "high", "price": high, "time": int(c.get("time", 0) or 0), "index": i})

        if all(low < f(x.get("low")) for x in left_side + right_side):
            swings.append({"type": "low", "price": low, "time": int(c.get("time", 0) or 0), "index": i})

    return swings


def latest_swing(swings: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    for swing in reversed(swings or []):
        if swing.get("type") == kind:
            return swing
    return None


def structure_for_tf(rates: List[Dict[str, Any]], max_bars: int) -> Dict[str, Any]:
    swings = confirmed_swings(rates, max_bars=max_bars)
    last_high = latest_swing(swings, "high")
    last_low = latest_swing(swings, "low")

    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    prev_high = highs[-2] if len(highs) >= 2 else None
    prev_low = lows[-2] if len(lows) >= 2 else None

    close = f(rates[-1].get("close")) if rates else 0.0
    eq = 0.0
    bias = HOLD
    label = "neutral"

    if last_high and last_low:
        eq = (f(last_high["price"]) + f(last_low["price"])) / 2.0

        if close > f(last_high["price"]):
            bias = BUY
            label = "bullish BOS"
        elif close < f(last_low["price"]):
            bias = SELL
            label = "bearish BOS"
        elif prev_high and prev_low:
            if f(last_high["price"]) > f(prev_high["price"]) and f(last_low["price"]) > f(prev_low["price"]):
                bias = BUY
                label = "bullish structure"
            elif f(last_high["price"]) < f(prev_high["price"]) and f(last_low["price"]) < f(prev_low["price"]):
                bias = SELL
                label = "bearish structure"
            else:
                bias = BUY if close >= eq else SELL
                label = "above EQ" if bias == BUY else "below EQ"
        else:
            bias = BUY if close >= eq else SELL
            label = "above EQ" if bias == BUY else "below EQ"

    return {
        "last_high": last_high,
        "prev_high": prev_high,
        "last_low": last_low,
        "prev_low": prev_low,
        "eq": eq,
        "bias": bias,
        "label": label,
        "close": close,
        "swings_count": len(swings),
    }


def all_structures(context: Dict[str, Any]) -> Dict[str, Any]:
    tfs = get_timeframes(context)
    structures: Dict[str, Any] = {}
    for tf in TIMEFRAMES:
        structures[tf] = structure_for_tf(tfs.get(tf, []), TF_BARS[tf])
    return {"timeframes": tfs, "structures": structures}


def combined_direction(structures: Dict[str, Any]) -> str:
    buy = 0.0
    sell = 0.0
    for tf, st in structures.items():
        if st.get("bias") == BUY:
            buy += TF_WEIGHT.get(tf, 1.0)
        elif st.get("bias") == SELL:
            sell += TF_WEIGHT.get(tf, 1.0)
    if buy > sell:
        return BUY
    if sell > buy:
        return SELL
    return HOLD


def ote_zone(low: float, high: float, direction: str) -> Dict[str, float]:
    low = f(low)
    high = f(high)
    if high <= low:
        return {}
    rng = high - low
    if direction == BUY:
        return {"62": high - rng * 0.62, "705": high - rng * 0.705, "79": high - rng * 0.79}
    if direction == SELL:
        return {"62": low + rng * 0.62, "705": low + rng * 0.705, "79": low + rng * 0.79}
    return {}


def price_in_zone(price: float, zone: Dict[str, float]) -> bool:
    vals = [f(v) for v in zone.values() if f(v) > 0]
    return bool(vals) and min(vals) <= price <= max(vals)


def build_ote(structures: Dict[str, Any], direction: str) -> Dict[str, Any]:
    # Prefer M15 swing pair, then M5. This matches the visual EA.
    for tf in ("M15", "M5"):
        st = structures.get(tf, {})
        hi = st.get("last_high")
        lo = st.get("last_low")
        if hi and lo:
            zone = ote_zone(f(lo["price"]), f(hi["price"]), direction)
            return {"tf": tf, "high": hi, "low": lo, "zone": zone}
    return {"tf": None, "zone": {}}


def make_signal(action: str, reason: str, confidence: float, context: Dict[str, Any], data: Optional[Dict[str, Any]] = None, close_ticket: Any = None) -> Dict[str, Any]:
    action = str(action or HOLD).upper()
    if action not in (BUY, SELL, CLOSE, HOLD):
        action = HOLD

    rules = context.get("rules") or {}
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
        "data": data or {},
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
    packed = all_structures(context)
    tfs = packed["timeframes"]
    structures = packed["structures"]
    m1 = tfs.get("M1", [])

    if not m1:
        return make_signal(HOLD, "HOLD: no closed M1 candles available.", 0.0, context, data=packed)

    positions = context.get("positions") or context.get("open_positions") or []
    if positions:
        pos = positions[0]
        age = position_age_candles(pos, m1)
        profit = position_in_profit(pos, m1)
        ticket = pos.get("ticket")
        pos_type = int(pos.get("type", 0) or 0)
        close = f(m1[-1].get("close"))
        h4 = structures.get("H4", {})
        target = h4.get("last_high") if pos_type == 0 else h4.get("last_low")

        if target:
            tp = f(target["price"])
            hit = (pos_type == 0 and close >= tp) or (pos_type == 1 and close <= tp)
            if hit:
                return make_signal(CLOSE, "CLOSE: H4 recent swing liquidity target reached.", 1.0, context, data=packed, close_ticket=ticket)

        if profit and age >= 7:
            return make_signal(CLOSE, f"CLOSE: profit after {age} closed M1 candles.", 1.0, context, data=packed, close_ticket=ticket)
        if not profit and age >= 4:
            return make_signal(CLOSE, f"CLOSE: not in profit after {age} closed M1 candles.", 1.0, context, data=packed, close_ticket=ticket)

        return make_signal(HOLD, f"HOLD: tracking open trade, candles_open={age}, in_profit={profit}.", 0.0, context, data=packed)

    direction = combined_direction(structures)
    if direction not in (BUY, SELL):
        return make_signal(HOLD, "HOLD: H4/M15/M5/M1 recent swing structure is mixed.", 0.0, context, data=packed)

    score = 0.0
    reasons: List[str] = []

    h4 = structures.get("H4", {})
    m15 = structures.get("M15", {})
    m5 = structures.get("M5", {})
    m1s = structures.get("M1", {})

    if h4.get("bias") == direction:
        score += 1.25
        reasons.append(f"H4 {h4.get('label')}")
    if m15.get("bias") == direction:
        score += 1.10
        reasons.append(f"M15 {m15.get('label')}")
    if m5.get("bias") == direction:
        score += 0.75
        reasons.append(f"M5 {m5.get('label')}")
    if m1s.get("bias") == direction:
        score += 0.50
        reasons.append(f"M1 {m1s.get('label')}")

    ote = build_ote(structures, direction)
    packed["ote"] = ote
    price = f(m1[-1].get("close"))
    if price_in_zone(price, ote.get("zone") or {}):
        score += 0.75
        reasons.append("price inside aligned M15/M5 OTE")

    if volume_confirm(m1, direction):
        score += 0.50
        reasons.append("M1 volume confirms direction")

    if candle_direction(m1[-1]) == direction:
        score += 0.35
        reasons.append("last closed M1 candle agrees")

    min_score = f((context.get("rules") or {}).get("min_confluence_score"), 1.50)
    action = direction if score >= min_score else HOLD

    return make_signal(
        action,
        "; ".join(reasons) if reasons else "HOLD: no aligned recent swing confluence.",
        min(score / 4.70, 1.0),
        context,
        data=packed,
    )


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


def seg(commands: List[Dict[str, Any]], name: str, price: float, color: str, text: str, width: int = 2, now: Optional[int] = None) -> None:
    if price <= 0:
        return
    now = now or int(time.time())
    future = now + 60 * 12
    commands.append({"type": "segment", "name": name, "time1": now - 60 * 28, "price1": price, "time2": future, "price2": price, "color": color, "width": width})
    commands.append({"type": "text", "name": f"{name}_TXT", "time": future, "price": price, "color": color, "text": text})


def build_draw_commands(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = (decision or {}).get("data") or all_structures(context)
    structures = data.get("structures", {})
    tfs = data.get("timeframes", {})
    m1 = tfs.get("M1", [])
    current = f(m1[-1].get("close")) if m1 else 0.0
    now = int(time.time())

    commands: List[Dict[str, Any]] = [{"type": "clear_all"}]

    for tf, width in (("H4", 3), ("M15", 2), ("M5", 1)):
        st = structures.get(tf, {})
        low = st.get("last_low")
        high = st.get("last_high")
        if low and f(low.get("price")) < current:
            seg(commands, f"TS_{tf}_RECENT_SUPPORT", f(low["price"]), "green", f"{tf} recent swing support / SSL {f(low['price']):.2f}", width, now)
        if high and f(high.get("price")) > current:
            seg(commands, f"TS_{tf}_RECENT_RESISTANCE", f(high["price"]), "red", f"{tf} recent swing resistance / BSL {f(high['price']):.2f}", width, now)

    m1s = structures.get("M1", {})
    for kind, color in (("last_low", "green"), ("last_high", "red")):
        sw = m1s.get(kind)
        if sw:
            price = f(sw.get("price"))
            commands.append({"type": "text", "name": f"TS_M1_{kind.upper()}_LABEL", "time": int(sw.get("time") or now), "price": price, "color": color, "text": f"M1 recent swing {'low' if kind == 'last_low' else 'high'} {price:.2f}"})

    direction = (decision or {}).get("action") or combined_direction(structures)
    ote = data.get("ote") or build_ote(structures, direction)
    zone = ote.get("zone") or {}
    if direction in (BUY, SELL) and zone:
        for key, color in (("62", "yellow"), ("705", "orange"), ("79", "yellow")):
            price = f(zone.get(key))
            seg(commands, f"TS_OTE_{key}", price, color, f"OTE {key} {direction} {price:.2f}", 1, now)

    if decision and current > 0:
        action = decision.get("action", HOLD)
        reason = str(decision.get("reason", ""))[:160]
        color = "green" if action == BUY else "red" if action == SELL else "yellow"
        commands.append({"type": "text", "name": "TS_DECISION_RECENT_SWING", "time": now + 60 * 8, "price": current, "color": color, "text": f"{action}: {reason}"})

    return commands


def write_draws(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> int:
    commands = build_draw_commands(context, decision)
    payload = {"version": 7, "source": "TradeSmartAI", "updated": time.time(), "command_count": len(commands), "commands": commands}
    for p in draw_paths():
        write_json(p, payload)
    return len(commands)


def write_debug(context: Dict[str, Any], result: Dict[str, Any], command_count: int) -> None:
    base = draw_paths()[0].parent
    write_json(base / DEBUG_FILE, {
        "updated": time.time(),
        "action": result.get("action"),
        "reason": result.get("reason"),
        "confidence": result.get("confidence"),
        "command_count": command_count,
        "data": result.get("data", {}),
    })
