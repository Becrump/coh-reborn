# usage: go.sh <option|-> <shotname> [cam]
cd C:/Users/rtcru/ClaudeProjects/coh-reborn
W=../coh-reborn-dm8n7k/unreal/scripts/glass
if [ "$1" != "-" ]; then (echo "import os; os.environ['GLASS_OPTION']='$1'"; cat $W/apply_test_overrides.py) > $TEMP/glass/_apply.py
  bash $TEMP/glass/uex.sh $TEMP/glass/_apply.py | cut -c1-160 || exit 1; fi
SS="C:/Users/rtcru/OneDrive/Documents/Unreal Projects/COHREBORN/Saved/Screenshots/WindowsEditor"
rm -f "$SS/glass_$2.png"
(echo "import os; os.environ['SHOT']='$2'; os.environ['CAM']='${3:-40778,29128,13709,24.4,78.2}'"; cat "$TEMP/glass/hrs.py") > $TEMP/glass/_hrs.py
bash $TEMP/glass/uex.sh $TEMP/glass/_hrs.py > /dev/null || exit 1
for i in $(seq 1 300); do [ -f "$SS/glass_$2.png" ] && break; sleep 2; done
sleep 2
python - "$SS/glass_$2.png" "$TEMP/glass/shots/$2.jpg" <<'PY'
import sys,os
from PIL import Image
im=Image.open(sys.argv[1]).convert('RGB'); out=sys.argv[2]; q=90
while True:
    im.save(out,quality=q)
    if os.path.getsize(out)<950_000 or q<60: break
    q-=5
im.resize((960,540)).save(out.replace('.jpg','_prev.jpg'),quality=80)
print(os.path.basename(out), os.path.getsize(out)//1024, 'KB')
PY
