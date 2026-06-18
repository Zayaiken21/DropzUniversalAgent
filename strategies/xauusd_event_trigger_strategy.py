from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

BUY = "BUY"
SELL = "SELL"
CLOSE = "CLOSE"
HOLD = "HOLD"
SCAN = "SCAN"
NONE = "NONE"
FIRST_15M_SECONDS = 900
HOUR_SECONDS = 3600
VALUE_AREA_RATIO = 0.70


def f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def closed(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return candles[:-1] if len(candles) > 1 else list(candles or [])


def floor_1h(ts: int) -> int:
    return int(ts) - (int(ts) % HOUR_SECONDS)


def candle_bias(rows: List[Dict[str, Any]], lookback: int = 8) -> str:
    sample = closed(rows)[-lookback:]
    if len(sample) < 2:
        return HOLD
    highs = [f(c.get("high")) for c in sample]
    lows = [f(c.get("low")) for c in sample]
    closes = [f(c.get("close")) for c in sample]
    if closes[-1] > closes[0] and highs[-1] >= max(highs[:-1]):
        return BUY
    if closes[-1] < closes[0] and lows[-1] <= min(lows[:-1]):
        return SELL
    last = sample[-1]
    if f(last.get("close")) > f(last.get("open")):
        return BUY
    if f(last.get("close")) < f(last.get("open")):
        return SELL
    return HOLD


def wick_targets(rows: List[Dict[str, Any]], current_price: float, lookback: int = 20) -> Dict[str, Any]:
    sample = closed(rows)[-lookback:]
    if not sample:
        return {"valid": False, "high": 0.0, "low": 0.0, "mid": current_price, "bias": HOLD, "location": "UNKNOWN"}
    hi = max(f(c.get("high")) for c in sample)
    lo = min(f(c.get("low")) for c in sample)
    mid = (hi + lo) / 2.0 if hi > lo else current_price
    return {
        "valid": True,
        "high": round(hi, 2),
        "low": round(lo, 2),
        "mid": round(mid, 2),
        "bias": candle_bias(rows),
        "location": "DISCOUNT" if current_price <= mid else "PREMIUM",
        "distance_to_high": round(max(0.0, hi - current_price), 2),
        "distance_to_low": round(max(0.0, current_price - lo), 2),
    }


def session_name(ts: int) -> Dict[str, Any]:
    try:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        h = dt.hour
        dow = dt.weekday()
        if 0 <= h < 7:
            name, quality = "ASIA", 0.55
        elif 7 <= h < 12:
            name, quality = "LONDON", 0.85
        elif 12 <= h < 17:
            name, quality = "NEW_YORK_AM", 1.0
        elif 17 <= h < 21:
            name, quality = "NEW_YORK_PM", 0.72
        else:
            name, quality = "ROLLOVER", 0.30
        return {"name": name, "quality": quality, "tradable": dow < 5, "hour": h, "weekday": dow}
    except Exception:
        return {"name": "UNKNOWN", "quality": 0.5, "tradable": True}


def avg_volume(rows: List[Dict[str, Any]], n: int = 20) -> float:
    vols = [f(c.get("tick_volume")) for c in closed(rows)[-n:] if f(c.get("tick_volume")) > 0]
    return sum(vols) / len(vols) if vols else 1.0


def volume_ratio(rows: List[Dict[str, Any]]) -> float:
    cs = closed(rows)
    if len(cs) < 3:
        return 1.0
    return round(f(cs[-1].get("tick_volume"), 1.0) / max(avg_volume(cs[:-1]), 1.0), 2)


def volume_profile(rows: List[Dict[str, Any]], bins: int = 24) -> Dict[str, Any]:
    sample = [c for c in rows if f(c.get("high")) > f(c.get("low"))]
    if len(sample) < 5:
        return {"valid": False}
    lo = min(f(c.get("low")) for c in sample)
    hi = max(f(c.get("high")) for c in sample)
    if hi <= lo:
        return {"valid": False}
    bins = max(8, min(80, bins))
    step = (hi - lo) / bins
    hist = [0.0] * bins
    for c in sample:
        mid = (f(c.get("high")) + f(c.get("low")) + f(c.get("close"))) / 3.0
        idx = max(0, min(bins - 1, int((mid - lo) / step)))
        hist[idx] += max(1.0, f(c.get("tick_volume"), 1.0))
    total = sum(hist)
    poc_i = max(range(bins), key=lambda i: hist[i])
    low_i = high_i = poc_i
    acc = hist[poc_i]
    while acc < total * VALUE_AREA_RATIO and (low_i > 0 or high_i < bins - 1):
        left = hist[low_i - 1] if low_i > 0 else -1
        right = hist[high_i + 1] if high_i < bins - 1 else -1
        if right >= left and high_i < bins - 1:
            high_i += 1
            acc += hist[high_i]
        elif low_i > 0:
            low_i -= 1
            acc += hist[low_i]
        else:
            break
    price = lambda i: round(lo + (i + 0.5) * step, 2)
    return {"valid": True, "poc": price(poc_i), "vah": price(high_i), "val": price(low_i), "high": round(hi, 2), "low": round(lo, 2)}


def recent_atr(rows: List[Dict[str, Any]], n: int = 14) -> float:
    """Average true-range-style volatility measure used to scale tolerances
    instead of a single fixed-dollar tolerance, so the strategy adapts to
    quiet vs fast XAUUSD conditions instead of using one tolerance for both.
    """
    sample = closed(rows)[-n:]
    if len(sample) < 2:
        return 0.0
    trs = []
    prev_close = f(sample[0].get("close"))
    for c in sample[1:]:
        hi, lo, cl = f(c.get("high")), f(c.get("low")), f(c.get("close"))
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs.append(tr)
        prev_close = cl
    return sum(trs) / len(trs) if trs else 0.0


def liquidity_sweep(rows: List[Dict[str, Any]], lookback: int = 30, recent: int = 3) -> Dict[str, Any]:
    """Detect a swing high/low sweep with rejection — the classic SMC
    'stop hunt then reverse' event, not just a touch of an old extreme.

    A sweep is valid when:
      1) a prior swing high/low (from the lookback window, excluding the
         most recent `recent` candles) is taken out, and
      2) the candle that took it out closes back inside the prior range
         (rejection), showing the breakout failed to hold.
    """
    sample = closed(rows)[-lookback:]
    if len(sample) < recent + 5:
        return {"valid": False}
    history = sample[:-recent]
    tail = sample[-recent:]
    if not history or not tail:
        return {"valid": False}
    prior_high = max(f(c.get("high")) for c in history)
    prior_low = min(f(c.get("low")) for c in history)
    result = {"valid": True, "prior_high": round(prior_high, 2), "prior_low": round(prior_low, 2),
               "swept_high": False, "swept_low": False, "sweep_time": 0}
    for c in tail:
        hi, lo, cl, op = f(c.get("high")), f(c.get("low")), f(c.get("close")), f(c.get("open"))
        ts = int(c.get("time", 0) or 0)
        if hi > prior_high and cl < prior_high:
            result["swept_high"] = True
            result["sweep_time"] = ts
            result["sweep_price"] = round(hi, 2)
        if lo < prior_low and cl > prior_low:
            result["swept_low"] = True
            result["sweep_time"] = ts
            result["sweep_price"] = round(lo, 2)
    return result


def order_blocks(rows: List[Dict[str, Any]], lookback: int = 40, displacement_mult: float = 1.6) -> Dict[str, Any]:
    """Find the most recent bullish and bearish order blocks: the last
    opposing candle before a displacement move (a candle whose range is
    meaningfully larger than the local average), which is the standard
    SMC definition rather than just "any candle before a big move".
    """
    sample = closed(rows)[-lookback:]
    out: Dict[str, Any] = {"bullish": None, "bearish": None}
    if len(sample) < 6:
        return out
    ranges = [max(f(c.get("high")) - f(c.get("low")), 0.0) for c in sample]
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0
    if avg_range <= 0:
        return out
    for i in range(1, len(sample)):
        candle = sample[i]
        rng = ranges[i]
        if rng < avg_range * displacement_mult:
            continue
        op, cl = f(candle.get("open")), f(candle.get("close"))
        prev = sample[i - 1]
        p_op, p_cl, p_hi, p_lo = f(prev.get("open")), f(prev.get("close")), f(prev.get("high")), f(prev.get("low"))
        ts = int(prev.get("time", 0) or 0)
        if cl > op and p_cl < p_op:
            out["bullish"] = {"high": round(p_hi, 2), "low": round(p_lo, 2), "time": ts}
        elif cl < op and p_cl > p_op:
            out["bearish"] = {"high": round(p_hi, 2), "low": round(p_lo, 2), "time": ts}
    return out


def fair_value_gaps(rows: List[Dict[str, Any]], lookback: int = 40, current_price: float = 0.0) -> Dict[str, Any]:
    """Detect the most recent unfilled bullish/bearish fair value gaps using
    the standard 3-candle imbalance definition: candle1.high < candle3.low
    (bullish gap) or candle1.low > candle3.high (bearish gap). A gap is
    treated as filled once price has traded back through it.
    """
    sample = closed(rows)[-lookback:]
    out: Dict[str, Any] = {"bullish": None, "bearish": None}
    if len(sample) < 3:
        return out
    for i in range(2, len(sample)):
        c1, c3 = sample[i - 2], sample[i]
        hi1, lo1 = f(c1.get("high")), f(c1.get("low"))
        hi3, lo3 = f(c3.get("high")), f(c3.get("low"))
        ts = int(sample[i - 1].get("time", 0) or 0)
        if hi1 < lo3:
            gap = {"top": round(lo3, 2), "bottom": round(hi1, 2), "time": ts}
            filled = current_price > 0 and current_price <= gap["bottom"]
            if not filled:
                out["bullish"] = gap
        elif lo1 > hi3:
            gap = {"top": round(lo1, 2), "bottom": round(hi3, 2), "time": ts}
            filled = current_price > 0 and current_price >= gap["top"]
            if not filled:
                out["bearish"] = gap
    return out


def session_range(m1: List[Dict[str, Any]], start_hour: int, end_hour: int, ref_ts: Optional[int] = None) -> Dict[str, Any]:
    """Generalized UTC-hour session range builder (Asia/London/etc.) using
    the same shape as first15_hour_range so draw_commands() can render any
    number of session ranges with one loop instead of one hardcoded range.
    Handles sessions that wrap past midnight (start_hour > end_hour).
    """
    if not m1:
        return {"valid": False, "reason": "No M1 data."}
    from datetime import datetime, timezone
    ts = int(ref_ts if ref_ts is not None else (m1[-1].get("time") or time.time()))
    day_start = ts - (ts % 86400)
    win_start = day_start + start_hour * HOUR_SECONDS
    win_end = day_start + end_hour * HOUR_SECONDS if end_hour > start_hour else day_start + 86400 + end_hour * HOUR_SECONDS
    # If the window already fully passed today, use yesterday's window instead
    # so a session range is always available rather than going stale at the
    # very start of a new UTC day.
    if ts >= win_end:
        win_start -= 86400
        win_end -= 86400
    window = [c for c in m1 if win_start <= int(c.get("time", 0) or 0) < min(ts, win_end)]
    if not window:
        return {"valid": False, "reason": "No candles in session window yet.", "range_start": win_start, "range_end": win_end}
    hi = max(f(c.get("high")) for c in window)
    lo = min(f(c.get("low")) for c in window)
    if hi <= lo:
        return {"valid": False, "reason": "Session window has no size yet.", "range_start": win_start, "range_end": win_end}
    return {
        "valid": True,
        "range_start": win_start,
        "range_end": win_end,
        "range_high": round(hi, 2),
        "range_low": round(lo, 2),
        "range_mid": round((hi + lo) / 2.0, 2),
        "range_size": round(hi - lo, 2),
        "complete": ts >= win_end,
    }


def previous_day_range(d1: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Previous completed daily candle's high/low/mid — a standard SMC
    reference level (PDH/PDL) independent of the intraday session ranges.
    """
    sample = closed(d1)
    if not sample:
        return {"valid": False, "reason": "No D1 history."}
    bar = sample[-1]
    hi, lo = f(bar.get("high")), f(bar.get("low"))
    if hi <= lo:
        return {"valid": False, "reason": "Previous day candle has no size."}
    return {
        "valid": True,
        "range_start": int(bar.get("time", 0) or 0),
        "range_high": round(hi, 2),
        "range_low": round(lo, 2),
        "range_mid": round((hi + lo) / 2.0, 2),
        "range_size": round(hi - lo, 2),
    }


def first15_hour_range(m1: List[Dict[str, Any]], m15: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not m1:
        return {"valid": False, "reason": "No M1 data."}
    ref_ts = int(m1[-1].get("time", time.time()) or time.time())
    hour_start = floor_1h(ref_ts)
    first_end = hour_start + FIRST_15M_SECONDS
    hour_end = hour_start + HOUR_SECONDS
    m15_closed = closed(m15)
    locked = [c for c in m15_closed if int(c.get("time", 0) or 0) == hour_start]
    if locked:
        bar = locked[-1]
        source = "locked_first_15m"
        is_locked = True
        window = [bar]
    else:
        window = [c for c in m1 if hour_start <= int(c.get("time", 0) or 0) < min(ref_ts + 60, first_end)]
        source = "building_first_15m"
        is_locked = False
    if not window:
        return {"valid": False, "reason": "Waiting for active hour first M1 candle.", "range_start": hour_start, "range_end": hour_end, "first_15m_end": first_end}
    hi = max(f(c.get("high")) for c in window)
    lo = min(f(c.get("low")) for c in window)
    op = f(window[0].get("open"))
    cl = f(window[-1].get("close"))
    if hi <= lo:
        return {"valid": False, "reason": "Hourly first15 range has no size yet.", "range_start": hour_start, "range_end": hour_end, "first_15m_end": first_end}
    return {
        "valid": True,
        "locked": is_locked,
        "source": source,
        "range_start": hour_start,
        "range_end": hour_end,
        "first_15m_end": first_end,
        "range_high": round(hi, 2),
        "range_low": round(lo, 2),
        "range_mid": round((hi + lo) / 2.0, 2),
        "range_size": round(hi - lo, 2),
        "range_open": round(op, 2),
        "range_close": round(cl, 2),
        "range_bias": BUY if cl > op else SELL if cl < op else HOLD,
    }


def rejection_trigger(m1: List[Dict[str, Any]], m5: List[Dict[str, Any]], side: str, zone: float, tol: float) -> Dict[str, Any]:
    c1s = closed(m1)
    c5s = closed(m5)
    last1 = c1s[-1] if c1s else {}
    last5 = c5s[-1] if c5s else {}
    if not last1:
        return {"ok": False, "reason": "No closed M1 trigger."}
    op, cl, hi, lo = f(last1.get("open")), f(last1.get("close")), f(last1.get("high")), f(last1.get("low"))
    body = abs(cl - op)
    candle_range = max(hi - lo, 0.01)
    # Displacement: the close needs to recover a meaningful share of the
    # candle's own range away from the zone, not just barely close back
    # over the line. This filters out weak one-tick reclaims that the old
    # touch+reclaim check would have accepted.
    if side == BUY:
        touched = lo <= zone + tol
        reclaimed = cl >= zone - tol
        recovery = (cl - lo) / candle_range if candle_range else 0.0
        displaced = recovery >= 0.45
        candle_ok = cl >= op or abs(cl - op) <= max((hi - lo) * 0.25, 0.05)
        m5_stall = bool(last5) and f(last5.get("low")) <= zone + tol and f(last5.get("close")) >= zone - tol
    else:
        touched = hi >= zone - tol
        reclaimed = cl <= zone + tol
        recovery = (hi - cl) / candle_range if candle_range else 0.0
        displaced = recovery >= 0.45
        candle_ok = cl <= op or abs(cl - op) <= max((hi - lo) * 0.25, 0.05)
        m5_stall = bool(last5) and f(last5.get("high")) >= zone - tol and f(last5.get("close")) <= zone + tol
    ok = touched and reclaimed and (candle_ok or m5_stall) and (displaced or m5_stall)
    return {
        "ok": ok, "touched": touched, "reclaimed": reclaimed, "candle_ok": candle_ok,
        "m5_stall": m5_stall, "displaced": displaced, "recovery": round(recovery, 2),
        "entry_candle_time": int(last1.get("time", 0) or 0),
    }


def rr_plan(side: str, entry: float, rng: Dict[str, Any], target: Optional[float] = None) -> Dict[str, float]:
    """Always target 1:1 R:R with a tight, realistic SL.

    SL is placed just beyond the first15 range boundary plus a small buffer.
    TP is set equal to the risk distance (1:1) so the trade has a balanced
    risk/reward that doesn't require price to travel too far.  This reduces
    SL hits before profit because we are not over-targeting.
    """
    high = f(rng.get("range_high"))
    low = f(rng.get("range_low"))
    size = max(high - low, 0.5)
    # Buffer: tight — just enough to absorb spread and minor wick noise.
    # Capped at 1.50 so XAUUSD SL is never more than a few dollars beyond the zone.
    buffer = max(0.20, min(1.50, size * 0.15))
    if side == BUY:
        sl = round(low - buffer, 2)
        risk = max(entry - sl, 0.50)
        # 1:1 TP; if range high is closer than risk distance use range high,
        # otherwise use exact 1:1 — never aim beyond 1:1 unless range structure allows it.
        natural_tp = round(entry + risk, 2)
        tp = round(min(natural_tp, high) if high > entry else natural_tp, 2)
        # Ensure TP is at least at 1:1
        if tp < entry + risk * 0.90:
            tp = natural_tp
    else:
        sl = round(high + buffer, 2)
        risk = max(sl - entry, 0.50)
        natural_tp = round(entry - risk, 2)
        tp = round(max(natural_tp, low) if low < entry else natural_tp, 2)
        if tp > entry - risk * 0.90:
            tp = natural_tp
    return {"sl": sl, "tp": tp, "risk": round(risk, 2), "reward": round(abs(tp - entry), 2)}


def draw_commands(data: Dict[str, Any], decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    cmds: List[Dict[str, Any]] = [{"type": "clear_all"}]
    rng = data.get("range") or {}
    profile = data.get("volume_profile") or {}
    now = int(time.time())
    if rng.get("valid"):
        high, low, mid = f(rng.get("range_high")), f(rng.get("range_low")), f(rng.get("range_mid"))
        start, first_end, end = int(rng.get("range_start", now - 3600)), int(rng.get("first_15m_end", now)), int(rng.get("range_end", now + 1800))
        bias = rng.get("range_bias", HOLD)
        color = "green" if bias == BUY else "red" if bias == SELL else "yellow"
        cmds += [
            {"type": "box", "name": "TS_ACTIVE_FIRST15_SOURCE", "time1": start, "time2": first_end, "price1": high, "price2": low, "color": color, "text": ""},
            {"type": "box", "name": "TS_ACTIVE_1H_RANGE", "time1": start, "time2": end, "price1": high, "price2": low, "color": color, "text": ""},
            {"type": "ray", "name": "TS_RANGE_HIGH", "time1": start, "price1": high, "color": "red", "width": 2, "text": f"H {high:.2f}"},
            {"type": "ray", "name": "TS_RANGE_MID", "time1": start, "price1": mid, "color": "yellow", "width": 1, "text": f"EQ {mid:.2f}"},
            {"type": "ray", "name": "TS_RANGE_LOW", "time1": start, "price1": low, "color": "green", "width": 2, "text": f"L {low:.2f}"},
        ]
    # Best SMC ranges: Asia / London / previous-day, drawn as lighter boxes so
    # the active first15/1H range above remains the visually dominant zone.
    smc_range_style = (
        ("asia_range", "TS_ASIA_RANGE", "aqua"),
        ("london_range", "TS_LONDON_RANGE", "violet"),
        ("prev_day_range", "TS_PDH_PDL", "white"),
    )
    for key, name, color in smc_range_style:
        zone = data.get(key) or {}
        if not zone.get("valid"):
            continue
        z_high, z_low = f(zone.get("range_high")), f(zone.get("range_low"))
        z_start = int(zone.get("range_start", now - HOUR_SECONDS))
        z_end = int(zone.get("range_end", now))
        cmds.append({"type": "box", "name": name, "time1": z_start, "time2": z_end, "price1": z_high, "price2": z_low, "color": color, "text": key.replace("_", " ").upper()})
        cmds.append({"type": "ray", "name": f"{name}_HIGH", "time1": z_start, "price1": z_high, "color": color, "width": 1, "text": f"{key.split('_')[0].upper()} H {z_high:.2f}"})
        cmds.append({"type": "ray", "name": f"{name}_LOW", "time1": z_start, "price1": z_low, "color": color, "width": 1, "text": f"{key.split('_')[0].upper()} L {z_low:.2f}"})
    # Liquidity sweep marker — shows where a stop-hunt swept a prior swing
    # extreme and rejected back inside, the core SMC entry trigger event.
    sweep = data.get("liquidity_sweep") or {}
    if sweep.get("valid") and (sweep.get("swept_high") or sweep.get("swept_low")):
        side_label = "SWEEP HIGH" if sweep.get("swept_high") else "SWEEP LOW"
        sweep_color = "red" if sweep.get("swept_high") else "green"
        cmds.append({
            "type": "text", "name": "TS_LIQUIDITY_SWEEP",
            "time": int(sweep.get("sweep_time", now)), "price": f(sweep.get("sweep_price")),
            "color": sweep_color, "text": side_label,
        })
    # Order blocks — last opposing candle before a displacement move.
    obs = data.get("order_blocks") or {}
    for side_key, label, color in (("bullish", "TS_BULLISH_OB", "lime"), ("bearish", "TS_BEARISH_OB", "orange")):
        ob = obs.get(side_key)
        if ob:
            cmds.append({"type": "box", "name": label, "time1": int(ob.get("time", now)), "time2": now, "price1": f(ob.get("high")), "price2": f(ob.get("low")), "color": color, "text": side_key.upper() + " OB"})
    # Fair value gaps — unfilled 3-candle imbalances.
    fvgs = data.get("fair_value_gaps") or {}
    for side_key, label, color in (("bullish", "TS_BULLISH_FVG", "teal"), ("bearish", "TS_BEARISH_FVG", "purple")):
        gap = fvgs.get(side_key)
        if gap:
            cmds.append({"type": "box", "name": label, "time1": int(gap.get("time", now)), "time2": now, "price1": f(gap.get("top")), "price2": f(gap.get("bottom")), "color": color, "text": side_key.upper() + " FVG"})
    if profile.get("valid"):
        for key, label, color in (("poc", "POC", "blue"), ("vah", "VAH", "orange"), ("val", "VAL", "cyan")):
            lv = f(profile.get(key))
            if lv:
                cmds.append({"type": "ray", "name": f"TS_{label}", "time1": int((rng or {}).get("range_start", now - 3600)), "price1": lv, "color": color, "width": 1, "text": f"{label} {lv:.2f}"})
    for key, label, color in (("d1", "D1", "magenta"), ("h4", "H4", "violet"), ("h1", "H1", "white")):
        ctx = data.get(f"{key}_context") or {}
        if ctx.get("valid"):
            cmds.append({"type": "ray", "name": f"TS_{label}_HIGH", "time1": now - 600, "price1": f(ctx.get("high")), "color": color, "width": 1, "text": f"{label} H"})
            cmds.append({"type": "ray", "name": f"TS_{label}_LOW", "time1": now - 600, "price1": f(ctx.get("low")), "color": color, "width": 1, "text": f"{label} L"})
    if decision.get("action") in (BUY, SELL):
        entry = f(decision.get("entry"))
        if entry:
            cmds.append({"type": "ray", "name": "TS_ENTRY", "time1": now - 180, "price1": entry, "color": "green" if decision.get("action") == BUY else "red", "width": 3, "text": f"{decision.get('action')} {entry:.2f}"})
    for key, color in (("sl", "orange"), ("tp", "blue")):
        lv = f(decision.get(key))
        if lv:
            cmds.append({"type": "ray", "name": f"TS_{key.upper()}", "time1": now - 180, "price1": lv, "color": color, "width": 2, "text": f"{key.upper()} {lv:.2f}"})
    status_price = f((rng or {}).get("range_mid")) or f(data.get("price"))
    cmds.append({"type": "text", "name": "TS_STATUS", "time": now - 240, "price": status_price, "color": "yellow", "text": str(decision.get("reason", "Scanning"))[:95]})
    return cmds


@dataclass
class XAUUSDEventTriggerStrategy:
    name: str = "xauusd_event_trigger_strategy"
    enabled: bool = True

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        tfs = context.get("timeframes") or {}
        m1, m5, m15 = tfs.get("M1", []), tfs.get("M5", []), tfs.get("M15", [])
        h1, h4, d1 = tfs.get("H1", []), tfs.get("H4", []), tfs.get("D1", [])
        # Robustness guard: require enough M1/M15 history AND make sure the
        # most recent M1 candle actually has real OHLC (not a zero/empty
        # placeholder row), which previously could slip through and corrupt
        # tolerance/score math downstream.
        if len(m1) < 20 or len(m15) < 2:
            return self._result(SCAN, 0.0, "Waiting for M1/M15 history.", {}, context)
        last_m1 = m1[-1] or {}
        if f(last_m1.get("high")) <= 0 or f(last_m1.get("low")) <= 0 or f(last_m1.get("high")) < f(last_m1.get("low")):
            return self._result(SCAN, 0.0, "Latest M1 candle data looks invalid; skipping this cycle.", {}, context)
        price = f(last_m1.get("close"))
        if price <= 0:
            return self._result(SCAN, 0.0, "Latest price is non-positive; skipping this cycle.", {}, context)
        rng = first15_hour_range(m1, m15)
        ref_ts = int(last_m1.get("time", time.time()) or time.time())
        session = session_name(ref_ts)
        hour_start = int((rng or {}).get("range_start", floor_1h(ref_ts)))
        hour_m1 = [c for c in m1 if hour_start <= int(c.get("time", 0) or 0) < hour_start + HOUR_SECONDS]
        profile = volume_profile(hour_m1 or closed(m1)[-80:])
        # Best SMC ranges: Asia (00:00-07:00 UTC), London (07:00-12:00 UTC),
        # and the previous completed daily candle, all computed alongside
        # the existing first15/1H range rather than replacing it.
        asia_rng = session_range(m1, 0, 7, ref_ts)
        london_rng = session_range(m1, 7, 12, ref_ts)
        pdr = previous_day_range(d1)
        atr_m1 = recent_atr(m1, 14)
        data = {
            "price": round(price, 2),
            "range": rng,
            "asia_range": asia_rng,
            "london_range": london_rng,
            "prev_day_range": pdr,
            "session": session,
            "d1_context": wick_targets(d1, price, 20),
            "h4_context": wick_targets(h4, price, 20),
            "h1_context": wick_targets(h1, price, 20),
            "volume_profile": profile,
            "volume_ratio_m1": volume_ratio(m1),
            "volume_ratio_m5": volume_ratio(m5),
            "atr_m1": round(atr_m1, 2),
            "liquidity_sweep": liquidity_sweep(m1),
            "order_blocks": order_blocks(m1),
            "fair_value_gaps": fair_value_gaps(m1, current_price=price),
        }
        if not rng.get("valid"):
            return self._result(SCAN, 0.0, f"Building hourly first15 range: {rng.get('reason')}", data, context)
        high, low, mid, size = f(rng.get("range_high")), f(rng.get("range_low")), f(rng.get("range_mid")), f(rng.get("range_size"))
        # Tolerance now scales with recent ATR as well as range size, so a
        # quiet overnight range and a fast NY session don't share one fixed
        # 0.35 floor that was either too tight or too loose depending on
        # conditions.
        tol = max(0.35, size * 0.22, atr_m1 * 0.35)
        location = "DISCOUNT" if price <= mid else "PREMIUM"
        data["location"] = location
        d1c, h4c, h1c = data["d1_context"], data["h4_context"], data["h1_context"]
        bias_votes = [x.get("bias") for x in (d1c, h4c, h1c) if x.get("bias") in (BUY, SELL)]
        bull_votes = bias_votes.count(BUY)
        bear_votes = bias_votes.count(SELL)
        buy_trigger = rejection_trigger(m1, m5, BUY, low, tol)
        sell_trigger = rejection_trigger(m1, m5, SELL, high, tol)
        vol_ok = data["volume_ratio_m1"] >= 0.45 or data["volume_ratio_m5"] >= 0.45
        profile_buy_ok = not profile.get("valid") or price <= f(profile.get("poc"), mid) or low <= f(profile.get("val"), low) + tol
        profile_sell_ok = not profile.get("valid") or price >= f(profile.get("poc"), mid) or high >= f(profile.get("vah"), high) - tol
        # SMC confluence: a real liquidity sweep of the low/high, a bullish/
        # bearish order block sitting near the zone, or an unfilled FVG in
        # the trade direction all add small score bonuses on top of the
        # core first15 event trigger, rewarding setups with more real SMC
        # evidence instead of treating every trigger as equally strong.
        sweep = data["liquidity_sweep"]
        obs = data["order_blocks"]
        fvgs = data["fair_value_gaps"]
        buy_sweep_ok = bool(sweep.get("valid") and sweep.get("swept_low"))
        sell_sweep_ok = bool(sweep.get("valid") and sweep.get("swept_high"))
        buy_ob_ok = bool(obs.get("bullish"))
        sell_ob_ok = bool(obs.get("bearish"))
        buy_fvg_ok = bool(fvgs.get("bullish"))
        sell_fvg_ok = bool(fvgs.get("bearish"))
        # Event triggers: premium/discount first, then trigger, then soft MTF vote,
        # then SMC confluence (sweep/OB/FVG) as smaller additive bonuses.
        buy_score = (
            0.20 + (0.22 if location == "DISCOUNT" else 0.04) + (0.25 if buy_trigger["ok"] else 0.0)
            + (0.10 if vol_ok else 0.0) + (0.10 if profile_buy_ok else 0.0) + min(0.18, bull_votes * 0.06)
            + session["quality"] * 0.05
            + (0.06 if buy_sweep_ok else 0.0) + (0.04 if buy_ob_ok else 0.0) + (0.04 if buy_fvg_ok else 0.0)
        )
        sell_score = (
            0.20 + (0.22 if location == "PREMIUM" else 0.04) + (0.25 if sell_trigger["ok"] else 0.0)
            + (0.10 if vol_ok else 0.0) + (0.10 if profile_sell_ok else 0.0) + min(0.18, bear_votes * 0.06)
            + session["quality"] * 0.05
            + (0.06 if sell_sweep_ok else 0.0) + (0.04 if sell_ob_ok else 0.0) + (0.04 if sell_fvg_ok else 0.0)
        )
        min_score = f((context.get("risk") or context.get("rules") or {}).get("min_strategy_score"), 0.62)
        if buy_score >= min_score and buy_score >= sell_score:
            entry = round(price, 2)
            target = high if high > entry else d1c.get("high")
            plan = rr_plan(BUY, entry, rng, f(target))
            data["setup_type"] = "DISCOUNT_REJECTION_SCALP"
            reason = f"BUY event: discount reclaim near first15 low {low:.2f}, target {plan['tp']:.2f}, score {buy_score:.2f}."
            return self._result(BUY, buy_score, reason, data, context, entry=entry, sl=plan["sl"], tp=plan["tp"], entry_candle_time=buy_trigger.get("entry_candle_time"))
        if sell_score >= min_score and sell_score > buy_score:
            entry = round(price, 2)
            target = low if low < entry else d1c.get("low")
            plan = rr_plan(SELL, entry, rng, f(target))
            data["setup_type"] = "PREMIUM_REJECTION_SCALP"
            reason = f"SELL event: premium rejection near first15 high {high:.2f}, target {plan['tp']:.2f}, score {sell_score:.2f}."
            return self._result(SELL, sell_score, reason, data, context, entry=entry, sl=plan["sl"], tp=plan["tp"], entry_candle_time=sell_trigger.get("entry_candle_time"))
        watch = BUY if location == "DISCOUNT" else SELL
        reason = f"SCAN: {location} | first15 {low:.2f}-{high:.2f} | watching {watch} trigger | buy {buy_score:.2f}, sell {sell_score:.2f}, min {min_score:.2f}."
        return self._result(SCAN, max(buy_score, sell_score), reason, data, context)

    def _result(self, action: str, score: float, reason: str, data: Dict[str, Any], context: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        decision = {"action": action, "score": round(float(score), 2), "confidence": round(float(score), 2), "reason": reason, "data": data, **extra}
        decision["draw_commands"] = draw_commands(data, decision)
        return decision


def get_strategy() -> XAUUSDEventTriggerStrategy:
    return XAUUSDEventTriggerStrategy()
