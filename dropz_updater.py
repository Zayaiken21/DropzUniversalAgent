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


def download_cached(url: str, version: str, build_id: str = "", expected_sha256: str = "") -> Path:
    cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _safe_cache_name(f"{version}-{build_id or 'asset'}")
    target = cache_dir / f"{APP_NAME}-{cache_key}.zip"

    if target.exists() and target.stat().st_size > 0:
        valid_hash = (not expected_sha256) or sha256_file(target).lower() == expected_sha256.lower()
        if valid_hash and _is_valid_zip(target):
            log(f"Using cached update ZIP: {target}")
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
    with urlopen(req, timeout=90) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or "0")
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\rDownload {int(done * 100 / total)}%", end="", flush=True)
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
        zf.extractall(extract_dir)

    nested = extract_dir / APP_NAME
    if nested.exists() and (nested / f"{APP_NAME}.exe").exists():
        return nested
    return extract_dir


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=flags,
                timeout=5,
            )
            return str(pid) in (result.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _write_state_files(src: Path, remote_state_json: str, version: str, build_id: str) -> None:
    try:
        state = json.loads(remote_state_json) if remote_state_json else {}
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}

    state.setdefault("version", version)
    state.setdefault("signature", build_id)
    state["installed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for name in ("update_state.json", "installed_update_state.json"):
        try:
            (src / name).write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    try:
        local_state = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "update_state.json"
        local_state.parent.mkdir(parents=True, exist_ok=True)
        local_state.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _write_finish_cmd(src: Path, app_dir: Path, main_exe: Path, wait_pid: int) -> Path:
    cmd_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd = cmd_dir / "finish_update.cmd"

    # /MIR keeps installed files exactly in sync with the new ZIP.
    # It runs after this updater exits, so Windows can replace DropzUpdater.exe too.
    script = f"""@echo off
setlocal
echo Finishing DropzUniversalAgent update...
timeout /t 2 /nobreak >nul
:waitapp
tasklist /FI "PID eq {wait_pid}" | find "{wait_pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitapp
)
robocopy "{src}" "{app_dir}" /MIR /R:30 /W:1 /NFL /NDL /NP
if %ERRORLEVEL% LEQ 7 (
  echo Update installed.
  start "" "{main_exe}"
) else (
  echo Update copy failed with code %ERRORLEVEL%.
  pause
)
endlocal
"""
    cmd.write_text(script, encoding="utf-8")
    return cmd


def main() -> int:
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
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    main_exe = Path(args.main_exe).resolve()

    try:
        log(f"Updater started. {args.current_version} -> {args.latest_version}")
        zip_path = download_cached(args.download_url, args.latest_version, args.build_id, args.sha256)
        src = extract_update(zip_path, args.latest_version, args.build_id)
        _write_state_files(src, args.remote_state_json, args.latest_version, args.build_id)

        log(f"Waiting for app process to close. PID={args.wait_pid}")
        finish_cmd = _write_finish_cmd(src, app_dir, main_exe, args.wait_pid)

        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(["cmd.exe", "/c", str(finish_cmd)], cwd=str(app_dir), creationflags=flags)
        else:
            # Non-Windows fallback for development.
            while _process_exists(args.wait_pid):
                time.sleep(1)
            for item in src.iterdir():
                dest = app_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            subprocess.Popen([str(main_exe)], cwd=str(app_dir))

        log("Background installer launched. Updater can close.")
        return 0
    except Exception as exc:
        log(f"Update failed: {exc}")
        if not args.background:
            try:
                input("Press Enter to close updater...")
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
