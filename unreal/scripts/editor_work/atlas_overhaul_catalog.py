import unreal,json,itertools
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert 'AtlasPark_Upgraded' in unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
ref='/Game/CitySampleBuildings/Building/Library/Kit_Ref_Bldg/LevelInstance/'
hero=ref.replace('Kit_Ref_Bldg','Kit_Hero_Bldg')
names=['BPP_NYAC_Ref_N1','BPP_NYAD_Ref_N1','BPP_NYAE_Ref_N1','BPP_NYAF_Ref_N1','BPP_NYH_Ref_N1','BPP_CHI_Ref_A1_N1','BPP_SFC_Ref_N1','BPP_SFE_Ref_N1',
'BPP_Bldg_Hero_Tower_CHJ_A01_N1','BPP_Bldg_Hero_Tower_CHJ_B01_N1','BPP_Bldg_Hero_Tower_SFJ_A01_N1','BPP_Bldg_Hero_Tower_CHC_CHD_Modern_A01_N1','BPP_Bldg_Hero_NYG_Modern_Square_A01_N1','BPP_Bldg_Hero_Mid_CHG_Long_A01_N1','BPP_Bldg_Hero_Low_SFD_Long_N1','BPP_Bldg_Hero_Mid_SFE_C01_N1']
rows=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_catalog.json'))+json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_hero_catalog.json'))
rows={r['name']:r for r in rows}
for name in names:
    if name in rows:continue
    path=(hero if name.startswith('BPP_Bldg_') else ref)+name
    a=sub.spawn_actor_from_class(unreal.EditorAssetLibrary.load_blueprint_class(path),unreal.Vector(0,0,0));assert a,path
    a.set_actor_label('AtlasUpgrade_Catalog_'+name)
    o,e=a.get_actor_bounds(False)
    rows[name]={'name':name,'path':path,'center':[o.x,o.y,o.z],'extent':[e.x,e.y,e.z]}
    sub.destroy_actor(a)
    json.dump(list(rows.values()),open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_catalog.json','w'),indent=2)
    print('CATALOG',name,[round(e.x*2),round(e.y*2),round(e.z*2)],flush=True)
print('DONE',len(rows))
