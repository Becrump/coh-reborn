import unreal
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in sub.get_all_level_actors():
 if a.get_actor_label().startswith('AtlasPass2_Prototype_'):sub.destroy_actor(a)
seen=set();n=0
for a in sub.get_all_level_actors():
 if not a.get_actor_label().startswith('AtlasUpgrade_') or 'fillershop' not in a.get_actor_label():continue
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  for j in range(c.get_num_materials()):
   mat=c.get_material(j)
   if not mat or mat.get_path_name() in seen or '_Wall_' not in mat.get_name() or 'NY' not in mat.get_name():continue
   seen.add(mat.get_path_name());n+=1
   print('FACADE',mat.get_path_name(),'VECTORS',[str(p) for p in unreal.MaterialEditingLibrary.get_vector_parameter_names(mat)],'SCALARS',[str(p) for p in unreal.MaterialEditingLibrary.get_scalar_parameter_names(mat) if any(s in str(p).lower() for s in ['color','tint','normal'])])
   if n>=3:break
  if n>=3:break
 if n>=3:break
print('Prototype actors removed')
