from __future__ import annotations

import os
import sys
import time
import socket
import traceback
import threading
import webbrowser
from pathlib import Path

APP_NAME = "DropzUniversalAgent"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DROPZ_DESKTOP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"

_opened_browser = False


def _base_dir() -> Path:
    # PyInstaller onedir puts bundled files in sys._MEIPASS / _internal.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
LOG_FILE = Path(os.environ.get("DROPZ_LAUNCHER_LOG", str(Path.home() / "DropzUniversalAgent_launcher.log")))


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.4):
            return True
    except OSError:
        return False


def _find_app_file() -> Path:
    candidates = [
        BASE_DIR / "streamlit_app.py",
        Path(sys.executable).resolve().parent / "streamlit_app.py",
        Path.cwd() / "streamlit_app.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "streamlit_app.py was not found. Make sure it is bundled next to the EXE."
    )


def _configure_streamlit_runtime() -> None:
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("DROPZ_DESKTOP_MODE", "true")

    # Keep user data writable outside the bundled _internal folder.
    user_data = Path.home() / ".dropz_universal_agent"
    user_data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DROPZ_USER_DATA_DIR", str(user_data))


def _run_streamlit_in_process(app_file: Path) -> None:
    """
    Starts Streamlit without spawning the EXE again.
    This avoids the old infinite launcher recursion caused by using sys.executable.
    """
    _configure_streamlit_runtime()

    import streamlit.web.cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_file),
        "--server.address",
        HOST,
        "--server.port",
        str(PORT),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]

    log("Starting Streamlit in-process.")
    stcli.main()


def _open_browser_once() -> None:
    global _opened_browser
    if _opened_browser:
        return
    _opened_browser = True
    log(f"Opening browser once: {URL}")
    webbrowser.open(URL, new=1, autoraise=True)


def _wait_and_open_browser() -> None:
    log(f"Waiting for Streamlit server at {URL}")
    for _ in range(120):
        if _port_open():
            # Small delay so Streamlit finishes first render.
            time.sleep(0.8)
            _open_browser_once()
            return
        time.sleep(0.5)
    log("Timed out waiting for Streamlit. Browser was not opened.")


def main() -> None:
    log("Launcher starting.")
    try:
        app_file = _find_app_file()
        log(f"Using app file: {app_file}")

        if _port_open():
            log("Streamlit already running. Reusing existing server.")
            _open_browser_once()
            return

        opener = threading.Thread(target=_wait_and_open_browser, daemon=True)
        opener.start()

        _run_streamlit_in_process(app_file)

    except BaseException as exc:
        log(f"Launcher fatal error: {type(exc).__name__}: {exc}")
        log(traceback.format_exc())
        try:
            input("Dropz Universal Agent failed to start. Press Enter to close...")
        except Exception:
            time.sleep(8)
    finally:
        log("Launcher stopped.")


if __name__ == "__main__":
    main()
