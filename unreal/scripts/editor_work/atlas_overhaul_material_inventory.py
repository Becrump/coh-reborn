import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
sources=set()
for a in sub.get_all_level_actors():
    if not a.get_actor_label().startswith('AtlasUpgrade_'):continue
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        for i in range(c.get_num_materials()):
            src=c.get_material(i)
            if isinstance(src,unreal.MaterialInstanceConstant):sources.add(src.get_path_name())
json.dump(sorted(sources),open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_material_sources.json','w'),indent=2)
print('MATERIAL_SOURCES',len(sources),sorted(sources)[:3])
unreal.SystemLibrary.execute_console_command(w,'r.EyeAdaptation.CachedLightingPreExposure 8')
