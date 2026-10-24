"""Run in batches with editor frames between commands. Duplicate compiled source instances."""
import unreal,json,os,hashlib
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
sources=json.load(open(base+'atlas_pass2_material_sources.json'))
statepath=base+'atlas_pass2_material_state.json'
state=json.load(open(statepath)) if os.path.exists(statepath) else {'cursor':0,'materials':[],'targets':{}}
root='/Game/AtlasSecondPass/BuildingMaterials';el.make_directory(root)
packages=[]
assert 'asset_name' in unreal.AssetTools.duplicate_asset.__doc__
assert 'packages' in unreal.EditorLoadingAndSavingUtils.save_packages.__doc__
start=state['cursor'];end=min(start+40,len(sources))
for key in sources[start:end]:
    src=el.load_asset(key);assert src,key
    if '/AtlasRebuiltStudy/BuildingMaterials/' in key or '/AtlasUpgraded/BuildingMaterials/' in key:continue
    edits={}
    for p in mel.get_scalar_parameter_names(src):
        p=str(p);low=p.lower()
        if 'normal inten' in low or low in ('detailintensity','detail intensity'):
            v=mel.get_material_instance_scalar_parameter_value(src,p)
            if v>.35:edits[p]=v*.3
    if not edits:continue
    name='MI_Comic_'+src.get_name();old='/Game/AtlasRebuiltStudy/BuildingMaterials/'+name
    dst=el.load_asset(old) if el.does_asset_exist(old) else None
    reused=bool(dst and dst.get_editor_property('parent')==src)
    if not reused:
        target=root+'/'+name+'_'+hashlib.sha256(key.encode()).hexdigest()[:6]
        dst=el.load_asset(target) if el.does_asset_exist(target) else unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(target.rsplit('/',1)[1],root,src)
        assert dst,target
        for p,v in edits.items():
            mel.set_material_instance_scalar_parameter_value(dst,p,v)
            assert abs(mel.get_material_instance_scalar_parameter_value(dst,p)-v)<.0001,(key,p)
        # Scalar setters update instance values; no static permutation rebuild is needed.
        packages.append(dst.get_outer())
    state['targets'][key]=dst.get_path_name();state['materials'].append({'source':key,'target':dst.get_path_name(),'overrides':edits,'reused':reused})
if packages:assert unreal.EditorLoadingAndSavingUtils.save_packages(packages,True)
state['cursor']=end;json.dump(state,open(statepath,'w'),indent=2)
print('MATERIAL_BATCH',end,len(sources),'variants',len(state['materials']))
unreal.SystemLibrary.collect_garbage()
