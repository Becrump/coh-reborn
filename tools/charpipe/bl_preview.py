"""Preview renders of a rigged character playing original CoH clips (Blender).

    blender -b --factory-startup -P bl_preview.py -- <rigged.glb> <out_dir> --coh <coh_character.gltf> --brawl <male_anims_01.gltf>

Retargets CoH idle, run and Brawl (male__brawl_high2) onto the rig (retarget2, coh -> meshy) and
writes preview_idle.png, preview_run.png, preview_brawl.png (impact frame) and preview_head.png
(1920x1080, same studio as model-upgrade-samples).
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import retarget2 as R  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], args[1]
coh = args[args.index("--coh") + 1]
brawl = args[args.index("--brawl") + 1]
os.makedirs(out, exist_ok=True)

C.reset()
cam = C.studio(samples=48)
bpy.context.scene.render.fps = 30
arm, meshes = C.import_gltf(src)
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"
C.ground(arm, meshes)


def clip(path, action, frames=None):
    before = set(bpy.data.objects)
    sa, sm = C.import_gltf(path)
    C.set_action(sa, action)
    act, log = R.retarget(sa, "coh", arm, "meshy", "PV_" + action, frames=frames)
    for o in set(bpy.data.objects) - before:
        bpy.data.objects.remove(o, do_unlink=True)
    return act


acts = {"idle": (clip(coh, "idle"), 10), "run": (clip(coh, "run"), 6),
        "brawl": (clip(brawl, "male__brawl_high2", list(range(1, 49))), 14)}
h = 1.8
for name, (act, f) in acts.items():
    C.set_action(arm, act, f)
    bpy.context.view_layer.update()
    C.frame_camera(cam, "full", char_h=1.95)
    C.render(os.path.join(out, "preview_%s.png" % name))
C.set_action(arm, acts["idle"][0], 10)
bpy.context.view_layer.update()
hp = arm.matrix_world @ arm.pose.bones["Head"].head
C.frame_camera(cam, "head", head_z=hp.z + 0.08, head_xy=(hp.x, hp.y))
C.render(os.path.join(out, "preview_head.png"))
print("PREVIEW_OK")
