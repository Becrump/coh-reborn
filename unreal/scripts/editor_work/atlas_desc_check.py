import unreal
x=unreal.WorldPartitionBlueprintLibrary.get_actor_descs()[0]
print('DESC',x)
print('FIELDS',[n for n in dir(x) if not n.startswith('_')])
