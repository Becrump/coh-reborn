@echo off
rem Watch C:\Users\rtcru\charpipe_test\tripo\in and rig every new Tripo download (see tripo_watch.py).
rem   tripo_watch.cmd          keep watching (close the window to stop)
rem   tripo_watch.cmd --once   process what is there now and exit
title Tripo watch - charpipe
python "%~dp0tripo_watch.py" %*
pause
