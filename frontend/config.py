import os
import sys
from pathlib import Path
from dotenv import load_dotenv


# Public production values embedded for the desktop EXE.
# SUPABASE_ANON_KEY is public by design. Do NOT embed service_role keys here.
PUBLIC_SUPABASE_URL = "https://gzondcztcusuwyksoyvp.supabase.co"
PUBLIC_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd6b25kY3p0Y3VzdXd5a3NveXZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3OTc1NzUsImV4cCI6MjA5NjM3MzU3NX0.qjSDCEqzKZB5dQp2IcVz3CJvUYUAowrbSOImaK0l-8U"
PUBLIC_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/Zayaiken21/DropzUniversalAgent/main/version_manifest.json"


def _runtime_root() -> Path:
    """
    Works in all modes:
    - localhost / PyCharm
    - Streamlit Cloud
    - PyInstaller onedir EXE
    - Streamlit running from _internal
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_ROOT = _runtime_root()
BASE_DIR = Path(__file__).resolve().parent


def _load_env_files() -> None:
    """
    Localhost/Admin only:
      DropzUniversalAgent/.env

    EXE:
      We do NOT require or bundle .env for Supabase.
      If a private admin .env is placed next to the EXE, it can still be read.
    """
    candidates = [
        Path.cwd() / ".env",
        APP_ROOT / ".env",
        APP_ROOT / "_internal" / ".env",
        BASE_DIR.parent / ".env",
        BASE_DIR / ".env",
    ]

    for path in candidates:
        try:
            if path.exists():
                load_dotenv(path, override=False)
        except Exception:
            pass

    try:
        load_dotenv(override=False)
    except Exception:
        pass


_load_env_files()


def _clean(value: object) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    return text.strip().rstrip(",").strip()


def _streamlit_secret(name: str) -> str:
    try:
        import streamlit as st
        return _clean(st.secrets.get(name, ""))
    except Exception:
        return ""


def _secret_or_env(name: str, default: str = "") -> str:
    env_value = _clean(os.getenv(name, ""))
    if env_value:
        return env_value

    st_value = _streamlit_secret(name)
    if st_value:
        return st_value

    return _clean(default)


CEO_SECRET_PHRASE = _secret_or_env("CEO_SECRET_PHRASE", "")
DATABASE_URL = _secret_or_env("DATABASE_URL", "sqlite:///dropz.db")

# Supabase is live for Streamlit Cloud, localhost, and the EXE.
# Local/Cloud secrets override these public defaults.
SUPABASE_URL = _secret_or_env("SUPABASE_URL", PUBLIC_SUPABASE_URL)
SUPABASE_ANON_KEY = _secret_or_env("SUPABASE_ANON_KEY", PUBLIC_SUPABASE_ANON_KEY)

# Never put service_role in the public desktop EXE. Keep it optional for private admin/local use only.
SUPABASE_SERVICE_ROLE_KEY = _secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")

DROPZ_UPDATE_MANIFEST_URL = _secret_or_env("DROPZ_UPDATE_MANIFEST_URL", PUBLIC_UPDATE_MANIFEST_URL)


def config_status() -> dict:
    return {
        "app_root": str(APP_ROOT),
        "base_dir": str(BASE_DIR),
        "supabase_url_set": bool(SUPABASE_URL),
        "supabase_anon_key_set": bool(SUPABASE_ANON_KEY),
        "service_role_set": bool(SUPABASE_SERVICE_ROLE_KEY),
        "update_manifest_set": bool(DROPZ_UPDATE_MANIFEST_URL),
    }
