
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from agents.tradesmart_agent import TradeSmartAgent

STATE_FILE = Path("data/tradesmart_worker_state.json")
LOG_FILE = Path("data/tradesmart_worker.log")
CHECK_SECONDS = 3


def _log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"enabled": False}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"enabled": False}
    except Exception:
        return {"enabled": False}


def run_worker() -> None:
    _log("TradeSmart worker started.")
    while True:
        state = _load_state()
        if not state.get("enabled"):
            time.sleep(CHECK_SECONDS)
            continue

        try:
            profile = state.get("profile") or {}
            risk = state.get("risk") or {}
            mode = state.get("mode") or "Demo"

            agent = TradeSmartAgent(profile=profile, rules={**risk, "mode": mode, "symbol": "XAUUSD"})
            result = agent.run_cycle(execution_enabled=True)

            state["last_result"] = result
            state["last_run"] = datetime.now().isoformat(timespec="seconds")
            STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

            _log(str(result.get("message") or result.get("phase") or "cycle complete"))
        except Exception as exc:
            _log(f"Worker error: {exc}")
            _log(traceback.format_exc())

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    run_worker()
