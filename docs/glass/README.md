# Window glass upgrade (test set) — work in progress

Map: `/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite`. Test set only; nothing map-wide,
no mesh assets or original CoH materials edited.

## Findings
- The original buildings are baked per map tile: the visible Nanite actors `Nanite_tile_X_Y_Solid_NN`
  (folder `AtlasNanite/Render`) each hold every building of a tile. All window meshes are Nanite.
- 45 distinct window/glass material instances on original meshes (names with window/glass/reflect),
  on about 230 actor slots. Opaque ones use `M_CoH_Surface`/`M_GLTF`, masked ones `M_CoH_Masked`
  (`*__GLASS` = masked "reflect" textures). No translucency anywhere.
- Window textures are small (128–256 px): frame and pane are baked into one texture, so a pane mask
  is derived per texture (`make_window_masks.py` → `window_masks.json`, luma or blue key).

## What was built (`/Game/GlassUpgrade`)
- `M_CoH_WindowGlass` (opaque, Nanite) + `MI_Glass_Reflective` (A), `MI_Glass_Smudgy` (B),
  `MI_Glass_Interior` (C); per-texture children in `PerTexture/`.
- Test overrides (per-actor `OverrideMaterials`, window slots only) on `Nanite_tile_2_3_Solid_01`
  and `Nanite_tile_3_3_Solid_00` (the three towers in the reference view).

## Screenshots (1920x1080)
`01..04` wide (before, A, B, C), `05..08` close-up (before, A, B, C). Night shots, perf numbers,
the furnished-interior rework of C and the exposure fix are still in progress.

## Scripts (`unreal/scripts/glass/`)
- `build_glass_material.py` builds the master + instances; `interior_room.hlsl` is the interior node.
- `make_window_masks.py` (offline) picks pane-mask settings per original window texture.
- `apply_test_overrides.py` sets/clears the test overrides (`GLASS_OPTION=none|Reflective|Smudgy|Interior`).
- `shoot.sh` + `highres_shot.py` + `uex.sh` take the HighResShot screenshots via Python remote execution.
