"""
strategy_common.py  —  TradeSmart SMC Scalp Engine  v4.0
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
    if not m1:
        return {"valid": False, "reason": "No M1 data."}

    # Identify current 15M bar start
    ref_ts    = int(m1[-1].get("time", 0) or time.time())
    bar_start = floor_15m(ref_ts)

    # Check if the current 15M bar has already CLOSED (appears in M15 closed list)
    # M15 list from MT5 includes the forming candle as the last element.
    # Closed bars = all except the last.
    m15_closed = m15[:-1] if len(m15) > 1 else []
    locked_bars = [c for c in m15_closed if int(c.get("time", 0) or 0) == bar_start]

    if locked_bars:
        # Use the closed 15M candle's wick extremes directly
        bar   = locked_bars[-1]
        high  = fv(bar.get("high"))
        low   = fv(bar.get("low"))
        open_ = fv(bar.get("open"))
        close = fv(bar.get("close"))
        source = "locked_15m_candle"
        is_locked = True
    else:
        # Bar is still forming — build from M1 wicks in the first 5 minutes
        first5_end = bar_start + 300
        window = [c for c in m1 if bar_start <= int(c.get("time", 0) or 0) < first5_end]
        if not window:
            return {"valid": False,
                    "reason": f"Waiting for first M1 candle of 15M bar at {bar_start}.",
                    "active_15m_start": bar_start}
        high  = max(fv(c.get("high")) for c in window)
        low   = min(fv(c.get("low"))  for c in window)
        open_ = fv(window[0].get("open"))
        close = fv(window[-1].get("close"))
        source = "live_first5m"
        is_locked = False

    rng = high - low
    if rng < MIN_RANGE_SIZE:
        return {"valid": False, "reason": f"Range too small ({rng:.2f} pts).",
                "active_15m_start": bar_start}

    direction = BUY if close > open_ else SELL if close < open_ else HOLD
    return {
        "valid":            True,
        "locked":           is_locked,
        "source":           source,
        "active_15m_start": bar_start,
        "range_start":      bar_start,
        "range_end":        bar_start + 900,
        "range_high":       high,
        "range_low":        low,
        "range_mid":        (high + low) / 2.0,
        "range_size":       rng,
        "range_open":       open_,
        "range_close":      close,
        "range_direction":  direction,
        "reason":           "Range locked." if is_locked else "Range building (first 5M).",
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
        "strategy":         "xauusd_m15_wick_scalp",
        "name":             "xauusd_m15_wick_scalp",
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

    positions = ctx.get("positions") or []

    # Guard: need enough data
    if len(m1) < 5:
        return make_signal(SCAN, "SCAN: Waiting for M1 candle history.", 0.0, ctx)
    if len(m15) < 3:
        return make_signal(SCAN, "SCAN: Waiting for M15 candle history.", 0.0, ctx)

    # Current price
    current_price = fv(m1[-1].get("close"))

    # Build the 15M range
    rng = build_15m_range(m1, m15)

    # Swing levels for context
    levels = nearest_swing_levels(m15, current_price, lookback=10)

    setup: Dict[str, Any] = {
        **rng,
        "_m1":      m1,
        "_m5":      m5,
        "_m15":     m15,
        "levels":   levels,
        "price":    current_price,
    }

    # ── Manage open position FIRST ─────────────
    if positions:
        sig = maybe_close(ctx, setup)
        if sig is not None:
            sig["data"].update({"levels": levels})
            return sig

    if not rng.get("valid"):
        return make_signal(SCAN, f"SCAN: {rng.get('reason', 'No valid range.')}",
                           0.0, ctx, data=setup)

    range_high = fv(rng["range_high"])
    range_low  = fv(rng["range_low"])
    range_mid  = fv(rng["range_mid"])
    range_size = fv(rng["range_size"])
    tol        = max(range_size * ZONE_TOL_RATIO, MIN_ZONE_TOL)

    # ── Breakout check ─────────────────────────
    bo = breakout_check(m5, range_high, range_low)
    setup["breakout"] = bo

    if bo["confirmed"]:
        direction = bo["direction"]
        liq = detect_liq_grab(m1,
                               range_low  if direction == BUY  else range_high,
                               direction)
        # Entry = close of last closed M1 candle
        closed_m1 = m1[:-1] if len(m1) > 1 else m1
        entry = fv(closed_m1[-1].get("close")) if closed_m1 else current_price
        entry_ct  = int(closed_m1[-1].get("time", 0)) if closed_m1 else 0

        rr  = {
            BUY:  {"sl": round(range_low  - max(SL_BUFFER, MIN_SL_POINTS), 2),
                   "tp": round(entry + (entry - (range_low - SL_BUFFER)) * 3, 2)},
            SELL: {"sl": round(range_high + max(SL_BUFFER, MIN_SL_POINTS), 2),
                   "tp": round(entry - ((range_high + SL_BUFFER) - entry) * 3, 2)},
        }[direction]

        conf = min(0.88 + (0.08 if liq else 0.0), 1.0)
        setup.update({"entry_level": entry, "sl": rr["sl"], "tp": rr["tp"]})
        return make_signal(
            direction,
            f"{direction} BREAKOUT: {bo['count']} M5 closes outside range. "
            f"E={entry:.2f}  SL={rr['sl']:.2f}  TP={rr['tp']:.2f}"
            + (" [LIQ]" if liq else ""),
            conf, ctx, data=setup, sl=rr["sl"], tp=rr["tp"],
            entry_candle_time=entry_ct,
        )

    # ── Zone touch detection ───────────────────
    last_m1 = m1[-1]
    lo1     = fv(last_m1.get("low"))
    hi1     = fv(last_m1.get("high"))

    at_buy_zone  = lo1 <= range_low  + tol
    at_sell_zone = hi1 >= range_high - tol

    if not at_buy_zone and not at_sell_zone:
        return make_signal(
            SCAN,
            f"SCAN: {range_low:.2f}–{range_high:.2f} | Price {current_price:.2f} — watching zones.",
            0.0, ctx, data=setup,
        )

    direction    = BUY if at_buy_zone else SELL
    zone_extreme = range_low if direction == BUY else range_high

    # ── 5M confirmation ────────────────────────
    if len(m5) >= 3:
        if not confirm_5m(m5, direction, zone_extreme):
            return make_signal(
                HOLD,
                f"HOLD: Price at {direction} zone {zone_extreme:.2f} — waiting for 5M rejection candle.",
                0.0, ctx, data=setup,
            )

    # ── 1M trigger  (candle color + volume) ───
    m1_ok, vol_ok, trigger_candle = confirm_1m(m1, direction, zone_extreme)

    if not m1_ok:
        return make_signal(
            HOLD,
            f"HOLD: 5M at {direction} zone — waiting for 1M {'red' if direction == BUY else 'green'} trigger candle.",
            0.0, ctx, data=setup,
        )

    # ── Liquidity grab confluence ───────────────
    liq   = detect_liq_grab(m1, zone_extreme, direction)

    # Entry = close of the trigger candle
    entry    = fv(trigger_candle.get("close"))
    entry_ct = int(trigger_candle.get("time", 0))

    rr    = calc_rr(direction, entry, range_high, range_low, liq_grab=liq)
    score = min(0.78 + (0.12 if liq else 0.0) + (0.07 if vol_ok else 0.0), 1.0)

    setup.update({"entry_level": entry, "sl": rr["sl"], "tp": rr["tp"],
                  "trigger_candle": trigger_candle})

    tag_liq = " [LIQ]"  if liq   else ""
    tag_vol = " [VOL+]" if vol_ok else ""
    reason  = (
        f"{direction}: 15M {range_low:.2f}–{range_high:.2f} | "
        f"5M+1M {'red' if direction==BUY else 'green'} trigger{tag_liq}{tag_vol} | "
        f"E={entry:.2f}  SL={rr['sl']:.2f}  TP={rr['tp']:.2f}  (1:3)"
    )
    return make_signal(direction, reason, score, ctx,
                       data=setup, sl=rr["sl"], tp=rr["tp"],
                       entry_candle_time=entry_ct)


# ══════════════════════════════════════════════
#  DRAW COMMANDS  —  clean, minimal chart markup
# ══════════════════════════════════════════════

def build_draw_commands(ctx: Dict[str, Any],
                        decision: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Clean chart markup:
      - Active 15M range box + HIGH / LOW rays only
      - 2 nearest resistance rays (red, short)
      - 2 nearest support rays   (green, short)
      - Entry / SL / TP rays when trade is live
      - Status text anchored LEFT of current bar (not drifting right)
    """
    cmds: List[Dict[str, Any]] = [{"type": "clear_all"}]
    now  = int(time.time())

    data     = (decision or {}).get("data") or {}
    action   = (decision or {}).get("action", SCAN)

    # Pull candle lists from data or re-fetch
    m15_list = data.get("_m15") or []
    m1_list  = data.get("_m1")  or []
    if not m15_list or not m1_list:
        tfs_ctx = get_timeframes(ctx)
        if not m15_list:
            m15_list = tfs_ctx.get("M15", [])
        if not m1_list:
            m1_list  = tfs_ctx.get("M1",  [])

    current_price = fv((m1_list[-1] if m1_list else {}).get("close"))

    # ── Active 15M range ───────────────────────
    rng_high  = fv(data.get("range_high"))
    rng_low   = fv(data.get("range_low"))
    rng_mid   = fv(data.get("range_mid"))
    bar_start = int(data.get("range_start") or now - 900)
    bar_end   = int(data.get("range_end")   or bar_start + 900)
    locked    = bool(data.get("locked"))
    rng_dir   = data.get("range_direction", HOLD)

    if rng_high > 0 and rng_low > 0:
        box_color = "green" if rng_dir == BUY else "red" if rng_dir == SELL else "yellow"
        status    = "RANGE" if locked else "BUILDING"

        # Box spanning only the active bar
        cmds.append({"type": "box", "name": "TS_RANGE_BOX",
                     "time1": bar_start, "time2": bar_end,
                     "price1": rng_high, "price2": rng_low,
                     "color": box_color, "text": ""})

        # HIGH ray — anchored at bar start, label LEFT of bar
        cmds.append({"type": "ray", "name": "TS_RANGE_HIGH",
                     "time1": bar_start, "price1": rng_high,
                     "color": "red", "width": 2,
                     "text": f"{status} H {rng_high:.2f}"})

        # LOW ray
        cmds.append({"type": "ray", "name": "TS_RANGE_LOW",
                     "time1": bar_start, "price1": rng_low,
                     "color": "green", "width": 2,
                     "text": f"{status} L {rng_low:.2f}"})

    # ── Nearest swing levels ───────────────────
    levels = data.get("levels") or (
        nearest_swing_levels(m15_list, current_price, lookback=10) if m15_list else {}
    )
    ray_start = now - 120  # short rays, anchored near current bar

    for j, lv in enumerate(levels.get("resistance", [])[:2]):
        cmds.append({"type": "ray", "name": f"TS_RES_{j}",
                     "time1": ray_start, "price1": lv,
                     "color": "orange", "width": 1,
                     "text": f"R {lv:.2f}"})

    for j, lv in enumerate(levels.get("support", [])[:2]):
        cmds.append({"type": "ray", "name": f"TS_SUP_{j}",
                     "time1": ray_start, "price1": lv,
                     "color": "cyan", "width": 1,
                     "text": f"S {lv:.2f}"})

    # ── Entry / SL / TP ────────────────────────
    entry_level = fv(data.get("entry_level"))
    tp_level    = fv((decision or {}).get("tp") or data.get("tp"))
    sl_level    = fv((decision or {}).get("sl") or data.get("sl"))

    if entry_level > 0 and action in (BUY, SELL):
        e_color = "green" if action == BUY else "red"
        cmds.append({"type": "ray", "name": "TS_ENTRY",
                     "time1": now - 60, "price1": entry_level,
                     "color": e_color, "width": 3,
                     "text": f"ENTRY {entry_level:.2f}"})
    if tp_level > 0:
        cmds.append({"type": "ray", "name": "TS_TP",
                     "time1": now - 60, "price1": tp_level,
                     "color": "blue", "width": 2,
                     "text": f"TP {tp_level:.2f}"})
    if sl_level > 0:
        cmds.append({"type": "ray", "name": "TS_SL",
                     "time1": now - 60, "price1": sl_level,
                     "color": "orange", "width": 2,
                     "text": f"SL {sl_level:.2f}"})

    # ── Breakout marker ────────────────────────
    bo = data.get("breakout", {})
    if bo.get("confirmed") and rng_mid > 0:
        bo_dir   = bo.get("direction", HOLD)
        bo_color = "green" if bo_dir == BUY else "red"
        # Offset text slightly above/below mid so it doesn't overlap range lines
        offset   = (rng_high - rng_low) * 0.15 if rng_high > rng_low else 0.5
        lbl_price= rng_mid + (offset if bo_dir == BUY else -offset)
        cmds.append({"type": "text", "name": "TS_BO_LABEL",
                     "time": now - 60, "price": lbl_price,
                     "color": bo_color,
                     "text": f"BO {bo_dir} x{bo.get('count')}"})

    # ── Status label  (anchored 2 bars LEFT) ──
    reason   = str((decision or {}).get("reason", "Scanning..."))
    # Truncate to 80 chars max so it fits within the chart window
    short_reason = reason[:80]
    lbl_price = rng_mid if rng_mid > 0 else current_price
    # Place label at now - 2 bars (120s) so it appears on the chart, not off-screen
    lbl_time  = now - 120
    a_color   = "green" if action == BUY else "red" if action == SELL else "yellow"
    cmds.append({"type": "text", "name": "TS_STATUS",
                 "time": lbl_time, "price": lbl_price,
                 "color": a_color,
                 "text": f"{action} | {short_reason}"})

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
        "version":       14,
        "source":        "TradeSmartAI",
        "strategy":      "m15_wick_scalp_v4",
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
