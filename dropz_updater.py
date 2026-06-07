from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
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


def download_cached(url: str, version: str, expected_sha256: str = "") -> Path:
    cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{APP_NAME}-{version}.zip"

    if target.exists() and target.stat().st_size > 0:
        if not expected_sha256 or sha256_file(target).lower() == expected_sha256.lower():
            log(f"Using cached update ZIP: {target}")
            return target
        target.unlink(missing_ok=True)

    tmp = target.with_suffix(".zip.part")
    log(f"Downloading update: {url}")
    req = Request(url, headers={"User-Agent": f"{APP_NAME}-Updater/{version}"})
    with urlopen(req, timeout=30) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or "0")
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = int(done * 100 / total)
                print(f"\rDownload {pct}%", end="", flush=True)
    print()

    tmp.replace(target)

    if expected_sha256:
        actual = sha256_file(target)
        if actual.lower() != expected_sha256.lower():
            target.unlink(missing_ok=True)
            raise RuntimeError(f"SHA256 mismatch. Expected {expected_sha256}, got {actual}")

    return target


def extract_update(zip_path: Path, version: str) -> Path:
    temp_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME / "update_extract"
    extract_dir = temp_root / version
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    log(f"Extracting update: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # Support both ZIP styles:
    # 1) files directly inside ZIP
    # 2) DropzUniversalAgent/files inside ZIP
    nested = extract_dir / APP_NAME
    if nested.exists() and (nested / f"{APP_NAME}.exe").exists():
        return nested
    return extract_dir


def wait_for_main_to_close(main_exe: Path) -> None:
    # Simple wait; launcher exits before updater starts. This just gives Windows a moment to release handles.
    log("Waiting for app to close.")
    time.sleep(2)


def copy_update(src: Path, app_dir: Path) -> None:
    log(f"Installing update into: {app_dir}")
    app_dir.mkdir(parents=True, exist_ok=True)

    skip_names = {"DropzUpdater.exe"}  # keep currently-running updater stable

    for item in src.iterdir():
        if item.name in skip_names:
            continue
        dest = app_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--main-exe", required=True)
    parser.add_argument("--current-version", default="0.0.0")
    parser.add_argument("--latest-version", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--sha256", default="")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    main_exe = Path(args.main_exe).resolve()

    try:
        log(f"Updater started. {args.current_version} -> {args.latest_version}")
        wait_for_main_to_close(main_exe)
        zip_path = download_cached(args.download_url, args.latest_version, args.sha256)
        src = extract_update(zip_path, args.latest_version)
        copy_update(src, app_dir)

        log("Update installed successfully.")
        if main_exe.exists():
            log("Restarting app.")
            subprocess.Popen([str(main_exe)], cwd=str(app_dir), close_fds=True)
        return 0
    except Exception as exc:
        log(f"Update failed: {exc}")
        try:
            input("Press Enter to close updater...")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
