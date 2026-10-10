"""Refresh City Hall surfaces through study-only material overrides."""
import unreal,json
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert 'AtlasPark_CitySampleStudy' in unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
root='/Game/AtlasRebuiltStudy/CivicMaterials'
el.make_directory(root)
names=['X_AP_CityHall_Concrete_01','X_AP_CityHall_BaseConcrete_01','X_AP_CityHall_Dome_01','X_AP_CityHall_Border_01','X_AP_CityHall_Border_02','X_AP_CityHall_Border_03','X_AP_CityHall_Border_04','X_AP_CityHall_Pillar_01','X_AP_CityHall_Details_01']
copies={}
for n in names:
    src=el.load_asset('/Game/atlas_park/Materials/'+n)
    if not src:continue
    dst=el.load_asset(root+'/MI_Restored_'+n) or el.duplicate_asset(src.get_path_name(),root+'/MI_Restored_'+n)
    assert dst,n
    dome='Dome' in n
    mel.set_material_instance_scalar_parameter_value(dst,'RoughnessFactor',.38 if dome else .63)
    mel.set_material_instance_vector_parameter_value(dst,'BaseColorFactor',unreal.LinearColor(.75,.81,.82,1) if dome else unreal.LinearColor(.92,.9,.85,1))
    if 'EmissiveStrength' in [str(p) for p in mel.get_scalar_parameter_names(dst)]:
        mel.set_material_instance_scalar_parameter_value(dst,'EmissiveStrength',0)
    mel.update_material_instance(dst);el.save_loaded_asset(dst,False)
    copies[n.lower()]=dst
changes=0
for a in sub.get_all_level_actors():
    if not isinstance(a,unreal.StaticMeshActor):continue
    c=a.static_mesh_component
    for i in range(c.get_num_materials()):
        mat=c.get_material(i)
        if mat and mat.get_name().lower() in copies:
            a.modify();c.modify();c.set_material(i,copies[mat.get_name().lower()]);changes+=1
print('CITY_HALL_SURFACE_OVERRIDES',changes)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
