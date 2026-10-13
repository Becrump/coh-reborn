import unreal,json
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);rows=[]
for a in sub.get_all_level_actors():
 if not a.get_actor_label().startswith('tile_'):continue
 c=a.static_mesh_component;m=c.static_mesh
 if not m:continue
 mats=[]
 for i in range(c.get_num_materials()):
  mat=m.get_material(i)
  if mat and any(k in mat.get_name().lower() for k in ['bench','trash','can_']):mats.append([i,mat.get_name(),str(c.get_material(i))])
 if mats:rows.append({'label':a.get_actor_label(),'mesh':m.get_path_name(),'materials':mats})
json.dump(rows,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_core_prop_materials.json','w'),indent=2)
print('TILES',len(rows));print(str(rows[:10]))
