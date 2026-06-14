"""
strategy_common.py  —  TradeSmart SMC Scalp Engine  v5.0
=========================================================
WHAT CHANGED IN v4
------------------
  1. CANDLE COLOR RULE
       BUY  entry: trigger 1M candle must be BEARISH (red) — price dipped to
            the range low, bearish close confirms the test, we buy the bounce.
       SELL entry: trigger 1M candle must be BULLISH (green) — price pushed to
            the range high, bullish close confirms the test, we sell the rejection.
       This prevents buying at the top of a move or selling at the bottom.

  2. ENTRY CANDLE FIX
       Entry price = CLOSE of the last FULLY CLOSED 1M candle (index [-2] of
       the raw list which includes the forming candle, or [-1] of _closed()).
       Previously the code sometimes used the forming candle's close.

  3. CANDLE-TIME DEDUP FIX
       The agent now only stamps last_entry_candle_time on a SUCCESSFUL order,
       not on the attempt.  Strategy does its part by returning a unique
       entry_candle_time in the signal so the agent can compare correctly.

  4. SWING LEVELS — NEAREST ONLY
       key_levels() now returns only the 2 nearest highs and 2 nearest lows
       relative to current price, using resistance-wick highs for sells and
       support-wick lows for buys.

  5. CHART CLEANUP
       - Historical range boxes removed (too cluttered).  Only the ACTIVE 15M
         range box is drawn.
       - Swing level rays are short (start 1 bar back, no future text drift).
       - All text labels anchored at now - 30s so they appear LEFT of the
         current bar and never run off-screen right.
       - Breakout and decision labels placed at range_mid ± offset so they
         never overlap.

  6. SL/TP ANCHORED TO RANGE
       BUY  : SL below range_low by buffer, TP = range_high (full range target).
       SELL : SL above range_high by buffer, TP = range_low.
       Breakout: SL = range extreme opposite side, TP = entry + 2× range.
       This makes SL/TP visually obvious on the range that is drawn.

  7. 1M TRIGGER REQUIRES CLOSED CANDLE
       confirm_1m() checks candles[-2] (last closed), never candles[-1]
       (forming).  This prevents firing on an incomplete candle.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ══════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════
BUY   = "BUY"
SELL  = "SELL"
CLOSE = "CLOSE"
HOLD  = "HOLD"
SCAN  = "SCAN"

SYMBOL_DEFAULT  = "XAUUSD"
DRAW_ENV        = "TRADESMART_MT5_BRIDGE_FILE"
DRAW_JSON1      = "TradeSmart_AI_DrawCommands.json1"
DRAW_JSONL      = "TradeSmart_AI_DrawCommands.jsonl"
DEBUG_FILE      = "TradeSmart_AI_Debug_LastSignal.json"

# Zone touch tolerance
ZONE_TOL_RATIO  = 0.10   # 10% of range size
MIN_ZONE_TOL    = 0.30   # min 0.30 pts
MIN_RANGE_SIZE  = 0.50   # ignore ranges smaller than this

# SL buffer above/below range extreme (price units)
SL_BUFFER       = 1.50   # SL sits 1.50 pts beyond the range extreme
MIN_SL_POINTS   = 2.00   # hard floor

# Volume filter
VOL_LOOKBACK    = 20
VOL_MIN_RATIO   = 0.70   # 70% of avg volume (relaxed slightly for more trades)

# Breakout: consecutive 5M closes outside range
BREAKOUT_THRESH = 2
# Breakout TP = range_size × multiplier
BREAKOUT_TP_MULT = 2.0

# Liquidity grab: wick beyond extreme by at least this much
LIQ_GRAB_MIN    = 0.40

# Enhanced PO3 / session engine
FIRST_15M_SECONDS = 900      # First 15 minutes of the active 1H candle
HOUR_SECONDS      = 3600
SESSION_TZ_OFFSET_HOURS = 0  # MT5 server-time offset. Keep 0 unless your broker needs adjustment.
VALUE_AREA_RATIO  = 0.70
PROFILE_BINS      = 24
MIN_BREAKOUT_SCORE = 0.86
MIN_SWEEP_SCORE    = 0.88
MAX_ALLOWED_SPREAD = 80      # broker points from MT5 spread column; skip entries if wider


# ══════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════

def fv(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except Exception:
        return default


def symbol_from_context(ctx: Dict[str, Any]) -> str:
    return str(ctx.get("symbol") or (ctx.get("profile") or {}).get("symbol") or SYMBOL_DEFAULT)


def normalize_candle(c: Any) -> Dict[str, Any]:
    if c is None:
        return {}
    if isinstance(c, dict):
        return c
    out: Dict[str, Any] = {}
    for k in ("time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"):
        try:
            out[k] = c[k]
        except Exception:
            try:
                out[k] = getattr(c, k)
            except Exception:
                pass
    return out


def floor_15m(ts: int) -> int:
    return int(ts) - (int(ts) % 900)


def floor_1h(ts: int) -> int:
    return int(ts) - (int(ts) % HOUR_SECONDS)


def _closed(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return candles[:-1] if len(candles) > 1 else list(candles or [])


def session_context(ts: int) -> Dict[str, Any]:
    """Return a simple MT5-server-time session map for XAUUSD intraday logic."""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc) + timedelta(hours=SESSION_TZ_OFFSET_HOURS)
        hour = dt.hour
        dow = dt.weekday()  # Mon=0 ... Sun=6
        if 0 <= hour < 7:
            name, quality = "ASIA", 0.55
        elif 7 <= hour < 12:
            name, quality = "LONDON", 0.85
        elif 12 <= hour < 17:
            name, quality = "NEW_YORK_AM", 1.00
        elif 17 <= hour < 21:
            name, quality = "NEW_YORK_PM", 0.72
        else:
            name, quality = "ROLLOVER", 0.20
        tradable = name in ("LONDON", "NEW_YORK_AM", "NEW_YORK_PM") and dow < 5
        if dow == 4 and hour >= 17:
            tradable = False
            quality = min(quality, 0.35)
        if dow >= 5:
            tradable = False
            quality = 0.0
        return {
            "name": name, "quality": quality, "tradable": tradable,
            "hour": hour, "weekday": dow, "iso": dt.isoformat(timespec="seconds"),
        }
    except Exception:
        return {"name": "UNKNOWN", "quality": 0.0, "tradable": False, "hour": 0, "weekday": 0}


def ema(values: List[float], period: int) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < period:
        return None
    k = 2.0 / (period + 1.0)
    e = sum(vals[:period]) / period
    for v in vals[period:]:
        e = (v * k) + (e * (1.0 - k))
    return e


def trend_context(h1: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = _closed(h1)
    closes = [fv(c.get("close")) for c in closed if fv(c.get("close")) > 0]
    e13 = ema(closes, 13)
    e21 = ema(closes, 21)
    if e13 is None or e21 is None:
        return {"bias": HOLD, "ema13": e13, "ema21": e21, "quality": 0.50}
    if e13 > e21:
        return {"bias": BUY, "ema13": round(e13, 2), "ema21": round(e21, 2), "quality": 0.75}
    if e13 < e21:
        return {"bias": SELL, "ema13": round(e13, 2), "ema21": round(e21, 2), "quality": 0.75}
    return {"bias": HOLD, "ema13": round(e13, 2), "ema21": round(e21, 2), "quality": 0.50}


def volume_ratio(candles: List[Dict[str, Any]], lookback: int = VOL_LOOKBACK) -> float:
    closed = _closed(candles)
    if len(closed) < 3:
        return 1.0
    last = fv(closed[-1].get("tick_volume"))
    avg = avg_volume(closed[:-1], lookback)
    return round(last / avg, 2) if avg > 0 else 1.0


def volume_profile_levels(candles: List[Dict[str, Any]], bins: int = PROFILE_BINS) -> Dict[str, Any]:
    """Internal MT5-only volume profile using OHLC + tick_volume bars."""
    rows = [c for c in candles if fv(c.get("high")) > fv(c.get("low"))]
    if len(rows) < 5:
        return {"valid": False}
    lo = min(fv(c.get("low")) for c in rows)
    hi = max(fv(c.get("high")) for c in rows)
    rng = hi - lo
    if rng <= 0:
        return {"valid": False}
    bins = max(8, min(int(bins), 80))
    step = rng / bins
    hist = [0.0 for _ in range(bins)]
    for c in rows:
        mid = (fv(c.get("high")) + fv(c.get("low")) + fv(c.get("close"))) / 3.0
        idx = int((mid - lo) / step)
        idx = max(0, min(bins - 1, idx))
        hist[idx] += max(1.0, fv(c.get("tick_volume"), 1.0))
    total = sum(hist)
    if total <= 0:
        return {"valid": False}
    poc_i = max(range(bins), key=lambda i: hist[i])
    included = {poc_i}
    vol = hist[poc_i]
    low_i = high_i = poc_i
    while vol < total * VALUE_AREA_RATIO and (low_i > 0 or high_i < bins - 1):
        left = hist[low_i - 1] if low_i > 0 else -1
        right = hist[high_i + 1] if high_i < bins - 1 else -1
        if right >= left and high_i < bins - 1:
            high_i += 1; included.add(high_i); vol += hist[high_i]
        elif low_i > 0:
            low_i -= 1; included.add(low_i); vol += hist[low_i]
        else:
            break
    def price_at(i: int) -> float:
        return round(lo + (i + 0.5) * step, 2)
    return {
        "valid": True, "poc": price_at(poc_i), "val": price_at(low_i), "vah": price_at(high_i),
        "low": round(lo, 2), "high": round(hi, 2), "bins": bins, "total_volume": round(total, 2),
    }


def avg_volume(candles: List[Dict[str, Any]], n: int = VOL_LOOKBACK) -> float:
    sample = [fv(c.get("tick_volume")) for c in candles[-n:] if fv(c.get("tick_volume")) > 0]
    return sum(sample) / len(sample) if sample else 1.0


def is_bearish(c: Dict[str, Any]) -> bool:
    return fv(c.get("close")) < fv(c.get("open"))


def is_bullish(c: Dict[str, Any]) -> bool:
    return fv(c.get("close")) > fv(c.get("open"))


# ══════════════════════════════════════════════
#  TIMEFRAME RESOLVER
# ══════════════════════════════════════════════

def _fetch_mt5_tf(symbol: str) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        import MetaTrader5 as mt5
        mt5.initialize()
    except Exception:
        return out
    tf_map = {
        "M1":  (getattr(mt5, "TIMEFRAME_M1",  None), 300),
        "M5":  (getattr(mt5, "TIMEFRAME_M5",  None), 200),
        "M15": (getattr(mt5, "TIMEFRAME_M15", None), 100),
        "H1":  (getattr(mt5, "TIMEFRAME_H1",  None),  60),
    }
    for tf, (const, count) in tf_map.items():
        if const is None:
            continue
        try:
            raw = mt5.copy_rates_from_pos(symbol, const, 0, count)
        except Exception:
            continue
        if raw is None:
            continue
        rows = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
                 "low": float(r["low"]), "close": float(r["close"]),
                 "tick_volume": int(r["tick_volume"]), "spread": int(r["spread"]),
                 "real_volume": int(r.get("real_volume", 0))} for r in raw]
        if rows:
            out[tf] = sorted(rows, key=lambda x: x["time"])
    return out


def get_timeframes(ctx: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    tfd = ctx.get("timeframes") or {}
    if isinstance(tfd, dict):
        for k, v in tfd.items():
            tf = str(k).upper()
            if tf in ("M1", "M5", "M15", "H1") and v:
                rows = sorted([normalize_candle(c) for c in v if normalize_candle(c)],
                              key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows

    aliases = {
        "M1":  ["rates_m1", "m1_rates", "rates", "closed_rates", "candles", "bars"],
        "M5":  ["rates_m5", "m5_rates"],
        "M15": ["rates_m15", "m15_rates"],
        "H1":  ["rates_h1",  "h1_rates"],
    }
    for tf, keys in aliases.items():
        if tf in out:
            continue
        for key in keys:
            val = ctx.get(key)
            if val:
                rows = sorted([normalize_candle(c) for c in val if normalize_candle(c)],
                              key=lambda x: int(x.get("time", 0) or 0))
                if rows:
                    out[tf] = rows
                    break

    if not out:
        out.update(_fetch_mt5_tf(symbol_from_context(ctx)))
    return out


# ══════════════════════════════════════════════
#  15M RANGE BUILDER
#  Range = HIGH and LOW of the closed 15M candle wicks.
#  While the bar is still forming, use M1 wicks in the first 5 minutes.
# ══════════════════════════════════════════════

def build_15m_range(m1: List[Dict[str, Any]], m15: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Enhanced PO3 range builder.

    The range is now the WICK HIGH/LOW of the FIRST 15 minutes of the ACTIVE 1H candle.
    While that first 15m window is forming, M1 wicks build it live. After the first
    15m closes, the range locks and stays fixed for the rest of the hour.
    """
    if not m1:
        return {"valid": False, "reason": "No M1 data."}

    ref_ts     = int(m1[-1].get("time", 0) or time.time())
    hour_start = floor_1h(ref_ts)
    first_end  = hour_start + FIRST_15M_SECONDS
    hour_end   = hour_start + HOUR_SECONDS

    m15_closed = _closed(m15)
    first_15 = [c for c in m15_closed if int(c.get("time", 0) or 0) == hour_start]

    if first_15:
        bar = first_15[-1]
        high  = fv(bar.get("high"))
        low   = fv(bar.get("low"))
        open_ = fv(bar.get("open"))
        close = fv(bar.get("close"))
        source = "locked_first_15m_of_1h"
        is_locked = True
    else:
        window = [c for c in m1 if hour_start <= int(c.get("time", 0) or 0) < min(ref_ts + 60, first_end)]
        if not window:
            return {
                "valid": False,
                "reason": f"Waiting for first M1 candle of active 1H range at {hour_start}.",
                "active_1h_start": hour_start,
                "range_start": hour_start,
                "range_end": hour_end,
            }
        high  = max(fv(c.get("high")) for c in window)
        low   = min(fv(c.get("low")) for c in window)
        open_ = fv(window[0].get("open"))
        close = fv(window[-1].get("close"))
        source = "building_first_15m_of_1h"
        is_locked = False

    rng = high - low
    if rng < MIN_RANGE_SIZE:
        return {
            "valid": False,
            "reason": f"First 15M 1H range too small ({rng:.2f} pts).",
            "active_1h_start": hour_start,
            "range_start": hour_start,
            "range_end": hour_end,
        }

    direction = BUY if close > open_ else SELL if close < open_ else HOLD
    sess = session_context(ref_ts)
    return {
        "valid": True,
        "locked": is_locked,
        "source": source,
        "active_1h_start": hour_start,
        "active_15m_start": hour_start,
        "range_start": hour_start,
        "range_end": hour_end,
        "first_15m_end": first_end,
        "range_high": high,
        "range_low": low,
        "range_mid": (high + low) / 2.0,
        "range_size": rng,
        "range_open": open_,
        "range_close": close,
        "range_direction": direction,
        "session": sess,
        "reason": "First 15M of 1H range locked." if is_locked else "Building first 15M wick range for active 1H candle.",
    }


