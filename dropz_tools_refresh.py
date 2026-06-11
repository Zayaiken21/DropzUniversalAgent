from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()
FRONTEND = ROOT / "frontend"
TOOLS = FRONTEND / "tools_page.py"
NEWS = FRONTEND / "news_endpoints.py"
WARNING = "news_endpoints.py must be in the same folder as tools_page.py"

print(f"Project root: {ROOT}")
print(f"Python: {sys.executable}")

if not FRONTEND.exists():
    raise SystemExit("ERROR: frontend folder was not found. Run this from C:\\Users\\Eric\\PycharmProjects\\DropzUniversalAgent")

# Delete Python caches everywhere in the project.
for p in ROOT.rglob("__pycache__"):
    try:
        shutil.rmtree(p)
        print(f"Deleted cache: {p}")
    except Exception as exc:
        print(f"Could not delete cache {p}: {exc}")

# Show every tools_page.py and whether it still contains the old warning.
print("\nTOOLS PAGE COPIES FOUND:")
for p in ROOT.rglob("tools_page.py"):
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    marker = " <-- CONTAINS OLD NEWS WARNING" if WARNING in text else ""
    print(f"- {p}{marker}")

print("\nNEWS ENDPOINT COPIES FOUND:")
for p in ROOT.rglob("news_endpoints.py"):
    print(f"- {p}")

# Check frontend files exist.
print("\nFRONTEND TARGETS:")
print(f"tools_page.py exists: {TOOLS.exists()} -> {TOOLS}")
print(f"news_endpoints.py exists: {NEWS.exists()} -> {NEWS}")

# Import check.
print("\nIMPORT CHECK:")
try:
    import importlib
    tp = importlib.import_module("frontend.tools_page")
    print(f"frontend.tools_page imported from: {Path(tp.__file__).resolve()}")
    print(f"render_frontend_tools_page exists: {hasattr(tp, 'render_frontend_tools_page')}")
except Exception as exc:
    print(f"frontend.tools_page import FAILED: {type(exc).__name__}: {exc}")

try:
    ne = importlib.import_module("frontend.news_endpoints")
    print(f"frontend.news_endpoints imported from: {Path(ne.__file__).resolve()}")
    print(f"get_gold_news_dashboard exists: {hasattr(ne, 'get_gold_news_dashboard')}")
except Exception as exc:
    print(f"frontend.news_endpoints import FAILED: {type(exc).__name__}: {exc}")

print("\nIf any tools_page.py says CONTAINS OLD NEWS WARNING, that is the file causing the repeated message.")
