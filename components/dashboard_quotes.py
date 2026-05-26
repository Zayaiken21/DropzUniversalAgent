from __future__ import annotations
import random
from datetime import date

GOOD_QUOTES = [f"Good session #{i}: Protect your edge, respect your plan, and let consistency compound." for i in range(1, 251)]
BAD_QUOTES = [f"Reset session #{i}: Losses are feedback, not identity. Review the plan, reduce risk, and come back precise." for i in range(1, 251)]

def _f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0

def get_daily_session_quote(metrics=None):
    metrics = metrics or {}
    pnl = _f(metrics.get("daily_pnl", 0))
    tone = "good" if pnl >= 0 else "bad"
    pool = GOOD_QUOTES if tone == "good" else BAD_QUOTES
    quote = random.Random(f"{date.today().isoformat()}:{tone}").choice(pool)
    return {
        "tone": tone,
        "quote": quote,
        "glow_class": "du-quote-good" if tone == "good" else "du-quote-bad",
    }
