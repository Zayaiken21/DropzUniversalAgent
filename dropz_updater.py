from __future__ import annotations

import argparse
import hashlib
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


def _safe_cache_name(version: str, build_id: str) -> str:
    raw = f"{version}-{build_id or 'asset'}"
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    return cleaned[:140]


def download_cached(url: str, version: str, build_id: str = "", expected_sha256: str = "") -> Path:
    cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{APP_NAME}-{_safe_cache_name(version, build_id)}.zip"

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
    req = Request(url, headers={"User-Agent": f"{APP_NAME}-Updater/{version}", "Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
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
    extract_dir = temp_root / _safe_cache_name(version, build_id)
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
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, creationflags=flags, timeout=5)
            return str(pid) in (result.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def wait_for_pid_to_close(pid: int) -> None:
    if pid <= 0:
        log("No PID supplied. Waiting briefly before install.")
        time.sleep(2)
        return
    log(f"Waiting for app process to close. PID={pid}")
    while _process_exists(pid):
        time.sleep(1.0)
    time.sleep(2.0)


def _write_install_cmd(src: Path, app_dir: Path, main_exe: Path, version: str, build_id: str) -> Path:
    cmd_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd = cmd_dir / "finish_update.cmd"
    state = '{{"version":"{version}","build_id":"{build_id}"}}'.format(version=version, build_id=build_id)
    script = (
        "@echo off\n"
        "setlocal\n"
        "timeout /t 2 /nobreak >nul\n"
        f'echo Installing {APP_NAME} update...\n'
        f'robocopy "{src}" "{app_dir}" /E /XD "__pycache__" /XF "DropzUpdater.exe" >nul\n'
        "if %ERRORLEVEL% LEQ 7 (\n"
        f'  echo {version}> "{app_dir}\\version.txt"\n'
        f'  echo {state}> "{app_dir}\\last_update_state.json"\n'
        f'  start "" "{main_exe}"\n'
        "  exit /b 0\n"
        ")\n"
        "echo Update copy failed with code %ERRORLEVEL%.\n"
        "pause\n"
        "exit /b %ERRORLEVEL%\n"
    )
    cmd.write_text(script, encoding="utf-8")
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--main-exe", required=True)
    parser.add_argument("--current-version", default="0.0.0")
    parser.add_argument("--latest-version", required=True)
    parser.add_argument("--latest-build-id", default="")
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--sha256", default="")
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    main_exe = Path(args.main_exe).resolve()

    try:
        log(f"Updater started. {args.current_version} -> {args.latest_version} build={args.latest_build_id}")
        zip_path = download_cached(args.download_url, args.latest_version, args.latest_build_id, args.sha256)
        wait_for_pid_to_close(args.wait_pid)
        src = extract_update(zip_path, args.latest_version, args.latest_build_id)

        if os.name == "nt":
            cmd = _write_install_cmd(src, app_dir, main_exe, args.latest_version, args.latest_build_id)
            log(f"Handing install to command script: {cmd}")
            subprocess.Popen(["cmd", "/c", str(cmd)], cwd=str(app_dir), close_fds=True)
            return 0

        # Non-Windows fallback.
        for item in src.iterdir():
            dest = app_dir / item.name
            if item.name == "DropzUpdater.exe":
                continue
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        if main_exe.exists():
            subprocess.Popen([str(main_exe)], cwd=str(app_dir), close_fds=True)
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
