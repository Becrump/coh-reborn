import unreal
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
 if isinstance(a,unreal.PostProcessVolume):
  s=a.get_editor_property('settings')
  s.set_editor_property('auto_exposure_min_brightness',2.0)
  s.set_editor_property('auto_exposure_max_brightness',16.0)
  a.set_editor_property('settings',s)
  print('DAYLIGHT EXPOSURE RESTORED',a.get_editor_property('settings').get_editor_property('auto_exposure_min_brightness'),a.get_editor_property('settings').get_editor_property('auto_exposure_max_brightness'))
print('Daylight restored. Dusk preview not saved to map.')
