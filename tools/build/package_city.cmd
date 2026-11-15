@echo off
rem Packages (cooks) a Development build of the game with the one-world map, unattended.
rem
rem   package_city.cmd                 cook + stage + pak/IoStore to C:\CoHBuilds\city
rem   package_city.cmd fly             also run the fly-through on the packaged game afterwards
rem   package_city.cmd flyonly [dir]   only run the packaged fly-through (dir defaults to the C: build;
rem                                    pass e.g. G:\CoHBuilds\city to test the slow SSD)
rem
rem Maps cooked: the entry map, the front end and L_ParagonCity (with all 18 zone levels it references).
rem Output: build_city_log.txt next to this file, package_status.txt with one PACKAGE OK / FAILED line.
rem The Unreal editor should be closed (cooking needs the RAM and the shader compilers); this script
rem never closes it and stops if it is open. Overrides: UE_ROOT, COH_PROJECT, COH_OUT.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if not defined COH_PROJECT set "COH_PROJECT=%USERPROFILE%\OneDrive\Documents\Unreal Projects\COHREBORN"
if not defined UE_ROOT (
  for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\EpicGames\Unreal Engine\5.8" /v InstalledDirectory 2^>nul ^| %SystemRoot%\System32\find.exe "InstalledDirectory"') do set "UE_ROOT=%%b"
)
if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
if not defined COH_OUT set "COH_OUT=C:\CoHBuilds\city"
set "UPROJECT=%COH_PROJECT%\COHREBORN.uproject"
set "LOG=%~dp0build_city_log.txt"
set "STATUS=%~dp0package_status.txt"
set "RESULTS=%~dp0bench_results.txt"
if not defined COH_MAP set "COH_MAP=/Game/Zones/L_ParagonCity"
if not defined COH_PATH set "COH_PATH=%~dp0flythrough_city.txt"
set "PATHFILE=%COH_PATH%"

if /i "%~1"=="flyonly" goto fly

tasklist /fi "imagename eq UnrealEditor.exe" 2>nul | %SystemRoot%\System32\find.exe /i "UnrealEditor.exe" >nul
if not errorlevel 1 (
  echo %date% %time% EDITOR OPEN: close every Unreal editor and game copy, then run this again > "%STATUS%"
  type "%STATUS%"
  exit /b 2
)

rem ---- wait while the character thread's Hunyuan3D GPU jobs (python from C:\Users\rtcru\hy3d) run
:waithy3d
powershell -NoProfile -c "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -match 'hy3d' -or $_.ExecutablePath -match 'hy3d' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo %date% %time% waiting for the hy3d GPU jobs to finish ...
  ping -n 181 127.0.0.1 >nul
  goto waithy3d
)

echo %date% %time% packaging to %COH_OUT% (log: %LOG%)
set "T0=%time%"
call "%UE_ROOT%\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -project="%UPROJECT%" -noP4 -utf8output ^
  -platform=Win64 -clientconfig=Development -build -cook -stage -pak -iostore -compressed -prereqs ^
  -map=/Engine/Maps/Entry+%COH_MAP% ^
  -archive -archivedirectory="%COH_OUT%" -nocompileeditor > "%LOG%" 2>&1
if errorlevel 1 (
  echo %date% %time% PACKAGE FAILED, see build_city_log.txt > "%STATUS%"
  findstr /i /c:"error" "%LOG%" > "%~dp0package_errors.txt"
  type "%STATUS%"
  exit /b 1
)
echo %date% %time% PACKAGE OK (started %T0%) to %COH_OUT% > "%STATUS%"
type "%STATUS%"
if /i not "%~1"=="fly" exit /b 0

:fly
rem ---- clean numbers: wait until the character thread's hy3d GPU jobs are done
:waitflyhy3d
powershell -NoProfile -c "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -match 'hy3d' -or $_.ExecutablePath -match 'hy3d' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo %date% %time% fly-through waiting for the hy3d GPU jobs ...
  ping -n 121 127.0.0.1 >nul
  goto waitflyhy3d
)
set "HOLD=C:\Users\rtcru\ClaudeProjects\COHReborn\CPU_HOLD.txt"
echo packaged fly-through %date% %time% - pause Blender renders until this file is gone> "%HOLD%"
set "GAMEDIR=%COH_OUT%"
if /i "%~1"=="flyonly" if not "%~2"=="" set "GAMEDIR=%~2"
set "EXE="
for /f "delims=" %%e in ('dir /s /b "%GAMEDIR%\COHREBORN.exe" 2^>nul') do if not defined EXE set "EXE=%%e"
if not defined EXE ( del "%HOLD%" 2>nul & echo no COHREBORN.exe under %GAMEDIR% & exit /b 3 )
if not exist "%PATHFILE%" python "%~dp0..\zones\flythrough_path.py" "%PATHFILE%"
echo Flying the packaged game from %GAMEDIR% ...
start "CoH packaged flythrough" /wait "%EXE%" %COH_MAP% -windowed -ResX=1920 -ResY=1080 -WinX=0 -WinY=0 -NOSTEAM -nosplash -log -Hero=Bench -cohquality=2 -cohflythrough="%PATHFILE%" -cohflyspeed=3000 -cohflyout="%RESULTS%" -abslog="%~dp0flythrough_packaged.log"
del "%HOLD%" 2>nul
findstr /c:"FLYTHROUGH" "%RESULTS%"
endlocal
