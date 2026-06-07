@echo off
setlocal
cd /d "%~dp0"

echo Building Dropz Universal Agent with Python:
python --version

echo Installing desktop requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements_desktop.txt
python -m pip install --upgrade cryptography cffi pycparser

echo Verifying critical packages...
python -c "import cryptography, cffi, streamlit, plotly, streamlit_autorefresh; print('Critical packages OK')"
if errorlevel 1 (
  echo Required package check failed.
  pause
  exit /b 1
)

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
  --collect-all cryptography ^
  --collect-all cffi ^
  --collect-all streamlit_autorefresh ^
  --collect-all streamlit_option_menu ^
  --collect-all streamlit_extras ^
  --collect-all streamlit_js_eval ^
  --collect-all streamlit_chat ^
  --collect-all streamlit_float ^
  --collect-all streamlit_webrtc ^
  --hidden-import cryptography ^
  --hidden-import cryptography.fernet ^
  --hidden-import cryptography.hazmat.bindings._rust ^
  --hidden-import cryptography.hazmat.primitives ^
  --hidden-import cryptography.hazmat.primitives.hashes ^
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --hidden-import cryptography.hazmat.primitives.ciphers ^
  --hidden-import cryptography.hazmat.primitives.padding ^
  --hidden-import cffi ^
  --hidden-import _cffi_backend ^
  --hidden-import streamlit_autorefresh ^
  --hidden-import streamlit_option_menu ^
  --hidden-import streamlit_extras ^
  --hidden-import streamlit_js_eval ^
  --hidden-import streamlit_chat ^
  --hidden-import streamlit_float ^
  --hidden-import streamlit_webrtc ^
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
  --collect-all cryptography ^
  --collect-all cffi ^
  --hidden-import cryptography ^
  --hidden-import cryptography.fernet ^
  --hidden-import cffi ^
  --hidden-import _cffi_backend ^
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
