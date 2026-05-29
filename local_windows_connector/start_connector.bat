@echo off
cd /d "%~dp0"
python -m pip install -r requirements_windows_connector.txt
python connector.py
pause
