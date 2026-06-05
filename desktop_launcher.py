from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from urllib.request import Request, urlopen

APP_NAME = "DropzUniversalAgent"
APP_VERSION = os.environ.get("DROPZ_APP_VERSION", "1.0.0")
HOST = "127.0.0.1"
PORT = int(os.environ.get("DROPZ_DESKTOP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"

_opened_browser = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
EXE_DIR = _exe_dir()
LOG_FILE = Path(os.environ.get("DROPZ_LAUNCHER_LOG", str(Path.home() / "DropzUniversalAgent_launcher.log")))


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.35):
            return True
    except OSError:
        return False


def _find_app_file() -> Path:
    candidates = [
        BASE_DIR / "streamlit_app.py",
        EXE_DIR / "streamlit_app.py",
        Path.cwd() / "streamlit_app.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("streamlit_app.py was not found next to the EXE or inside _internal.")


def _configure_runtime() -> None:
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("DROPZ_DESKTOP_MODE", "true")
    os.environ.setdefault("DROPZ_APP_VERSION", APP_VERSION)

    user_data = Path.home() / ".dropz_universal_agent"
    user_data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DROPZ_USER_DATA_DIR", str(user_data))


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for piece in str(value or "0").replace("-", ".").split("."):
        try:
            parts.append(int("".join(ch for ch in piece if ch.isdigit()) or "0"))
        except Exception:
            parts.append(0)
    return tuple(parts or [0])


def _read_update_manifest() -> dict:
    manifest_url = os.environ.get("DROPZ_UPDATE_MANIFEST_URL", "").strip()
    if not manifest_url:
        manifest_file = EXE_DIR / "update_manifest_url.txt"
        if manifest_file.exists():
            manifest_url = manifest_file.read_text(encoding="utf-8").strip()
    if not manifest_url:
        return {}

    req = Request(manifest_url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urlopen(req, timeout=5) as resp:
        raw = resp.read(1024 * 1024).decode("utf-8")
    data = json.loads(raw)
    data["_manifest_url"] = manifest_url
    return data if isinstance(data, dict) else {}


def _maybe_launch_updater() -> bool:
    """Return True when the launcher should exit because the updater was started."""
    if os.environ.get("DROPZ_DISABLE_UPDATES", "").lower() in {"1", "true", "yes", "on"}:
        return False

    try:
        data = _read_update_manifest()
        latest = str(data.get("version", "")).strip()
        download_url = str(data.get("download_url", "")).strip()
        if not latest or not download_url:
            return False
        if _version_tuple(latest) <= _version_tuple(APP_VERSION):
            log(f"No update needed. Current={APP_VERSION} Latest={latest}")
            return False

        updater = EXE_DIR / "DropzUpdater.exe"
        if not updater.exists():
            log("Update available, but DropzUpdater.exe is missing.")
            return False

        log(f"Update available: {APP_VERSION} -> {latest}. Starting updater.")
        args = [
            str(updater),
            "--app-dir", str(EXE_DIR),
            "--main-exe", str(EXE_DIR / f"{APP_NAME}.exe"),
            "--current-version", APP_VERSION,
            "--latest-version", latest,
            "--download-url", download_url,
            "--sha256", str(data.get("sha256", "") or ""),
        ]
        subprocess.Popen(args, cwd=str(EXE_DIR), close_fds=True)
        return True
    except Exception as exc:
        log(f"Update check skipped: {exc}")
        return False


def _run_streamlit_in_process(app_file: Path) -> None:
    _configure_runtime()
    import streamlit.web.cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_file),
        "--server.address", HOST,
        "--server.port", str(PORT),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    log("Starting Streamlit in-process.")
    stcli.main()


def _open_browser_once() -> None:
    global _opened_browser
    if _opened_browser:
        return
    _opened_browser = True
    log(f"Opening browser once: {URL}")
    webbrowser.open_new(URL)


def _wait_and_open_browser() -> None:
    log(f"Waiting for Streamlit server at {URL}")
    deadline = time.time() + 90
    while time.time() < deadline:
        if _port_open():
            time.sleep(0.8)
            _open_browser_once()
            return
        time.sleep(0.35)
    log("Streamlit did not respond before timeout. Opening browser once anyway.")
    _open_browser_once()


def main() -> int:
    log("Launcher starting.")
    try:
        if _maybe_launch_updater():
            log("Launcher exiting for updater.")
            return 0

        app_file = _find_app_file()
        log(f"Using app file: {app_file}")

        browser_thread = threading.Thread(target=_wait_and_open_browser, daemon=True)
        browser_thread.start()

        _run_streamlit_in_process(app_file)
        return 0
    except Exception as exc:
        log(f"Launcher fatal error: {type(exc).__name__}: {exc}")
        log(traceback.format_exc())
        try:
            print(f"\n{APP_NAME} failed to start. See log:\n{LOG_FILE}\n")
            input("Press Enter to close...")
        except Exception:
            pass
        return 1
    finally:
        log("Launcher stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
