"""Study-only material children reduce fine normal detail under the comic filter."""
import unreal,re,json
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_CitySampleStudy' in w.get_path_name()
unreal.SystemLibrary.execute_console_command(w,'r.EyeAdaptation.CachedLightingPreExposure 8')
root='/Game/AtlasRebuiltStudy/BuildingMaterials';el.make_directory(root)
cache={};changed=0;report=[]
for a in sub.get_all_level_actors():
    if str(a.get_folder_path())!='Atlas25/Buildings':continue
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        for i in range(c.get_num_materials()):
            src=c.get_material(i)
            if not isinstance(src,unreal.MaterialInstanceConstant):continue
            key=src.get_path_name()
            if key in cache:
                if cache[key]:c.set_material(i,cache[key]);changed+=1
                continue
            params=[str(n) for n in mel.get_scalar_parameter_names(src)]
            edits={}
            for p in params:
                low=p.lower()
                if 'normal inten' in low or low in ('detailintensity','detail intensity'):
                    value=mel.get_material_instance_scalar_parameter_value(src,p)
                    if value>.35:edits[p]=value*.3
            if not edits:cache[key]=None;continue
            # Inherit original textures and all static switches; override only inspected scalar controls.
            path=root+'/MI_Comic_'+src.get_name()
            dst=el.load_asset(path) if el.does_asset_exist(path) else None
            if not dst:
                dst=unreal.AssetToolsHelpers.get_asset_tools().create_asset('MI_Comic_'+src.get_name(),root,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
                assert dst,path
                mel.set_material_instance_parent(dst,src)
            for p,v in edits.items():
                mel.set_material_instance_scalar_parameter_value(dst,p,v)
                # UE can return False even when an inherited scalar override is stored.
                assert abs(mel.get_material_instance_scalar_parameter_value(dst,p)-v)<.0001,(path,p)
            mel.update_material_instance(dst);el.save_loaded_asset(dst,False)
            c.set_material(i,dst);cache[key]=dst;changed+=1
            report.append({'source':key,'study':dst.get_path_name(),'overrides':edits})
sun=next(a for a in sub.get_all_level_actors() if a.get_actor_label()=='Sun')
sun.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(80000)
sky=next(a for a in sub.get_all_level_actors() if isinstance(a,unreal.SkyLight))
sky.get_component_by_class(unreal.SkyLightComponent).set_intensity(1.2)
v=next(a for a in sub.get_all_level_actors() if isinstance(a,unreal.PostProcessVolume))
p=v.get_editor_property('settings');p.auto_exposure_max_brightness=16;p.override_auto_exposure_bias=True;p.auto_exposure_bias=0
assert any(b.object and 'MI_CoH_Comic' in b.object.get_path_name() and b.weight>0 for b in p.weighted_blendables.array),'Comic filter missing'
v.set_editor_property('settings',p)
json.dump(report,open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_material_manifest.json','w'),indent=2)
print('MATERIAL_DETAIL',len(report),'material children;',changed,'actor slots')
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
