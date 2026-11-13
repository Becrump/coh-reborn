#!/usr/bin/env bash
# Rerunnable install of a local Hunyuan3D-2 (shape: 2mini / 2mv, texture: paint v2.0 turbo)
# image-to-3D pipeline for an RTX 3070 8 GB. Own env, nothing in the repo.
#   bash tools/charpipe/install/install_hy3d.sh 2>&1 | tee /c/Users/rtcru/hy3d/install.log
# Uses: uv (Python 3.12), torch 2.6.0+cu126 (pytorch.org), Tencent-Hunyuan/Hunyuan3D-2 (GitHub),
# the prebuilt Windows custom_rasterizer wheel + mesh_processor .pyd shipped with
# 3D Gen Studio's ComfyUI-Hunyuan3DWrapper (kijai), so no CUDA toolkit / compiler is needed.
set -euo pipefail
HERE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=/c/Users/rtcru/hy3d
WRAP=/c/Users/rtcru/AppData/Roaming/3DGenStudio/comfyui/custom_nodes/ComfyUI-Hunyuan3DWrapper
mkdir -p "$ROOT"
cd "$ROOT"
echo "== python 3.12 via uv"
uv python install 3.12
[ -d venv ] || uv venv --python 3.12 venv
PY="$ROOT/venv/Scripts/python.exe"
echo "== torch 2.6.0 cu126"
uv pip install --python "$PY" torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu126
echo "== Hunyuan3D-2 source"
[ -d Hunyuan3D-2 ] || git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git
cd Hunyuan3D-2
git rev-parse HEAD > "$ROOT/hy3d_commit.txt"
uv pip install --python "$PY" -r requirements.txt
uv pip install --python "$PY" -e .
# newer transformers renamed DINOv2 attention keys -> checkpoints fail to load
uv pip install --python "$PY" "transformers==4.46.3" "diffusers==0.31.0" "huggingface_hub<0.30"
echo "== texture extensions"
# mesh_processor (CPU, pybind11): prebuilt .pyd from 3D Gen Studio's ComfyUI-Hunyuan3DWrapper
cp "$WRAP/hy3dgen/texgen/differentiable_renderer/mesh_processor.cp312-win_amd64.pyd" hy3dgen/texgen/differentiable_renderer/
# custom_rasterizer (CUDA): the prebuilt wheels are sm_89 (RTX 40) only, so build it for this GPU
uv pip install --python "$PY" pip setuptools wheel ninja
HERE="$HERE_SCRIPT_DIR"
bash "$HERE/setup_cuda.sh"
cp "$HERE/build_rasterizer.cmd" "$ROOT/"
cmd //c "$(cygpath -w "$ROOT/build_rasterizer.cmd")"
echo "== check"
"$PY" -c "import torch, custom_rasterizer, custom_rasterizer_kernel, hy3dgen; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); from hy3dgen.texgen.differentiable_renderer import mesh_processor; print('ok')"
"$PY" -m pip freeze > "$ROOT/pip_freeze.txt" 2>/dev/null || uv pip freeze --python "$PY" > "$ROOT/pip_freeze.txt"
echo "INSTALL OK"
