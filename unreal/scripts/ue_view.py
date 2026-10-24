"""python ue_view.py name [x y z pitch yaw]  -> real editor viewport capture (Lumen) as PNG"""
import sys, json, base64, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue
name = sys.argv[1]
args = {"bShowUI": False, "annotations": {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0, "maxLabelDistance": 0, "classFilter": {"refPath": "/Script/Engine.Actor"}, "maxLabels": 0}}
if len(sys.argv) < 7:
    cam = json.loads(ue.tool("GetCameraTransform", {}, "EditorToolset.EditorAppToolset"))["returnValue"]
    json.dump({"returnValue": cam}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cam.json"), "w"))
    args["captureTransform"] = {"location": cam["location"], "rotation": cam["rotation"], "scale": {"x": 1, "y": 1, "z": 1}}
if len(sys.argv) >= 7:
    x, y, z, p, yw = map(float, sys.argv[2:7])
    args["captureTransform"] = {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": p, "yaw": yw, "roll": 0}, "scale": {"x": 1, "y": 1, "z": 1}}
r = ue.call("tools/call", {"name": "call_tool", "arguments": {
    "tool_name": "CaptureViewport", "toolset_name": "EditorToolset.EditorAppToolset", "arguments": args}})
saved = False
for c in r.get("result", {}).get("content", []):
    if c.get("type") == "image":
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".png")
        open(out, "wb").write(base64.b64decode(c["data"])); print(out); saved = True
    elif c.get("type") == "text":
        try:
            img = json.loads(c["text"])["returnValue"]["image"]["data"]
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".png")
            open(out, "wb").write(base64.b64decode(img)); print(out); saved = True
        except Exception:
            print(c["text"][:500])
if not saved: print(json.dumps(r)[:1500])
