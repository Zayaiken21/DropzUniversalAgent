import base64
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv, dotenv_values


def _runtime_root() -> Path:
    """
    Works in:
    - PyCharm / localhost
    - Streamlit Cloud
    - PyInstaller onedir EXE
    - Streamlit running from bundled _internal folder
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_ROOT = _runtime_root()
BASE_DIR = Path(__file__).resolve().parent


def _candidate_env_paths() -> list[Path]:
    paths: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / ".env")
        paths.append(Path(meipass).parent / ".env")

    paths.extend([
        APP_ROOT / ".env",
        APP_ROOT / "_internal" / ".env",
        Path.cwd() / ".env",
        BASE_DIR.parent / ".env",
        BASE_DIR / ".env",
    ])

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        paths.append(Path(local_appdata) / "DropzUniversalAgent" / ".env")

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


def _clean_secret_value(value: object) -> str:
    if value in (None, ""):
        return ""
    cleaned = str(value).strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return cleaned.strip().rstrip(",").strip()


def _streamlit_secret(name: str) -> str:
    try:
        import streamlit as st
        return _clean_secret_value(st.secrets.get(name, ""))
    except Exception:
        return ""


def _env_value(name: str) -> str:
    return _clean_secret_value(os.getenv(name, ""))


def _dotenv_candidates(name: str) -> list[str]:
    values: list[str] = []
    for path in _candidate_env_paths():
        try:
            if path.exists():
                val = dotenv_values(path).get(name)
                cleaned = _clean_secret_value(val)
                if cleaned:
                    values.append(cleaned)
        except Exception:
            pass
    return values


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _secret_or_env(name: str, default: str = "") -> str:
    return _streamlit_secret(name) or _env_value(name) or (_dotenv_candidates(name)[0] if _dotenv_candidates(name) else "") or default


def _project_ref_from_url(url: str) -> str:
    # https://project-ref.supabase.co -> project-ref
    url = _clean_secret_value(url).replace("https://", "").replace("http://", "")
    host = url.split("/", 1)[0]
    return host.split(".", 1)[0].strip()


def _jwt_payload(token: str) -> dict:
    token = _clean_secret_value(token)
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}


def _key_project_ref(token: str) -> str:
    payload = _jwt_payload(token)
    return str(payload.get("ref") or "").strip()


def _choose_supabase_key(url: str, name: str) -> str:
    """
    Select the key that matches SUPABASE_URL when multiple sources exist.

    This fixes local/EXE cases where a stale .streamlit/secrets.toml or OS env var
    has a key from a different Supabase project than the .env URL.
    """
    candidates = _unique([
        _streamlit_secret(name),
        _env_value(name),
        *_dotenv_candidates(name),
    ])
    if not candidates:
        return ""

    url_ref = _project_ref_from_url(url)
    for candidate in candidates:
        key_ref = _key_project_ref(candidate)
        if key_ref and url_ref and key_ref == url_ref:
            return candidate

    # Newer Supabase publishable keys may not be JWTs. If one exists, use it.
    for candidate in candidates:
        if candidate.startswith("sb_publishable_"):
            return candidate

    return candidates[0]


def _read_text_file_first(*names: str) -> str:
    candidates: list[Path] = []
    for name in names:
        candidates.extend([
            APP_ROOT / name,
            APP_ROOT / "_internal" / name,
            Path.cwd() / name,
            BASE_DIR.parent / name,
        ])

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
SUPABASE_ANON_KEY = _choose_supabase_key(SUPABASE_URL, "SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = _choose_supabase_key(SUPABASE_URL, "SUPABASE_SERVICE_ROLE_KEY")
DROPZ_LICENSE_ENDPOINT = _secret_or_env("DROPZ_LICENSE_ENDPOINT", "")
DROPZ_UPDATE_MANIFEST_URL = (
    _secret_or_env("DROPZ_UPDATE_MANIFEST_URL", "")
    or _read_text_file_first("update_manifest_url.txt")
)


def _mask(value: str, left: int = 10, right: int = 6) -> str:
    value = _clean_secret_value(value)
    if not value:
        return ""
    if len(value) <= left + right:
        return "*" * len(value)
    return f"{value[:left]}...{value[-right:]}"


def supabase_config_status() -> dict:
    return {
        "SUPABASE_URL_loaded": bool(SUPABASE_URL),
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY_loaded": bool(SUPABASE_ANON_KEY),
        "SUPABASE_ANON_KEY_length": len(SUPABASE_ANON_KEY or ""),
        "SUPABASE_ANON_KEY_preview": _mask(SUPABASE_ANON_KEY),
        "SUPABASE_ANON_KEY_PROJECT_REF": _key_project_ref(SUPABASE_ANON_KEY),
        "SUPABASE_URL_PROJECT_REF": _project_ref_from_url(SUPABASE_URL),
        "SUPABASE_SERVICE_ROLE_KEY_loaded": bool(SUPABASE_SERVICE_ROLE_KEY),
        "DROPZ_LICENSE_ENDPOINT_loaded": bool(DROPZ_LICENSE_ENDPOINT),
    }
