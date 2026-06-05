"""
Dropz Universal Agent PyInstaller runtime hook.

Purpose:
- Keep the frozen Streamlit app stable inside the EXE.
- Force Plotly to use the standard JSON serializer instead of orjson.
  Some frozen builds bundle an incompatible orjson binary missing
  OPT_NON_STR_KEYS/OPT_SERIALIZE_NUMPY, which breaks st.plotly_chart.
"""

from __future__ import annotations

import os

os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")

# Force Plotly away from orjson in the frozen app.
os.environ["PLOTLY_RENDERER"] = "browser"
os.environ["PLOTLY_JSON_ENGINE"] = "json"

try:
    import plotly.io as pio
    try:
        pio.json.config.default_engine = "json"
    except Exception:
        pass
except Exception:
    pass

# Defensive compatibility patch. If a bad/incomplete orjson is bundled,
# add the option flags Plotly expects so imports do not crash.
try:
    import orjson  # type: ignore
    if not hasattr(orjson, "OPT_NON_STR_KEYS"):
        orjson.OPT_NON_STR_KEYS = 0  # type: ignore[attr-defined]
    if not hasattr(orjson, "OPT_SERIALIZE_NUMPY"):
        orjson.OPT_SERIALIZE_NUMPY = 0  # type: ignore[attr-defined]
except Exception:
    pass
