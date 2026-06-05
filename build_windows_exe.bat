@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo Installing desktop requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements_desktop.txt

echo Checking required packages...
python -c "from importlib.util import find_spec; import sys; required=['streamlit','pandas','numpy','plotly','requests','dotenv','cryptography','PyInstaller','altair','pyarrow','watchdog']; missing=[m for m in required if find_spec(m) is None]; print('Missing:', missing) if missing else print('Required packages OK'); sys.exit(1 if missing else 0)"
if errorlevel 1 (
  echo Required package check failed.
  pause
  exit /b 1
)

echo Cleaning old build output...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q DropzUniversalAgent-Windows.zip 2>nul

echo Building Dropz Universal Agent desktop app...
python -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onedir ^
  --name DropzUniversalAgent ^
  --icon assets\dropz_icon.ico ^
  --runtime-hook pyi_runtime_hook_dropz.py ^
  --collect-all streamlit ^
  --collect-all tornado ^
  --collect-all altair ^
  --collect-all pyarrow ^
  --collect-all plotly ^
  --collect-all pandas ^
  --collect-all numpy ^
  --collect-all requests ^
  --collect-all dotenv ^
  --collect-all cryptography ^
  --collect-all MetaTrader5 ^
  --collect-all streamlit_option_menu ^
  --collect-all streamlit_extras ^
  --collect-all streamlit_autorefresh ^
  --collect-all streamlit_webrtc ^
  --collect-all streamlit_js_eval ^
  --collect-all streamlit_chat ^
  --collect-all streamlit_float ^
  --hidden-import chat_backend ^
  --hidden-import chat_backend.chat_db ^
  --hidden-import components ^
  --hidden-import components.charts ^
  --hidden-import components.dashboard_mt5_data ^
  --add-data "streamlit_app.py;." ^
  --add-data "frontend;frontend" ^
  --add-data "components;components" ^
  --add-data "chat_backend;chat_backend" ^
  --add-data "backend;backend" ^
  --add-data "agents;agents" ^
  --add-data "strategies;strategies" ^
  --add-data "styles;styles" ^
  --add-data "tools;tools" ^
  --add-data "assets;assets" ^
  --add-data "data;data" ^
  --add-data "frontend\dropz.db;frontend" ^
  desktop_launcher.py

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo Creating ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '.\dist\DropzUniversalAgent\*' -DestinationPath '.\DropzUniversalAgent-Windows.zip' -Force"

echo.
echo Build complete:
echo dist\DropzUniversalAgent\DropzUniversalAgent.exe
echo ZIP ready:
echo DropzUniversalAgent-Windows.zip
pause
