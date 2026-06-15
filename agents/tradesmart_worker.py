from __future__ import annotations

import json
import os
import hashlib
import re
import time
from pathlib import Path
from typing import Any, Dict, List

DRAW_ENV = "TRADESMART_MT5_BRIDGE_FILE"
DRAW_JSON1 = "TradeSmart_AI_DrawCommands.json1"
DRAW_JSONL = "TradeSmart_AI_DrawCommands.jsonl"


def _safe_user_id(value: Any) -> str:
    raw = str(value or "default")
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")[:64]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{clean or 'user'}_{digest}"


def draw_paths(project_root: Path | None = None, user_key: str | None = None) -> List[Path]:
    user_id = _safe_user_id(user_key or "default")
    env_key = f"{DRAW_ENV}_{user_id.upper()}"
    raw = os.environ.get(env_key) or os.environ.get(DRAW_ENV)
    if raw:
        p = Path(raw)
        # If the global bridge path is used, write a user-scoped sibling too so
        # app-side outputs never collide across clients.
        suffix = p.suffix or ".json1"
        scoped = p.with_name(f"{p.stem}_{user_id}{suffix}")
        alt = scoped.with_suffix(".jsonl" if scoped.suffix.lower() == ".json1" else ".json1")
        return [p, scoped, alt]
    root = Path(project_root or Path.cwd())
    files_dir = root / "data" / "users" / user_id / "mt5_files"
    return [files_dir / DRAW_JSON1, files_dir / DRAW_JSONL]


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def write_draw_commands(result: Dict[str, Any], project_root: Path | None = None, user_key: str | None = None) -> int:
    """Drawing-only worker hook.

    The TradeSmart page owns the 3-second live cycle. The agent owns MT5 order
    execution. This module only writes the MT5 bridge draw file from the winning
    strategy decision, so chart drawing can be upgraded without changing the page.
    """
    result = result or {}
    decision = result.get("decision") or {}
    strategy_info = result.get("strategy_info") or {}
    raw = strategy_info.get("raw") if isinstance(strategy_info.get("raw"), dict) else {}
    commands = decision.get("draw_commands") or raw.get("draw_commands") or []
    if not isinstance(commands, list):
        commands = []
    user_id = _safe_user_id(user_key or result.get("user_id") or result.get("user_key") or "default")
    payload = {
        "version": 31,
        "user_id": user_id,
        "user_key": str(user_key or result.get("user_key") or "default"),
        "source": "TradeSmartAI",
        "strategy": result.get("strategy") or strategy_info.get("winner") or "strategy",
        "updated": time.time(),
        "command_count": len(commands),
        "commands": commands,
    }
    for path in draw_paths(project_root, user_id):
        _atomic_write(path, payload)
    return len(commands)


# Backward-compatible alias for old imports.
def run_worker_once(result: Dict[str, Any], project_root: Path | None = None, user_key: str | None = None) -> int:
    return write_draw_commands(result, project_root, user_key=user_key)
