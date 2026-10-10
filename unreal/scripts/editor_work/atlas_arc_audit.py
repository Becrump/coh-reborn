import unreal,json
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a=s.get_all_level_actors()
print('JET MATERIAL',unreal.EditorAssetLibrary.does_asset_exist('/Game/CoH/Materials/M_CoH_WaterJet'))
print('LOCAL WATER',[(x.get_actor_label(),str(x.get_actor_bounds(False))) for x in a if 'water' in x.get_actor_label().lower() and any(abs(v)<25000 for v in [x.get_actor_bounds(False)[0].x,x.get_actor_bounds(False)[0].y])][:15])
e=next(x for x in a if x.get_actor_label().startswith('CoHOriginal_'))
c=e.get_component_by_class(unreal.SkeletalMeshComponent)
print('ENEMY',e.get_actor_label(),'BONES',c.get_all_socket_names())
