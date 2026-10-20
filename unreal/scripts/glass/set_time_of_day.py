"""Scrub the map's day/night LevelSequence in Sequencer (editor preview only, nothing saved).
  GLASS_TOD = day | evening | night | late | close   (close = close Sequencer and restore the pre-animated state)
Night keys: MPC_CoH.Night = 1 from frame 17100 to ~34000 (30 fps, 0..43200)."""
import os
import unreal

SEQ = "/Game/CoH/DayNight_AtlasPark_DressingStudy"
FRAMES = {"day": 6000, "evening": 17775, "night": 25200, "late": 30375}  # 12:30, 19:00, 23:05, 02:00
tod = os.environ.get("GLASS_TOD", "night")
LSE = unreal.LevelSequenceEditorBlueprintLibrary
if tod == "close":
    LSE.close_level_sequence()
else:
    LSE.open_level_sequence(unreal.load_asset(SEQ))
    LSE.set_current_time(FRAMES[tod])
    LSE.refresh_current_level_sequence()
print("time of day:", tod)
