@echo off
setlocal
cd /d "%~dp0"

echo Building Dropz Universal Agent with Python:
python --version

echo Installing desktop requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements_desktop.txt

echo Cleaning old build output...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del DropzUniversalAgent-Windows.zip 2>nul

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
  --collect-all streamlit_autorefresh ^
  --collect-all streamlit_option_menu ^
  --collect-all streamlit_extras ^
  --collect-all streamlit_js_eval ^
  --collect-all streamlit_chat ^
  --collect-all streamlit_float ^
  --hidden-import streamlit_autorefresh ^
  --hidden-import streamlit_option_menu ^
  --hidden-import streamlit_extras ^
  --hidden-import streamlit_js_eval ^
  --hidden-import streamlit_chat ^
  --hidden-import streamlit_float ^
  --hidden-import components ^
  --hidden-import chat_backend ^
  --hidden-import backend ^
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
  --add-data "version_manifest.json;." ^
  --add-data "update_manifest_url.txt;." ^
  desktop_launcher.py

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo Building updater...

python -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onedir ^
  --name DropzUpdater ^
  --icon assets\dropz_icon.ico ^
  dropz_updater.py

if exist "dist\DropzUpdater\DropzUpdater.exe" (
  copy /Y "dist\DropzUpdater\DropzUpdater.exe" "dist\DropzUniversalAgent\DropzUpdater.exe"
)

echo Creating ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '.\dist\DropzUniversalAgent\*' -DestinationPath '.\DropzUniversalAgent-Windows.zip' -Force"

echo.
echo Build complete:
echo dist\DropzUniversalAgent\DropzUniversalAgent.exe
echo DropzUniversalAgent-Windows.zip
pause
