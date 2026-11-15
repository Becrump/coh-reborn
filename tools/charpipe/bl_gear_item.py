"""Turn a Tripo accessory export into a wardrobe gear item on the shared skeleton (Blender).

    blender -b --factory-startup -P bl_gear_item.py -- <base_body.glb> <gear.glb|fbx|obj> <wardrobe_dir> [--name gear_cap] [--slot head]

The slot comes from the name unless --slot is given:
  head   (crown)  cap, hat, beanie, helmet, hood, bandana_head          rigid on Head, sized to the skull
  face            mask, goggles, glasses, visor, bandana_face, respirator rigid on Head, in front of the face
  neck            bandana, scarf, neckchain/necklace, chain               neck -> Spine blend, around the neck
  hand_r          bat, pipe, axe, knife, gun, pistol, shotgun, smg, sledge, crowbar, wrench, machete, weapon
                                                                        rigid on RightHand, along the grip
  belt            wallet, pouch, holster, belt                           rigid on Hips, right hip
Size: longest side from the item name (cap 24 cm, bat 84, shotgun 95, ...; Tripo exports are 1 unit), then
fitted to the slot (skull / face / neck width). Untextured pieces get a flat Hellion red.
Writes <wardrobe_dir>/<slot>/<name>.glb (armature + piece) and adds it to wardrobe.json (slot, socket, size).
"""
import json
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
BODY, SRC, WDIR = a[0], a[1], a[2]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
NAME = opt("--name", os.path.splitext(os.path.basename(SRC))[0].lower().replace(" ", "_"))
if not NAME.startswith("gear_"):
    NAME = "gear_" + NAME
low = NAME.lower()
RULES = [("face", r"mask|goggle|glasses|visor|respirator|bandana_?face|face_?bandana"),
         ("head", r"cap|hat|beanie|helmet|hood|bandana_?head|headband|hair"),
         ("belt", r"wallet|pouch|holster|belt"),
         ("hand_r", r"bat|pipe|axe|knife|gun|pistol|shotgun|smg|sledge|crowbar|wrench|machete|weapon|club|hammer"),
         ("neck", r"bandana|scarf|necklace|neck_?chain|chain")]
SLOT = opt("--slot") or next((s for s, rx in RULES if re.search(rx, low)), "belt")
SIZE_CM = [("shotgun", 95), ("sledge", 90), ("bat", 84), ("axe", 80), ("crowbar", 75), ("pipe", 70), ("machete", 60),
           ("smg", 55), ("wrench", 35), ("knife", 30), ("pistol", 22), ("gun", 70), ("hammer", 40), ("club", 70),
           ("helmet", 30), ("hat", 30), ("hood", 30), ("cap", 24), ("beanie", 22), ("mask", 24), ("goggle", 19),
           ("glasses", 15), ("visor", 22), ("respirator", 18), ("bandana", 45), ("scarf", 60), ("chain", 45),
           ("wallet", 18), ("pouch", 18), ("holster", 25), ("belt", 45)]
CM = next((c for k, c in SIZE_CM if k in low), 30)
rep = {"name": NAME, "slot": SLOT, "size_cm": CM}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=BODY)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
AW = arm.matrix_world
jp = lambda n, tail=False: AW @ (arm.data.bones[n].tail_local if tail else arm.data.bones[n].head_local)  # noqa: E731
before = set(bpy.data.objects)
ext = SRC.lower().rsplit(".", 1)[-1]
if ext == "fbx":
    bpy.ops.import_scene.fbx(filepath=SRC)
elif ext == "obj":
    bpy.ops.wm.obj_import(filepath=SRC)
else:
    bpy.ops.import_scene.gltf(filepath=SRC)
new = [o for o in bpy.data.objects if o not in before]
ms = [o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]
for o in new:
    if o not in ms:
        bpy.data.objects.remove(o, do_unlink=True)
for o in ms:
    mw = o.matrix_world.copy()
    o.parent = None
    o.modifiers.clear()
    o.vertex_groups.clear()
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
for x in bpy.data.objects:
    if x.name in bpy.context.view_layer.objects:
        x.select_set(False)
for o in ms:
    o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1:
    bpy.ops.object.join()
G = bpy.context.view_layer.objects.active
G.name = NAME
vs = [v.co.copy() for v in G.data.vertices]
lo = Vector([min(p[i] for p in vs) for i in range(3)])
hi = Vector([max(p[i] for p in vs) for i in range(3)])
size, ctr = hi - lo, (lo + hi) / 2
bv = body.matrix_world
gname = {g.index: g.name for g in body.vertex_groups}


def body_pts(bones):
    out = []
    for v in body.data.vertices:
        tot = sum(g.weight for g in v.groups)
        w = sum(g.weight for g in v.groups if gname[g.group] in bones)
        if tot > 0 and w / tot > 0.5:
            out.append(bv @ v.co)
    return out


def bbox(P):
    return Vector([min(p[i] for p in P) for i in range(3)]), Vector([max(p[i] for p in P) for i in range(3)])


