import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert 'AtlasPark_CitySampleStudy' in unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
for a in sub.get_all_level_actors():
    if str(a.get_folder_path())!='Atlas25/Buildings':continue
    rows=[]
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh:continue
        box=c.static_mesh.get_bounding_box();lo=box.min;hi=box.max
        ts=[c.get_instance_transform(i,True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
        for t in ts:
            low=min(unreal.MathLibrary.transform_location(t,unreal.Vector(x,y,z)).z for x in [lo.x,hi.x] for y in [lo.y,hi.y] for z in [lo.z,hi.z])
            rows.append((low,c.static_mesh.get_name()))
    lowest=min(v[0] for v in rows)
    print('GROUND',a.get_actor_label(),lowest)
    if lowest>100:
        loc=a.get_actor_location();loc.z-=lowest-12
        a.set_actor_location(loc,False,True)
        for c in a.get_components_by_class(unreal.StaticMeshComponent):c.set_relative_transform(c.get_relative_transform(),False,True)
        print('CORRECTED',a.get_actor_label(),loc.z)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
