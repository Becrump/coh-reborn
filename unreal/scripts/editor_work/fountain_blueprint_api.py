import unreal
print('ARC DESCS',[(str(d.label),str(d.actor_path)) for d in unreal.WorldPartitionBlueprintLibrary.get_actor_descs() if 'arc' in str(d.label).lower() and 'ArchLight' not in str(d.label)])
s=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
for n in ['k2_gather_subobject_data_for_blueprint','add_new_subobject','rename_subobject']:
 print(n,getattr(s,n).__doc__)
print('LIB',unreal.SubobjectDataBlueprintFunctionLibrary.get_object.__doc__)
print('PARAMS',unreal.AddNewSubobjectParams.__doc__)