# ══════════════════════════════════════════════
#  NEAREST SWING LEVELS
#  Only the 2 nearest swing highs (resistance wick tips) and
#  2 nearest swing lows (support wick tips) relative to current price.
# ══════════════════════════════════════════════

def nearest_swing_levels(m15: List[Dict[str, Any]],
                          current_price: float,
                          lookback: int = 10) -> Dict[str, List[float]]:
    """
    Returns {"resistance": [r1, r2], "support": [s1, s2]}
    where resistance = swing-high wick tips ABOVE current price (nearest first)
    and   support    = swing-low  wick tips BELOW current price (nearest first).
    """
    closed = (m15[:-1] if len(m15) > 1 else m15)[-lookback:]
    swing_highs: List[float] = []
    swing_lows:  List[float] = []

    for i in range(1, len(closed) - 1):
        prev_h = fv(closed[i-1].get("high"))
        curr_h = fv(closed[i].get("high"))
        next_h = fv(closed[i+1].get("high"))
        prev_l = fv(closed[i-1].get("low"))
        curr_l = fv(closed[i].get("low"))
        next_l = fv(closed[i+1].get("low"))

        if curr_h > prev_h and curr_h > next_h:
            swing_highs.append(curr_h)
        if curr_l < prev_l and curr_l < next_l:
            swing_lows.append(curr_l)

    # Keep only levels above/below current price, sorted nearest first
    resistance = sorted([h for h in swing_highs if h > current_price])[:2]
    support    = sorted([l for l in swing_lows  if l < current_price], reverse=True)[:2]

    return {"resistance": resistance, "support": support}


