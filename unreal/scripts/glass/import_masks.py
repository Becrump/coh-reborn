"""Import the hand-painted pane masks (masks/T_GlassMask_*.png, from make_rect_masks.py) into
/Game/GlassUpgrade/Masks as small linear grayscale textures. Run once, inside the editor.
Import only: never export textures from the editor (that crashed it on 2026-10-21)."""
import os
import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\rtcru\ClaudeProjects\coh-reborn-dm8n7k\unreal\scripts\glass"
SRC = os.path.join(HERE, "masks")
DEST = "/Game/GlassUpgrade/Masks"

tasks = []
for f in sorted(os.listdir(SRC)):
    if not f.endswith(".png") or unreal.EditorAssetLibrary.does_asset_exist("%s/%s" % (DEST, f[:-4])):
        continue
    t = unreal.AssetImportTask()
    t.filename = os.path.join(SRC, f)
    t.destination_path = DEST
    t.automated = True
    t.replace_existing = False
    t.save = False
    tasks.append(t)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

done = []
for t in tasks:
    for p in t.imported_object_paths:
        tex = unreal.load_asset(p)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        unreal.EditorAssetLibrary.save_loaded_asset(tex)
        done.append(p)
print("imported", len(done), done)
