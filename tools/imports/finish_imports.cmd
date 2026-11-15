@echo off
rem Finishes importing the original game's content (enemies of every zone,
rem contacts, story arcs, missions, dialog, badges, enhancements, inventions,
rem stores, hero presets and contact models), unattended. Safe to stop and
rem re-run: finished stages and already imported models are skipped.
rem
rem   finish_imports.cmd            convert, then import into the open editor
rem   finish_imports.cmd convert    convert only (no editor needed, ~15 min)
rem   finish_imports.cmd unreal     Unreal import only (needs the editor open)
rem
rem The Unreal part needs exactly ONE Unreal editor open on COHREBORN with
rem Python Remote Execution on, and no other Claude thread using it.
rem Log: C:\Users\rtcru\CoHReborn\out\finish_imports_log.txt
title CoH Reborn: finish imports
cd /d "%~dp0..\.."
set "MODE="
if /i "%~1"=="convert" set "MODE=--convert-only"
if /i "%~1"=="unreal" set "MODE=--unreal-only"
python tools\imports\finish_imports.py %MODE%
echo.
echo Finished. See C:\Users\rtcru\CoHReborn\out\finish_imports_log.txt