# ══════════════════════════════════════════════
#  LIQUIDITY GRAB
# ══════════════════════════════════════════════

def detect_liq_grab(candles: List[Dict[str, Any]], extreme: float, direction: str) -> bool:
    """
    BUY  side: recent M1 wick went BELOW extreme then closed ABOVE it.
    SELL side: recent M1 wick went ABOVE extreme then closed BELOW it.
    """
    for c in reversed(candles[-4:]):
        if direction == BUY:
            if fv(c.get("low")) < extreme - LIQ_GRAB_MIN and fv(c.get("close")) > extreme:
                return True
        else:
            if fv(c.get("high")) > extreme + LIQ_GRAB_MIN and fv(c.get("close")) < extreme:
                return True
    return False


# ══════════════════════════════════════════════
#  BREAKOUT CHECK
# ══════════════════════════════════════════════

def breakout_check(m5: List[Dict[str, Any]],
                   range_high: float, range_low: float) -> Dict[str, Any]:
    closed = m5[:-1] if len(m5) > 1 else m5
    bull = bear = 0
    for c in reversed(closed[-6:]):
        cl = fv(c.get("close"))
        if cl > range_high:
            bull += 1; bear = 0
        elif cl < range_low:
            bear += 1; bull = 0
        else:
            break
    if bull >= BREAKOUT_THRESH:
        return {"direction": BUY,  "count": bull, "confirmed": True}
    if bear >= BREAKOUT_THRESH:
        return {"direction": SELL, "count": bear, "confirmed": True}
    return {"direction": HOLD, "count": 0, "confirmed": False}


