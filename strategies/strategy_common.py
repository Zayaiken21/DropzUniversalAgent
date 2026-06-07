"""
strategy_common.py
==================
XAU/USD SMC Scalp Strategy — Enhanced Edition
----------------------------------------------
Core Flow:
  1. Every 15 minutes — scan the closed 15M candle for wick zones (buy/sell zones).
  2. When price returns to a 15M wick zone — drop to 5M for confirmation candle.
  3. When 5M confirms — drop to 1M for entry candle + liquidity-grab fingerprint.
  4. Breakout detection tracks consecutive closes outside zone to read market direction strength.
  5. Liquidity-grab logic identifies stop-hunt wicks above highs / below lows before reversal.

Trade placement structure is preserved from the original (make_signal / build_decision / maybe_close).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────
BUY  = "BUY"
SELL = "SELL"
CLOSE = "CLOSE"
HOLD  = "HOLD"

SYMBOL_DEFAULT = "XAUUSD"
DRAW_ENV   = "TRADESMART_MT5_BRIDGE_FILE"
DRAW_JSON1 = "TradeSmart_AI_DrawCommands.json1"
DRAW_JSONL = "TradeSmart_AI_DrawCommands.jsonl"
DEBUG_FILE = "TradeSmart_AI_Debug_LastSignal.json"

# Minimum wick-body ratio for a candle to qualify as a wick zone.
WICK_BODY_RATIO_MIN = 0.40          # wick must be ≥ 40% of the full candle range
# How many pips of wick before we tag it as a liquidity-grab candidate.
LIQ_GRAB_WICK_PIPS  = 0.30          # 30 pips (price units) — tune for XAU
# Breakout strength: consecutive closed candles beyond zone to declare directional break.
BREAKOUT_CANDLE_THRESH = 2
# Default zone tolerance multiplier (fraction of 15M range).
ZONE_TOL_RATIO = 0.08


# ──────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────

def f(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except Exception:
        return default


def symbol_from_context(context: Dict[str, Any]) -> str:
    return str(
        context.get("symbol")
        or (context.get("profile") or {}).get("symbol")
        or SYMBOL_DEFAULT
    )


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


def candle_direction(candle: Dict[str, Any]) -> str:
    c = f(candle.get("close"))
    o = f(candle.get("open"))
    if c > o:
        return BUY
    if c < o:
        return SELL
    return HOLD


def candle_body(candle: Dict[str, Any]) -> float:
    return abs(f(candle.get("close")) - f(candle.get("open")))


def candle_range(candle: Dict[str, Any]) -> float:
    return f(candle.get("high")) - f(candle.get("low"))


def upper_wick(candle: Dict[str, Any]) -> float:
    return f(candle.get("high")) - max(f(candle.get("open")), f(candle.get("close")))


def lower_wick(candle: Dict[str, Any]) -> float:
    return min(f(candle.get("open")), f(candle.get("close"))) - f(candle.get("low"))


def floor_15m(ts: int) -> int:
    """Floor a unix timestamp to the most recent 15-minute boundary."""
    return int(ts) - (int(ts) % 900)


def hour_start(ts: int) -> int:
    return int(ts) - (int(ts) % 3600)


# ──────────────────────────────────────────────
#  MT5 Data Fetch
# ──────────────────────────────────────────────

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
        "M1":  getattr(mt5, "TIMEFRAME_M1",  None),
        "M5":  getattr(mt5, "TIMEFRAME_M5",  None),
        "M15": getattr(mt5, "TIMEFRAME_M15", None),
        "H1":  getattr(mt5, "TIMEFRAME_H1",  None),
    }
    bars = {"M1": 300, "M5": 200, "M15": 100, "H1": 100}

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
                "time":        int(r["time"]),
                "open":        float(r["open"]),
                "high":        float(r["high"]),
                "low":         float(r["low"]),
                "close":       float(r["close"]),
                "tick_volume": int(r["tick_volume"]),
                "spread":      int(r["spread"]),
                "real_volume": int(r["real_volume"]),
            })

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
            if tf in ("M1", "M5", "M15", "H1"):
                rows = [normalize_candle(c) for c in list(v or [])]
                rows = [r for r in rows if r]
                rows.sort(key=lambda x: int(x.get("time", 0) or 0))
                out[tf] = rows if include_forming else (rows[:-1] if len(rows) > 2 else rows)

    aliases = {
        "M1":  ("rates", "closed_rates", "candles", "m1_rates", "rates_m1", "bars"),
        "M5":  ("m5_rates",  "rates_m5"),
        "M15": ("m15_rates", "rates_m15"),
        "H1":  ("h1_rates",  "rates_h1"),
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


# ──────────────────────────────────────────────
#  15M Wick Zone Scanner
# ──────────────────────────────────────────────

def classify_15m_wick_zone(candle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Inspect a closed 15M candle and return a wick zone if significant wicks exist.

    A zone is created when the wick is ≥ WICK_BODY_RATIO_MIN × full range.
    Zones come in two flavours:
      - "sell_zone"  — upper wick dominant  (price rejected from highs, sellers lurk)
      - "buy_zone"   — lower wick dominant  (price rejected from lows, buyers lurk)
    If both wicks qualify, the dominant one takes priority.

    Returns a zone dict or None.
    """
    rng = candle_range(candle)
    if rng <= 0:
        return None

    uw = upper_wick(candle)
    lw = lower_wick(candle)
    body = candle_body(candle)

    uw_ratio = uw / rng
    lw_ratio = lw / rng

    upper_qualifies = uw_ratio >= WICK_BODY_RATIO_MIN
    lower_qualifies = lw_ratio >= WICK_BODY_RATIO_MIN

    if not (upper_qualifies or lower_qualifies):
        return None

    # Dominant wick wins; in a tie, both zones are returned separately via the caller.
    if upper_qualifies and (not lower_qualifies or uw >= lw):
        zone_type  = "sell_zone"
        zone_high  = f(candle.get("high"))
        zone_low   = max(f(candle.get("open")), f(candle.get("close")))
        wick_size  = uw
    else:
        zone_type  = "buy_zone"
        zone_high  = min(f(candle.get("open")), f(candle.get("close")))
        zone_low   = f(candle.get("low"))
        wick_size  = lw

    is_liq_grab = wick_size >= LIQ_GRAB_WICK_PIPS

    return {
        "type":          zone_type,
        "zone_high":     zone_high,
        "zone_low":      zone_low,
        "zone_mid":      (zone_high + zone_low) / 2.0,
        "wick_size":     wick_size,
        "wick_ratio":    uw_ratio if zone_type == "sell_zone" else lw_ratio,
        "body_size":     body,
        "candle_range":  rng,
        "is_liq_grab":   is_liq_grab,
        "candle_time":   int(candle.get("time", 0) or 0),
        "candle_open":   f(candle.get("open")),
        "candle_high":   f(candle.get("high")),
        "candle_low":    f(candle.get("low")),
        "candle_close":  f(candle.get("close")),
    }


