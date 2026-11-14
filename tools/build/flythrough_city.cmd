@echo off
rem Flies across the zone borders of the one-world map (L_ParagonCity) and measures streaming.
rem
rem   flythrough_city.cmd              High preset, 1920x1080, 30 m/s along flythrough_city.txt
rem   flythrough_city.cmd low          another preset (low / medium / high / epic)
rem
rem Route (tools/zones/flythrough_path.py writes it from docs/zones/zone_offsets.json):
rem Atlas Park side, Galaxy City, Perez Park, Kings Row, Steel Canyon, Skyway City, Talos Island,
rem 60 m up, through each zone's centre. Waits 20 s for the start to stream in, then flies.
rem Results: one FLYTHROUGH line in bench_results.txt next to this file (FPS, 1%% low, worst
rem frame, hitches over 50 ms, how often streaming was behind, VRAM and RAM peaks); every
rem frame in <project>\Saved\Logs\coh_flythrough.csv, hitches in coh_flythrough_hitches.txt.
rem
rem The Unreal editor and other game copies must be closed (they share RAM and video memory);
rem this script never closes them. Overrides: UE_ROOT, COH_PROJECT, COH_RES, COH_SPEED (cm/s).
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
set "PATHFILE=%~dp0flythrough_city.txt"
if not defined COH_RES set "COH_RES=1920x1080"
if not defined COH_SPEED set "COH_SPEED=3000"
for /f "tokens=1,2 delims=x" %%a in ("%COH_RES%") do ( set "RX=%%a" & set "RY=%%b" )

set "Q=2"
if /i "%~1"=="low" set "Q=0"
if /i "%~1"=="medium" set "Q=1"
if /i "%~1"=="high" set "Q=2"
if /i "%~1"=="epic" set "Q=3"

rem ---- the editor and other game copies must be closed (never close them from here)
tasklist /fi "imagename eq UnrealEditor.exe" 2>nul | find /i "UnrealEditor.exe" >nul
if not errorlevel 1 (
  echo %date% %time% EDITOR OR GAME OPEN: close every Unreal editor and game copy, then run this again
  exit /b 2
)
if not exist "%PATHFILE%" (
  python "%~dp0..\zones\flythrough_path.py" "%PATHFILE%" || ( echo could not write %PATHFILE% & exit /b 3 )
)

echo Flying L_ParagonCity at preset %Q%, %COH_RES%, %COH_SPEED% cm/s ...
start "CoH flythrough" /wait "%EXE%" "%UPROJECT%" "/Game/Zones/L_ParagonCity" -game -windowed -ResX=%RX% -ResY=%RY% -WinX=0 -WinY=0 -NOSTEAM -nosplash -log -Hero=Bench -cohquality=%Q% -cohflythrough="%PATHFILE%" -cohflyspeed=%COH_SPEED% -cohflyout="%OUT%" -abslog="%~dp0flythrough_city.log"
findstr /c:"FLYTHROUGH" "%OUT%" | more +0 > "%TEMP%\coh_fly_last.txt"
for /f "delims=" %%l in (%TEMP%\coh_fly_last.txt) do set "LAST=%%l"
if defined LAST ( echo !LAST! ) else ( echo No FLYTHROUGH line written: see flythrough_city.log & exit /b 1 )
endlocal
