import unreal, json
ROOT='/Game/CitySampleBuildings/Building/Library/Kit_Ref_Bldg/LevelInstance/'
names=['BPP_CHA_Ref_N1','BPP_CHB_Ref_A1_N1','BPP_CHC_Ref_A1_N1','BPP_CHD_Ref_A1_N1','BPP_CHE_Ref_A1_N1','BPP_CHF_Ref_A1_N1','BPP_NYAA_Ref_N1','BPP_NYAB_Ref_N1','BPP_NYG_Ref_N1','BPP_SFA_Ref_N1']
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rows=[]
for n in names:
    cls=unreal.EditorAssetLibrary.load_blueprint_class(ROOT+n)
    if not cls:
        print('MISSING',n);continue
    a=sub.spawn_actor_from_class(cls,unreal.Vector(0,0,0))
    origin,extent=a.get_actor_bounds(False)
    row={'name':n,'path':ROOT+n,'center':[origin.x,origin.y,origin.z],'extent':[extent.x,extent.y,extent.z],'components':len(a.get_components_by_class(unreal.StaticMeshComponent))}
    rows.append(row); print(row)
    sub.destroy_actor(a)
json.dump(rows,open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_catalog.json','w'),indent=2)
