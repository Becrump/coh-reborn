"""Give the glass material a clock: /Game/GlassUpgrade/MPC_GlassTime.Hour (0-24, may run past 24),
driven by one extra MPC track in the map's day/night sequence. The sequence only animates
MPC_CoH.Night (the sun does not move), so Hour is keyed linearly to match it:
Night ramps up 15750-17100 (dusk ~18:15) and down 36450-37800 (dawn ~05:45), so midnight = frame 26775,
1800 frames per hour -> frame 0 = 09:07.5, frame 43200 = 33:07.5. Idempotent."""
import unreal

SEQ = "/Game/CoH/DayNight_AtlasPark_DressingStudy"
MPC = "/Game/GlassUpgrade/MPC_GlassTime"
EAL = unreal.EditorAssetLibrary

if EAL.does_asset_exist(MPC):
    mpc = unreal.load_asset(MPC)
else:
    mpc = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "MPC_GlassTime", "/Game/GlassUpgrade", unreal.MaterialParameterCollection,
        unreal.MaterialParameterCollectionFactoryNew())
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "Hour")
    p.set_editor_property("default_value", 12.0)
    mpc.set_editor_property("scalar_parameters", [p])
    EAL.save_loaded_asset(mpc)

seq = unreal.load_asset(SEQ)
for t in seq.get_tracks():  # drop an earlier copy of our track
    if isinstance(t, unreal.MovieSceneMaterialParameterCollectionTrack) and t.get_editor_property("mpc") == mpc:
        seq.remove_track(t)
track = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
track.set_editor_property("mpc", mpc)
sec = track.add_section()
sec.set_range(0, 43200)
for f, h in ((0, 9.125), (43200, 33.125)):
    sec.add_scalar_parameter_key("Hour", unreal.FrameNumber(f), h)
for ch in sec.get_all_channels():
    for k in ch.get_keys():
        k.set_interpolation_mode(unreal.RichCurveInterpMode.RCIM_LINEAR)
EAL.save_loaded_asset(seq)
print("Hour track keys:", [(k.get_time().frame_number.value, k.get_value()) for ch in sec.get_all_channels() for k in ch.get_keys()])
