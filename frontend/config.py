import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

def _secret_or_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        if value not in (None, ""):
            return str(value).strip()
    except Exception:
        pass
    return default

CEO_SECRET_PHRASE = _secret_or_env("CEO_SECRET_PHRASE", "")
DATABASE_URL = _secret_or_env("DATABASE_URL", "sqlite:///dropz.db")
BASE_DIR = Path(__file__).resolve().parent

SUPABASE_URL = _secret_or_env("SUPABASE_URL", "https://gzondcztcusuwyksoyvp.supabase.co")
SUPABASE_ANON_KEY = _secret_or_env("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = _secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")
