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


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "update"))
    return cleaned[:140] or "update"


def _progress(label: str, percent: int) -> None:
    percent = max(0, min(100, int(percent)))
    blocks = percent // 5
    bar = "#" * blocks + "-" * (20 - blocks)
    print(f"\r{label}: [{bar}] {percent:3d}%", end="", flush=True)


def _is_valid_zip(path: Path) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


def download_cached(url: str, version: str, expected_sha256: str = "", build_id: str = "") -> Path:
    cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_key = _safe_name(f"{version}-{build_id or hashlib.sha1(url.encode()).hexdigest()[:12]}")
    target = cache_dir / f"{APP_NAME}-{cache_key}.zip"

    if target.exists() and target.stat().st_size > 0:
        valid_hash = not expected_sha256 or sha256_file(target).lower() == expected_sha256.lower()
        if valid_hash and _is_valid_zip(target):
            log(f"Using cached update ZIP: {target}")
            _progress("Download", 100)
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
        last_pct = -1
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = int(done * 100 / total)
                if pct != last_pct:
                    _progress("Download", pct)
                    last_pct = pct
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
    extract_dir = temp_root / _safe_name(f"{version}-{build_id or 'build'}")

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
                _progress("Extract", int(idx * 100 / total))
    print()

    nested = extract_dir / APP_NAME
    if nested.exists() and (nested / f"{APP_NAME}.exe").exists():
        return nested
    return extract_dir


def _write_finish_cmd(src: Path, app_dir: Path, main_exe: Path, wait_pid: int) -> Path:
    cmd_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd = cmd_dir / "finish_update.cmd"

    # Use robocopy from a detached .cmd so the updater EXE is not locked while files are replaced.
    script = f"""@echo off
setlocal
title Dropz Universal Agent Update Installer
echo Installing Dropz Universal Agent update...
echo Please keep this window open.

timeout /t 1 /nobreak >nul

if not "{wait_pid}"=="0" (
  :waitapp
  tasklist /FI "PID eq {wait_pid}" | find "{wait_pid}" >nul
  if not errorlevel 1 (
    echo Waiting for Dropz Universal Agent to close...
    timeout /t 1 /nobreak >nul
    goto waitapp
  )
)

echo Copying update files...
robocopy "{src}" "{app_dir}" /MIR /R:30 /W:1 /NFL /NDL /NP
set COPY_RESULT=%ERRORLEVEL%

if %COPY_RESULT% LEQ 7 (
  echo Update installed successfully.

  echo Refreshing Windows icon cache...
  if exist "%LOCALAPPDATA%\\IconCache.db" del /f /q "%LOCALAPPDATA%\\IconCache.db" >nul 2>nul
  if exist "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache*" del /f /q "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache*" >nul 2>nul
  ie4uinit.exe -ClearIconCache >nul 2>nul
  ie4uinit.exe -show >nul 2>nul

  echo Refreshing Explorer...
  taskkill /f /im explorer.exe >nul 2>nul
  timeout /t 1 /nobreak >nul
  start explorer.exe >nul 2>nul

  echo Starting Dropz Universal Agent...
  timeout /t 1 /nobreak >nul
  start "" "{main_exe}"
) else (
  echo Update copy failed with code %COPY_RESULT%.
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
    parser.add_argument("--wait-pid", type=int, default=0)
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    main_exe = Path(args.main_exe).resolve()

    try:
        log(f"Updater started. {args.current_version} -> {args.latest_version}")
        zip_path = download_cached(args.download_url, args.latest_version, args.sha256, args.build_id)
        src = extract_update(zip_path, args.latest_version, args.build_id)

        log("Preparing safe installer handoff.")
        finish_cmd = _write_finish_cmd(src, app_dir, main_exe, args.wait_pid)

        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(["cmd.exe", "/c", str(finish_cmd)], cwd=str(app_dir), creationflags=flags)
        else:
            # Non-Windows development fallback.
            for item in src.iterdir():
                dest = app_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            subprocess.Popen([str(main_exe)], cwd=str(app_dir))

        log("Installer launched. Updater can close.")
        return 0
    except Exception as exc:
        log(f"Update failed: {exc}")
        try:
            input("Press Enter to open the current app without updating...")
            if main_exe.exists():
                subprocess.Popen([str(main_exe)], cwd=str(app_dir))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
