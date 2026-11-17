#!/bin/bash
# Clean + rig one Tripo download onto the shared skeleton (with fingers) and export an Unreal FBX.
#   bash tools/charpipe/tripo_rig.sh <in.glb|fbx> <work_dir> <name> [--headless] [--height-cm 182]
# Steps: bl_tripo_clean -> (headless: bl_proxy_head) -> bl_autorig -> rig_cleanup -> bl_fingers
#        -> bl_weight_polish (cuts the proxy head) -> bl_export (FBX, cm via unit scale) -> <work>/<name>.glb
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
B="${BLENDER:-C:/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
SRC="$1"; W="$2"; N="$3"; shift 3
HEADLESS=""; HCM=182
while [ $# -gt 0 ]; do
  case "$1" in --headless) HEADLESS=1;; --height-cm) HCM="$2"; shift;; esac; shift
done
mkdir -p "$W"
run() { "$B" -b --factory-startup -P "$HERE/$1" -- "${@:2}" 2>&1 | grep -E "_OK|AUTORIG|FINGERS|CLEAN|Error|Traceback" || true; }
run bl_tripo_clean.py "$SRC" "$W/${N}_clean.glb" --height-cm "$HCM" ${HEADLESS:+--headless} --report "$W/${N}_clean.json"
IN="$W/${N}_clean.glb"; CUT=""
if [ -n "$HEADLESS" ]; then
  run bl_proxy_head.py "$IN" "$W/${N}_proxy.glb" --height-cm "$HCM" --report "$W/${N}_proxy.json"
  IN="$W/${N}_proxy.glb"
  CUT=$(python -c "import json;print(json.load(open(r'$W/${N}_proxy.json'))['cut_above'])")
fi
H=$(python -c "print($HCM/100)")
run bl_autorig.py "$IN" "$W/${N}_rig_raw.glb" --height "$H" --report "$W/${N}_autorig.json"
run rig_cleanup.py "$W/${N}_rig_raw.glb" "$W/${N}_rig_clean.glb" --report "$W/${N}_cleanup.json"
run bl_fingers.py "$W/${N}_rig_clean.glb" "$W/${N}_fingers.glb" --report "$W/${N}_fingers.json"
run bl_weight_polish.py "$W/${N}_fingers.glb" "$W/${N}.glb" ${CUT:+--cut-above $CUT} --report "$W/${N}_polish.json"
run bl_export.py "$W/${N}.glb" "$W/ue" "$N"
echo "TRIPO_RIG_DONE $N"
