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
USER_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = Path(os.environ.get("DROPZ_LAUNCHER_LOG", str(Path.home() / "DropzUniversalAgent_launcher.log")))
UPDATE_STATE_FILE = USER_DATA_DIR / "update_state.json"


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


def _pid_using_port() -> int | None:
    """Return the Windows PID currently bound to HOST:PORT, when available."""
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        needle_1 = f"{HOST}:{PORT}"
        needle_2 = f"0.0.0.0:{PORT}"
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper().startswith("TCP"):
                local_addr = parts[1]
                state = parts[3].upper() if len(parts) >= 4 else ""
                pid_text = parts[-1]
                if (needle_1 in local_addr or needle_2 in local_addr) and state == "LISTENING":
                    try:
                        return int(pid_text)
                    except Exception:
                        return None
    except Exception as exc:
        log(f"Could not inspect port {PORT}: {exc}")
    return None


def _process_name(pid: int) -> str:
    if os.name != "nt" or not pid:
        return ""
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        line = (proc.stdout or "").strip().splitlines()[0]
        return line.split(",", 1)[0].strip().strip('"')
    except Exception:
        return ""


def _clear_desktop_streamlit_cache() -> None:
    """Clear only this desktop app's Streamlit/runtime cache, never user data."""
    cache_roots = [
        USER_DATA_DIR / "streamlit_cache",
        USER_DATA_DIR / ".streamlit",
        USER_DATA_DIR / "runtime_cache",
        Path(os.environ.get("TEMP", str(USER_DATA_DIR))) / f"{APP_NAME}_streamlit_cache",
    ]
    for root in cache_roots:
        try:
            if root.exists():
                import shutil
                shutil.rmtree(root, ignore_errors=True)
                log(f"Cleared runtime cache: {root}")
        except Exception as exc:
            log(f"Could not clear runtime cache {root}: {exc}")


def _stop_stale_port_owner() -> None:
    """Prevent the browser from opening a stale local Streamlit server on 8501."""
    if os.environ.get("DROPZ_SKIP_PORT_CLEANUP", "").lower() in {"1", "true", "yes", "on"}:
        return
    pid = _pid_using_port()
    if not pid or pid == os.getpid():
        return
    name = _process_name(pid).lower()
    safe_names = ("python", "python.exe", "streamlit", "dropzuniversalagent", "dropzuniversalagent.exe")
    if any(part in name for part in safe_names) or not name:
        try:
            log(f"Port {PORT} is already in use by PID {pid} ({name or 'unknown'}). Stopping stale server.")
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            time.sleep(1.0)
        except Exception as exc:
            log(f"Could not stop stale port owner PID {pid}: {exc}")
    else:
        log(f"Port {PORT} is used by PID {pid} ({name}); not stopping unknown process.")


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


def _configure_runtime() -> None:
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
    os.environ.setdefault("STREAMLIT_SERVER_RUN_ON_SAVE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", HOST)
    os.environ.setdefault("STREAMLIT_SERVER_PORT", str(PORT))
    os.environ.setdefault("DROPZ_DESKTOP_MODE", "true")
    os.environ.setdefault("DROPZ_USER_DATA_DIR", str(USER_DATA_DIR))
    os.environ.setdefault("XDG_CACHE_HOME", str(USER_DATA_DIR / "streamlit_cache"))
    os.environ.setdefault("STREAMLIT_CACHE_DIR", str(USER_DATA_DIR / "streamlit_cache"))

    # Make frozen EXE imports resolve exactly like local `streamlit run` imports.
    for path in (BASE_DIR, EXE_DIR, EXE_DIR / "_internal"):
        path_text = str(path)
        if path.exists() and path_text not in sys.path:
            sys.path.insert(0, path_text)

    installed = _installed_info()
    os.environ.setdefault("DROPZ_APP_VERSION", str(installed.get("version") or "1.0.0"))


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
    candidates = [
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
    info.setdefault("build_id", "")
    info.setdefault("build_time_utc", "")
    return info


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for piece in str(value or "0").replace("v", "").replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts or [0])