# ══════════════════════════════════════════════
#  5M CONFIRMATION
#  BUY zone : last closed 5M is BEARISH but closes ABOVE range_low
#             (tested the low, rejected, body closing back inside range)
#  SELL zone: last closed 5M is BULLISH but closes BELOW range_high
#             (tested the high, rejected, body closing back inside range)
# ══════════════════════════════════════════════

def confirm_5m(m5: List[Dict[str, Any]], direction: str, zone_extreme: float) -> bool:
    closed = m5[:-1] if len(m5) > 1 else m5
    if not closed:
        return False
    c  = closed[-1]
    cl = fv(c.get("close"))
    op = fv(c.get("open"))
    if direction == BUY:
        # Bearish candle that still closes above the low — rejection from below
        return cl < op and cl > zone_extreme
    else:
        # Bullish candle that still closes below the high — rejection from above
        return cl > op and cl < zone_extreme


# ══════════════════════════════════════════════
#  1M TRIGGER — CANDLE COLOR RULE + VOLUME
#
#  BUY  : trigger candle must be BEARISH (red).
#          Price dipped to/below range_low (the support), closed above it.
#          We buy the bounce — entry on the close of that red candle.
#
#  SELL : trigger candle must be BULLISH (green).
#          Price pushed to/above range_high (the resistance), closed below it.
#          We sell the rejection — entry on the close of that green candle.
#
#  Rationale: A bearish candle touching support shows the level was TESTED and
#  held (sellers tried, buyers absorbed).  A bullish candle touching resistance
#  shows buyers tried and sellers absorbed.  This is the institutional fingerprint.
# ══════════════════════════════════════════════

def confirm_1m(m1: List[Dict[str, Any]],
               direction: str,
               zone_extreme: float) -> Tuple[bool, bool, Optional[Dict[str, Any]]]:
    """
    Returns (confirmed, volume_ok, trigger_candle).
    Uses the LAST CLOSED candle (m1[-2] when m1 includes the forming bar).
    """
    # Get strictly closed candles (exclude forming)
    closed = m1[:-1] if len(m1) > 1 else m1
    if not closed:
        return False, False, None

    c   = closed[-1]   # last fully closed 1M candle
    cl  = fv(c.get("close"))
    op  = fv(c.get("open"))
    lo  = fv(c.get("low"))
    hi  = fv(c.get("high"))
    vol = fv(c.get("tick_volume"))
    avg = avg_volume(closed[:-1])
    vol_ok = avg == 0 or vol >= avg * VOL_MIN_RATIO

    if direction == BUY:
        # Red candle that wicked to/below range_low then closed above it
        candle_red    = cl < op                         # bearish body
        tested_low    = lo <= zone_extreme + MIN_ZONE_TOL  # wick touched the zone
        closed_inside = cl > zone_extreme - MIN_ZONE_TOL   # close did not break down
        confirmed     = candle_red and tested_low and closed_inside
        return confirmed, vol_ok, c if confirmed else None
    else:
        # Green candle that wicked to/above range_high then closed below it
        candle_green  = cl > op                         # bullish body
        tested_high   = hi >= zone_extreme - MIN_ZONE_TOL  # wick touched the zone
        closed_inside = cl < zone_extreme + MIN_ZONE_TOL   # close did not break up
        confirmed     = candle_green and tested_high and closed_inside
        return confirmed, vol_ok, c if confirmed else None


# ══════════════════════════════════════════════
#  SL / TP  —  RANGE-ANCHORED  1:3 RR
#
#  BUY  : SL = range_low  - SL_BUFFER
#          TP = range_high + (range_high - range_low) * 0.5   (~1.5× range)
#              adjusted so RR is at least 1:3
#
#  SELL : SL = range_high + SL_BUFFER
#          TP = range_low  - (range_high - range_low) * 0.5
# ══════════════════════════════════════════════

def calc_rr(direction: str, entry: float,
            range_high: float, range_low: float,
            liq_grab: bool = False) -> Dict[str, float]:
    rng    = range_high - range_low
    buffer = SL_BUFFER * (0.70 if liq_grab else 1.0)

    if direction == BUY:
        sl     = round(range_low - max(buffer, MIN_SL_POINTS), 2)
        sl_dist= entry - sl
        tp_dist= sl_dist * 3.0
        tp     = round(entry + tp_dist, 2)
    else:
        sl     = round(range_high + max(buffer, MIN_SL_POINTS), 2)
        sl_dist= sl - entry
        tp_dist= sl_dist * 3.0
        tp     = round(entry - tp_dist, 2)

    return {"sl": sl, "tp": tp, "sl_dist": sl_dist, "tp_dist": tp_dist}


# ══════════════════════════════════════════════
#  POSITION UTILITIES
# ══════════════════════════════════════════════

def position_age_m1(pos: Dict[str, Any], m1: List[Dict[str, Any]]) -> int:
    open_time = int(pos.get("time", 0) or 0)
    return sum(1 for c in m1 if int(c.get("time", 0) or 0) > open_time)


def position_in_profit(pos: Dict[str, Any], m1: List[Dict[str, Any]]) -> bool:
    if pos.get("profit") is not None:
        return fv(pos.get("profit")) > 0
    if not m1:
        return False
    entry    = fv(pos.get("price_open") or pos.get("open_price") or pos.get("entry_price"))
    last_cl  = fv(m1[-1].get("close"))
    pos_type = int(pos.get("type", 0) or 0)
    return last_cl > entry if pos_type == 0 else last_cl < entry


