@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set APP_VERSION=1.0.1
set APP_NAME=DropzUniversalAgent
set GITHUB_OWNER=Zayaiken21
set GITHUB_REPO=DropzUniversalAgent

for /f %%i in ('powershell -NoProfile -Command "Get-Date -AsUTC -Format yyyyMMddHHmmss"') do set BUILD_ID=%%i
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -AsUTC -Format o"`) do set BUILD_TIME_UTC=%%i

echo Building %APP_NAME% version %APP_VERSION% build %BUILD_ID%
echo Python:
python --version

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

echo Writing build_info.json...
python -c "import json,os; info={'version':os.environ.get('APP_VERSION','%APP_VERSION%'),'build_id':os.environ.get('BUILD_ID','%BUILD_ID%'),'build_time_utc':os.environ.get('BUILD_TIME_UTC','%BUILD_TIME_UTC%'),'github_owner':'%GITHUB_OWNER%','github_repo':'%GITHUB_REPO%','asset_name':'%APP_NAME%-Windows.zip'}; open('build_info.json','w',encoding='utf-8').write(json.dumps(info,indent=2))"

echo Cleaning old build output...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q %APP_NAME%-Windows.zip 2>nul

echo Building updater...
python -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --name DropzUpdater ^
  --icon assets\dropz_icon.ico ^
  dropz_updater.py

if errorlevel 1 (
  echo Updater build failed.
  pause
  exit /b 1
)

echo Building Dropz Universal Agent desktop app...

set EXTRA_CHAT_DATA=
if exist chat_agent.py set EXTRA_CHAT_DATA=--add-data "chat_agent.py;."

python -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onedir ^
  --name %APP_NAME% ^
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
  --collect-all certifi ^
  --collect-all urllib3 ^
  --collect-all charset_normalizer ^
  --collect-all idna ^
  --collect-all dotenv ^
  --collect-all cryptography ^
  --collect-all cffi ^
  --collect-all MetaTrader5 ^
  --collect-all streamlit_option_menu ^
  --collect-all streamlit_extras ^
  --collect-all streamlit_autorefresh ^
  --collect-all streamlit_webrtc ^
  --collect-all streamlit_js_eval ^
  --collect-all streamlit_chat ^
  --collect-all streamlit_float ^
  --hidden-import chat_agent ^
  --hidden-import chat_backend ^
  --hidden-import chat_backend.chat_db ^
  --hidden-import components ^
  --hidden-import components.charts ^
  --hidden-import components.dashboard_mt5_data ^
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
  --add-data "build_info.json;." ^
  %EXTRA_CHAT_DATA% ^
  desktop_launcher.py

if errorlevel 1 (
  echo App build failed.
  pause
  exit /b 1
)

echo Copying updater into app folder...
copy /Y "dist\DropzUpdater.exe" "dist\%APP_NAME%\DropzUpdater.exe" >nul

echo Writing version/build files...
echo %APP_VERSION%> "dist\%APP_NAME%\version.txt"
copy /Y "build_info.json" "dist\%APP_NAME%\build_info.json" >nul
if exist "dist\%APP_NAME%\_internal" copy /Y "build_info.json" "dist\%APP_NAME%\_internal\build_info.json" >nul

echo Creating ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '.\dist\%APP_NAME%\*' -DestinationPath '.\%APP_NAME%-Windows.zip' -Force"

echo.
echo Build complete:
echo dist\%APP_NAME%\%APP_NAME%.exe
echo ZIP ready:
echo %APP_NAME%-Windows.zip
echo.
echo Upload %APP_NAME%-Windows.zip to GitHub Releases.
echo Advanced updater checks GitHub release asset ID/update time/size and can detect changed ZIP assets even with the same tag/version after the first baseline check.
pause
