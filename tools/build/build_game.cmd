@echo off
rem Builds the COHREBORN editor module (all game C++) unattended, with a log.
rem
rem   build_game.cmd                 build the project as it is on this PC
rem   build_game.cmd sync <repo>     back up Source + game config, copy them from a
rem                                  coh-reborn checkout (e.g. after "git pull"), then build
rem
rem Output next to this file:
rem   build_log.txt      full UnrealBuildTool output
rem   build_errors.txt   only the error lines (empty when the build is clean)
rem   build_status.txt   one line: BUILD OK / BUILD FAILED / EDITOR OPEN, with the time
rem
rem The Unreal editor must be closed: it holds the game DLL open. The editor is shared
rem by several Claude threads, so this script never closes it; it stops and says so.
rem Overrides: set UE_ROOT=<engine folder> and/or COH_PROJECT=<folder with COHREBORN.uproject>.
setlocal EnableExtensions EnableDelayedExpansion
title CoH Reborn build
cd /d "%~dp0"
set "HERE=%~dp0"
set "LOG=%HERE%build_log.txt"
set "ERR=%HERE%build_errors.txt"
set "STATUS=%HERE%build_status.txt"

if not defined COH_PROJECT set "COH_PROJECT=%USERPROFILE%\OneDrive\Documents\Unreal Projects\COHREBORN"
set "UPROJECT=%COH_PROJECT%\COHREBORN.uproject"
if not exist "%UPROJECT%" (
  echo %date% %time% NO PROJECT at "%UPROJECT%" > "%STATUS%"
  type "%STATUS%"
  exit /b 3
)

rem ---- find the engine (5.8: the project's EngineAssociation)
if not defined UE_ROOT (
  for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\EpicGames\Unreal Engine\5.8" /v InstalledDirectory 2^>nul ^| find "InstalledDirectory"') do set "UE_ROOT=%%b"
)
if not defined UE_ROOT if exist "C:\Program Files\Epic Games\UE_5.8" set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
if not exist "%UE_ROOT%\Engine\Build\BatchFiles\Build.bat" (
  echo %date% %time% NO ENGINE: set UE_ROOT to the UE 5.8 folder > "%STATUS%"
  type "%STATUS%"
  exit /b 4
)

rem ---- the editor must be closed (never close it from here: other threads may be using it)
tasklist /fi "imagename eq UnrealEditor.exe" 2>nul | find /i "UnrealEditor.exe" >nul
if not errorlevel 1 (
  echo %date% %time% EDITOR OPEN: close the Unreal editor, then run this again > "%STATUS%"
  type "%STATUS%"
  exit /b 2
)

rem ---- optional: back up, then copy Source + game config from a repo checkout
if /i "%~1"=="sync" (
  set "REPO=%~2"
  if not exist "!REPO!\unreal\project\Source\COHREBORN" (
    echo %date% %time% NO REPO at "!REPO!" > "%STATUS%"
    type "%STATUS%"
    exit /b 5
  )
  for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%t"
  set "BACKUP=%COH_PROJECT%\..\COHREBORN_backups\build_!STAMP!"
  echo Backing up Source and Config to "!BACKUP!"
  robocopy "%COH_PROJECT%\Source" "!BACKUP!\Source" /E /NFL /NDL /NJH /NJS >nul
  robocopy "%COH_PROJECT%\Config" "!BACKUP!\Config" /E /NFL /NDL /NJH /NJS >nul
  copy /y "%UPROJECT%" "!BACKUP!\" >nul
  echo Copying Source from "!REPO!"
  rem no /PURGE: local .bak files and anything only on this PC stay
  robocopy "!REPO!\unreal\project\Source" "%COH_PROJECT%\Source" /E /NFL /NDL /NJH /NJS >nul
  copy /y "!REPO!\unreal\project\Config\DefaultGame.ini" "%COH_PROJECT%\Config\DefaultGame.ini" >nul
  copy /y "!REPO!\unreal\project\Config\DefaultEngine.ini" "%COH_PROJECT%\Config\DefaultEngine.ini" >nul
  if exist "!REPO!\unreal\project\Config\DefaultScalability.ini" copy /y "!REPO!\unreal\project\Config\DefaultScalability.ini" "%COH_PROJECT%\Config\DefaultScalability.ini" >nul
  rem the HQ lobby backdrop (read at runtime, not an asset)
  robocopy "!REPO!\unreal\project\Content\Frontend" "%COH_PROJECT%\Content\Frontend" /E /NFL /NDL /NJH /NJS >nul
)

rem ---- build
echo %date% %time% building, log: "%LOG%"
echo %date% %time% BUILDING > "%STATUS%"
call "%UE_ROOT%\Engine\Build\BatchFiles\Build.bat" COHREBORNEditor Win64 Development -Project="%UPROJECT%" -WaitMutex > "%LOG%" 2>&1
set "RC=%errorlevel%"
findstr /i /r /c:": error" /c:": fatal error" /c:"error C[0-9]" /c:"error LNK" /c:"ERROR:" "%LOG%" > "%ERR%"
if "%RC%"=="0" (
  echo %date% %time% BUILD OK > "%STATUS%"
) else (
  for /f %%n in ('type "%ERR%" ^| find /c /v ""') do set "NERR=%%n"
  echo %date% %time% BUILD FAILED ^(exit %RC%, !NERR! error lines, see build_errors.txt^) > "%STATUS%"
)
type "%STATUS%"
exit /b %RC%
