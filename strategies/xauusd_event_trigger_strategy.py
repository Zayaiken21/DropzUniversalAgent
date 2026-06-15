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
    if side == BUY:
        touched = lo <= zone + tol
        reclaimed = cl >= zone - tol
        candle_ok = cl >= op or abs(cl - op) <= max((hi - lo) * 0.25, 0.05)
        m5_stall = bool(last5) and f(last5.get("low")) <= zone + tol and f(last5.get("close")) >= zone - tol
    else:
        touched = hi >= zone - tol
        reclaimed = cl <= zone + tol
        candle_ok = cl <= op or abs(cl - op) <= max((hi - lo) * 0.25, 0.05)
        m5_stall = bool(last5) and f(last5.get("high")) >= zone - tol and f(last5.get("close")) <= zone + tol
    ok = touched and reclaimed and (candle_ok or m5_stall)
    return {"ok": ok, "touched": touched, "reclaimed": reclaimed, "candle_ok": candle_ok, "m5_stall": m5_stall, "entry_candle_time": int(last1.get("time", 0) or 0)}


def rr_plan(side: str, entry: float, rng: Dict[str, Any], target: Optional[float] = None) -> Dict[str, float]:
    high = f(rng.get("range_high"))
    low = f(rng.get("range_low"))
    size = max(high - low, 0.5)
    buffer = max(0.35, min(2.0, size * 0.25))
    if side == BUY:
        sl = round(low - buffer, 2)
        tp = round(target if target and target > entry else max(high, entry + (entry - sl) * 2.0), 2)
    else:
        sl = round(high + buffer, 2)
        tp = round(target if target and target < entry else min(low, entry - (sl - entry) * 2.0), 2)
    return {"sl": sl, "tp": tp, "risk": round(abs(entry - sl), 2), "reward": round(abs(tp - entry), 2)}


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
        if len(m1) < 20 or len(m15) < 2:
            return self._result(SCAN, 0.0, "Waiting for M1/M15 history.", {}, context)
        price = f(m1[-1].get("close"))
        rng = first15_hour_range(m1, m15)
        session = session_name(int(m1[-1].get("time", time.time()) or time.time()))
        hour_start = int((rng or {}).get("range_start", floor_1h(int(m1[-1].get("time", time.time())))))
        hour_m1 = [c for c in m1 if hour_start <= int(c.get("time", 0) or 0) < hour_start + HOUR_SECONDS]
        profile = volume_profile(hour_m1 or closed(m1)[-80:])
        data = {
            "price": round(price, 2),
            "range": rng,
            "session": session,
            "d1_context": wick_targets(d1, price, 20),
            "h4_context": wick_targets(h4, price, 20),
            "h1_context": wick_targets(h1, price, 20),
            "volume_profile": profile,
            "volume_ratio_m1": volume_ratio(m1),
            "volume_ratio_m5": volume_ratio(m5),
        }
        if not rng.get("valid"):
            return self._result(SCAN, 0.0, f"Building hourly first15 range: {rng.get('reason')}", data, context)
        high, low, mid, size = f(rng.get("range_high")), f(rng.get("range_low")), f(rng.get("range_mid")), f(rng.get("range_size"))
        tol = max(0.35, size * 0.22)
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
        # Event triggers: premium/discount first, then trigger, then soft MTF vote.
        buy_score = 0.20 + (0.22 if location == "DISCOUNT" else 0.04) + (0.25 if buy_trigger["ok"] else 0.0) + (0.10 if vol_ok else 0.0) + (0.10 if profile_buy_ok else 0.0) + min(0.18, bull_votes * 0.06) + session["quality"] * 0.05
        sell_score = 0.20 + (0.22 if location == "PREMIUM" else 0.04) + (0.25 if sell_trigger["ok"] else 0.0) + (0.10 if vol_ok else 0.0) + (0.10 if profile_sell_ok else 0.0) + min(0.18, bear_votes * 0.06) + session["quality"] * 0.05
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
