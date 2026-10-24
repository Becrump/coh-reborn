import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors={a.get_actor_label():a for a in sub.get_all_level_actors()};keys=set()
for i in [1,2,3,4]:
 a=actors['AtlasPass2_Prototype_'+str(i)]
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  keys.update(c.get_material(j).get_path_name() for j in range(c.get_num_materials()) if isinstance(c.get_material(j),unreal.MaterialInstanceConstant))
state=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_materials.json'))
missing=sorted(keys-set(state['targets']))
json.dump(missing,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_pass2_material_sources.json','w'),indent=2)
print('NEW SOURCES',len(keys),'MISSING OLD STYLE',len(missing))
seen=set()
for a in actors.values():
 if not a.get_actor_label().startswith('AtlasUpgrade_'):continue
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  for j in range(c.get_num_materials()):
   mat=c.get_material(j)
   if not mat or mat.get_path_name() in seen or 'brick' not in mat.get_name().lower():continue
   seen.add(mat.get_path_name())
   print('BRICK',mat.get_path_name(),'VECTORS',[str(p) for p in unreal.MaterialEditingLibrary.get_vector_parameter_names(mat)])
   if len(seen)>=4:break
  if len(seen)>=4:break
 if len(seen)>=4:break
