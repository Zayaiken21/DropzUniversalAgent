# Dropz Universal Agent EXE Fix

This fixes:

- `PackageNotFoundError: No package metadata was found for streamlit`
- EXE opening the browser before Streamlit is ready
- many browser tabs opening
- launcher recursively starting itself

## Why the error happened

Inside a PyInstaller EXE, Streamlit still calls `importlib.metadata.version("streamlit")`.
If the build does not bundle Streamlit metadata, Streamlit crashes with:

```txt
PackageNotFoundError: No package metadata was found for streamlit
```

The fixed `build_windows_exe.bat` uses:

```txt
--collect-all streamlit
--copy-metadata streamlit
```

so Streamlit can start properly inside the EXE.

## How to rebuild

From project root:

```powershell
cd C:\Users\Eric\PycharmProjects\DropzUniversalAgent
.\.venv\Scripts\activate
.\build_windows_exe.bat
```

## Before testing

Close all old stuck launchers:

```powershell
taskkill /F /IM DropzUniversalAgent.exe
taskkill /F /IM python.exe
taskkill /F /IM streamlit.exe
```

Then run:

```txt
dist\DropzUniversalAgent\DropzUniversalAgent.exe
```

## What to send clients

Send:

```txt
DropzUniversalAgent-Windows.zip
```

Clients should extract the ZIP and open:

```txt
DropzUniversalAgent.exe
```