def scan_15m_wick_zones(m15_candles: List[Dict[str, Any]], lookback: int = 8) -> List[Dict[str, Any]]:
    """
    Walk the last `lookback` closed 15M candles and collect all wick zones.
    Returns newest-first list of zone dicts.
    """
    zones: List[Dict[str, Any]] = []
    closed = m15_candles[:-1] if len(m15_candles) > 1 else m15_candles  # exclude forming
    for candle in reversed(closed[-lookback:]):
        zone = classify_15m_wick_zone(candle)
        if zone:
            zones.append(zone)
    return zones


def price_in_zone(price: float, zone: Dict[str, Any], tol: float = 0.0) -> bool:
    return (zone["zone_low"] - tol) <= price <= (zone["zone_high"] + tol)


def current_zone(
    m15_candles: List[Dict[str, Any]],
    current_price: float,
    tol_ratio: float = ZONE_TOL_RATIO,
    lookback: int = 8,
) -> Optional[Dict[str, Any]]:
    """Return the most recent 15M wick zone that price is currently touching."""
    zones = scan_15m_wick_zones(m15_candles, lookback=lookback)
    for zone in zones:
        tol = max(zone["candle_range"] * tol_ratio, 0.20)
        if price_in_zone(current_price, zone, tol=tol):
            return {**zone, "tolerance": tol}
    return None


