@echo off
rem Converts every remaining Paragon City zone, no Claude needed.
rem Double-click it. Safe to stop and re-run: finished zones are skipped,
rem so a re-run only retries failures. Results: zones\, convert_log.txt.
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is not installed or not on PATH. Install it from python.org, tick "Add to PATH", then run this again. & pause & exit /b 1)
where git >nul 2>nul || (echo Git is not installed or not on PATH. Install Git for Windows, then run this again. & pause & exit /b 1)
python -c "import PIL" 2>nul || python -m pip install --quiet pillow
if exist converter_kit.zip (
  powershell -NoProfile -Command "Expand-Archive -Force converter_kit.zip kit"
)
echo Converting zones. This takes about 1-3 minutes per zone, plus a one-time
echo download of the game data (about 3 GB). The log is convert_log.txt.
python kit\tools\zones\convert_all_zones.py --work "%~dp0." %*
echo.
type convert_log.txt
echo.
echo Finished. Lines starting with FAIL above need a look; everything else is ready to import.
pause
