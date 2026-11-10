"""Step 9: day/night cycle for AtlasPark_Reborn.

LS_Reborn_DayNight is a looping level sequence: 24 game hours in 24 real
minutes (30 fps, 43200 frames), auto-played by a LevelSequenceActor. It keys
  * the sun's rotation (rises in the east at 06:00, sets at 18:00),
  * MPC_Reborn.Night: 0 by day, 1 from just after sunset to just before
    sunrise. Night drives the City Sample window lights, the street lamp glow
    and the street lights' light function,
  * a faint bluish moonlight (second directional light, 0.15 lux) that only
    shows once the sun is down.
The sky light recaptures in real time so the ambient follows the sun.
Exposure is allowed to adapt down for night."""
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa

require_map()
FPS, MINUTES = 30, 24
FRAMES = FPS * 60 * MINUTES
path = ROOT + "/LS_Reborn_DayNight"
for a in find(label="Reborn_DayNight"):
    actors.destroy_actor(a)
seq = el.load_asset(path)
if seq:
    # reuse the asset (it may still be referenced), clear what was keyed
    for b in list(seq.get_bindings()):
        b.remove()
    for t in list(seq.get_tracks()):
        seq.remove_track(t)
else:
    seq = tools.create_asset("LS_Reborn_DayNight", ROOT, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
seq.set_display_rate(unreal.FrameRate(FPS, 1))
seq.set_tick_resolution(unreal.FrameRate(FPS, 1))
seq.set_playback_start(0)
seq.set_playback_end(FRAMES)

sun = find(cls=unreal.DirectionalLight)
sun = [a for a in sun if a.get_actor_label() != "Reborn_Moon"][0]
for a in find(label="Reborn_Moon"):
    actors.destroy_actor(a)
moon = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 0))
moon.set_actor_label("Reborn_Moon")
moon.set_folder_path("AtlasReborn/Lighting")
mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
mc.set_editor_property("intensity", 0.15)  # invisible next to a 75,000 lux sun
mc.set_editor_property("forward_shading_priority", 0)
sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("forward_shading_priority", 1)
mc.set_editor_property("light_color", unreal.Color(255, 200, 170, 255))  # BGRA: bluish
mc.set_editor_property("atmosphere_sun_light_index", 1)
mc.set_editor_property("cast_shadows", True)
moon.set_actor_rotation(unreal.Rotator(pitch=-35, yaw=150, roll=0), False)
for s in find(cls=unreal.SkyLight):
    s.get_component_by_class(unreal.SkyLightComponent).set_editor_property("real_time_capture", True)
for p in find(label="Reborn_PostProcess"):
    st = p.get_editor_property("settings")
    st.set_editor_property("auto_exposure_min_brightness", 1.5)
    p.set_editor_property("settings", st)


def frame(hour):
    return unreal.FrameNumber(int(hour / 24.0 * FRAMES))


def sun_rot(hour):
    # elevation: +80 at noon, 0 at 6 and 18, -50 at midnight; azimuth east -> west
    e = math.sin((hour - 6) / 24 * 2 * math.pi)
    elev = 80 * e if e > 0 else 50 * e
    yaw = -90 + (hour - 6) / 12 * 180
    return -elev, yaw


def night(hour):
    e = math.sin((hour - 6) / 24 * 2 * math.pi) * 90      # rough sun elevation
    return min(1.0, max(0.0, (4 - e) / 10))                 # on below ~4 deg, full at -6


def keyed_transform(actor, value_fn):
    b = seq.add_possessable(actor)
    tr = b.add_track(unreal.MovieScene3DTransformTrack)
    sec = tr.add_section()
    sec.set_range(0, FRAMES)
    ch = sec.get_all_channels()   # loc x y z, rot x y z, scale x y z
    for h10 in range(0, 241, 5):
        h = h10 / 10.0
        pitch, yaw = value_fn(h)
        ch[4].add_key(frame(h), pitch)
        ch[5].add_key(frame(h), yaw)
    return b


keyed_transform(sun, sun_rot)
keyed_transform(moon, lambda h: (-35.0, 150 + h * 5))
# Night parameter
mt = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
mt.set_editor_property("mpc", el.load_asset(ROOT + "/Materials/MPC_Reborn"))
msec = mt.add_section()
msec.set_range(0, FRAMES)
for h10 in range(0, 241, 5):
    h = h10 / 10.0
    msec.add_scalar_parameter_key("Night", frame(h), night(h))
el.save_loaded_asset(seq)

for a in find(label="Reborn_DayNight"):
    actors.destroy_actor(a)
lsa = actors.spawn_actor_from_class(unreal.LevelSequenceActor, unreal.Vector(0, 0, 0))
lsa.set_actor_label("Reborn_DayNight")
lsa.set_folder_path("AtlasReborn/Lighting")
lsa.set_sequence(seq)
ps = lsa.get_editor_property("playback_settings")
ps.set_editor_property("auto_play", True)
lp = ps.get_editor_property("loop_count")
lp.set_editor_property("value", -1)
ps.set_editor_property("loop_count", lp)
# start the game at 10:00
ps.set_editor_property("start_time", 10 / 24.0 * MINUTES * 60) if hasattr(ps, "start_time") else None
lsa.set_editor_property("playback_settings", ps)
print("day/night sequence", path, "frames", FRAMES)