# ──────────────────────────────────────────────
#  Liquidity Grab Detection
# ──────────────────────────────────────────────

def detect_liquidity_grab(
    candles: List[Dict[str, Any]],
    zone: Dict[str, Any],
    direction: str,
) -> Dict[str, Any]:
    """
    A liquidity grab (stop hunt) is when the wick of a candle breaches the zone extreme
    but the CLOSE returns inside the zone — trapping breakout traders.

    direction: "BUY"  → look for a wick below zone_low that closes back above it.
               "SELL" → look for a wick above zone_high that closes back below it.

    Returns a dict with:
      - confirmed (bool)
      - grab_candle_time
      - grab_extreme (the wick tip that grabbed stops)
      - grab_candle_index (-1 = last closed, -2 = two ago, …)
    """
    result = {"confirmed": False, "grab_candle_time": None, "grab_extreme": None, "grab_candle_index": None}

    if not candles or not zone:
        return result

    # Inspect last 3 closed candles for the grab signature.
    for i, idx in enumerate([-1, -2, -3]):
        try:
            c = candles[idx]
        except IndexError:
            break

        if direction == BUY:
            # Wick poked below zone_low, close recovered above zone_low.
            if f(c.get("low")) < zone["zone_low"] and f(c.get("close")) > zone["zone_low"]:
                result = {
                    "confirmed":          True,
                    "grab_candle_time":   int(c.get("time", 0) or 0),
                    "grab_extreme":       f(c.get("low")),
                    "grab_candle_index":  idx,
                    "grab_direction":     BUY,
                }
                break
        else:  # SELL
            # Wick poked above zone_high, close came back below zone_high.
            if f(c.get("high")) > zone["zone_high"] and f(c.get("close")) < zone["zone_high"]:
                result = {
                    "confirmed":          True,
                    "grab_candle_time":   int(c.get("time", 0) or 0),
                    "grab_extreme":       f(c.get("high")),
                    "grab_candle_index":  idx,
                    "grab_direction":     SELL,
                }
                break

    return result


# ──────────────────────────────────────────────
#  Breakout Strength
# ──────────────────────────────────────────────

