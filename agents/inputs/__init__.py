from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_tradesmart_inputs(project_root: Path, runtime_rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Neutral TradeSmart input hook.

    The page saves/passes Custom TradeSmart Agent Rules as runtime_rules["custom_rules"].
    Later, you can add files or database loaders here without editing the TradeSmart page
    or the execution agent.
    """
    rules = dict(runtime_rules or {})
    rules["custom_rules"] = str(rules.get("custom_rules") or "").strip()
    rules["input_source"] = "agents.inputs"
    return rules
