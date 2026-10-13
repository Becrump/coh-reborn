import unreal
worlds=unreal.EditorLevelLibrary.get_pie_worlds(False)
for w in worlds:
 actors=unreal.GameplayStatics.get_all_actors_of_class(w,unreal.LevelSequenceActor)
 for a in actors:
  if a.get_actor_label()=='DayNightCycle':
   p=a.get_editor_property('sequence_player')
   print('LIVE',p.is_playing(),p.get_current_time(),p.get_play_rate())
   sun=next((x for x in unreal.GameplayStatics.get_all_actors_of_class(w,unreal.DirectionalLight) if x.get_actor_label()=='Sun'),None)
   print('LIVE SUN',sun.get_actor_rotation() if sun else None)
