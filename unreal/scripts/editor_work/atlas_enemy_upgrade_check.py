import unreal,json
s=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a=next(a for a in s.get_all_level_actors() if a.get_actor_label()=='CoHOriginal_Hellions_8432ec4abda32d_0')
c=a.get_component_by_class(unreal.SkeletalMeshComponent)
print('BONES',c.get_all_socket_names())
print('IDLES',[(str(d.asset_name),str(d.package_name)) for d in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path('/Game/Characters/Enemies/Hellions/hellion_punk',True) if str(d.asset_class_path.asset_name)=='AnimSequence'])
print('LOC',a.get_actor_location(),c.get_editor_property('relative_location'))
