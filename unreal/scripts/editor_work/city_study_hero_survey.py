import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
root='/Game/CitySampleBuildings/Building/Library/Kit_Hero_Bldg/LevelInstance/'
names=['BPP_Bldg_Hero_Mid_NYG_Modern_A01_N1','BPP_Bldg_Hero_Tower_CHC_CHD_Modern_A01_N1','BPP_Bldg_Hero_CHA_A01_N1','BPP_Bldg_Hero_Tower_CHE_B01_N1']
rows=[]
for name in names:
    a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(root+name),unreal.Vector(0,0,0))
    a.set_actor_label('STUDY_Catalog_'+name)
    o,e=a.get_actor_bounds(False)
    rows.append({'name':name,'path':root+name,'center':[o.x,o.y,o.z],'extent':[e.x,e.y,e.z]})
    print(rows[-1]);sub.destroy_actor(a)
json.dump(rows,open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_hero_catalog.json','w'),indent=2)
