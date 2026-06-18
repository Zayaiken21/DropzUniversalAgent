from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

APP_NAME = "DropzUniversalAgent"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        log_file = Path.home() / "DropzUniversalAgent_updater.log"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_valid_zip(path: Path) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


def _safe_cache_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "asset"))
    return cleaned[:160] or "asset"


def _progress_bar(label: str, percent: int) -> None:
    percent = max(0, min(100, int(percent)))
    blocks = percent // 5
    bar = "#" * blocks + "-" * (20 - blocks)
    print(f"\r{label}: [{bar}] {percent:3d}%", end="", flush=True)


def download_cached(url: str, version: str, build_id: str = "", expected_sha256: str = "") -> Path:
    cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _safe_cache_name(f"{version}-{build_id or 'asset'}")
    target = cache_dir / f"{APP_NAME}-{cache_key}.zip"

    if target.exists() and target.stat().st_size > 0:
        valid_hash = (not expected_sha256) or sha256_file(target).lower() == expected_sha256.lower()
        if valid_hash and _is_valid_zip(target):
            log(f"Using cached update ZIP: {target}")
            _progress_bar("Download", 100)
            print()
            return target
        log("Cached update ZIP is invalid or mismatched. Re-downloading.")
        target.unlink(missing_ok=True)

    tmp = target.with_suffix(".zip.part")
    tmp.unlink(missing_ok=True)

    log(f"Downloading update: {url}")
    req = Request(
        url,
        headers={
            "User-Agent": f"{APP_NAME}-Updater/{version}",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or "0")
        done = 0
        last_percent = -1
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                percent = int(done * 100 / total)
                if percent != last_percent:
                    _progress_bar("Download", percent)
                    last_percent = percent
            else:
                print(f"\rDownloaded {done / (1024 * 1024):.1f} MB", end="", flush=True)
    print()

    tmp.replace(target)

    if expected_sha256:
        actual = sha256_file(target)
        if actual.lower() != expected_sha256.lower():
            target.unlink(missing_ok=True)
            raise RuntimeError(f"SHA256 mismatch. Expected {expected_sha256}, got {actual}")

    if not _is_valid_zip(target):
        target.unlink(missing_ok=True)
        raise RuntimeError("Downloaded update is not a valid ZIP file.")

    return target


def extract_update(zip_path: Path, version: str, build_id: str = "") -> Path:
    temp_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "update_extract"
    extract_dir = temp_root / _safe_cache_name(f"{version}-{build_id or 'asset'}")
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    log(f"Extracting update: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        total = max(1, len(members))
        for idx, member in enumerate(members, start=1):
            zf.extract(member, extract_dir)
            if idx == total or idx % max(1, total // 100) == 0:
                _progress_bar("Extract", int(idx * 100 / total))
    print()

    nested = extract_dir / APP_NAME
    if nested.exists() and (nested / f"{APP_NAME}.exe").exists():
        return nested
    return extract_dir


def _write_installed_state(src: Path, version: str, build_id: str = "", remote_state_json: str = "") -> dict:
    """Writes update metadata into the extracted update so it is copied into app_dir,
    AND mirrors it to the local %LOCALAPPDATA% update_state.json used by the launcher's
    same-version/changed-asset detection (_should_update in desktop_launcher.py).

    This lets future launches compare the installed build against GitHub asset metadata,
    even when the visible version number stays the same. Returns the final state dict
    that was written, for logging/verification.
    """
    state: dict = {}
    if remote_state_json:
        try:
            parsed = json.loads(remote_state_json)
            if isinstance(parsed, dict):
                state.update(parsed)
        except Exception as exc:
            log(f"Could not parse remote update state JSON: {exc}")

    state.setdefault("version", version)
    state.setdefault("build_id", build_id)
    state.setdefault("signature", build_id)
    state["installed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Written into the update payload itself, so it ends up inside app_dir after robocopy.
    for name in ("installed_update_state.json", "update_state.json", "build_info.json"):
        try:
            (src / name).write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            log(f"Could not write {name} into update payload: {exc}")

    # Also written directly to %LOCALAPPDATA%, since that's what the launcher reads
    # immediately on next start (before re-deriving it from build_info.json next to the exe).
    try:
        local_state = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "update_state.json"
        local_state.parent.mkdir(parents=True, exist_ok=True)
        local_state.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        log(f"Could not write local update_state.json: {exc}")

    return state


def _desktop_runtime_cache_roots() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
    return [
        local / "streamlit_cache",
        local / ".streamlit",
        local / "runtime_cache",
        Path(os.environ.get("TEMP", str(local))) / f"{APP_NAME}_streamlit_cache",
    ]


def _clear_runtime_caches() -> None:
    for root in _desktop_runtime_cache_roots():
        try:
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)
                log(f"Cleared runtime cache: {root}")
        except Exception as exc:
            log(f"Could not clear runtime cache {root}: {exc}")


def _write_finish_cmd(src: Path, app_dir: Path, main_exe: Path, wait_pid: int, expected_signature: str = "") -> Path:
    cmd_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd = cmd_dir / "finish_update.cmd"
    main_exe_name = main_exe.name
    expected_sig_escaped = expected_signature.replace('"', "")

    script = f"""@echo off
setlocal EnableDelayedExpansion
title Dropz Universal Agent Update Installer
echo Installing Dropz Universal Agent update...
echo Please keep this window open.
timeout /t 1 /nobreak >nul
:waitapp
tasklist /FI "PID eq {wait_pid}" | find "{wait_pid}" >nul
if not errorlevel 1 (
  echo Waiting for launcher to close...
  timeout /t 1 /nobreak >nul
  goto waitapp
)
echo Clearing old desktop runtime cache...
rmdir /s /q "%LOCALAPPDATA%\\DropzUniversalAgent\\streamlit_cache" 2>nul
rmdir /s /q "%LOCALAPPDATA%\\DropzUniversalAgent\\.streamlit" 2>nul
rmdir /s /q "%LOCALAPPDATA%\\DropzUniversalAgent\\runtime_cache" 2>nul
for /d %%D in ("%TEMP%\\DropzUniversalAgent_streamlit_cache*") do rmdir /s /q "%%D" 2>nul
echo Copying update files...
robocopy "{src}" "{app_dir}" /MIR /R:30 /W:1 /NFL /NDL /NP
set RC_COPY=%ERRORLEVEL%
if %RC_COPY% GTR 7 (
  echo Update copy failed with code %RC_COPY%.
  pause
  exit /b 1
)
echo Verifying installed update...
if not exist "{app_dir}\\{main_exe_name}" (
  echo Verification failed: {main_exe_name} not found after copy.
  pause
  exit /b 1
)
if not exist "{app_dir}\\build_info.json" (
  echo Verification failed: build_info.json not found after copy.
  pause
  exit /b 1
)
findstr /C:"{expected_sig_escaped}" "{app_dir}\\build_info.json" >nul
if errorlevel 1 if not "{expected_sig_escaped}"=="" (
  echo Warning: build_info.json signature does not match expected update signature.
  echo Expected to find: {expected_sig_escaped}
  echo Continuing anyway, but please verify the installed version if issues occur.
)
echo Update installed and verified successfully.
echo Starting Dropz Universal Agent...
start "" "{main_exe}"
endlocal
"""
    cmd.write_text(script, encoding="utf-8")
    return cmd


def _build_arg_parser() -> argparse.ArgumentParser:
    """Builds the updater's argument parser.

    IMPORTANT: each --flag must be added exactly once. A duplicate
    add_argument() call for the same flag raises argparse.ArgumentError
    at startup (before any try/except in main() can catch it), which
    crashes the updater immediately. If you need to add a new flag,
    add it once here; do not copy-paste an existing add_argument line
    without removing/renaming it.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--main-exe", required=True)
    parser.add_argument("--current-version", default="0.0.0")
    parser.add_argument("--latest-version", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--sha256", default="")
    parser.add_argument("--build-id", default="")
    parser.add_argument("--remote-state-json", default="")
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--background", action="store_true")
    return parser


def main() -> int:
    # Building the parser can itself raise argparse.ArgumentError if a flag
    # were ever declared twice (e.g. from a bad merge/edit). Catch that here
    # too so a malformed updater build fails with a clear log line instead
    # of an opaque PyInstaller traceback with no recovery.
    try:
        parser = _build_arg_parser()
    except argparse.ArgumentError as exc:
        log(f"FATAL: updater argument parser is misconfigured (duplicate flag?): {exc}")
        return 1

    # Backward/forward compatibility: ignore unknown future launcher args instead of crashing.
    args, unknown = parser.parse_known_args()
    if unknown:
        log(f"Ignoring unsupported updater arguments: {unknown}")

    app_dir = Path(args.app_dir).resolve()
    main_exe = Path(args.main_exe).resolve()

    try:
        log(f"Updater started. {args.current_version} -> {args.latest_version}")

        # Backward compatibility guard:
        # Some broken transitional builds passed the remote update JSON into
        # updater arguments incorrectly. If download_url ever receives JSON,
        # recover instead of crashing.
        if str(args.download_url).lstrip().startswith("{"):
            try:
                recovered = json.loads(args.download_url)
                if isinstance(recovered, dict):
                    args.download_url = str(recovered.get("download_url") or recovered.get("asset_download_url") or "")
                    args.latest_version = str(recovered.get("version") or args.latest_version)
                    args.build_id = str(recovered.get("signature") or recovered.get("asset_id") or args.build_id)
                    args.sha256 = str(recovered.get("sha256") or args.sha256)
                    args.remote_state_json = json.dumps(recovered, separators=(",", ":"))
                    log("Recovered updater metadata from JSON argument.")
            except Exception as exc:
                log(f"Could not recover JSON updater metadata: {exc}")

        if not args.download_url or not str(args.download_url).lower().startswith(("http://", "https://")):
            raise RuntimeError(f"Invalid update download URL: {args.download_url!r}")

        zip_path = download_cached(args.download_url, args.latest_version, args.build_id, args.sha256)
        src = extract_update(zip_path, args.latest_version, args.build_id)
        written_state = _write_installed_state(src, args.latest_version, args.build_id, args.remote_state_json)
        log(f"Installed state recorded: version={written_state.get('version')} signature={written_state.get('signature')}")
        _clear_runtime_caches()

        log("Preparing safe installer handoff.")
        finish_cmd = _write_finish_cmd(src, app_dir, main_exe, args.wait_pid, written_state.get("signature", ""))

        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(["cmd.exe", "/c", str(finish_cmd)], cwd=str(app_dir), creationflags=flags)
        else:
            # Non-Windows fallback for development/testing.
            for item in src.iterdir():
                dest = app_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            if not (app_dir / "build_info.json").exists():
                log("Warning: build_info.json missing from app_dir after dev-mode copy.")
            subprocess.Popen([str(main_exe)], cwd=str(app_dir))

        log("Installer launched. Updater can close.")
        return 0
    except Exception as exc:
        log(f"Update failed: {exc}")
        try:
            input("Press Enter to open the current app without updating...")
            subprocess.Popen([str(main_exe)], cwd=str(app_dir))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
