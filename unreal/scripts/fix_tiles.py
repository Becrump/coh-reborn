import json, unreal
NEW = "/Game/atlas_park/atlas_park/StaticMeshes/"
OUT = r"C:/Users/rtcru/CoHReborn/out/atlas_park_v5/"
asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
inv = unreal.load_asset("/Game/CoH/Materials/M_Invisible")
hide = {"x_archent_int_window_cube", "portal_door1_tga"}
for s in json.load(open(OUT + "statues.json"))["statues"]:
    hide |= {m.lower() for m in s.get("hide_materials", [])}
hide |= {m.lower() for m in json.load(open(OUT + "atlas_park_trees.json"))["materials"]}
tiles = [a for a in asub.get_all_level_actors()
         if isinstance(a, unreal.StaticMeshActor) and a.get_actor_label().startswith("tile_")]
swapped = hidden = coll_off = fixed = 0
meshes_done = set()
with unreal.ScopedSlowTask(len(tiles), "Repairing tiles") as task:
    task.make_dialog(False)
    for a in tiles:
        task.enter_progress_frame(1, a.get_actor_label())
        c = a.static_mesh_component
        a.modify(); c.modify()
        if not c.static_mesh.get_path_name().startswith(NEW):
            new = unreal.load_asset(NEW + a.get_actor_label())
            if new:
                c.set_static_mesh(new); swapped += 1
        c.set_editor_property("override_materials", [])
        m = c.static_mesh
        slots = []
        for i in range(c.get_num_materials()):
            mat = m.get_material(i)
            if mat and mat.get_name().lower() in hide:
                c.set_material(i, inv); slots.append(i); hidden += 1
        if m.get_path_name() not in meshes_done:
            meshes_done.add(m.get_path_name())
            changed = False
            for s in range(m.get_num_sections(0)):
                if sms.get_lod_material_slot(m, 0, s) in slots and sms.is_section_collision_enabled(m, 0, s):
                    sms.enable_section_collision(m, False, 0, s); coll_off += 1; changed = True
            bs = m.get_editor_property("body_setup")
            ag = bs.get_editor_property("agg_geom")
            if len(ag.get_editor_property("convex_elems")) or bs.get_editor_property("collision_trace_flag") != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
                ag.set_editor_property("convex_elems", [])
                bs.set_editor_property("agg_geom", ag)
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                m.set_editor_property("body_setup", bs); changed = True; fixed += 1
            if changed:
                unreal.EditorAssetLibrary.save_loaded_asset(m, False)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
print("swapped to v5:", swapped, "| hidden slots:", hidden, "| section collision off:", coll_off, "| meshes given exact collision:", fixed)
unreal.EditorLevelLibrary.save_current_level()
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
bad = total = 0
for x in range(-20000, 40000, 2500):
    for y in range(-15000, 45000, 2500):
        hc = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(x, y, 8000), unreal.Vector(x, y, -3000), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
        if not hc: continue
        total += 1
        hs = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(x, y, 8000), unreal.Vector(x, y, -3000), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        if not hs or abs(hs.to_tuple()[4].z - hc.to_tuple()[4].z) > 50: bad += 1
print("collision survey:", total, "points,", bad, "mismatched")
