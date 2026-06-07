import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _runtime_root() -> Path:
    """
    Works in:
    - PyCharm / localhost
    - PyInstaller onedir EXE
    - Streamlit running from bundled _internal folder
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_ROOT = _runtime_root()
BASE_DIR = Path(__file__).resolve().parent


def _candidate_env_paths() -> list[Path]:
    """
    Load the same root .env on localhost and in the packaged EXE.

    Build output layout:
      DropzUniversalAgent.exe
      .env
      update_manifest_url.txt
      _internal/.env
      _internal/frontend/config.py
    """
    paths: list[Path] = []

    # PyInstaller internal folder.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / ".env")
        paths.append(Path(meipass).parent / ".env")

    # EXE folder, _internal folder, current working folder.
    paths.extend(
        [
            APP_ROOT / ".env",
            APP_ROOT / "_internal" / ".env",
            Path.cwd() / ".env",
            BASE_DIR.parent / ".env",
            BASE_DIR / ".env",
        ]
    )

    # User app data override for future updates or support installs.
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        paths.append(Path(local_appdata) / "DropzUniversalAgent" / ".env")

    # Walk parents as safety net.
    for parent in list(BASE_DIR.parents)[:5]:
        paths.append(parent / ".env")

    seen: set[str] = set()
    clean: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key not in seen:
            seen.add(key)
            clean.append(path)
    return clean


def _load_env_files() -> None:
    for path in _candidate_env_paths():
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


def _read_text_file_first(*names: str) -> str:
    candidates: list[Path] = []
    for name in names:
        candidates.extend(
            [
                APP_ROOT / name,
                APP_ROOT / "_internal" / name,
                Path.cwd() / name,
                BASE_DIR.parent / name,
            ]
        )
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        for name in names:
            candidates.append(Path(local_appdata) / "DropzUniversalAgent" / name)

    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


CEO_SECRET_PHRASE = _secret_or_env("CEO_SECRET_PHRASE", "")
DATABASE_URL = _secret_or_env("DATABASE_URL", "sqlite:///dropz.db")

SUPABASE_URL = _secret_or_env("SUPABASE_URL", "https://gzondcztcusuwyksoyvp.supabase.co")
SUPABASE_ANON_KEY = _secret_or_env("SUPABASE_ANON_KEY", "")
# Optional only for your private build. Do not distribute service_role in public builds.
SUPABASE_SERVICE_ROLE_KEY = _secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")

DROPZ_UPDATE_MANIFEST_URL = (
    _secret_or_env("DROPZ_UPDATE_MANIFEST_URL", "")
    or _read_text_file_first("update_manifest_url.txt")
)
