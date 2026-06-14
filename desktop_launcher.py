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
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

APP_NAME = "DropzUniversalAgent"
GITHUB_OWNER = os.environ.get("DROPZ_GITHUB_OWNER", "Zayaiken21")
GITHUB_REPO = os.environ.get("DROPZ_GITHUB_REPO", "DropzUniversalAgent")
UPDATE_ASSET_NAME = os.environ.get("DROPZ_UPDATE_ASSET_NAME", "DropzUniversalAgent-Windows.zip")
UPDATE_CHECK_TIMEOUT_SECONDS = int(os.environ.get("DROPZ_UPDATE_CHECK_TIMEOUT_SECONDS", "8"))

HOST = "127.0.0.1"
PORT = int(os.environ.get("DROPZ_DESKTOP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"

_opened_browser = False


def _base_dir() -> Path:
    # PyInstaller onedir places bundled app files in sys._MEIPASS / _internal.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
EXE_DIR = _exe_dir()
USER_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = Path(os.environ.get("DROPZ_LAUNCHER_LOG", str(Path.home() / "DropzUniversalAgent_launcher.log")))
UPDATE_STATE_FILE = USER_DATA_DIR / "update_state.json"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        log(f"Could not write {path.name}: {exc}")


def _installed_info() -> dict:
    # installed_update_state.json/update_state.json are written by the updater after a successful update.
    candidates = [
        UPDATE_STATE_FILE,
        EXE_DIR / "installed_update_state.json",
        EXE_DIR / "update_state.json",
        EXE_DIR / "build_info.json",
        EXE_DIR / "_internal" / "build_info.json",
        BASE_DIR / "build_info.json",
    ]

    info: dict = {}
    for candidate in candidates:
        info = _read_json(candidate)
        if info:
            break

    version_txt = EXE_DIR / "version.txt"
    if version_txt.exists():
        try:
            info.setdefault("version", version_txt.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    info.setdefault("version", "1.0.0")
    info.setdefault("signature", info.get("build_id", ""))
    info.setdefault("build_id", info.get("signature", ""))
    return info


def _github_latest_release() -> dict:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    req = Request(
        url,
        headers={
            "User-Agent": f"{APP_NAME}-Launcher",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(req, timeout=UPDATE_CHECK_TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}


def _remote_update_info() -> dict:
    release = _github_latest_release()
    assets = release.get("assets") or []
    asset = None
    for item in assets:
        if str(item.get("name") or "").lower() == UPDATE_ASSET_NAME.lower():
            asset = item
            break
    if not asset:
        return {}

    tag = str(release.get("tag_name") or release.get("name") or "0.0.0").lstrip("v")
    asset_id = str(asset.get("id") or "")
    updated_at = str(asset.get("updated_at") or asset.get("created_at") or release.get("published_at") or "")
    size = str(asset.get("size") or "")
    download_url = str(asset.get("browser_download_url") or "")
    release_id = str(release.get("id") or "")

    # Signature is intentionally based on GitHub asset metadata, not just version.
    # If you delete/re-upload the ZIP under the same release tag, asset id/updated_at/size changes.
    signature = f"github:{GITHUB_OWNER}/{GITHUB_REPO}:{release_id}:{asset_id}:{updated_at}:{size}:{UPDATE_ASSET_NAME}"

    return {
        "version": tag or "0.0.0",
        "signature": signature,
        "build_id": signature,
        "download_url": download_url,
        "asset_name": UPDATE_ASSET_NAME,
        "asset_id": asset_id,
        "asset_updated_at": updated_at,
        "asset_size": size,
        "release_id": release_id,
        "release_url": str(release.get("html_url") or ""),
    }


def _update_available(local: dict, remote: dict) -> bool:
    if not remote or not remote.get("download_url") or not remote.get("signature"):
        return False

    local_sig = str(local.get("signature") or local.get("build_id") or "")
    remote_sig = str(remote.get("signature") or remote.get("build_id") or "")
    if remote_sig and remote_sig != local_sig:
        return True

    # Fallback: version changed.
    return str(remote.get("version") or "") != str(local.get("version") or "")


def _run_prelaunch_update_if_available() -> bool:
    """
    Checks GitHub Releases before opening the app. If an update exists, this launches
    DropzUpdater.exe in foreground mode so the user sees download/install progress,
    then exits this launcher. The updater installs and relaunches the updated app.
    """
    try:
        if os.environ.get("DROPZ_SKIP_UPDATE_CHECK", "").lower() in {"1", "true", "yes"}:
            log("Update check skipped by DROPZ_SKIP_UPDATE_CHECK.")
            return False

        updater = EXE_DIR / "DropzUpdater.exe"
        if not updater.exists():
            log("No updater found. Opening app normally.")
            return False

        local = _installed_info()
        log("Checking GitHub Releases for updates...")
        remote = _remote_update_info()
        if not _update_available(local, remote):
            log("No update available.")
            return False

        log(f"Update available: {local.get('version')} -> {remote.get('version')} ({remote.get('asset_updated_at')}).")
        log("Starting updater before opening the app so progress is visible.")

        args = [
            str(updater),
            "--app-dir", str(EXE_DIR),
            "--main-exe", str(EXE_DIR / f"{APP_NAME}.exe"),
            "--current-version", str(local.get("version") or "0.0.0"),
            "--latest-version", str(remote.get("version") or "0.0.0"),
            "--download-url", str(remote.get("download_url") or ""),
            "--build-id", str(remote.get("signature") or ""),
            "--remote-state-json", json.dumps(remote, separators=(",", ":")),
            "--wait-pid", str(os.getpid()),
        ]

        subprocess.Popen(args, cwd=str(EXE_DIR), close_fds=True)
        log("Launcher exiting so updater can safely replace app files.")
        return True
    except Exception as exc:
        # Never block app launch if update check fails.
        log(f"Update check failed; opening app normally: {exc}")
        return False


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.4):
            return True
    except OSError:
        return False


def _find_app_file() -> Path:
    candidates = [
        BASE_DIR / "streamlit_app.py",
        EXE_DIR / "streamlit_app.py",
        EXE_DIR / "_internal" / "streamlit_app.py",
        Path.cwd() / "streamlit_app.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("streamlit_app.py was not found next to the EXE or inside _internal.")


def _configure_streamlit_runtime() -> None:
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("DROPZ_DESKTOP_MODE", "true")
    os.environ.setdefault("DROPZ_USER_DATA_DIR", str(USER_DATA_DIR))

    installed = _installed_info()
    os.environ.setdefault("DROPZ_APP_VERSION", str(installed.get("version") or "1.0.0"))


def _run_streamlit_in_process(app_file: Path) -> None:
    """
    Starts Streamlit without spawning this EXE again.
    This avoids infinite launcher recursion from using sys.executable.
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
            time.sleep(0.8)
            _open_browser_once()
            return
        time.sleep(0.5)
    log("Timed out waiting for Streamlit. Browser was not opened.")


def main() -> int:
    log("Launcher starting.")
    try:
        # Pre-launch update: if update exists, updater shows progress and relaunches updated app.
        if _run_prelaunch_update_if_available():
            return 0

        app_file = _find_app_file()
        log(f"Using app file: {app_file}")

        if _port_open():
            log("Streamlit already running. Reusing existing server.")
            _open_browser_once()
            return 0

        opener = threading.Thread(target=_wait_and_open_browser, daemon=True)
        opener.start()

        _run_streamlit_in_process(app_file)
        return 0

    except BaseException as exc:
        log(f"Launcher fatal error: {type(exc).__name__}: {exc}")
        log(traceback.format_exc())
        try:
            input("Dropz Universal Agent failed to start. Press Enter to close...")
        except Exception:
            time.sleep(8)
        return 1
    finally:
        log("Launcher stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
