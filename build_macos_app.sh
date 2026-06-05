#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements_desktop.txt

python3 -m PyInstaller \
  --noconfirm \
  --onedir \
  --name "DropzUniversalAgent" \
  --add-data "streamlit_app.py:." \
  --add-data "frontend:frontend" \
  --add-data "agents:agents" \
  --add-data "config.py:." \
  --add-data "data:data" \
  desktop_launcher.py

echo "Build complete: dist/DropzUniversalAgent/DropzUniversalAgent"
echo "Note: MT5 Python trading is Windows-only. macOS build can run the UI, but direct MT5 trading requires Windows MT5 support."