# ══════════════════════════════════════════════
#  SIGNAL FACTORY
# ══════════════════════════════════════════════

def make_signal(
    action: str,
    reason: str,
    confidence: float,
    ctx: Dict[str, Any],
    data: Optional[Dict[str, Any]] = None,
    close_ticket: Any = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    entry_candle_time: Optional[int] = None,
) -> Dict[str, Any]:
    action = str(action or HOLD).upper()
    if action not in (BUY, SELL, CLOSE, HOLD, SCAN):
        action = HOLD
    rules = ctx.get("rules") or {}
    return {
        "enabled":          True,
        "active":           True,
        "valid":            True,
        "strategy":         "xauusd_first15m_1h_po3",
        "name":             "xauusd_first15m_1h_po3",
        "symbol":           symbol_from_context(ctx),
        "volume":           fv(rules.get("volume") or rules.get("trade_volume") or ctx.get("volume"), 0.01),
        "action":           action,
        "signal":           action,
        "trade_signal":     action,
        "direction":        action,
        "side":             action,
        "mt5_action":       action,
        "mt5_order_type":   action,
        "order_type":       action,
        "should_trade":     action in (BUY, SELL),
        "execute":          action in (BUY, SELL),
        "should_execute":   action in (BUY, SELL),
        "should_close":     action == CLOSE,
        "close_ticket":     close_ticket,
        "confidence":       max(0.0, min(fv(confidence), 1.0)),
        "reason":           reason,
        "thought":          reason,
        "sl":               sl,
        "tp":               tp,
        "entry_candle_time": entry_candle_time,
        "data":             data or {},
    }


# ══════════════════════════════════════════════
#  POSITION MANAGEMENT  (maybe_close)
# ══════════════════════════════════════════════

