@echo off
rem Unattended Mixamo bulk download (resumable). Needs %USERPROFILE%\.mixamo_token - see mixamo_bulk.py header.
python "%~dp0mixamo_bulk.py" %*
echo exit code %ERRORLEVEL%  (0 = finished, 2 = no token, 3 = stopped: token expired or too many errors - re-run to resume)
