"""Day/night for the Nanite dressing map.

The map was copied from AtlasPark_DressingStudy together with its
DayNightCycle actor, whose binding overrides still pointed at the dressing
study's actors: in the Nanite map the sequence played but drove nothing (sun,
moon, lamps, night tiles all unbound). This gives the Nanite map its own copy
of the sequence (/Game/CoH/DayNight_AtlasPark_Nanite, so the dressing study
and its sequence can go later) and binds every root binding to the actor with
the same label in this map (component bindings follow their actor).
Run with the Nanite map open; saves the sequence and the map."""
import unreal

MAP = "/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite"
SRC = "/Game/CoH/DayNight_AtlasPark_DressingStudy"
DST = "/Game/CoH/DayNight_AtlasPark_Nanite"

el = unreal.EditorAssetLibrary
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
w = editor.get_editor_world()
assert w.get_path_name().startswith(MAP), "open %s first" % MAP
assert editor.get_game_world() is None, "stop Play-In-Editor first"

seq = el.load_asset(DST) if el.does_asset_exist(DST) else el.duplicate_asset(SRC, DST)
el.save_loaded_asset(seq)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
cycle = next(a for a in actors if isinstance(a, unreal.LevelSequenceActor) and a.get_actor_label() == "DayNightCycle")
cycle.modify()
cycle.set_sequence(seq)
cycle.reset_bindings()
bylabel = {a.get_actor_label(): a for a in actors}
bound, missing = 0, []
for b in seq.get_bindings():
    if b.get_parent().is_valid():
        continue
    a = bylabel.get(str(b.get_name()))
    if a:
        cycle.set_binding(seq.get_binding_id(b), [a], False)
        bound += 1
    else:
        missing.append(str(b.get_name()))
unreal.EditorLoadingAndSavingUtils.save_map(w, MAP)
print("day/night: %s bound %d root bindings, missing %s" % (DST, bound, missing))
