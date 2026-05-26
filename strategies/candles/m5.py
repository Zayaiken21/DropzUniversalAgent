from __future__ import annotations

from typing import Any, Dict

try:
    from ..strategy_common import get_timeframes, support_resistance_levels, timeframe_bias
except Exception:
    from strategy_common import get_timeframes, support_resistance_levels, timeframe_bias

TIMEFRAME = "M5"


def analyze(context: Dict[str, Any]):
    rates = get_timeframes(context).get(TIMEFRAME, [])
    return {
        "timeframe": TIMEFRAME,
        "count": len(rates),
        "bias": timeframe_bias(rates),
        "levels": support_resistance_levels(rates) if rates else {"support": [], "resistance": [], "swings": []},
    }
