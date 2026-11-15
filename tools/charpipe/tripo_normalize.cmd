@echo off
rem One-click: normalise every Tripo GLB/FBX/OBJ in charpipe_test\tripo\in to MetaHuman-ready FBX (cm, feet at origin, +Y facing).
rem Optional: tripo_normalize.cmd <height_cm>   (default 182; file names with kid/average/heavy/big/veteran pick their own)
setlocal
set "BLENDER=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
set "IN=C:\Users\rtcru\charpipe_test\tripo\in"
set "OUT=C:\Users\rtcru\charpipe_test\tripo\mh_ready"
set "H=%~1"
if "%H%"=="" set "H=182"
if not exist "%IN%" mkdir "%IN%"
if not exist "%OUT%" mkdir "%OUT%"
"%BLENDER%" -b --factory-startup -P "%~dp0bl_tripo_normalize.py" -- "%IN%" "%OUT%" --height %H% > "%OUT%\blender_out.txt" 2>&1
echo.
type "%OUT%\normalize_log.txt"
echo.
echo Output: %OUT%
pause
