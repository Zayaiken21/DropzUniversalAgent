from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, List, Optional


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _debug_log(project_root: Path, message: str) -> None:
    try:
        log_path = project_root / "strategies" / "strategy_loader_debug.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass


def _ensure_strategy_import_path(project_root: Path) -> None:
    strategies_dir = project_root / "strategies"
    for item in (project_root, strategies_dir):
        text = str(item)
        if text not in sys.path:
            sys.path.insert(0, text)


def _load_module(path: Path, project_root: Optional[Path] = None) -> Optional[Any]:
    try:
        if project_root is None:
            project_root = _project_root_from_here()
        _ensure_strategy_import_path(project_root)
        module_name = f"dropz_strategy_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if not spec or not spec.loader:
            _debug_log(project_root, f"SKIP {path.name}: missing import spec/loader")
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        root = project_root or _project_root_from_here()
        _debug_log(root, f"FAILED loading {path.name}:\n{traceback.format_exc()}")
        return None


def _instances_from_module(module: Any) -> List[Any]:
    found: List[Any] = []
    getter = getattr(module, "get_strategy", None)
    if callable(getter):
        try:
            value = getter()
            if isinstance(value, list):
                found.extend([v for v in value if v is not None])
            elif value is not None:
                found.append(value)
        except Exception:
            pass
    else:
        for _, obj in vars(module).items():
            if not isinstance(obj, type):
                continue
            if not hasattr(obj, "evaluate"):
                continue
            try:
                found.append(obj())
            except Exception:
                continue

    deduped: List[Any] = []
    seen = set()
    for strategy in found:
        key = f"{strategy.__class__.__module__}.{strategy.__class__.__name__}"
        if key in seen:
            continue
        seen.add(key)
        if getattr(strategy, "enabled", True):
            deduped.append(strategy)
    return deduped


def load_enabled_strategies(project_root: Optional[Path] = None) -> List[Any]:
    root = Path(project_root) if project_root else _project_root_from_here()
    strategies_dir = root / "strategies"
    _ensure_strategy_import_path(root)

    try:
        (strategies_dir / "strategy_loader_debug.log").write_text("", encoding="utf-8")
    except Exception:
        pass

    if not strategies_dir.exists():
        return []

    loaded: List[Any] = []
    paths = sorted(strategies_dir.glob("*.py"))
    paths.sort(key=lambda p: 0 if p.name == "xauusd_m1_candle_strategy.py" else 1)

    for path in paths:
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        module = _load_module(path, root)
        if module is None:
            continue
        instances = _instances_from_module(module)
        if instances:
            _debug_log(root, f"LOADED {path.name}: {[getattr(s, 'name', s.__class__.__name__) for s in instances]}")
        else:
            _debug_log(root, f"NO ENABLED INSTANCES {path.name}")
        loaded.extend(instances)

    return loaded
