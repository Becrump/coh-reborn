import unreal,json
sms=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for prefix in ['AtlasUpgraded/Geometry/atlas_upgraded','AtlasSecondPass/Geometry/atlas_secondpass']:
 m=unreal.load_asset('/Game/'+prefix+'/StaticMeshes/tile_-4_-3');print('MESH',prefix)
 mats=m.get_editor_property('static_materials')
 print('DISABLED',[(i,sms.get_lod_material_slot(m,0,i),str(mats[sms.get_lod_material_slot(m,0,i)].material_slot_name),m.get_material(sms.get_lod_material_slot(m,0,i)).get_name() if m.get_material(sms.get_lod_material_slot(m,0,i)) else None) for i in range(m.get_num_sections(0)) if not sms.is_section_collision_enabled(m,0,i)])
 print('ALLMATS',[(i,str(s.material_slot_name),s.material_interface.get_name() if s.material_interface else None) for i,s in enumerate(mats)])
