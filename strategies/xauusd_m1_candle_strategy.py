from __future__ import annotations

from typing import Any, Dict
from strategy_common import build_decision, write_debug, write_draws

ENABLED = True
enabled = True
ACTIVE = True
active = True
IS_ENABLED = True
name = "xauusd_m1_candle_strategy"


class XAUUSDM1CandleStrategy:
    name = "xauusd_m1_candle_strategy"
    enabled = True
    active = True

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        result = build_decision(context)
        count = write_draws(context, result)
        write_debug(context, result, count)
        return result


def get_strategy():
    return XAUUSDM1CandleStrategy()


def evaluate(context: Dict[str, Any]) -> Dict[str, Any]:
    return XAUUSDM1CandleStrategy().evaluate(context)


strategy = XAUUSDM1CandleStrategy()
STRATEGY = strategy
