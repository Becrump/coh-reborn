import unreal
print('SET BINDING',unreal.LevelSequenceActor.set_binding.__doc__)
print('BIND ID',unreal.MovieSceneSequenceExtensions.get_binding_id.__doc__)
print('PROXY API',[n for n in dir(unreal.MovieSceneBindingProxy) if 'class' in n])
