"""Normalise Tripo downloads to MetaHuman / Unreal scale (Blender, batch).

    blender -b --factory-startup -P bl_tripo_normalize.py -- <in_dir> <out_dir> [--height 182] [--no-apose]

Tripo exports every model about 1 unit tall. For each .glb/.gltf/.fbx/.obj in <in_dir>:
  * height in cm from the file name (first match wins), else --height (default 182):
      kid|lean 172, veteran 178, average 180, heavy|brawler 183, big|biker 193
  * headless bodies (name contains "headless"): scaled so the neck stump sits at 0.87 x height
  * gear/props (bandana, cap, hat, mask, helmet, goggles, bat, axe, shotgun, knife, pipe, chain, prop...):
    longest side set to a typical real size (e.g. bandana 45 cm, cap 24, bat 84, shotgun 95); final fit on
    the character is done by bl_accessory.py
  * feet at the origin, centred on X/Y, front facing Blender -Y (= +Y after Unreal's FBX import,
    like MetaHuman meshes), transforms applied, scene units centimetres
  * MetaHuman A-pose (upper arms 52 deg below horizontal) when the file has a skeleton with
    LeftArm/RightArm or upperarm_l/upperarm_r bones; unrigged meshes keep their pose (Gemini
    concepts are already drawn in that A-pose) and the log says so
  * writes <out_dir>/<name>.fbx (embedded textures) and appends a line to <out_dir>/normalize_log.txt
"""
import math
import os
import re
import sys
import time

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
IN, OUT = a[0], a[1]
DEF_H = float(a[a.index("--height") + 1]) if "--height" in a else 182.0
APOSE = "--no-apose" not in a
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "normalize_log.txt")
BUILDS = [(r"kid|lean", 172), (r"veteran", 178), (r"average", 180), (r"heavy|brawler", 183), (r"big|biker", 193)]
GEAR_CM = [("bandana", 45), ("helmet", 30), ("mask", 24), ("goggle", 19), ("cap", 24), ("hat", 30), ("bat", 84),
           ("axe", 80), ("sledge", 90), ("shotgun", 95), ("smg", 55), ("gun", 70), ("pistol", 22), ("knife", 30),
           ("pipe", 70), ("chain", 45), ("weapon", 80), ("prop", 30)]  # longest side in cm
ARMS = (("LeftArm", "RightArm"), ("upperarm_l", "upperarm_r"))


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere") or o.type not in ("MESH", "ARMATURE", "EMPTY"):
            bpy.data.objects.remove(o, do_unlink=True)


def world_bbox(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        for v in me.vertices:
            p = o.matrix_world @ v.co
            lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
        ev.to_mesh_clear()
    return lo, hi


def apose(arm):
    W = arm.matrix_world
    names = next((pair for pair in ARMS if all(n in arm.pose.bones for n in pair)), None)
    if not names:
        return None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    out = []
    for bname, side in zip(names, (1, -1)):
        b = arm.data.bones[bname]
        d = (W @ b.tail_local) - (W @ b.head_local)
        cur = math.degrees(math.atan2(-d.z, abs(d.x)))
        pb = arm.pose.bones[bname]
        head = W @ pb.head
        R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(-side * (cur - 52.0)), 4, "Y") @ Matrix.Translation(-head)
        pb.matrix = W.inverted() @ (R @ (W @ pb.matrix))
        bpy.context.view_layer.update()
        out.append(round(cur, 1))
    return out


def process(path):
    base = os.path.splitext(os.path.basename(path))[0]
    low = base.lower()
    load(path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        log("SKIP %s: no mesh" % base)
        return
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    note = []
    if arm and APOSE:
        r = apose(arm)
        note.append("A-pose from %s deg" % r if r else "skeleton without arm bones: pose kept")
    elif APOSE:
        note.append("no skeleton: pose kept")
    # bake: apply armature pose and all transforms into the meshes, drop the skeleton
    for o in meshes:
        bpy.context.view_layer.objects.active = o
        for m in list(o.modifiers):
            if m.type == "ARMATURE":
                bpy.ops.object.modifier_apply(modifier=m.name)
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for o in [o for o in bpy.data.objects if o.type in ("ARMATURE", "EMPTY")]:
        bpy.data.objects.remove(o, do_unlink=True)
    lo, hi = world_bbox(meshes)
    h_src = hi.z - lo.z
    gear = next((cm for k, cm in GEAR_CM if k in low), None)
    target = next((h for pat, h in BUILDS if re.search(pat, low)), DEF_H)
    if gear is not None:
        s = gear / max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
        kind = "gear (longest side %d cm)" % gear
    elif "headless" in low:
        s = target * 0.87 / h_src
        kind = "headless (neck at %.0f cm of %.0f)" % (target * 0.87, target)
    else:
        s = target / h_src
        kind = "full body %.0f cm" % target
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    M = Matrix.Scale(s, 4) @ Matrix.Translation(-off)
    for o in meshes:
        o.data.transform(M)
        o.data.update()
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.01
    sc.unit_settings.length_unit = "CENTIMETERS"
    lo, hi = world_bbox(meshes)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    dst = os.path.join(OUT, base + ".fbx")
    bpy.ops.export_scene.fbx(filepath=dst, use_selection=True, object_types={"MESH"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_UNITS", path_mode="COPY", embed_textures=True,
                             mesh_smooth_type="FACE", add_leaf_bones=False)
    log("OK %s -> %s | %s | source %.3f units -> %.1f x %.1f x %.1f cm | %s"
        % (base, os.path.basename(dst), kind, h_src, hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, "; ".join(note) or "-"))


files = sorted(f for f in os.listdir(IN) if f.lower().rsplit(".", 1)[-1] in ("glb", "gltf", "fbx", "obj"))
if not files:
    log("nothing to do in %s" % IN)
for f in files:
    try:
        process(os.path.join(IN, f))
    except Exception as e:  # keep going with the rest of the batch
        log("FAIL %s: %s" % (f, e))
log("DONE %d file(s)" % len(files))
