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


def f(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
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


def mt5_rates(symbol: str, include_forming: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        import MetaTrader5 as mt5
    except Exception:
        return out

    try:
        mt5.initialize()
    except Exception:
        pass

    mapping = {
        "M1": getattr(mt5, "TIMEFRAME_M1", None),
        "M5": getattr(mt5, "TIMEFRAME_M5", None),
        "H1": getattr(mt5, "TIMEFRAME_H1", None),
    }
    bars = {"M1": 1000, "M5": 600, "H1": 200}

    for tf, tf_const in mapping.items():
        if tf_const is None:
            continue
        try:
            raw = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars[tf])
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

        # Keep forming data for drawing the live first-5M range.
        # Strategy entry still uses closed candles only.
        if not include_forming and len(rows) > 2:
            rows = rows[:-1]

        out[tf] = rows

    return out


def get_timeframes(context: Dict[str, Any], include_forming: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    raw = context.get("timeframes") or context.get("timeframe_rates") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            tf = str(k).upper()
            if tf in ("M1", "M5", "H1"):
                rows = [normalize_candle(c) for c in list(v or [])]
                rows = [r for r in rows if r]
                rows.sort(key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows if include_forming else (rows[:-1] if len(rows) > 2 else rows)

    aliases = {
        "M1": ("rates", "closed_rates", "candles", "m1_rates", "rates_m1", "bars"),
        "M5": ("m5_rates", "rates_m5"),
        "H1": ("h1_rates", "rates_h1"),
    }

    for tf, keys in aliases.items():
        if tf in out:
            continue
        for key in keys:
            if context.get(key):
                rows = [normalize_candle(c) for c in list(context.get(key) or [])]
                rows = [r for r in rows if r]
                rows.sort(key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows if include_forming else (rows[:-1] if len(rows) > 2 else rows)
                break

    direct = mt5_rates(symbol_from_context(context), include_forming=include_forming)
    for tf, rows in direct.items():
        if rows:
            out[tf] = rows

    return out


def candle_direction(candle: Dict[str, Any]) -> str:
    if f(candle.get("close")) > f(candle.get("open")):
        return BUY
    if f(candle.get("close")) < f(candle.get("open")):
        return SELL
    return HOLD


def hour_start(ts: int) -> int:
    return int(ts) - (int(ts) % 3600)


def active_hour_open_range(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Current-hour first-5M range.

    It updates live from the current hour open using M1 candles during minute 00-04.
    Once the first M5 candle is closed, the wick range locks until the next hour.
    It never falls back to the previous hour unless there is no current-hour data at all.
    """
    tfs_live = get_timeframes(context, include_forming=True)
    tfs_closed = get_timeframes(context, include_forming=False)

    m1_live = tfs_live.get("M1", [])
    m5_live = tfs_live.get("M5", [])
    m1_closed = tfs_closed.get("M1", [])
    m5_closed = tfs_closed.get("M5", [])

    all_ref = m1_live or m5_live or m1_closed or m5_closed
    if not all_ref:
        return {"valid": False, "reason": "Waiting for M1/M5 candles.", "timeframes": tfs_closed, "live_timeframes": tfs_live}

    reference_ts = int(all_ref[-1].get("time", 0) or time.time())
    current_hour = hour_start(reference_ts)
    range_start = current_hour
    range_end = current_hour + 300

    first_m5_closed = [
        c for c in m5_closed
        if range_start <= int(c.get("time", 0) or 0) < range_end
    ]

    is_locked = False
    source = "live_m1_building"

    if first_m5_closed:
        candles = [first_m5_closed[-1]]
        is_locked = True
        source = "closed_m5_locked"
    else:
        # Build the current first-5M range live from M1 candles in the current hour.
        candles = [
            c for c in m1_live
            if range_start <= int(c.get("time", 0) or 0) < range_end
        ]

        # If MT5 has the current forming M5 but no M1s yet, use that for visual only.
        if not candles:
            live_m5 = [
                c for c in m5_live
                if range_start <= int(c.get("time", 0) or 0) < range_end
            ]
            candles = live_m5[-1:] if live_m5 else []

    if not candles:
        return {
            "valid": False,
            "reason": "Waiting for current hour first 5-minute range to start.",
            "timeframes": tfs_closed,
            "live_timeframes": tfs_live,
            "active_hour": current_hour,
            "locked": False,
        }

    high = max(f(c.get("high")) for c in candles)
    low = min(f(c.get("low")) for c in candles)
    open_ = f(candles[0].get("open"))
    close = f(candles[-1].get("close"))
    direction = BUY if close > open_ else SELL if close < open_ else HOLD

    return {
        "valid": high > low,
        "locked": is_locked,
        "source": source,
        "timeframes": tfs_closed,
        "live_timeframes": tfs_live,
        "active_hour": current_hour,
        "range_start": range_start,
        "range_end": range_end,
        "range_high": high,
        "range_low": low,
        "range_open": open_,
        "range_close": close,
        "range_mid": (high + low) / 2.0,
        "range_size": high - low,
        "range_direction": direction,
        "m1_parts_count": len(candles),
        "reason": "Current hour first-5M wick range is locked." if is_locked else "Current hour first-5M wick range is building live.",
    }


def tolerance(context: Dict[str, Any], setup: Dict[str, Any]) -> float:
    rules = context.get("rules") or {}
    explicit = f(rules.get("hour_open_range_tolerance") or rules.get("ray_touch_tolerance"), 0.0)
    if explicit > 0:
        return explicit
    return max(f(setup.get("range_size")) * 0.04, 0.20)


def hour_open_range_signal(context: Dict[str, Any]) -> Dict[str, Any]:
    setup = active_hour_open_range(context)
    if not setup.get("valid"):
        return {**setup, "action": HOLD, "score": 0.0}

    # Do not enter until first 5M candle is locked. Still draws live while building.
    if not setup.get("locked"):
        return {
            **setup,
            "action": HOLD,
            "score": 0.0,
            "entry_type": "building_range",
            "reason": f"HOLD: current hour first-5M wick range is building live {setup.get('range_low'):.2f}-{setup.get('range_high'):.2f}. Wait for 5M close.",
        }

    m1 = setup.get("timeframes", {}).get("M1", [])
    if len(m1) < 3:
        return {**setup, "action": HOLD, "score": 0.0, "reason": "Waiting for closed M1 execution candles."}

    last = m1[-1]
    prev = m1[-2]

    high = f(setup["range_high"])
    low = f(setup["range_low"])
    mid = f(setup["range_mid"])
    rng = f(setup["range_size"])
    tol = tolerance(context, setup)

    last_open = f(last.get("open"))
    last_high = f(last.get("high"))
    last_low = f(last.get("low"))
    last_close = f(last.get("close"))
    prev_close = f(prev.get("close"))

    bull = last_close >= last_open
    bear = last_close <= last_open

    buy_breakout = prev_close <= high and last_close > high and bull
    sell_breakdown = prev_close >= low and last_close < low and bear

    buy_retest_after_break = last_low <= high + tol and last_close > high and bull
    sell_retest_after_break = last_high >= low - tol and last_close < low and bear

    buy_support_respected = last_low <= low + tol and last_close > low and bull
    sell_resistance_respected = last_high >= high - tol and last_close < high and bear

    if buy_breakout:
        return {
            **setup,
            "action": BUY,
            "score": 1.0,
            "entry_type": "breakout_above_5m_high",
            "entry_level": high,
            "target_level": high + rng,
            "stop_reference": mid,
            "tolerance": tol,
            "reason": f"BUY: closed M1 broke above current hour first-5M wick high @ {high:.2f}.",
        }

    if sell_breakdown:
        return {
            **setup,
            "action": SELL,
            "score": 1.0,
            "entry_type": "breakdown_below_5m_low",
            "entry_level": low,
            "target_level": low - rng,
            "stop_reference": mid,
            "tolerance": tol,
            "reason": f"SELL: closed M1 broke below current hour first-5M wick low @ {low:.2f}.",
        }

    if buy_retest_after_break:
        return {
            **setup,
            "action": BUY,
            "score": 0.90,
            "entry_type": "high_retest_holding_as_support",
            "entry_level": high,
            "target_level": high + rng,
            "stop_reference": mid,
            "tolerance": tol,
            "reason": f"BUY: current hour first-5M high held as support @ {high:.2f}.",
        }

    if sell_retest_after_break:
        return {
            **setup,
            "action": SELL,
            "score": 0.90,
            "entry_type": "low_retest_holding_as_resistance",
            "entry_level": low,
            "target_level": low - rng,
            "stop_reference": mid,
            "tolerance": tol,
            "reason": f"SELL: current hour first-5M low held as resistance @ {low:.2f}.",
        }

    if buy_support_respected:
        return {
            **setup,
            "action": BUY,
            "score": 0.80,
            "entry_type": "range_low_respected",
            "entry_level": low,
            "target_level": high,
            "stop_reference": low - tol,
            "tolerance": tol,
            "reason": f"BUY: range low respected as support @ {low:.2f}.",
        }

    if sell_resistance_respected:
        return {
            **setup,
            "action": SELL,
            "score": 0.80,
            "entry_type": "range_high_respected",
            "entry_level": high,
            "target_level": low,
            "stop_reference": high + tol,
            "tolerance": tol,
            "reason": f"SELL: range high respected as resistance @ {high:.2f}.",
        }

    return {
        **setup,
        "action": HOLD,
        "score": 0.0,
        "entry_type": "waiting",
        "entry_level": None,
        "target_level": high if last_close >= mid else low,
        "stop_reference": mid,
        "tolerance": tol,
        "reason": f"HOLD: waiting for current hour first-5M range respect/break {low:.2f}-{high:.2f}.",
    }


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


def maybe_close(context: Dict[str, Any], setup: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    positions = context.get("positions") or context.get("open_positions") or []
    if not positions:
        return None

    m1 = setup.get("timeframes", {}).get("M1", [])
    if not m1:
        return None

    pos = positions[0]
    ticket = pos.get("ticket")
    age = position_age_candles(pos, m1)
    profit = position_in_profit(pos, m1)
    pos_type = int(pos.get("type", 0) or 0)
    close = f(m1[-1].get("close"))

    target = f(setup.get("target_level"))
    high = f(setup.get("range_high"))
    low = f(setup.get("range_low"))

    if pos_type == 0:
        if target > 0 and close >= target:
            return make_signal(CLOSE, f"CLOSE: BUY reached current hour range target @ {target:.2f}.", 1.0, context, data=setup, close_ticket=ticket)
        if profit and high > 0 and close >= high:
            return make_signal(CLOSE, f"CLOSE: BUY reached current first-5M high @ {high:.2f}.", 0.95, context, data=setup, close_ticket=ticket)

    if pos_type == 1:
        if target > 0 and close <= target:
            return make_signal(CLOSE, f"CLOSE: SELL reached current hour range target @ {target:.2f}.", 1.0, context, data=setup, close_ticket=ticket)
        if profit and low > 0 and close <= low:
            return make_signal(CLOSE, f"CLOSE: SELL reached current first-5M low @ {low:.2f}.", 0.95, context, data=setup, close_ticket=ticket)

    # Keep your original 4/7 candle close flow.
    if profit and age >= 7:
        return make_signal(CLOSE, f"CLOSE: profit after {age} closed M1 candles.", 1.0, context, data=setup, close_ticket=ticket)

    if not profit and age >= 4:
        return make_signal(CLOSE, f"CLOSE: not in profit after {age} closed M1 candles.", 1.0, context, data=setup, close_ticket=ticket)

    return make_signal(HOLD, f"HOLD: tracking open position, candles_open={age}, in_profit={profit}.", 0.0, context, data=setup)


def build_decision(context: Dict[str, Any]) -> Dict[str, Any]:
    setup = hour_open_range_signal(context)

    close_signal = maybe_close(context, setup)
    if close_signal is not None:
        return close_signal

    return make_signal(
        setup.get("action", HOLD),
        str(setup.get("reason", "HOLD: waiting for current hour first-5M range.")),
        f(setup.get("score"), 0.0),
        context,
        data=setup,
    )


def draw_paths() -> List[Path]:
    raw = os.environ.get(DRAW_ENV)
    if raw:
        p = Path(raw)
        return [p, p.with_suffix(".jsonl" if p.suffix.lower() == ".json1" else ".json1")]
    cwd = Path.cwd()
    return [cwd / DRAW_JSON1, cwd / DRAW_JSONL]


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def build_draw_commands(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = (decision or {}).get("data") or active_hour_open_range(context)
    commands: List[Dict[str, Any]] = [{"type": "clear_all"}]

    if not data.get("valid"):
        return commands

    start = int(data.get("range_start") or data.get("active_hour") or 0)
    end = int(data.get("range_end") or start + 300)

    high = f(data.get("range_high"))
    low = f(data.get("range_low"))
    open_ = f(data.get("range_open"))
    mid = f(data.get("range_mid"))
    close = f(data.get("range_close"))
    direction = data.get("range_direction", HOLD)
    locked = bool(data.get("locked"))

    status = "LOCKED" if locked else "LIVE BUILDING"
    bias_color = "green" if direction == BUY else "red" if direction == SELL else "yellow"

    commands.extend([
        {"type": "box", "name": "TS_CURRENT_HOUR_5M_RANGE_BOX", "time1": start, "time2": end, "price1": high, "price2": low, "color": "gray", "text": f"{status} FIRST 5M RANGE"},
        {"type": "ray", "name": "TS_CURRENT_HOUR_5M_HIGH", "time1": start, "price1": high, "color": "yellow", "width": 2, "text": f"{status} 5M WICK HIGH {high:.2f}"},
        {"type": "ray", "name": "TS_CURRENT_HOUR_5M_LOW", "time1": start, "price1": low, "color": "green", "width": 2, "text": f"{status} 5M WICK LOW {low:.2f}"},
        {"type": "ray", "name": "TS_CURRENT_HOUR_5M_MID", "time1": start, "price1": mid, "color": "gray", "width": 1, "text": f"{status} MID {mid:.2f}"},
        {"type": "ray", "name": "TS_CURRENT_HOUR_5M_OPEN", "time1": start, "price1": open_, "color": "blue", "width": 1, "text": f"{status} OPEN {open_:.2f}"},
        {"type": "text", "name": "TS_CURRENT_HOUR_5M_DECISION", "time": int(time.time()) + 60 * 8, "price": close, "color": bias_color, "text": f"{status} CURRENT HOUR 5M RANGE: {direction}\\n{str((decision or {}).get('reason', data.get('reason', '')))}"},
    ])

    for key, name, color in (
        ("entry_level", "TS_ENTRY_AREA", bias_color),
        ("target_level", "TS_TARGET", "blue"),
        ("stop_reference", "TS_STOP_REFERENCE", "orange"),
    ):
        value = data.get(key)
        if value is not None:
            commands.append({"type": "ray", "name": name, "time1": start, "price1": f(value), "color": color, "width": 2, "text": f"{key.replace('_', ' ').upper()} {f(value):.2f}"})

    return commands


def write_draws(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> int:
    commands = build_draw_commands(context, decision)
    payload = {
        "version": 11,
        "source": "TradeSmartAI",
        "strategy": "live_current_hour_first_5m_range",
        "updated": time.time(),
        "command_count": len(commands),
        "commands": commands,
    }
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
