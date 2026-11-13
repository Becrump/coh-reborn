@echo off
rem Measures how the game runs at each graphics preset: one copy of the game, nothing else.
rem
rem   bench_lowend.cmd                 Low, Medium, High and Epic on Atlas Park at 1920x1080
rem   bench_lowend.cmd low             one preset (low / medium / high / epic)
rem   bench_lowend.cmd all city        the one-world map (L_ParagonCity) instead of Atlas Park
rem   bench_lowend.cmd lowend          the low-end target: Low at 1280x720, 67%% render scale
rem
rem Each run waits 20 s for the city to stream in, then turns the camera a full circle
rem for 60 s and quits. Results are appended, one line per run, to bench_results.txt next
rem to this file: average FPS, 1%% low, GPU ms, video memory (now / peak / card size) and RAM.
rem Logs: bench_<preset>.log. Memory detail: <project>\Saved\Profiling\MemReports.
rem
rem The Unreal editor and any other game copies must be closed: they share the graphics
rem card's memory, which is what this measures. The script stops if one is running.
rem Your own graphics settings are backed up first and put back afterwards.
rem Overrides: UE_ROOT, COH_PROJECT, COH_MAP, COH_RES (e.g. 2560x1440), COH_SECONDS.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if not defined COH_PROJECT set "COH_PROJECT=%USERPROFILE%\OneDrive\Documents\Unreal Projects\COHREBORN"
if not defined UE_ROOT (
  for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\EpicGames\Unreal Engine\5.8" /v InstalledDirectory 2^>nul ^| find "InstalledDirectory"') do set "UE_ROOT=%%b"
)
if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
set "EXE=%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe"
set "UPROJECT=%COH_PROJECT%\COHREBORN.uproject"
set "OUT=%~dp0bench_results.txt"
if not defined COH_SECONDS set "COH_SECONDS=60"
if not defined COH_RES set "COH_RES=1920x1080"

set "WHICH=%~1"
if "%WHICH%"=="" set "WHICH=all"
set "MAPKEY=%~2"
if /i "%WHICH%"=="city" ( set "WHICH=all" & set "MAPKEY=city" )
if not defined COH_MAP (
  if /i "%MAPKEY%"=="city" ( set "COH_MAP=/Game/Zones/L_ParagonCity" ) else ( set "COH_MAP=/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite" )
)

tasklist /fi "imagename eq UnrealEditor.exe" 2>nul | find /i "UnrealEditor.exe" >nul
if not errorlevel 1 (
  echo The Unreal editor or a game copy is running. Close it first: it uses the same video memory.
  echo %date% %time% SKIPPED: UnrealEditor.exe running>> "%OUT%"
  exit /b 2
)

rem back up the player's settings (the test presets are not meant to stick)
set "BK=%~dp0bench_settings_backup"
if exist "%BK%" rd /s /q "%BK%"
mkdir "%BK%"
for /d %%d in ("%COH_PROJECT%\Saved\Config\Windows*") do (
  if exist "%%d\GameUserSettings.ini" ( mkdir "%BK%\%%~nxd" & copy /y "%%d\GameUserSettings.ini" "%BK%\%%~nxd\" >nul )
)

if /i "%WHICH%"=="all" (
  for %%q in (low medium high epic) do call :run %%q
) else (
  call :run %WHICH%
)

rem put the player's settings back
for /d %%d in ("%BK%\*") do copy /y "%%d\GameUserSettings.ini" "%COH_PROJECT%\Saved\Config\%%~nxd\GameUserSettings.ini" >nul
echo.
echo Done. Results:
type "%OUT%"
exit /b 0

:run
set "Q=" & set "RES=%COH_RES%" & set "EXTRA="
if /i "%~1"=="low" set "Q=0"
if /i "%~1"=="medium" set "Q=1"
if /i "%~1"=="high" set "Q=2"
if /i "%~1"=="epic" set "Q=3"
if /i "%~1"=="lowend" ( set "Q=0" & set "RES=1280x720" & set "EXTRA=-ExecCmds="r.ScreenPercentage 67"" )
if not defined Q ( echo Unknown preset %~1 & exit /b 1 )
for /f "tokens=1,2 delims=x" %%a in ("%RES%") do ( set "RX=%%a" & set "RY=%%b" )
echo %date% %time% running %~1 on %COH_MAP% at %RES% ...
echo --- %~1 at %RES% --->> "%OUT%"
start "CoH bench %~1" /wait "%EXE%" "%UPROJECT%" "%COH_MAP%" -game -windowed -ResX=%RX% -ResY=%RY% -WinX=0 -WinY=0 -NOSTEAM -nosplash -log -Hero=Bench -cohquality=%Q% -cohbench=%COH_SECONDS% -cohbenchout="%OUT%" %EXTRA% -abslog="%~dp0bench_%~1.log"
exit /b 0
