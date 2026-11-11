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
- 2026-10-21 00:44-00:46 UTC, three crashes (plus the one at ~00:42): `Assertion failed: SupportsTexture(Texture)`
  (EditorFactories.cpp:4698) from this work's Python `Exporter.run_asset_export_task` on City Sample's
  `T_BlindsAtlas_Col` (TextureExporterPNG). The `uex.sh` wrapper took the lost connection for "editor busy" and
  re-sent the export after each restart. Rules now: never export textures from the editor (reference
  them as material parameters, read pixel data only from source files on disk); `uex.sh` only retries
  when the editor could not be reached before sending, never after a command may have run.
- 2026-10-20 01:31 UTC crash: monorail glass mesh render resource (another session), not this work.
- 2026-10-20 10:24 UTC crash: a long RecompileMaterial of this master on the editor thread hit the
  Windows 10,000 USER-object limit. Scripts now recompile once per batch and reuse instances.

## Scripts (`unreal/scripts/glass/`)
- `build_glass_material.py` builds the master + instances; `interior_room.hlsl` is the interior node.
- `make_window_masks.py` (offline) picks pane-mask settings per original window texture.
- `apply_test_overrides.py` sets/clears the test overrides (`GLASS_OPTION=none|Reflective|Smudgy|Interior`).
- `shoot.sh` + `highres_shot.py` + `uex.sh` take the HighResShot screenshots via Python remote execution.

## Zones: glaze at import (asset level)
Approved 2026-11-10: the glass goes into the original window materials themselves, so every map and future
zone that uses them gets it, with no per-actor overrides.
- Table: `unreal/scripts/glass/glass_map.json` (window material -> texture key, panes, theme, masked/mirror),
  plus `skip` (not windows, with the reason) and `pending_galaxy_city` (need a mask from source first).
  Masks per texture: `window_masks.json` (colour key) or `masks/T_GlassMask_*.png` (hand-painted).
- After a zone import (coh2unreal route), run once in the editor:
  `GLASS_ZONE_PATH=/Game/<zone_folder>` + `unreal/scripts/glass/glaze_zone.py` (`GLASS_DRY=1` to preview).
  It backs up each matched original MI to `/Game/GlassUpgrade/OriginalBackup/...`, re-parents it to its
  per-texture glass instance, logs skipped / pending / unmapped window-like names, and saves only the
  changed packages. Never re-send it after a lost editor connection.
- Galaxy City (2026-11-10): 13 more windows (deco towers office/residential, Store_Front_Window_1 retail;
  12 are alpha-cut -> masked) and 6 skips (3 reflection overlay layers, roller shutter, boarded window,
  dark arched doorway). Masks from the zone export's own textures (`GLASS_TEX_SRC=...\galaxy_city	extures`
  with `make_clean_masks.py` / `make_rect_masks.py`). `glaze_zone.py` imports any missing mask textures itself.
- New window textures: add a `glass_map.json` entry, then a mask (`make_window_masks.py` for colour-keyable
  glass, `make_rect_masks.py` + `import_masks.py` for painted ones), then re-run `glaze_zone.py`.

## 2026-11-11: asset-level rollout in Atlas Park (done)
- `glaze_zone.py` on `/Game/atlas_park;/Game/AtlasExpansionTest;/Game/AtlasUpgraded;/Game/AtlasSecondPass;/Game/AtlasNanite`:
  59 original window MIs re-parented to the glass (backups in `/Game/GlassUpgrade/OriginalBackup/...`),
  32 skipped by the table, 72 window-like names not in the table left untouched (interior props,
  `deco_reflect1__GLASS` overlay panes, curtained ruin windows, ...). The 6 skyscraper tiles' per-actor
  overrides were cleared (the materials carry the glass now). 138 packages saved by explicit list.
- Tuned `MI_Glass_Interior` first: `ForegroundSteps` 4, `InteriorMipDistance` 800, `MaskMipDistance` 1500.
- Perf (PIE, GPU ms/frame, RTX 3070): tower view 65.7 before -> ~65 after; low-rise street 77.0 -> 74.0;
  2D texture memory 318-323 MB -> 318-350 MB. Untuned the same rollout cost +3..6 ms.
  (The editor viewport doesn't draw when the window is unfocused, so measure in PIE.)
- Shots `20_*`: day wide, 19:00 wide, 02:00 wide, 02:00 close-up, 19:00 street, day street (Simulate,
  day/night sequence jumped to the frame). The blue panels are the map's zone-boundary walls.
- Still open: Lumen `r.EyeAdaptation.CachedLightingPreExposure` warning. Setting 128 live did not clear the
  on-screen warning (likely read at startup); next step is `r.EyeAdaptation.CachedLightingPreExposure=128`
  under `[SystemSettings]` in Config/DefaultEngine.ini plus an editor restart to verify day and night.
