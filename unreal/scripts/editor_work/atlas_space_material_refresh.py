import unreal
for name in ['Sidewalk','Stone','Soil','Seat','Metal']:
 m=unreal.load_asset('/Game/AtlasDressingStudy/Materials/MI_'+name)
 print(name,unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(m,'Color'))
 unreal.MaterialEditingLibrary.update_material_instance(m)
 assert unreal.EditorAssetLibrary.save_loaded_asset(m,False)
print('FIVE DRESSING MATERIALS REFRESHED')
