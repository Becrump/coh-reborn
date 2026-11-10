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
import time
log = max(glob.glob(os.path.join(unreal.Paths.project_log_dir(), "*.log")), key=os.path.getmtime)
start = os.path.getsize(log)
unreal.SystemLibrary.execute_console_command(world(), "obj dump " + zg[0].get_name())
# the log is written by a background thread: wait for THIS dump's line
# (an older ZoneStorage line further up is stale lane data)
line = None
for _ in range(120):
    with open(log, encoding="utf-8", errors="replace") as fh:
        fh.seek(start)
        new = [l for l in fh if "  ZoneStorage=" in l]
    if new:
        line = new[-1]
        break
    time.sleep(0.5)
assert line, "the dump did not reach the log in 60 s"
with open(os.path.join(OUT, "zonegraph_dump.txt"), "w", encoding="utf-8") as f:
    f.write(line)
print("zonegraph dump", len(line), "chars")
