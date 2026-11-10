"""Step 6: physically based daylight so City Sample materials read right.

The template level's sun is 6 lux; City Sample's window interiors and
facades are calibrated for real daylight (~75,000 lux), so at 6 lux the
camera exposes up and every window blooms. Sets the sun to 75,000 lux and
adds an unbound post-process volume with a daylight exposure range."""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
for a in find(cls=unreal.DirectionalLight):
    c = a.get_component_by_class(unreal.DirectionalLightComponent)
    c.set_editor_property("intensity", 75000.0)
    a.set_actor_rotation(unreal.Rotator(pitch=-42, yaw=-35, roll=0), False)
for a in find(label="Reborn_PostProcess"):
    actors.destroy_actor(a)
ppv = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
ppv.set_actor_label("Reborn_PostProcess")
ppv.set_folder_path("AtlasReborn/Lighting")
ppv.set_editor_property("unbound", True)
s = ppv.get_editor_property("settings")
for k, v in [("override_auto_exposure_method", True), ("auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM),
             ("override_auto_exposure_min_brightness", True), ("auto_exposure_min_brightness", 11.0),
             ("override_auto_exposure_max_brightness", True), ("auto_exposure_max_brightness", 15.0),
             ("override_auto_exposure_apply_physical_camera_exposure", True), ("auto_exposure_apply_physical_camera_exposure", False)]:
    try:
        s.set_editor_property(k, v)
    except Exception as e:
        print("skip", k, e)
ppv.set_editor_property("settings", s)
print("daylight set")
