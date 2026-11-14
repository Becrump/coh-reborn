@echo off
rem One-world fixes for every imported connected zone, then L_ParagonCity:
rem per-zone sky removed, Far/Ground runtime grids, trees re-planted as 256 m chunks (500 m cull),
rem one day/night sky + a PlayerStart in L_ParagonCity. Unattended, resumable; log: import_log.txt.
title CoH zone fix
cd /d "%~dp0"
for /l %%p in (1,1,2) do (
  python "C:\Users\rtcru\ClaudeProjects\coh-reborn-zfix\tools\zones\import_zones.py" --fix >> fix_console.txt 2>&1
)
echo Finished. See import_log.txt
