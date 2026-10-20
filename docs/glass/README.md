# Window glass upgrade (test set) — work in progress

Map: `/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite`. Test set only; nothing map-wide,
no mesh assets or original CoH materials edited.

## Findings
- The original buildings are baked per map tile: the visible Nanite actors `Nanite_tile_X_Y_Solid_NN`
  (folder `AtlasNanite/Render`) each hold every building of a tile. All window meshes are Nanite.
- 41 material instances on original meshes match window/glass/reflect (about 30 are real windows;
  the rest are false hits such as urns, seals, statue wings), on roughly 210 actor slots. Opaque ones use `M_CoH_Surface`/`M_GLTF`, masked ones `M_CoH_Masked`
  (`*__GLASS` = masked "reflect" textures). No translucency anywhere.
- Window textures are small (128–256 px): frame and pane are baked into one texture, so a pane mask
  is derived per texture (`make_window_masks.py` → `window_masks.json`, luma or blue key).

## What was built (`/Game/GlassUpgrade`)
- `M_CoH_WindowGlass` (opaque, Nanite) + `MI_Glass_Reflective` (A), `MI_Glass_Smudgy` (B),
  `MI_Glass_Interior` (C); per-texture children in `PerTexture/`.
- C uses City Sample's furnished room captures (the arrays its `M_Window` uses, so no new textures):
  `TCA_1x1x1_Rooms` (15 rooms) and `TCA_2x2x1_Rooms` (11 wide rooms) plus the matching
  `T2A_*_CaptureFG/DepthFG` foreground layers. One room spans `RoomWidthMin..Max` panes (re-rolled per
  floor) x `RoomHeight` panes, random mirror, blinds (`BlindsFraction`), empty floors
  (`EmptyFloorFraction`), lights on at night for `LitFraction` of rooms (MPC_CoH.Night).
- Theme per actor: Custom Primitive Data[0] = 0 office, 1 residential, 2 retail ([1] = seed);
  `ThemeOverride` on the MI wins when >= 0. Test set: tile 3_3 office, tile 2_3 residential (demo).
- Test overrides (per-actor `OverrideMaterials`, window slots only) on `Nanite_tile_2_3_Solid_01`
  and `Nanite_tile_3_3_Solid_00` (the three towers in the reference view).

## Screenshots (1920x1080)
- `01..04` wide (before, A, B, C first try), `05..08` close-up (before, A, B, C first try).
- `09..10` furnished interior C (handover view, close-up).
- `11` before (wide, after restart), `12..14` C with the closed-window mix (about 50% covered by day:
  blinds full/half, curtains, frosted, plain mirror glass; open rooms in clusters).

## Night lights
- Clock: `/Game/GlassUpgrade/MPC_GlassTime.Hour`, keyed linearly by one extra track in
  `/Game/CoH/DayNight_AtlasPark_DressingStudy` (`add_hour_clock.py`; midnight = frame 26775).
- Lit share per room follows the clock (`LightsDimHours`, `LightsShare`): offices dim 18:00-22:00,
  homes 22:00-01:00, down to 25% lit late at night; each room has its own switch-off time; lights
  come back 05:00-08:00. Emissive is gated by `MPC_CoH.Night`.

## Still open
- Night screenshots: scrubbing the day/night sequence in the editor (Sequencer) changes the MPCs but
  the scene still renders as day in HighResShot, so the 19:00 / 02:00 shots came out in daylight and
  were not kept. Needs a PIE/Simulate capture or checking how the sequence drives the lights.
- Perf numbers (stat unit GPU ms, stat RHI VRAM with C on vs off) and the Lumen
  `r.EyeAdaptation.CachedLightingPreExposure` warning fix (current value 4.0 gives the safe range
  [-8, 12]; day exposure is ~12.3, so a value around 2^7 = 128 would cover the PPV clamp of 2..16 EV).
- Option C is applied on the two test tiles in memory only; the map is not saved.

## Incidents
- 2026-10-20 01:31 UTC crash: monorail glass mesh render resource (another session), not this work.
- 2026-10-20 10:24 UTC crash: a long RecompileMaterial of this master on the editor thread hit the
  Windows 10,000 USER-object limit. Scripts now recompile once per batch and reuse instances.

## Scripts (`unreal/scripts/glass/`)
- `build_glass_material.py` builds the master + instances; `interior_room.hlsl` is the interior node.
- `make_window_masks.py` (offline) picks pane-mask settings per original window texture.
- `apply_test_overrides.py` sets/clears the test overrides (`GLASS_OPTION=none|Reflective|Smudgy|Interior`).
- `shoot.sh` + `highres_shot.py` + `uex.sh` take the HighResShot screenshots via Python remote execution.
