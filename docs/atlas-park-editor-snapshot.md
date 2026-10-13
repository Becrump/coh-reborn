# Atlas Park editor snapshot (2026-10-10)

The active map is `/Game/AtlasPark4/AtlasPark_DressingStudy`.

This snapshot includes the current C++ project source and configuration, the map and its World Partition external actor/object packages, authored CoH materials and fountain FX, the map-specific day/night sequence, and editor setup/diagnostic scripts.

Imported CoH geometry, textures, characters, original game archives, and downloaded marketplace asset libraries remain external dependencies. This repository is therefore not a standalone playable build. Keep the existing Unreal Content directory when applying this snapshot; the saved map references assets that are not included here.

Day/night: `DayNightCycle` uses `/Game/CoH/DayNight_AtlasPark_DressingStudy`. All 743 root actor bindings and their child component bindings resolved in the current map. Sun motion and automatic playback were verified in simulation. Rate 2 at 30 FPS over 43,200 frames gives a 12-minute day. It runs in Play/Simulate; design-mode preview uses Sequencer playback.

Fountains: `/Game/CoH/FX/BP_CoH_ArcFountain` includes Stream, Splash, Ripples, and a metal nozzle with a dark bore and mounting base. Twelve placed fountains were updated without changing actor transforms. Ripple rings/foam and droplets animate through time-driven materials. These are lightweight visual effects, not fluid simulation. The impact components follow the endpoint at local X=600; keep the impact at the water surface when adjusting jets. A pre-ripple Blueprint backup is included.

Scripts under `unreal/scripts/editor_work` are a historical working archive, with local PC paths and diagnostic experiments. Do not run them all. The verified current cycle repair is `repair_cycle_editor.py`; the earlier `repair_daynight_bindings.py` runtime override experiment is superseded and must not be used. Fountain setup order is `make_fountain_spray.py`, `build_fountain_impact_fx.py`, then `bundle_fountain_impact_fx.py` and `bundle_fountain_nozzles.py`, outside Play mode. Generated mesh files are reproducible using the generator scripts.

Verification: 154 changed/archived Python sources parsed successfully; fountain materials saved and the Blueprint compiled; all 12 instances have the three components; saves succeeded. C++ source is copied from the existing project, without a new C++ rebuild in this snapshot. A restart test for remembered World Partition regions and a visual review of the new ripple look are still pending.
