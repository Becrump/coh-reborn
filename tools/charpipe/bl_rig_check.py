"""Read-only check of a rigged character (FBX/GLB): height, facing, armature scale, bone count, fingers, detected
bone map and missing joints. blender -b --factory-startup -P bl_rig_check.py -- <file>"""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skeleton_detect as SD  # noqa: E402
import retarget2 as R  # noqa: E402

f = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
(bpy.ops.import_scene.fbx if f.lower().endswith(".fbx") else bpy.ops.import_scene.gltf)(filepath=f)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
ms = [o for o in bpy.data.objects if o.type == "MESH"]
dg = bpy.context.evaluated_depsgraph_get()
vs = [o.matrix_world @ v.co for o in ms for v in o.evaluated_get(dg).to_mesh().vertices]
rep = {"meshes": len(ms), "verts": len(vs), "height_m": round(max(v.z for v in vs) - min(v.z for v in vs), 3),
       "feet_z": round(min(v.z for v in vs), 3)}
if arm:
    fam = SD.detect(arm)
    rep.update(armature_scale=[round(x, 4) for x in arm.matrix_world.to_scale()], bones=len(arm.data.bones),
               finger_chains=len(R.finger_chains(arm)), missing=SD.missing(fam), sample_names=[b.name for b in arm.data.bones][:6])
    h = arm.matrix_world @ arm.data.bones[fam["head"]].head_local if "head" in fam else None
    hand = arm.matrix_world @ arm.data.bones[fam["hand_l"]].head_local if "hand_l" in fam else None
    if hand is not None:
        rep["left_hand_x_positive"] = bool(hand.x > 0)  # charpipe / CoH convention: character faces -Y, its left at +X
else:
    rep["error"] = "no armature"
print("RIGCHECK_OK", json.dumps(rep))
