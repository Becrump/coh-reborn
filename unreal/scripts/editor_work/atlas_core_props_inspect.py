import unreal,json
u=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
print('MAP',u.get_editor_world().get_path_name());out=[]
for a in sub.get_all_level_actors():
 label=a.get_actor_label();cs=a.get_components_by_class(unreal.StaticMeshComponent)
 matches=[c for c in cs if c.static_mesh and any(k in c.static_mesh.get_name().lower() for k in ['bench','trash','bin','planter','hydrant'])]
 if matches or any(k in label.lower() for k in ['bench','trash','planter']):
  p=a.get_actor_location();r=a.get_actor_rotation()
  out.append({'label':label,'class':a.get_class().get_name(),'location':[p.x,p.y,p.z],'yaw':r.yaw,'meshes':[c.static_mesh.get_path_name() for c in matches]})
json.dump(out,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_core_props_inventory.json','w'),indent=2)
print('PROP ACTORS',len(out));print(str(out[:15]))