weights = None
if SLOT in ("head", "face"):
    hp = body_pts({"Head", "head_end", "headfront"})
    hlo, hhi = bbox(hp)
    hw = hhi.x - hlo.x
    if SLOT == "head":
        k = hw * 1.04 / max(size.x, 1e-6)
        z = hhi.z - 0.38 * (hhi.z - hlo.z)
        M = Matrix.Translation(Vector(((hlo.x + hhi.x) / 2, (hlo.y + hhi.y) / 2 + 0.01, z))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-Vector((ctr.x, ctr.y, lo.z)))
    else:  # face: in front of the face; goggles at the eyes, masks centred, face bandanas over nose + mouth
        k = hw * (1.02 if "goggle" not in low and "glasses" not in low else 0.98) / max(size.x, 1e-6)
        hz = hhi.z - hlo.z
        z = hlo.z + hz * (0.62 if ("goggle" in low or "glasses" in low or "visor" in low) else 0.30 if "bandana" in low else 0.48)
        front = hlo.y  # the face is at -Y
        M = Matrix.Translation(Vector(((hlo.x + hhi.x) / 2, front + size.y * k * 0.35, z))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-ctr)
    bone = "Head"
elif SLOT == "neck":
    nb, hb = jp("neck"), jp("Head")
    sl = [p for p in (bv @ v.co for v in body.data.vertices) if nb.z - 0.01 < p.z < nb.z + 0.03 and abs(p.x - nb.x) < 0.12]
    nw = (max(p.x for p in sl) - min(p.x for p in sl)) if sl else 0.14
    ny = sum(p.y for p in sl) / len(sl) if sl else nb.y
    top = [p for p in vs if p.z > hi.z - 0.1 * size.z]
    rw = max(p.x for p in top) - min(p.x for p in top)
    rc = Vector(((max(p.x for p in top) + min(p.x for p in top)) / 2, (max(p.y for p in top) + min(p.y for p in top)) / 2, hi.z))
    k = min(0.26, max(0.17, nw * 1.15)) / max(rw, 1e-6)
    tgt = Vector((nb.x, ny, hb.z + 0.015))
    M = Matrix.Translation(tgt) @ Matrix.Scale(k, 4) @ Matrix.Translation(-rc)
    bone = None
elif SLOT == "hand_r":
    ax = max(range(3), key=lambda i: size[i])
    grip = (jp("RightHand") - jp("RightForeArm")).normalized()
    k = CM / 100.0 / size[ax]
    la = Vector([1.0 if i == ax else 0.0 for i in range(3)])
    R = la.rotation_difference(grip).to_matrix().to_4x4()
    start = ctr - la * size[ax] / 2
    M = Matrix.Translation(jp("RightHand") + grip * 0.07 - grip * 0.12) @ R @ Matrix.Scale(k, 4) @ Matrix.Translation(-start)
    bone = "RightHand"
else:  # belt
    k = CM / 100.0 / max(size)
    M = Matrix.Translation(jp("RightUpLeg") + Vector((0.03, -0.10, 0.07))) @ Matrix.Scale(k, 4) @ Matrix.Translation(-ctr)
    bone = "Hips"
G.data.transform(M)
if SLOT == "neck":
    tip = min(G.data.vertices, key=lambda v: v.co.z).co
    if tip.y > tgt.y:
        G.data.transform(Matrix.Translation(tgt) @ Matrix.Rotation(math.pi, 4, "Z") @ Matrix.Translation(-tgt))
    zs = [v.co.z for v in G.data.vertices]
    z0, z1 = min(zs), max(zs)
    gn, gs = G.vertex_groups.new(name="neck"), G.vertex_groups.new(name="Spine")
    for v in G.data.vertices:
        wn = 0.15 + 0.35 * (v.co.z - z0) / max(z1 - z0, 1e-4)
        gn.add([v.index], wn, "REPLACE")
        gs.add([v.index], 1 - wn, "REPLACE")
else:
    G.vertex_groups.new(name=bone).add(list(range(len(G.data.vertices))), 1.0, "REPLACE")
if not any(m and m.use_nodes and any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes) for m in G.data.materials):
    mat = bpy.data.materials.new("gear_flat_red")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.04, 0.04, 1)
    G.data.materials.clear()
    G.data.materials.append(mat)
    rep["untextured"] = True
G.parent = arm
G.modifiers.new("Armature", "ARMATURE").object = arm
bpy.data.objects.remove(body, do_unlink=True)
for x in bpy.data.objects:
    x.select_set(x is arm or x is G)
out = os.path.join(WDIR, SLOT, NAME + ".glb")
os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_skins=True, export_animations=False)
jpth = os.path.join(WDIR, "wardrobe.json")
wd = json.load(open(jpth)) if os.path.exists(jpth) else {"items": {}}
wd.setdefault("items", {})[NAME] = {"slot": SLOT, "socket": None if SLOT == "neck" else bone, "size_cm": CM,
                                    "file": "%s/%s.glb" % (SLOT, NAME), "source": os.path.basename(SRC),
                                    "hides_body_verts": [], "covers_bones": {}}
json.dump(wd, open(jpth, "w"), indent=1)
rep["scale"] = round(k, 4)
print("GEAR_ITEM_OK", json.dumps(rep))
