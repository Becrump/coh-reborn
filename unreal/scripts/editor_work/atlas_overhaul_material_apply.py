import unreal,json
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
state=json.load(open(base+'atlas_overhaul_material_batch_state.json'));sources=json.load(open(base+'atlas_overhaul_material_sources.json'));assert state['cursor']==len(sources)
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert 'AtlasPark_Upgraded' in w.get_path_name()
targets={s:unreal.EditorAssetLibrary.load_asset(t) for s,t in state['targets'].items()};slots=0
targetpaths={t.get_path_name() for t in targets.values()}
for a in sub.get_all_level_actors():
    if not a.get_actor_label().startswith('AtlasUpgrade_'):continue
    a.modify()
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        c.modify()
        for i in range(c.get_num_materials()):
            src=c.get_material(i);dst=targets.get(src.get_path_name()) if src else None
            if dst:c.set_material(i,dst);slots+=1
            elif src and src.get_path_name() in targetpaths:slots+=1
state['slots']=slots;state['created']=sum(not r['reused'] for r in state['materials']);state['reused']=sum(r['reused'] for r in state['materials'])
json.dump(state,open(base+'atlas_overhaul_materials.json','w'),indent=2)
print('MATERIALS',state['created'],'created',state['reused'],'reused',slots,'slots')
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
