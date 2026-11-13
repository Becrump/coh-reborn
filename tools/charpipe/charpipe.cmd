@echo off
rem charpipe: reference images -> rigged, CoH-animatable character (see docs\character-pipeline.md)
rem   tools\charpipe\charpipe.cmd <in_dir> <out_dir> [--only NAME] [--parts] [--wait] [--redo STEP] [--height 1.8]
python "%~dp0charpipe.py" %*
