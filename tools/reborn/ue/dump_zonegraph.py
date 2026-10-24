"""Write the built ZoneGraph lane data to zonegraph_dump.txt for make_life.py.

Runs 'obj dump' on the level's ZoneGraphData and copies its ZoneStorage line
out of the editor log."""
import glob
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
zg = find(cls=unreal.ZoneGraphData)
assert zg, "no ZoneGraphData: build the lanes first"
unreal.SystemLibrary.execute_console_command(world(), "obj dump " + zg[0].get_name())
log = max(glob.glob(os.path.join(unreal.Paths.project_log_dir(), "*.log")), key=os.path.getmtime)
line = [l for l in open(log, encoding="utf-8", errors="replace") if "  ZoneStorage=" in l][-1]
with open(os.path.join(OUT, "zonegraph_dump.txt"), "w", encoding="utf-8") as f:
    f.write(line)
print("zonegraph dump", len(line), "chars")
