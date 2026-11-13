@echo off
rem Builds Hunyuan3D-2's custom_rasterizer for the RTX 3070 (sm_86) with the portable CUDA 12.6
rem from setup_cuda.sh and the VS 2022 Build Tools (v14.29 toolset, supported by CUDA 12.6).
rem   C:\Users\rtcru\hy3d\build_rasterizer.cmd  > build_rasterizer.log 2>&1
setlocal
set ROOT=C:\Users\rtcru\hy3d
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" -vcvars_ver=14.29 || exit /b 1
set CUDA_HOME=%ROOT%\cuda126
set CUDA_PATH=%ROOT%\cuda126
set PATH=%CUDA_HOME%\bin;%ROOT%\venv\Scripts;%PATH%
set TORCH_CUDA_ARCH_LIST=8.6
set DISTUTILS_USE_SDK=1
set MAX_JOBS=4
"%ROOT%\venv\Scripts\python.exe" -m pip uninstall -y custom_rasterizer
cd /d "%ROOT%\Hunyuan3D-2\hy3dgen\texgen\custom_rasterizer"
"%ROOT%\venv\Scripts\python.exe" -m pip install --no-build-isolation --no-deps . || exit /b 1
"%ROOT%\venv\Scripts\python.exe" -c "import torch, custom_rasterizer, custom_rasterizer_kernel; print('rasterizer import ok', torch.__version__)" || exit /b 1
echo BUILD OK
