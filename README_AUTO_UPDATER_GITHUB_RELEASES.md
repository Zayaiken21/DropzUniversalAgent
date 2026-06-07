# Dropz Universal Agent — Auto-Updater + GitHub Release Setup

## What this adds

Your shipped ZIP now includes:

```txt
DropzUniversalAgent.exe
DropzUpdater.exe
version.txt
_internal/
```

The main app checks an online `version_manifest.json`. If the manifest has a newer version, the app starts `DropzUpdater.exe`, exits, downloads the new ZIP, installs it, and reopens the app.

## Files to place in your project root

```txt
desktop_launcher.py
dropz_updater.py
pyi_runtime_hook_dropz.py
build_windows_exe.bat
requirements_desktop.txt
.gitignore
version_manifest.json
update_manifest_url.txt
```

## update_manifest_url.txt

Put the public raw URL to your manifest in this file. Example:

```txt
https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/DropzUniversalAgent/main/version_manifest.json
```

This file gets bundled into the client ZIP. The app uses it to check for updates.

## GitHub repo reset

Only do this from your project root:

```powershell
cd C:\Users\Eric\PycharmProjects\DropzUniversalAgent
rmdir /s /q .git
git init
git branch -M main
git add .
git commit -m "Initial Dropz Universal Agent desktop release"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/DropzUniversalAgent.git
git push -u origin main
```

## Build the app

Use Python 3.11:

```powershell
cd C:\Users\Eric\PycharmProjects\DropzUniversalAgent
.\.venv311\Scripts\activate
.\build_windows_exe.bat
```

Output:

```txt
DropzUniversalAgent-Windows.zip
```

## Publish an update

1. Change `APP_VERSION` inside `build_windows_exe.bat`:

```bat
set APP_VERSION=1.0.2
```

2. Build again:

```powershell
.\build_windows_exe.bat
```

3. Upload `DropzUniversalAgent-Windows.zip` to GitHub Releases.

4. Compute SHA256:

```powershell
Get-FileHash .\DropzUniversalAgent-Windows.zip -Algorithm SHA256
```

5. Update `version_manifest.json`:

```json
{
  "version": "1.0.2",
  "download_url": "https://github.com/YOUR_GITHUB_USERNAME/DropzUniversalAgent/releases/download/v1.0.2/DropzUniversalAgent-Windows.zip",
  "sha256": "PASTE_SHA256_HERE",
  "notes": "Update notes here."
}
```

6. Commit and push `version_manifest.json`:

```powershell
git add version_manifest.json
git commit -m "Release 1.0.2"
git push
```

Clients will update automatically on next app open.

## Fast download caching

The updater stores downloaded update ZIPs in:

```txt
%LOCALAPPDATA%\DropzUniversalAgent\updates
```

If the same version is already downloaded and the SHA256 matches, it reuses the cached ZIP instead of downloading again.

## Important production notes

- Do not commit `.env`, secrets, MT5 credentials, or build folders.
- Do not ship your service role key inside the EXE.
- Use Supabase anon key only for safe client-side reads, or use an Edge Function for protected license checks.
- Windows MT5 auto-trading is Windows-only.