def breakout_strength(
    candles: List[Dict[str, Any]],
    zone: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Count consecutive candle closes ABOVE zone_high (bullish breakout)
    or BELOW zone_low (bearish breakout).

    Returns:
      - direction    : BUY / SELL / HOLD
      - candle_count : consecutive candles confirming break
      - confirmed    : True if count >= BREAKOUT_CANDLE_THRESH
      - momentum     : "strong" / "forming" / "none"
    """
    if not candles or not zone:
        return {"direction": HOLD, "candle_count": 0, "confirmed": False, "momentum": "none"}

    bull_count = 0
    bear_count = 0

    for c in reversed(candles[-6:]):
        close = f(c.get("close"))
        if close > zone["zone_high"]:
            bull_count += 1
            bear_count  = 0
        elif close < zone["zone_low"]:
            bear_count += 1
            bull_count  = 0
        else:
            break  # inside zone — streak ends

    if bull_count > 0:
        confirmed = bull_count >= BREAKOUT_CANDLE_THRESH
        return {
            "direction":    BUY,
            "candle_count": bull_count,
            "confirmed":    confirmed,
            "momentum":     "strong" if bull_count >= BREAKOUT_CANDLE_THRESH + 1 else ("forming" if confirmed else "building"),
        }
    if bear_count > 0:
        confirmed = bear_count >= BREAKOUT_CANDLE_THRESH
        return {
            "direction":    SELL,
            "candle_count": bear_count,
            "confirmed":    confirmed,
            "momentum":     "strong" if bear_count >= BREAKOUT_CANDLE_THRESH + 1 else ("forming" if confirmed else "building"),
        }

    return {"direction": HOLD, "candle_count": 0, "confirmed": False, "momentum": "none"}


# ──────────────────────────────────────────────
#  5M Confirmation
# ──────────────────────────────────────────────

def confirm_5m(
    m5_candles: List[Dict[str, Any]],
    zone: Dict[str, Any],
) -> Dict[str, Any]:
    """
    On the 5M timeframe, look for a confirmation candle that:
      - For a buy_zone : closes ABOVE zone_low with a bullish candle and lower-wick rejection.
      - For a sell_zone: closes BELOW zone_high with a bearish candle and upper-wick rejection.

    Returns:
      - confirmed (bool)
      - signal    : BUY / SELL / HOLD
      - reason    : human-readable explanation
      - candle    : the confirming 5M candle dict
    """
    base = {"confirmed": False, "signal": HOLD, "reason": "No 5M confirmation.", "candle": None}
    if not m5_candles or not zone:
        return base

    # Use last 3 closed 5M candles to find the confirmation.
    closed = m5_candles[:-1] if len(m5_candles) > 1 else m5_candles
    for c in reversed(closed[-3:]):
        close_  = f(c.get("close"))
        open_   = f(c.get("open"))
        high_   = f(c.get("high"))
        low_    = f(c.get("low"))
        rng     = high_ - low_
        uw      = upper_wick(c)
        lw      = lower_wick(c)

        if zone["type"] == "buy_zone":
            bullish = close_ > open_
            # Body closed above zone_low, lower wick shows rejection.
            if bullish and close_ >= zone["zone_low"] and lw >= rng * 0.25:
                return {
                    "confirmed": True,
                    "signal":    BUY,
                    "reason":    f"5M bullish rejection candle above buy zone low @ {zone['zone_low']:.2f}.",
                    "candle":    c,
                }

        elif zone["type"] == "sell_zone":
            bearish = close_ < open_
            # Body closed below zone_high, upper wick shows rejection.
            if bearish and close_ <= zone["zone_high"] and uw >= rng * 0.25:
                return {
                    "confirmed": True,
                    "signal":    SELL,
                    "reason":    f"5M bearish rejection candle below sell zone high @ {zone['zone_high']:.2f}.",
                    "candle":    c,
                }

    return base


# ──────────────────────────────────────────────
#  1M Entry Confirmation
# ──────────────────────────────────────────────

def confirm_1m(
    m1_candles: List[Dict[str, Any]],
    zone: Dict[str, Any],
    signal_direction: str,
) -> Dict[str, Any]:
    """
    On the 1M timeframe, look for the entry trigger candle:
      - BUY : last closed 1M is bullish and closes above zone_low.
      - SELL: last closed 1M is bearish and closes below zone_high.
    Also checks for a 1M-level liquidity grab as extra confluence.
    """
    base = {"confirmed": False, "signal": HOLD, "reason": "No 1M confirmation.", "candle": None, "liq_grab": False}
    if not m1_candles or not zone:
        return base

    closed = m1_candles[:-1] if len(m1_candles) > 1 else m1_candles
    if not closed:
        return base

    last = closed[-1]
    close_ = f(last.get("close"))
    open_  = f(last.get("open"))

    liq = detect_liquidity_grab(closed, zone, signal_direction)

    if signal_direction == BUY:
        if close_ > open_ and close_ >= zone["zone_low"]:
            return {
                "confirmed": True,
                "signal":    BUY,
                "reason":    f"1M bullish close above buy zone low @ {zone['zone_low']:.2f}. Liq grab={'YES' if liq['confirmed'] else 'NO'}.",
                "candle":    last,
                "liq_grab":  liq["confirmed"],
                "liq_data":  liq,
            }

    elif signal_direction == SELL:
        if close_ < open_ and close_ <= zone["zone_high"]:
            return {
                "confirmed": True,
                "signal":    SELL,
                "reason":    f"1M bearish close below sell zone high @ {zone['zone_high']:.2f}. Liq grab={'YES' if liq['confirmed'] else 'NO'}.",
                "candle":    last,
                "liq_grab":  liq["confirmed"],
                "liq_data":  liq,
            }

    return {**base, "liq_grab": liq["confirmed"], "liq_data": liq}


# ──────────────────────────────────────────────
#  Main Signal Builder
# ──────────────────────────────────────────────

def scalp_signal(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full top-down signal builder:
      15M wick zones → 5M confirmation → 1M entry → liquidity grab + breakout strength.

    Returns a signal dict compatible with make_signal / build_decision.
    """
    tfs = get_timeframes(context, include_forming=False)

    m15 = tfs.get("M15", [])
    m5  = tfs.get("M5",  [])
    m1  = tfs.get("M1",  [])

    # ── Minimum data guard ──────────────────────
    if len(m15) < 3:
        return _hold(context, tfs, "Waiting for M15 candle history.")
    if len(m5) < 3:
        return _hold(context, tfs, "Waiting for M5 candle history.")
    if len(m1) < 3:
        return _hold(context, tfs, "Waiting for M1 candle history.")

    current_price = f(m1[-1].get("close"))

    # ── Step 1: Find the active 15M wick zone ───
    active_zone = current_zone(m15, current_price)

    if active_zone is None:
        zones = scan_15m_wick_zones(m15)
        return {
            **_hold(context, tfs, "Price not in any 15M wick zone — waiting for zone retest."),
            "zones": zones,
            "zone_count": len(zones),
        }

    # ── Step 2: Check for breakout from this zone ─
    bo = breakout_strength(m5, active_zone)

    if bo["confirmed"]:
        # Price is breaking out — ride the momentum, not the scalp.
        direction = bo["direction"]
        score     = 0.85 if bo["momentum"] == "forming" else 0.95
        entry     = active_zone["zone_high"] if direction == BUY else active_zone["zone_low"]
        target    = entry + active_zone["candle_range"] if direction == BUY else entry - active_zone["candle_range"]
        stop_ref  = active_zone["zone_low"]  if direction == BUY else active_zone["zone_high"]

        return {
            **_base_setup(context, tfs, active_zone, bo),
            "action":       direction,
            "score":        score,
            "entry_type":   f"breakout_{bo['momentum']}",
            "entry_level":  entry,
            "target_level": target,
            "stop_reference": stop_ref,
            "reason":       f"{direction}: 15M zone breakout — {bo['candle_count']} consecutive M5 closes ({bo['momentum']}). Zone {active_zone['zone_low']:.2f}-{active_zone['zone_high']:.2f}.",
        }

    # ── Step 3: 5M confirmation for scalp ───────
    conf5 = confirm_5m(m5, active_zone)
    if not conf5["confirmed"]:
        return {
            **_hold(context, tfs, f"In 15M wick zone ({active_zone['type']}) — waiting for 5M confirmation candle."),
            "active_zone": active_zone,
            "breakout":    bo,
        }

    signal_dir = conf5["signal"]

    # ── Step 4: 1M entry confirmation ───────────
    conf1 = confirm_1m(m1, active_zone, signal_dir)
    if not conf1["confirmed"]:
        return {
            **_hold(context, tfs, f"5M confirmed {signal_dir} — waiting for 1M entry candle."),
            "active_zone":    active_zone,
            "confirm_5m":     conf5,
            "breakout":       bo,
        }

    # ── Step 5: Score and package the trade ─────
    base_score = 0.75
    if conf1["liq_grab"]:
        base_score += 0.15       # liquidity grab adds confluence
    if active_zone["is_liq_grab"]:
        base_score += 0.05       # 15M zone itself was a liq grab wick
    if bo["direction"] == signal_dir:
        base_score += 0.05       # momentum behind us even if not a confirmed breakout
    score = min(base_score, 1.0)

    zone_rng = active_zone["candle_range"]
    tol      = active_zone.get("tolerance", max(zone_rng * ZONE_TOL_RATIO, 0.20))

    if signal_dir == BUY:
        entry     = active_zone["zone_low"]
        target    = active_zone["zone_high"] + zone_rng * 0.5
        stop_ref  = active_zone["zone_low"] - tol
    else:
        entry     = active_zone["zone_high"]
        target    = active_zone["zone_low"] - zone_rng * 0.5
        stop_ref  = active_zone["zone_high"] + tol

    liq_tag = " [LIQ GRAB]" if conf1["liq_grab"] else ""
    reason  = (
        f"{signal_dir}: 15M wick zone ({active_zone['type']}) + 5M + 1M confirmed{liq_tag}. "
        f"Zone {active_zone['zone_low']:.2f}–{active_zone['zone_high']:.2f}. "
        f"Wick ratio {active_zone['wick_ratio']:.0%}. "
        f"{conf5['reason']} | {conf1['reason']}"
    )

    return {
        **_base_setup(context, tfs, active_zone, bo),
        "action":           signal_dir,
        "score":            score,
        "entry_type":       "scalp_zone_confluence" + ("_liq_grab" if conf1["liq_grab"] else ""),
        "entry_level":      entry,
        "target_level":     target,
        "stop_reference":   stop_ref,
        "tolerance":        tol,
        "confirm_5m":       conf5,
        "confirm_1m":       conf1,
        "reason":           reason,
    }


# ──────────────────────────────────────────────
#  Internal Helpers
# ──────────────────────────────────────────────

def _hold(context: Dict[str, Any], tfs: Dict, reason: str) -> Dict[str, Any]:
    return {
        "valid":       True,
        "action":      HOLD,
        "score":       0.0,
        "entry_type":  "waiting",
        "entry_level": None,
        "target_level": None,
        "stop_reference": None,
        "tolerance":   0.0,
        "timeframes":  tfs,
        "reason":      f"HOLD: {reason}",
    }


def _base_setup(
    context: Dict[str, Any],
    tfs: Dict,
    zone: Dict[str, Any],
    bo: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "valid":        True,
        "timeframes":   tfs,
        "active_zone":  zone,
        "breakout":     bo,
    }


def tolerance(context: Dict[str, Any], setup: Dict[str, Any]) -> float:
    rules    = context.get("rules") or {}
    explicit = f(rules.get("zone_tolerance") or rules.get("ray_touch_tolerance"), 0.0)
    if explicit > 0:
        return explicit
    rng = f(setup.get("active_zone", {}).get("candle_range") if setup.get("active_zone") else setup.get("range_size"), 0.0)
    return max(rng * ZONE_TOL_RATIO, 0.20)


# ──────────────────────────────────────────────
#  Trade Signal Factory (unchanged interface)
# ──────────────────────────────────────────────

def make_signal(
    action: str,
    reason: str,
    confidence: float,
    context: Dict[str, Any],
    data: Optional[Dict[str, Any]] = None,
    close_ticket: Any = None,
) -> Dict[str, Any]:
    action = str(action or HOLD).upper()
    if action not in (BUY, SELL, CLOSE, HOLD):
        action = HOLD

    rules = context.get("rules") or {}
    return {
        "enabled":       True,
        "active":        True,
        "valid":         True,
        "strategy":      "xauusd_m15_wick_scalp_strategy",
        "name":          "xauusd_m15_wick_scalp_strategy",
        "symbol":        symbol_from_context(context),
        "volume":        f(rules.get("volume") or rules.get("trade_volume") or context.get("volume"), 0.01),
        "action":        action,
        "signal":        action,
        "trade_signal":  action,
        "direction":     action,
        "side":          action,
        "mt5_action":    action,
        "mt5_order_type": action,
        "order_type":    action,
        "should_trade":  action in (BUY, SELL),
        "execute":       action in (BUY, SELL),
        "should_execute": action in (BUY, SELL),
        "should_close":  action == CLOSE,
        "close_ticket":  close_ticket,
        "confidence":    max(0.0, min(f(confidence), 1.0)),
        "reason":        reason,
        "thought":       reason,
        "data":          data or {},
    }


# ──────────────────────────────────────────────
#  Position Management (unchanged interface)
# ──────────────────────────────────────────────

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
    entry    = f(position.get("price_open") or position.get("open_price") or position.get("entry_price"))
    close    = f(rates[-1].get("close"))
    pos_type = int(position.get("type", 0) or 0)
    return close > entry if pos_type == 0 else close < entry


def maybe_close(context: Dict[str, Any], setup: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    positions = context.get("positions") or context.get("open_positions") or []
    if not positions:
        return None

    m1 = setup.get("timeframes", {}).get("M1", [])
    if not m1:
        return None

    pos      = positions[0]
    ticket   = pos.get("ticket")
    age      = position_age_candles(pos, m1)
    profit   = position_in_profit(pos, m1)
    pos_type = int(pos.get("type", 0) or 0)
    close    = f(m1[-1].get("close"))

    zone     = setup.get("active_zone") or {}
    target   = f(setup.get("target_level"))
    zone_high = f(zone.get("zone_high") or setup.get("range_high"))
    zone_low  = f(zone.get("zone_low")  or setup.get("range_low"))

    # Target hit.
    if pos_type == 0:
        if target > 0 and close >= target:
            return make_signal(CLOSE, f"CLOSE: BUY reached target @ {target:.2f}.", 1.0, context, data=setup, close_ticket=ticket)
        if profit and zone_high > 0 and close >= zone_high:
            return make_signal(CLOSE, f"CLOSE: BUY reached 15M zone high @ {zone_high:.2f}.", 0.95, context, data=setup, close_ticket=ticket)

    if pos_type == 1:
        if target > 0 and close <= target:
            return make_signal(CLOSE, f"CLOSE: SELL reached target @ {target:.2f}.", 1.0, context, data=setup, close_ticket=ticket)
        if profit and zone_low > 0 and close <= zone_low:
            return make_signal(CLOSE, f"CLOSE: SELL reached 15M zone low @ {zone_low:.2f}.", 0.95, context, data=setup, close_ticket=ticket)

    # Time-based exits.
    if profit and age >= 7:
        return make_signal(CLOSE, f"CLOSE: profit after {age} M1 candles.", 1.0, context, data=setup, close_ticket=ticket)
    if not profit and age >= 4:
        return make_signal(CLOSE, f"CLOSE: not in profit after {age} M1 candles.", 1.0, context, data=setup, close_ticket=ticket)

    return make_signal(HOLD, f"HOLD: tracking open position, candles_open={age}, in_profit={profit}.", 0.0, context, data=setup)


# ──────────────────────────────────────────────
#  Decision Entry Point
# ──────────────────────────────────────────────

def build_decision(context: Dict[str, Any]) -> Dict[str, Any]:
    setup = scalp_signal(context)

    close_signal = maybe_close(context, setup)
    if close_signal is not None:
        return close_signal

    return make_signal(
        setup.get("action", HOLD),
        str(setup.get("reason", "HOLD: waiting for 15M wick zone setup.")),
        f(setup.get("score"), 0.0),
        context,
        data=setup,
    )


# ──────────────────────────────────────────────
#  Draw Commands
# ──────────────────────────────────────────────

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
    data     = (decision or {}).get("data") or {}
    setup    = data if data.get("active_zone") else scalp_signal(context)
    commands: List[Dict[str, Any]] = [{"type": "clear_all"}]

    zone = setup.get("active_zone")
    bo   = setup.get("breakout", {})

    # ── Draw all scanned 15M wick zones ─────────
    tfs  = setup.get("timeframes") or get_timeframes(context, include_forming=False)
    m15  = tfs.get("M15", [])
    now  = int(time.time())

    all_zones = scan_15m_wick_zones(m15, lookback=8)
    for z in all_zones:
        color = "green" if z["type"] == "buy_zone" else "red"
        liq   = " [LIQ GRAB]" if z["is_liq_grab"] else ""
        commands.append({
            "type": "box",
            "name": f"TS_ZONE_{z['candle_time']}",
            "time1": z["candle_time"],
            "time2": now + 3600,
            "price1": z["zone_high"],
            "price2": z["zone_low"],
            "color": color,
            "text": f"{z['type'].upper()}{liq} wick {z['wick_ratio']:.0%}",
        })

    if zone:
        bias_color = "green" if setup.get("action") == BUY else "red" if setup.get("action") == SELL else "yellow"
        t = int(zone.get("candle_time", now))

        commands.extend([
            {"type": "ray", "name": "TS_ACTIVE_ZONE_HIGH", "time1": t, "price1": zone["zone_high"],
             "color": "yellow", "width": 2, "text": f"ACTIVE ZONE HIGH {zone['zone_high']:.2f}"},
            {"type": "ray", "name": "TS_ACTIVE_ZONE_LOW",  "time1": t, "price1": zone["zone_low"],
             "color": "cyan",   "width": 2, "text": f"ACTIVE ZONE LOW  {zone['zone_low']:.2f}"},
            {"type": "ray", "name": "TS_ACTIVE_ZONE_MID",  "time1": t, "price1": zone["zone_mid"],
             "color": "gray",   "width": 1, "text": f"ZONE MID {zone['zone_mid']:.2f}"},
        ])

        if bo.get("confirmed"):
            commands.append({
                "type": "text", "name": "TS_BREAKOUT_LABEL",
                "time": now + 120, "price": zone["zone_mid"],
                "color": bias_color,
                "text": f"BREAKOUT {bo['direction']} | {bo['candle_count']} candles | {bo['momentum'].upper()}",
            })

    for key, name, color in (
        ("entry_level",   "TS_ENTRY_AREA",       "yellow"),
        ("target_level",  "TS_TARGET",            "blue"),
        ("stop_reference","TS_STOP_REFERENCE",    "orange"),
    ):
        value = setup.get(key)
        if value is not None:
            commands.append({"type": "ray", "name": name, "time1": now - 300, "price1": f(value), "color": color, "width": 2,
                             "text": f"{key.replace('_', ' ').upper()} {f(value):.2f}"})

    action = setup.get("action", HOLD)
    commands.append({
        "type":  "text",
        "name":  "TS_DECISION_LABEL",
        "time":  now + 60 * 8,
        "price": f(setup.get("entry_level") or (zone or {}).get("zone_mid") or 0),
        "color": "green" if action == BUY else "red" if action == SELL else "yellow",
        "text":  f"[M15 SCALP] {action}\n{str(setup.get('reason', ''))}",
    })

    return commands


def write_draws(context: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> int:
    commands = build_draw_commands(context, decision)
    payload  = {
        "version":       12,
        "source":        "TradeSmartAI",
        "strategy":      "m15_wick_scalp_liq_grab",
        "updated":       time.time(),
        "command_count": len(commands),
        "commands":      commands,
    }
    for p in draw_paths():
        write_json(p, payload)
    return len(commands)


def write_debug(context: Dict[str, Any], result: Dict[str, Any], command_count: int) -> None:
    base = draw_paths()[0].parent
    write_json(base / DEBUG_FILE, {
        "updated":       time.time(),
        "action":        result.get("action"),
        "reason":        result.get("reason"),
        "confidence":    result.get("confidence"),
        "command_count": command_count,
        "data":          result.get("data", {}),
    })