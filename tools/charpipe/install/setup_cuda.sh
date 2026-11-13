#!/usr/bin/env bash
# Portable CUDA 12.6.3 toolkit (no admin, no system changes) assembled from NVIDIA's official
# redistributable zips into C:/Users/rtcru/hy3d/cuda126, enough to compile PyTorch CUDA extensions.
#   bash /c/Users/rtcru/hy3d/setup_cuda.sh
set -euo pipefail
ROOT=/c/Users/rtcru/hy3d
DL=$ROOT/cuda_dl
DST=$ROOT/cuda126
BASE=https://developer.download.nvidia.com/compute/cuda/redist
mkdir -p "$DL" "$DST"
cd "$DL"
[ -f redist.json ] || curl -sSf -o redist.json $BASE/redistrib_12.6.3.json
for k in cuda_nvcc cuda_cudart cuda_cccl libcublas libcusparse libcusolver libcurand cuda_nvtx cuda_profiler_api; do
  rel=$(python -I -c "import json;print(json.load(open('redist.json'))['$k']['windows-x86_64']['relative_path'])")
  sha=$(python -I -c "import json;print(json.load(open('redist.json'))['$k']['windows-x86_64']['sha256'])")
  f=$(basename "$rel")
  if [ ! -f "$f" ]; then echo "download $f"; curl -sSf -o "$f.part" "$BASE/$rel"; mv "$f.part" "$f"; fi
  got=$(sha256sum "$f" | cut -d' ' -f1)
  [ "$got" = "$sha" ] || { echo "SHA MISMATCH $f"; exit 1; }
  d="${f%.zip}"
  [ -d "$d" ] || unzip -q "$f"
  cp -r "$d"/. "$DST"/
done
"$DST/bin/nvcc.exe" --version | tail -2
echo "CUDA OK -> $DST"
