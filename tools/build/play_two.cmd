@echo off
rem Starts two copies of the game on this PC for a multiplayer test (no packaging needed).
rem
rem   play_two.cmd           both copies open in the HQ lobby: host in one, join 127.0.0.1 in the other
rem   play_two.cmd direct    skip the lobby: copy A hosts Atlas Park, copy B joins it straight away
rem
rem Each copy writes its own log next to this file: play_A.log and play_B.log.
rem Close the Unreal editor first only if the build is out of date (run build_game.cmd).
rem Overrides: UE_ROOT, COH_PROJECT, COH_MAP.
setlocal EnableExtensions
cd /d "%~dp0"
if not defined COH_PROJECT set "COH_PROJECT=%USERPROFILE%\OneDrive\Documents\Unreal Projects\COHREBORN"
if not defined COH_MAP set "COH_MAP=/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
if not defined UE_ROOT (
  for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\EpicGames\Unreal Engine\5.8" /v InstalledDirectory 2^>nul ^| find "InstalledDirectory"') do set "UE_ROOT=%%b"
)
if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
set "EXE=%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe"
set "UPROJECT=%COH_PROJECT%\COHREBORN.uproject"
set "COMMON=-game -windowed -ResX=1280 -ResY=720 -log -NOSTEAM -nosplash"

if /i "%~1"=="direct" (
  start "CoH A (host)" "%EXE%" "%UPROJECT%" "%COH_MAP%?listen" %COMMON% -WinX=0 -WinY=40 -Hero=TestA -abslog="%~dp0play_A.log"
  rem give the host time to load the zone before the client knocks
  timeout /t 45 /nobreak >nul
  start "CoH B (client)" "%EXE%" "%UPROJECT%" 127.0.0.1 %COMMON% -WinX=1290 -WinY=40 -Hero=TestB -abslog="%~dp0play_B.log"
) else (
  start "CoH A" "%EXE%" "%UPROJECT%" %COMMON% -WinX=0 -WinY=40 -abslog="%~dp0play_A.log"
  start "CoH B" "%EXE%" "%UPROJECT%" %COMMON% -WinX=1290 -WinY=40 -abslog="%~dp0play_B.log"
)
echo Started. Logs: play_A.log, play_B.log
