from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, List, Optional


def _project_root(project_root: Optional[Path] = None) -> Path:
    if project_root:
        return Path(project_root)
    return Path(__file__).resolve().parents[2]


def _debug(root: Path, message: str) -> None:
    try:
        path = root / "data" / "tradesmart_strategy_loader.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass


def _ensure_paths(root: Path) -> None:
    for item in (root, root / "strategies"):
        text = str(item)
        if text not in sys.path:
            sys.path.insert(0, text)


def _load_module(path: Path, root: Path) -> Optional[Any]:
    try:
        _ensure_paths(root)
        name = f"tradesmart_strategy_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, str(path))
        if not spec or not spec.loader:
            _debug(root, f"SKIP {path.name}: no spec/loader")
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        _debug(root, f"FAILED {path.name}:\n{traceback.format_exc()}")
        return None


def _instances(module: Any) -> List[Any]:
    out: List[Any] = []
    getter = getattr(module, "get_strategy", None)
    if callable(getter):
        try:
            value = getter()
            if isinstance(value, list):
                out.extend([x for x in value if x is not None])
            elif value is not None:
                out.append(value)
        except Exception:
            return []
    else:
        for obj in vars(module).values():
            if isinstance(obj, type) and hasattr(obj, "evaluate"):
                try:
                    out.append(obj())
                except Exception:
                    pass
    clean = []
    seen = set()
    for strategy in out:
        enabled = bool(getattr(strategy, "enabled", True))
        key = f"{strategy.__class__.__module__}.{strategy.__class__.__name__}"
        if enabled and key not in seen:
            clean.append(strategy)
            seen.add(key)
    return clean


def load_enabled_strategies(project_root: Optional[Path] = None) -> List[Any]:
    root = _project_root(project_root)
    strategies_dir = root / "strategies"
    _ensure_paths(root)
    try:
        log = root / "data" / "tradesmart_strategy_loader.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")
    except Exception:
        pass
    loaded: List[Any] = []
    if not strategies_dir.exists():
        _debug(root, "NO strategies folder")
        return loaded
    for path in sorted(strategies_dir.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        module = _load_module(path, root)
        if module is None:
            continue
        found = _instances(module)
        if found:
            _debug(root, f"LOADED {path.name}: {[getattr(s, 'name', s.__class__.__name__) for s in found]}")
        else:
            _debug(root, f"NO ENABLED STRATEGIES {path.name}")
        loaded.extend(found)
    return loaded