def maybe_close(ctx: Dict[str, Any], setup: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    positions = ctx.get("positions") or []
    if not positions:
        return None
    m1 = setup.get("_m1", [])
    if not m1:
        return None

    pos       = positions[0]
    ticket    = pos.get("ticket")
    age       = position_age_m1(pos, m1)
    in_profit = position_in_profit(pos, m1)
    pos_type  = int(pos.get("type", 0) or 0)   # 0=BUY, 1=SELL
    last_cl   = fv(m1[-1].get("close"))
    rng_high  = fv(setup.get("range_high"))
    rng_low   = fv(setup.get("range_low"))

    # Read SL/TP stored in setup (placed on the order by agent)
    tp_level = fv(setup.get("tp"))
    sl_level = fv(setup.get("sl"))

    # Software TP backup
    if pos_type == 0 and tp_level > 0 and last_cl >= tp_level:
        return make_signal(CLOSE, f"CLOSE: BUY TP {tp_level:.2f} reached.", 1.0, ctx, data=setup, close_ticket=ticket)
    if pos_type == 1 and tp_level > 0 and last_cl <= tp_level:
        return make_signal(CLOSE, f"CLOSE: SELL TP {tp_level:.2f} reached.", 1.0, ctx, data=setup, close_ticket=ticket)

    # Software SL backup
    if pos_type == 0 and sl_level > 0 and last_cl <= sl_level:
        return make_signal(CLOSE, f"CLOSE: BUY SL {sl_level:.2f} hit.", 1.0, ctx, data=setup, close_ticket=ticket)
    if pos_type == 1 and sl_level > 0 and last_cl >= sl_level:
        return make_signal(CLOSE, f"CLOSE: SELL SL {sl_level:.2f} hit.", 1.0, ctx, data=setup, close_ticket=ticket)

    # Breakout against trade
    if rng_high > 0 and rng_low > 0:
        if pos_type == 0 and last_cl < rng_low - SL_BUFFER:
            return make_signal(CLOSE, f"CLOSE: BUY — broke below range low {rng_low:.2f}.", 0.95, ctx, data=setup, close_ticket=ticket)
        if pos_type == 1 and last_cl > rng_high + SL_BUFFER:
            return make_signal(CLOSE, f"CLOSE: SELL — broke above range high {rng_high:.2f}.", 0.95, ctx, data=setup, close_ticket=ticket)

    # Time-based exits
    if in_profit and age >= 7:
        return make_signal(CLOSE, f"CLOSE: BUY in profit {age} candles — securing.", 1.0, ctx, data=setup, close_ticket=ticket)
    if not in_profit and age >= 4:
        return make_signal(CLOSE, f"CLOSE: {'BUY' if pos_type==0 else 'SELL'} not in profit after {age} candles — cut.", 1.0, ctx, data=setup, close_ticket=ticket)

    pos_dir = "BUY" if pos_type == 0 else "SELL"
    return make_signal(HOLD, f"HOLD: Managing {pos_dir} ticket {ticket} — age={age} candles, profit={in_profit}.",
                       0.0, ctx, data=setup, close_ticket=ticket)


# ══════════════════════════════════════════════
#  MAIN DECISION ENGINE
# ══════════════════════════════════════════════

def build_decision(ctx: Dict[str, Any]) -> Dict[str, Any]:
    tfs = get_timeframes(ctx)
    m1  = tfs.get("M1",  [])
    m5  = tfs.get("M5",  [])
    m15 = tfs.get("M15", [])
    h1  = tfs.get("H1",  [])

    positions = ctx.get("positions") or []

    if len(m1) < 20:
        return make_signal(SCAN, "SCAN: Waiting for M1 candle history.", 0.0, ctx)
    if len(m15) < 3:
        return make_signal(SCAN, "SCAN: Waiting for M15 candle history.", 0.0, ctx)

    current_price = fv(m1[-1].get("close"))
    current_spread = int(fv(m1[-1].get("spread"), 0))

    # First 15 minutes of the active 1H candle, using wick high/low.
    rng = build_15m_range(m1, m15)

    levels  = nearest_swing_levels(m15, current_price, lookback=16)
    trend   = trend_context(h1)
    sess    = rng.get("session") or session_context(int(m1[-1].get("time", time.time())))
    vol_m1  = volume_ratio(m1)
    vol_m5  = volume_ratio(m5) if m5 else 1.0

    hour_start = int(rng.get("active_1h_start") or floor_1h(int(m1[-1].get("time", time.time()))))
    hour_m1 = [c for c in m1 if hour_start <= int(c.get("time", 0) or 0) < hour_start + HOUR_SECONDS]
    profile = volume_profile_levels(hour_m1 or _closed(m1)[-80:])

    setup: Dict[str, Any] = {
        **rng,
        "_m1": m1,
        "_m5": m5,
        "_m15": m15,
        "_h1": h1,
        "levels": levels,
        "trend": trend,
        "session": sess,
        "volume_ratio_m1": vol_m1,
        "volume_ratio_m5": vol_m5,
        "volume_profile": profile,
        "price": current_price,
        "spread": current_spread,
    }

    # Manage open positions before looking for new trades.
    if positions:
        sig = maybe_close(ctx, setup)
        if sig is not None:
            sig["data"].update({"levels": levels, "trend": trend, "session": sess, "volume_profile": profile})
            return sig

    if not rng.get("valid"):
        return make_signal(SCAN, f"SCAN: {rng.get('reason', 'No valid first-15M 1H range.')}", 0.0, ctx, data=setup)

    range_high = fv(rng["range_high"])
    range_low  = fv(rng["range_low"])
    range_mid  = fv(rng["range_mid"])
    range_size = fv(rng["range_size"])
    tol        = max(range_size * ZONE_TOL_RATIO, MIN_ZONE_TOL)

    # Do not open trades until the first 15M range locks. Still draw it while building.
    if not rng.get("locked"):
        return make_signal(
            SCAN,
            f"SCAN: 1H first-15M range building {range_low:.2f}-{range_high:.2f} | {sess.get('name')} | waiting lock.",
            0.0, ctx, data=setup,
        )

    # Session + spread guards. These do not stop markup, only live entries.
    if not bool(sess.get("tradable")):
        return make_signal(
            SCAN,
            f"SCAN: {sess.get('name')} session filter active. Range {range_low:.2f}-{range_high:.2f}; no new entries.",
            0.0, ctx, data=setup,
        )
    if current_spread and current_spread > MAX_ALLOWED_SPREAD:
        return make_signal(
            HOLD,
            f"HOLD: spread too wide ({current_spread}) for clean execution. Range {range_low:.2f}-{range_high:.2f}.",
            0.0, ctx, data=setup,
        )

    bo = breakout_check(m5, range_high, range_low)
    setup["breakout"] = bo

    closed_m1 = _closed(m1)
    closed_m5 = _closed(m5)
    last1 = closed_m1[-1] if closed_m1 else m1[-1]
    last5 = closed_m5[-1] if closed_m5 else (m5[-1] if m5 else last1)
    entry_ct = int(last1.get("time", 0) or 0)

    trend_bias = trend.get("bias", HOLD)
    profile_poc = fv(profile.get("poc")) if profile.get("valid") else 0.0
    profile_vah = fv(profile.get("vah")) if profile.get("valid") else 0.0
    profile_val = fv(profile.get("val")) if profile.get("valid") else 0.0

    def confluence_score(direction: str, setup_type: str, liq: bool) -> float:
        score = 0.0
        score += 0.18 if rng.get("locked") else 0.0
        score += min(float(sess.get("quality", 0.0)), 1.0) * 0.14
        score += 0.14 if liq else 0.0
        score += 0.10 if vol_m1 >= 0.85 else 0.0
        score += 0.08 if vol_m5 >= 0.90 else 0.0
        score += 0.10 if trend_bias in (direction, HOLD) else 0.02
        if profile.get("valid"):
            if direction == BUY:
                score += 0.08 if current_price >= profile_poc else 0.04
                score += 0.06 if range_low <= profile_val + tol else 0.03
            else:
                score += 0.08 if current_price <= profile_poc else 0.04
                score += 0.06 if range_high >= profile_vah - tol else 0.03
        score += 0.14 if setup_type == "SWEEP" else 0.10
        score += 0.08 if range_size >= MIN_RANGE_SIZE * 2 else 0.04
        score += 0.08  # closed-candle confirmation baseline
        return round(min(score, 1.0), 2)

    # Liquidity sweep reversal: sweep one side, close back inside, target the other side.
    sweep_buy  = detect_liq_grab(closed_m1, range_low, BUY)
    sweep_sell = detect_liq_grab(closed_m1, range_high, SELL)

    if sweep_buy:
        direction = BUY
        entry = round(range_low, 2)  # range low line is the planned reclaim entry zone
        rr = calc_rr(direction, entry, range_high, range_low, liq_grab=True)
        # For sweep reversals, first target is the opposite range wick, then runner uses RR.
        rr["tp"] = max(round(range_high, 2), rr["tp"])
        score = confluence_score(direction, "SWEEP", True)
        setup.update({"entry_level": entry, "sl": rr["sl"], "tp": rr["tp"], "setup_type": "LIQUIDITY_SWEEP_BUY"})
        if score < MIN_SWEEP_SCORE:
            return make_signal(HOLD, f"HOLD: BUY sweep seen but score {score:.2f} < {MIN_SWEEP_SCORE:.2f} | {sess.get('name')} | POC {profile_poc:.2f}", score, ctx, data=setup)
        return make_signal(BUY, f"BUY SWEEP: first-15M 1H low {range_low:.2f} swept/reclaimed | entry line {entry:.2f} | TP {rr['tp']:.2f} | {sess.get('name')} | score {score:.2f}", score, ctx, data=setup, sl=rr["sl"], tp=rr["tp"], entry_candle_time=entry_ct)

    if sweep_sell:
        direction = SELL
        entry = round(range_high, 2)  # range high line is the planned rejection entry zone
        rr = calc_rr(direction, entry, range_high, range_low, liq_grab=True)
        rr["tp"] = min(round(range_low, 2), rr["tp"])
        score = confluence_score(direction, "SWEEP", True)
        setup.update({"entry_level": entry, "sl": rr["sl"], "tp": rr["tp"], "setup_type": "LIQUIDITY_SWEEP_SELL"})
        if score < MIN_SWEEP_SCORE:
            return make_signal(HOLD, f"HOLD: SELL sweep seen but score {score:.2f} < {MIN_SWEEP_SCORE:.2f} | {sess.get('name')} | POC {profile_poc:.2f}", score, ctx, data=setup)
        return make_signal(SELL, f"SELL SWEEP: first-15M 1H high {range_high:.2f} swept/reclaimed | entry line {entry:.2f} | TP {rr['tp']:.2f} | {sess.get('name')} | score {score:.2f}", score, ctx, data=setup, sl=rr["sl"], tp=rr["tp"], entry_candle_time=entry_ct)

    # Breakout continuation: 2 closed 5M candles outside the first-15M 1H wick range.
    if bo.get("confirmed"):
        direction = bo.get("direction", HOLD)
        if direction in (BUY, SELL):
            # Entry line is the range extreme that broke. We prefer continuation only with volume.
            entry = round(range_high if direction == BUY else range_low, 2)
            if direction == BUY:
                sl = round(range_low - max(SL_BUFFER, MIN_SL_POINTS), 2)
                risk = max(entry - sl, MIN_SL_POINTS)
                tp = round(entry + risk * 2.5, 2)
            else:
                sl = round(range_high + max(SL_BUFFER, MIN_SL_POINTS), 2)
                risk = max(sl - entry, MIN_SL_POINTS)
                tp = round(entry - risk * 2.5, 2)
            score = confluence_score(direction, "BREAKOUT", False)
            if vol_m5 < 1.0:
                score = round(score - 0.08, 2)
            if trend_bias not in (direction, HOLD):
                score = round(score - 0.08, 2)
            setup.update({"entry_level": entry, "sl": sl, "tp": tp, "setup_type": f"BREAKOUT_{direction}"})
            if score < MIN_BREAKOUT_SCORE:
                return make_signal(HOLD, f"HOLD: {direction} breakout x{bo.get('count')} but score {score:.2f} < {MIN_BREAKOUT_SCORE:.2f}; waiting retest/volume.", score, ctx, data=setup)
            return make_signal(direction, f"{direction} BREAKOUT: 2x M5 outside first-15M 1H range | entry line {entry:.2f} | SL {sl:.2f} | TP {tp:.2f} | {sess.get('name')} | score {score:.2f}", score, ctx, data=setup, sl=sl, tp=tp, entry_candle_time=entry_ct)

    # Zone watch / no trade.
    lo1 = fv(m1[-1].get("low")); hi1 = fv(m1[-1].get("high"))
    at_buy_zone  = lo1 <= range_low + tol
    at_sell_zone = hi1 >= range_high - tol
    if at_buy_zone or at_sell_zone:
        side = BUY if at_buy_zone else SELL
        zone = range_low if side == BUY else range_high
        return make_signal(HOLD, f"HOLD: price testing {side} line {zone:.2f}; waiting sweep/reclaim or 2x M5 breakout | {sess.get('name')} | vol {vol_m1:.2f}/{vol_m5:.2f}", 0.0, ctx, data=setup)

    return make_signal(
        SCAN,
        f"SCAN: 1H first-15M wick range {range_low:.2f}-{range_high:.2f} | price {current_price:.2f} | {sess.get('name')} | trend {trend_bias} | POC {profile_poc:.2f}",
        0.0, ctx, data=setup,
    )


# ══════════════════════════════════════════════
#  DRAW COMMANDS  —  clean, minimal chart markup
# ══════════════════════════════════════════════

def build_draw_commands(ctx: Dict[str, Any],
                        decision: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Enhanced live markup:
      - First 15M wick range of the active 1H candle, extended through the full hour
      - High/low/mid entry framework
      - Session label and trend context
      - Internal MT5-volume profile POC / VAH / VAL from tick volume
      - Entry / SL / TP rays from real signal prices
    """
    cmds: List[Dict[str, Any]] = [{"type": "clear_all"}]
    now = int(time.time())
    data = (decision or {}).get("data") or {}
    action = str((decision or {}).get("action", SCAN)).upper()

    m15_list = data.get("_m15") or []
    m1_list = data.get("_m1") or []
    if not m15_list or not m1_list:
        tfs_ctx = get_timeframes(ctx)
        m15_list = m15_list or tfs_ctx.get("M15", [])
        m1_list = m1_list or tfs_ctx.get("M1", [])

    current_price = fv((m1_list[-1] if m1_list else {}).get("close"))
    rng_high = fv(data.get("range_high"))
    rng_low = fv(data.get("range_low"))
    rng_mid = fv(data.get("range_mid"))
    bar_start = int(data.get("range_start") or now - HOUR_SECONDS)
    bar_end = int(data.get("range_end") or bar_start + HOUR_SECONDS)
    first_end = int(data.get("first_15m_end") or bar_start + FIRST_15M_SECONDS)
    locked = bool(data.get("locked"))
    rng_dir = data.get("range_direction", HOLD)
    sess = data.get("session") or session_context(now)
    trend = data.get("trend") or {}
    profile = data.get("volume_profile") or {}

    if rng_high > 0 and rng_low > 0:
        box_color = "green" if rng_dir == BUY else "red" if rng_dir == SELL else "yellow"
        status = "1H PO3 LOCKED" if locked else "1H PO3 BUILDING"

        # First 15M source box only, matching your wick range concept.
        cmds.append({"type": "box", "name": "TS_FIRST15_SOURCE_BOX",
                     "time1": bar_start, "time2": first_end,
                     "price1": rng_high, "price2": rng_low,
                     "color": box_color, "text": ""})

        # Full active-hour range box so the 1H chart is marked like your TradingView example.
        cmds.append({"type": "box", "name": "TS_1H_PO3_RANGE_BOX",
                     "time1": bar_start, "time2": bar_end,
                     "price1": rng_high, "price2": rng_low,
                     "color": box_color, "text": ""})

        cmds.append({"type": "ray", "name": "TS_RANGE_HIGH",
                     "time1": bar_start, "price1": rng_high,
                     "color": "red", "width": 2,
                     "text": f"{status} HIGH / SELL-SWEEP / BUY-BO {rng_high:.2f}"})
        cmds.append({"type": "ray", "name": "TS_RANGE_LOW",
                     "time1": bar_start, "price1": rng_low,
                     "color": "green", "width": 2,
                     "text": f"{status} LOW / BUY-SWEEP / SELL-BO {rng_low:.2f}"})
        cmds.append({"type": "ray", "name": "TS_RANGE_MID",
                     "time1": bar_start, "price1": rng_mid,
                     "color": "yellow", "width": 1,
                     "text": f"MID / CONTROL {rng_mid:.2f}"})

        label = f"{status} | Range {rng_high-rng_low:.2f} USD | {sess.get('name')} | Trend {trend.get('bias', HOLD)}"
        cmds.append({"type": "text", "name": "TS_PO3_LABEL",
                     "time": max(bar_start, now - 300), "price": rng_mid,
                     "color": "yellow", "text": label[:95]})

    # Volume profile levels calculated from MT5 bars/tick volume.
    if profile.get("valid"):
        for nm, lv, col, txt in [
            ("TS_VP_POC", fv(profile.get("poc")), "blue", "POC"),
            ("TS_VP_VAH", fv(profile.get("vah")), "orange", "VAH"),
            ("TS_VP_VAL", fv(profile.get("val")), "cyan", "VAL"),
        ]:
            if lv > 0:
                cmds.append({"type": "ray", "name": nm,
                             "time1": bar_start, "price1": lv,
                             "color": col, "width": 1,
                             "text": f"{txt} {lv:.2f}"})

    # Nearest swing levels.
    levels = data.get("levels") or (nearest_swing_levels(m15_list, current_price, lookback=16) if m15_list else {})
    ray_start = now - 240
    for j, lv in enumerate(levels.get("resistance", [])[:2]):
        cmds.append({"type": "ray", "name": f"TS_RES_{j}",
                     "time1": ray_start, "price1": lv,
                     "color": "orange", "width": 1,
                     "text": f"Nearest R {lv:.2f}"})
    for j, lv in enumerate(levels.get("support", [])[:2]):
        cmds.append({"type": "ray", "name": f"TS_SUP_{j}",
                     "time1": ray_start, "price1": lv,
                     "color": "cyan", "width": 1,
                     "text": f"Nearest S {lv:.2f}"})

    entry_level = fv(data.get("entry_level"))
    tp_level = fv((decision or {}).get("tp") or data.get("tp"))
    sl_level = fv((decision or {}).get("sl") or data.get("sl"))
    setup_type = str(data.get("setup_type") or "")

    if entry_level > 0 and action in (BUY, SELL):
        e_color = "green" if action == BUY else "red"
        cmds.append({"type": "ray", "name": "TS_ENTRY",
                     "time1": now - 180, "price1": entry_level,
                     "color": e_color, "width": 3,
                     "text": f"{action} ENTRY LINE {entry_level:.2f} {setup_type}"})
    if tp_level > 0:
        cmds.append({"type": "ray", "name": "TS_TP",
                     "time1": now - 180, "price1": tp_level,
                     "color": "blue", "width": 2,
                     "text": f"TAKE PROFIT {tp_level:.2f}"})
    if sl_level > 0:
        cmds.append({"type": "ray", "name": "TS_SL",
                     "time1": now - 180, "price1": sl_level,
                     "color": "orange", "width": 2,
                     "text": f"STOP LOSS {sl_level:.2f}"})

    bo = data.get("breakout", {})
    if bo.get("confirmed") and rng_mid > 0:
        bo_dir = bo.get("direction", HOLD)
        bo_color = "green" if bo_dir == BUY else "red"
        offset = (rng_high - rng_low) * 0.18 if rng_high > rng_low else 0.5
        lbl_price = rng_mid + (offset if bo_dir == BUY else -offset)
        cmds.append({"type": "text", "name": "TS_BO_LABEL",
                     "time": now - 120, "price": lbl_price,
                     "color": bo_color,
                     "text": f"BREAKOUT {bo_dir} x{bo.get('count')}"})

    reason = str((decision or {}).get("reason", "Scanning..."))[:100]
    lbl_price = rng_mid if rng_mid > 0 else current_price
    a_color = "green" if action == BUY else "red" if action == SELL else "yellow"
    cmds.append({"type": "text", "name": "TS_STATUS",
                 "time": now - 180, "price": lbl_price,
                 "color": a_color,
                 "text": f"{action} | {reason}"})

    return cmds


# ══════════════════════════════════════════════
#  FILE I/O
# ══════════════════════════════════════════════

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


def write_draws(ctx: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> int:
    cmds    = build_draw_commands(ctx, decision)
    payload = {
        "version":       21,
        "source":        "TradeSmartAI",
        "strategy":      "first15m_1h_po3_liquidity_v5",
        "updated":       time.time(),
        "command_count": len(cmds),
        "commands":      cmds,
    }
    for p in draw_paths():
        write_json(p, payload)
    return len(cmds)


def write_debug(ctx: Dict[str, Any], result: Dict[str, Any], command_count: int) -> None:
    base = draw_paths()[0].parent
    write_json(base / DEBUG_FILE, {
        "updated":       time.time(),
        "action":        result.get("action"),
        "reason":        result.get("reason"),
        "confidence":    result.get("confidence"),
        "sl":            result.get("sl"),
        "tp":            result.get("tp"),
        "command_count": command_count,
        "data":          result.get("data", {}),
    })
