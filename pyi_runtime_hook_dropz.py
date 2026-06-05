from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
os.environ.setdefault("DROPZ_DESKTOP_MODE", "true")

user_data = Path.home() / ".dropz_universal_agent"
user_data.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DROPZ_USER_DATA_DIR", str(user_data))
