@echo off
rem Bench for AI talking: downloads llama.cpp + two small models once, then times the mock conversations.
rem Options are passed through, e.g.  bench_talk.cmd -Models 4b -Threads 4   or   bench_talk.cmd -Load 300
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bench_talk.ps1" %*