def _fetch_json(url: str, timeout: int = 10) -> dict:
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
        raw = resp.read(3 * 1024 * 1024).decode("utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _github_latest_release() -> dict:
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    release = _fetch_json(api_url)

    assets = release.get("assets") or []
    asset = None
    for item in assets:
        if str(item.get("name") or "") == UPDATE_ASSET_NAME:
            asset = item
            break

    if not asset:
        raise RuntimeError(f"Release asset not found: {UPDATE_ASSET_NAME}")

    tag = str(release.get("tag_name") or release.get("name") or "").strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version:
        version = str(release.get("id") or "0")

    asset_id = str(asset.get("id") or "")
    updated_at = str(asset.get("updated_at") or asset.get("created_at") or "")
    size = str(asset.get("size") or "")
    download_url = str(asset.get("browser_download_url") or "")

    if not download_url:
        raise RuntimeError("GitHub release asset has no download URL.")

    signature = "|".join(
        [
            "github_release_asset",
            str(release.get("id") or ""),
            tag,
            asset_id,
            updated_at,
            size,
            UPDATE_ASSET_NAME,
        ]
    )

    return {
        "source": "github",
        "version": version,
        "tag_name": tag,
        "release_id": str(release.get("id") or ""),
        "asset_id": asset_id,
        "asset_name": UPDATE_ASSET_NAME,
        "asset_updated_at": updated_at,
        "asset_size": size,
        "download_url": download_url,
        "sha256": "",
        "signature": signature,
    }


def _manifest_fallback() -> dict:
    manifest_url = os.environ.get("DROPZ_UPDATE_MANIFEST_URL", "").strip()
    if not manifest_url:
        for candidate in (EXE_DIR / "update_manifest_url.txt", EXE_DIR / "_internal" / "update_manifest_url.txt", BASE_DIR / "update_manifest_url.txt"):
            if candidate.exists():
                manifest_url = candidate.read_text(encoding="utf-8").strip()
                break

    if not manifest_url:
        return {}

    data = _fetch_json(manifest_url)
    version = str(data.get("version") or "").strip()
    download_url = str(data.get("download_url") or "").strip()
    if not version or not download_url:
        return {}

    signature = str(data.get("build_id") or data.get("sha256") or data.get("updated_at") or version)
    return {
        "source": "manifest",
        "version": version,
        "tag_name": f"v{version}",
        "release_id": "",
        "asset_id": "",
        "asset_name": UPDATE_ASSET_NAME,
        "asset_updated_at": str(data.get("updated_at") or ""),
        "asset_size": "",
        "download_url": download_url,
        "sha256": str(data.get("sha256") or ""),
        "signature": f"manifest|{signature}|{download_url}",
    }


def _remote_update_info() -> dict:
    try:
        return _github_latest_release()
    except Exception as exc:
        log(f"GitHub release update check failed: {exc}")
        try:
            data = _manifest_fallback()
            if data:
                log("Using manifest fallback for update check.")
                return data
        except Exception as manifest_exc:
            log(f"Manifest fallback failed: {manifest_exc}")
    return {}


def _should_update(remote: dict, installed: dict, state: dict) -> tuple[bool, str]:
    if not remote:
        return False, "No remote update info."

    local_version = str(installed.get("version") or "0.0.0")
    remote_version = str(remote.get("version") or "0.0.0")

    if _version_tuple(remote_version) > _version_tuple(local_version):
        return True, f"newer version {local_version} -> {remote_version}"

    if _version_tuple(remote_version) < _version_tuple(local_version):
        return False, f"installed version {local_version} is newer than remote {remote_version}"

    remote_sig = str(remote.get("signature") or "")
    state_sig = str(state.get("signature") or "")

    if not remote_sig:
        return False, "Remote signature missing."

    if not state_sig:
        # First run of the advanced updater on this installed version.
        # Adopt the current GitHub asset as the baseline so we do not keep
        # reinstalling the same ZIP forever. Future reuploads with the same
        # version/tag will change asset_id/updated_at/size and will update.
        baseline = dict(remote)
        baseline["adopted_without_update"] = True
        baseline["adopted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json(UPDATE_STATE_FILE, baseline)
        return False, "Baseline update asset recorded for same-version tracking."

    if state_sig != remote_sig:
        return True, "same version but GitHub release asset changed"

    return False, "No update needed; release asset signature matches installed state."


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
            state = _read_json(UPDATE_STATE_FILE)
            remote = _remote_update_info()

            should_update, reason = _should_update(remote, installed, state)
            if not should_update:
                log(f"Update check complete: {reason}")
                return

            updater = EXE_DIR / "DropzUpdater.exe"
            if not updater.exists():
                log("Update available, but DropzUpdater.exe is missing.")
                return

            latest = str(remote.get("version") or "0.0.0")
            download_url = str(remote.get("download_url") or "")
            build_id = str(remote.get("signature") or remote.get("asset_id") or remote.get("asset_updated_at") or latest)

            log(f"Update available: {reason}. Starting updater in background.")
            # Stable updater protocol:
            # Keep this argument list simple and compatible forever.
            # Extra metadata is encoded into build_id/update state, not passed as
            # raw JSON flags, so older cached updater builds cannot crash on
            # unknown command-line arguments.
            args = [
                str(updater),
                "--app-dir", str(EXE_DIR),
                "--main-exe", str(EXE_DIR / f"{APP_NAME}.exe"),
                "--current-version", str(installed.get("version") or "0.0.0"),
                "--latest-version", latest,
                "--download-url", download_url,
                "--sha256", str(remote.get("sha256", "") or ""),
                "--build-id", build_id,
                "--wait-pid", str(os.getpid()),
            ]
            subprocess.Popen(args, cwd=str(EXE_DIR), close_fds=True)
        except Exception as exc:
            log(f"Update check skipped: {type(exc).__name__}: {exc}")

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
        "--server.fileWatcherType", "none",
        "--server.runOnSave", "false",
    ]
    try:
        os.chdir(str(app_file.parent))
    except Exception:
        pass
    log(f"Starting Streamlit in-process at {URL} from {app_file.parent}.")
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

        _configure_runtime()
        _clear_desktop_streamlit_cache()
        _stop_stale_port_owner()

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
