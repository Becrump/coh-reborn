@echo off
rem Finishes the one playable city unattended, step by step, logging to city_chain_log.txt:
rem   0. waits until no Unreal editor runs and no CPU_HOLD.txt / GPU_HOLD.txt exists (other threads)
rem   1. world step 4 (headless): Galaxy-Kings Row road, zone-gate arrival starts
rem   2. build_game.cmd sync from this checkout (per-zone encounters, gate arrivals)
rem   3. package L_ParagonCity (all 19 zones) to C:\CoHBuilds\city + fly-through from C:
rem   4. copy to G:\CoHBuilds\city + fly-through from G: (slow SSD)
rem   5. playtest flight: Atlas plaza -> Galaxy -> Kings Row -> Skyway at 20 m, 30 m/s; encounter spawns per zone
rem A failing step is logged and the chain stops. Re-run to resume from the top (each step is safe to repeat).
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "REPO=%~dp0..\.."
for %%r in ("%REPO%") do set "REPO=%%~fr"
set "LOG=%~dp0city_chain_log.txt"
set "HOLDDIR=C:\Users\rtcru\ClaudeProjects\COHReborn"
set "UE=C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64"
if not defined COH_PROJECT set "COH_PROJECT=C:\UnrealProjects\COHREBORN"
set "UPROJECT=%COH_PROJECT%\COHREBORN.uproject"
echo %date% %time% chain started >> "%LOG%"

:wait
set "BUSY="
tasklist /fi "imagename eq UnrealEditor.exe" 2>nul | %SystemRoot%\System32\find.exe /i "UnrealEditor.exe" >nul && set "BUSY=editor"
tasklist /fi "imagename eq UnrealEditor-Cmd.exe" 2>nul | %SystemRoot%\System32\find.exe /i "UnrealEditor-Cmd.exe" >nul && set "BUSY=commandlet"
if exist "%HOLDDIR%\CPU_HOLD.txt" set "BUSY=CPU_HOLD"
if exist "%HOLDDIR%\GPU_HOLD.txt" set "BUSY=GPU_HOLD"
if defined BUSY (
  ping -n 121 127.0.0.1 >nul
  goto wait
)
echo %date% %time% editor free, no holds: starting >> "%LOG%"

rem ---- 1. world step 4
set "CITY_REPO=%REPO%"
"%UE%\UnrealEditor-Cmd.exe" "%UPROJECT%" -run=pythonscript -script="%REPO%\coh2unreal\unreal\world_step4.py" -unattended -nullrhi -nosplash -abslog="%~dp0world_step4.log"
findstr /l /c:"[city4] saved" "%~dp0world_step4.log" >nul || ( echo %date% %time% STEP 1 FAILED world_step4, see world_step4.log >> "%LOG%" & exit /b 1 )
for /f "delims=" %%l in ('findstr /l /c:"[city4]" "%~dp0world_step4.log"') do echo     %%l >> "%LOG%"
echo %date% %time% step 1 OK >> "%LOG%"

rem ---- 2. build
call "%~dp0build_game.cmd" sync "%REPO%"
type "%~dp0build_status.txt" >> "%LOG%"
findstr /c:"BUILD OK" "%~dp0build_status.txt" >nul || ( echo %date% %time% STEP 2 FAILED build, see build_errors.txt >> "%LOG%" & exit /b 2 )

rem ---- 3. package + fly from C:
set "COH_MAP=/Game/Zones/L_ParagonCity"
set "COH_PATH=%~dp0flythrough_city.txt"
call "%~dp0package_city.cmd" fly
type "%~dp0package_status.txt" >> "%LOG%"
findstr /c:"PACKAGE OK" "%~dp0package_status.txt" >nul || ( echo %date% %time% STEP 3 FAILED package, see build_city_log.txt >> "%LOG%" & exit /b 3 )
copy /y "%~dp0flythrough_packaged.log" "%~dp0flythrough_packaged_C.log" >nul

rem ---- 4. G: copy + fly
robocopy "C:\CoHBuilds\city" "G:\CoHBuilds\city" /MIR /MT:8 /R:1 /W:1 /NFL /NDL /NP /NJH >nul
call "%~dp0package_city.cmd" flyonly "G:\CoHBuilds\city"
copy /y "%~dp0flythrough_packaged.log" "%~dp0flythrough_packaged_G.log" >nul

rem ---- 5. playtest flight
set "COH_PATH=%~dp0playtest_city.txt"
call "%~dp0package_city.cmd" flyonly "C:\CoHBuilds\city"
copy /y "%~dp0flythrough_packaged.log" "%~dp0playtest_city.log" >nul
findstr /c:"CoH encounters" /c:"CoH start" "%~dp0playtest_city.log" > "%~dp0playtest_encounters.txt"
echo %date% %time% playtest encounter lines: >> "%LOG%"
type "%~dp0playtest_encounters.txt" >> "%LOG%"
findstr /c:"FLYTHROUGH" "%~dp0bench_results.txt" >> "%LOG%"
echo %date% %time% chain finished >> "%LOG%"
endlocal
