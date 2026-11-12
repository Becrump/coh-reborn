@echo off
rem Imports every remaining converted zone into the open Unreal editor, unattended.
rem Needs: exactly one Unreal editor open on COHREBORN, nothing else using it.
rem Safe to stop and re-run: finished zones are skipped, an unfinished zone resumes.
rem One line per zone goes to import_log.txt next to this file.
title CoH zone import
cd /d "%~dp0"
for /l %%p in (1,1,3) do (
  echo === pass %%p ===
  python "C:\Users\rtcru\ClaudeProjects\coh-reborn-zones\tools\zones\import_zones.py" >> import_console.txt 2>&1
)
echo Finished. See import_log.txt
