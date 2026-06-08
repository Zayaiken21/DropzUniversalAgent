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
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

APP_NAME = "DropzUniversalAgent"
GITHUB_OWNER = os.environ.get("DROPZ_GITHUB_OWNER", "Zayaiken21")
GITHUB_REPO = os.environ.get("DROPZ_GITHUB_REPO", "DropzUniversalAgent")
UPDATE_ASSET_NAME = os.environ.get("DROPZ_UPDATE_ASSET_NAME", "DropzUniversalAgent-Windows.zip")

HOST = "127.0.0.1"
PORT = int(os.environ.get("DROPZ_DESKTOP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"

_opened_browser = False
_update_started = False


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

    user_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
    user_data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DROPZ_USER_DATA_DIR", str(user_data))


def _read_json_file(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _installed_info() -> dict:
    candidates = [
        EXE_DIR / "build_info.json",
        BASE_DIR / "build_info.json",
        EXE_DIR / "_internal" / "build_info.json",
    ]
    info: dict = {}
    for candidate in candidates:
        info = _read_json_file(candidate)
        if info:
            break

    version_txt = EXE_DIR / "version.txt"
    if version_txt.exists():
        try:
            info.setdefault("version", version_txt.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    info.setdefault("version", os.environ.get("DROPZ_APP_VERSION", "1.0.0"))
    info.setdefault("build_id", "")
    info.setdefault("build_time_utc", "")
    return info


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for piece in str(value or "0").replace("v", "").replace("-", ".").split("."):
        try:
            parts.append(int("".join(ch for ch in piece if ch.isdigit()) or "0"))
        except Exception:
            parts.append(0)
    return tuple(parts or [0])


def _parse_time(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _fetch_json(url: str, timeout: int = 8) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": f"{APP_NAME}-Launcher",
            "Accept": "application/vnd.github+json, application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024).decode("utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _read_update_manifest() -> dict:
    manifest_url = os.environ.get("DROPZ_UPDATE_MANIFEST_URL", "").strip()
    if not manifest_url:
        manifest_file = EXE_DIR / "update_manifest_url.txt"
        if manifest_file.exists():
            manifest_url = manifest_file.read_text(encoding="utf-8").strip()

    if manifest_url:
        try:
            data = _fetch_json(manifest_url)
            data["_source"] = "manifest"
            return data
        except Exception as exc:
            log(f"Manifest update check failed; falling back to GitHub latest release: {exc}")

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    data = _fetch_json(api_url)
    assets = data.get("assets") or []
    asset = None
    for item in assets:
        if str(item.get("name", "")).lower() == UPDATE_ASSET_NAME.lower():
            asset = item
            break
    if asset is None and assets:
        for item in assets:
            if str(item.get("name", "")).lower().endswith(".zip"):
                asset = item
                break
    if not asset:
        return {}

    tag = str(data.get("tag_name") or "").lstrip("v") or str(data.get("name") or "").lstrip("v")
    latest_build_id = str(asset.get("id") or "") + "-" + str(asset.get("updated_at") or asset.get("created_at") or "")
    return {
        "_source": "github_latest_release",
        "version": tag or "0.0.0",
        "release_tag": data.get("tag_name", ""),
        "release_id": data.get("id", ""),
        "release_published_at": data.get("published_at") or data.get("created_at") or "",
        "asset_id": asset.get("id", ""),
        "asset_name": asset.get("name", UPDATE_ASSET_NAME),
        "asset_size": asset.get("size", 0),
        "asset_updated_at": asset.get("updated_at") or asset.get("created_at") or "",
        "build_id": latest_build_id,
        "download_url": asset.get("browser_download_url", ""),
        "sha256": "",
        "notes": data.get("body", "") or "",
    }


def _update_needed(installed: dict, remote: dict) -> tuple[bool, str]:
    current_version = str(installed.get("version") or "0.0.0")
    latest_version = str(remote.get("version") or "0.0.0")
    if _version_tuple(latest_version) > _version_tuple(current_version):
        return True, f"new version {current_version} -> {latest_version}"

    current_build_id = str(installed.get("build_id") or "")
    latest_build_id = str(remote.get("build_id") or "")
    if latest_build_id and current_build_id and latest_build_id != current_build_id:
        return True, f"same version but different GitHub asset ({current_build_id} -> {latest_build_id})"

    build_time = _parse_time(str(installed.get("build_time_utc") or ""))
    asset_time = _parse_time(str(remote.get("asset_updated_at") or remote.get("release_published_at") or ""))
    if asset_time and build_time and asset_time > build_time + 60:
        return True, "same version but GitHub asset is newer than installed build"

    return False, "current build is up to date"


def _start_update_check_in_background() -> None:
    global _update_started
    if _update_started:
        return
    _update_started = True

    def worker() -> None:
        try:
            if os.environ.get("DROPZ_DISABLE_UPDATES", "").lower() in {"1", "true", "yes", "on"}:
                log("Updates disabled by DROPZ_DISABLE_UPDATES.")
                return

            installed = _installed_info()
            remote = _read_update_manifest()
            if not remote:
                log("No update release/asset found.")
                return

            download_url = str(remote.get("download_url") or "").strip()
            latest = str(remote.get("version", "") or "").strip()
            if not latest or not download_url:
                log("Update source missing version or download_url.")
                return

            needed, reason = _update_needed(installed, remote)
            if not needed:
                log(f"No update needed. Current={installed.get('version')} Latest={latest}. Reason={reason}.")
                return

            updater = EXE_DIR / "DropzUpdater.exe"
            if not updater.exists():
                log("Update available, but DropzUpdater.exe is missing.")
                return

            latest_build_id = str(remote.get("build_id") or remote.get("asset_id") or latest)
            log(f"Update available ({reason}). Starting updater in background.")
            args = [
                str(updater),
                "--app-dir", str(EXE_DIR),
                "--main-exe", str(EXE_DIR / f"{APP_NAME}.exe"),
                "--current-version", str(installed.get("version") or "0.0.0"),
                "--latest-version", latest,
                "--latest-build-id", latest_build_id,
                "--download-url", download_url,
                "--sha256", str(remote.get("sha256", "") or ""),
                "--wait-pid", str(os.getpid()),
                "--background",
            ]
            subprocess.Popen(args, cwd=str(EXE_DIR), close_fds=True)
        except Exception as exc:
            log(f"Update check skipped: {exc}")

    threading.Thread(target=worker, daemon=True).start()


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
            _start_update_check_in_background()
            return
        time.sleep(0.35)
    log("Streamlit did not respond before timeout. Opening browser once anyway.")
    _open_browser_once()
    _start_update_check_in_background()


def main() -> int:
    log("Launcher starting.")
    try:
        app_file = _find_app_file()
        log(f"Using app file: {app_file}")
        threading.Thread(target=_wait_and_open_browser, daemon=True).start()
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
