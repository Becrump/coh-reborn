@echo off
rem Splits every imported connected zone's instance actors into 256 m streaming chunks and
rem culls small clutter at 150 m. Unattended, resumable; one line per zone in import_log.txt.
title CoH zone split
cd /d "%~dp0"
for /l %%p in (1,1,2) do (
  python "C:\Users\rtcru\ClaudeProjects\coh-reborn-zones\tools\zones\import_zones.py" --split >> split_console.txt 2>&1
)
echo Finished. See import_log.txt
