# CoH Reborn – Unreal progress log

Covers the Unreal 5.8 work done on Robert's PC from 2026-10-03 03:22 UTC to 2026-10-04 07:01 UTC (one long Claude Code session, compacted twice). This file was rebuilt from that session's transcript. Unreal content (`.uasset`/`.umap`) and game data aren't in git; this file says where they live.

## Where things live

| What | Path |
| --- | --- |
| Unreal project | `C:\Users\rtcru\OneDrive\Documents\Unreal Projects\COHREBORN` (UE 5.8) |
| **Working level** | `/Game/AtlasPark4/AtlasPark` (World Partition, external actors) |
| Older levels (keep for reference) | `/Game/AtlasPark2/Untitled` (instanced attempt, flawed), `/Game/AtlasPark2/Untitled_TilesBackup` |
| Zone meshes / materials | `/Game/atlas_park/atlas_park/StaticMeshes`, `/Game/atlas_park/Materials` |
| Our shared assets | `/Game/CoH/*` (master materials, `MPC_CoH`, `M_Invisible`, `M_CoH_Stars`, Turf, Layers, Water, Sky, FX/`NS_CoH_Fountain`, Vehicles, Props, Statues, `DayNight` sequence) |
| Hero (playable) | `/Game/Characters/CaptainValor` (+ Meshy clips in `/Meshy`, anims in `/Anims`) |
| Other heroes | `/Game/Characters/IronVanguard`, `/Game/Characters/IronVanguardHero`, `/Game/Characters/AstroMale` |
| Enemies (Meshy) | `/Game/Characters/Enemies/Hellions/{hellion_biker,hellion_hood,hellion_punk,hellion_lieutenant}` (+ `IK_`, `RTG_`, `Anims/`) |
| MetaHuman prototype | `/Game/Characters/MetaHumans/MH_Hellion_Biker` (blank, see below) |
| Converter output | `C:\Users\rtcru\CoHReborn\out\atlas_park_v5` (current; v2–v4 + `atlas_park_patch` are older) |
| Character sources | `C:\Users\rtcru\CoHReborn\characters\` (captain_valor, astro_male, atlas_statue, iron_vanguard), `C:\Users\rtcru\CoHReborn\meshy\hellion_*` |
| Meshy API key | `C:\Users\rtcru\.meshy_key` (read by scripts, never printed, never committed) |

## What was built

### Setup
- Python + Pillow installed, i24 cloned, 41 piggs (3.1 GB) downloaded, `coh2unreal` run for Atlas Park.
- Repo `Becrump/coh-reborn` created; converter pushed on `coh2unreal-converter`.
- Unreal MCP: built-in **ModelContextProtocol** plugin. Its server is off by default. Turn on Editor Prefs → Plugins → Model Context Protocol → Auto Start Server, or run the `ModelContextProtocol.StartServer` console command. It's registered in Claude Code as `unreal` → `http://localhost:8000/mcp`. Python Remote Execution is used alongside it (`unreal/scripts/ue_exec.py`).

### Atlas Park level
- **Converter fixes:**
  - CoH `Rot` is radians (`PYR` is degrees). This was the cause of the rotated junction tiles.
  - Glass is kept unless ReflectTex is combined with Additive.
  - `water_coll_*` volumes get water tops.
  - `plan_lods` drops far-only duplicates, which fixed the mismatched S-curves.
  - Tiles are split into `tile_x_y`, `_night`, `_glass` and `_water`.
  - The AddGlow mask, scale and invert are honoured, so bricks no longer glow.
  - Exports `_life.json`, `_trees.json`, `_layers.json`, `_sky.json` and `_props.json`.
- **v5 reimport:**
  - Tiles relinked (`swap_to_v5.py`, `fix_tiles.py`).
  - `tile_2_2` scale reset.
  - Complex-as-simple collision with section collision off for hidden slots, which removed the invisible walls and stopped players falling under the world. A 570-point survey found 0 mismatches.
  - `PlayerStart_AtlasPlaza` added.
- **Materials:**
  - Our own masters (masked, surface/detail/glow, decal, additive, water), built by script.
  - Grass005 turf.
  - Bronze statues.
  - Glass.
  - Road and manhole decals fixed.
- **Water:** Substrate Single Layer Water (SLW BSDF plus the legacy SLW output), three ripple layers, tuned extinction and albedo. The canal bed is no longer reparented to water.
- **Fountains:** the fountains have water jets (`setup_fountains.py`).
- **Lighting and sky:**
  - Lumen with hardware ray tracing.
  - Day/night Level Sequence `DayNight` with an MPC `Night` track. It runs at 2 game hours per real minute.
  - Moon directional light and a star dome.
  - `SKY_INTENSITY` 12 for ambient fill, so characters no longer go black in shadow.
- **Light fixtures and fire:**
  - Modern street and parking lamps (our GLBs) with spotlights.
  - Statue uplights and City Hall floods with physical fixtures (`setup_fixtures.py`).
  - Fire in the City Hall braziers (`setup_fires.py`, NS_FireEffect).
  - Plaza, statue and fire lights are always on.
- **Atlas statue:** replaced with a scaled-up Meshy model, with the pedestal cut below ground.
- **Comic post-process:**
  - Custom HLSL: Kuwahara, banding, and edges from the Laplacian of 1/depth.
  - Lightened: thinner lines, `DepthSensitivity` 4, `PaintRadius` 0.
- **Living city:** C++ `CoHLifeManager`.
  - **Traffic:** lanes with car-following and yield, max 30 cars, 10 headlight spotlights, parked cars (more at night).
  - **Civilians:**
    - Walk graph with walkers spread out over 16 long circuits built with Dijkstra.
    - Civilians thin out at night.
    - `ReportDanger`/`CoHPanic` makes them flee and makes cars stop.
  - **Ambient:** monorail, blimp and drones.
  - **Instancing:** `CoHInstances` HISM actor.
- **Trees:** 1,080 trees replaced with Megaplant/Nanite plants (`setup_trees.py`). Leaves render black until the wind plugins load (see Open issues).
- **Performance:** cloud sampling 0.25, skin cache off, fewer civilians, civilians excluded from ray tracing.

### Hero
- **Iron Vanguard (Meshy):**
  - Imported as a skeletal mesh with Stand_Dodge.
  - Its Meshy hips had a ×100 bone scale, fixed by `fix_rig_scale.py`.
  - Its gait looked ape-like, so the playable hero was switched.
- **Captain Valor (Meshy) is the playable hero:** C++ `ACoHHeroCharacter` and `ACoHGameMode`.
  - Retargeted from the UE Mannequin anim set. The IK Retargeter's ops are added with `add_default_ops`, and the Root Motion and Run IK Rig ops are disabled for Meshy rigs.
  - Super Jump on F (velocity 2400, gravity ×1.5).
  - Wall climbing with Meshy climb clips. The clips are detrended and height-normalised, and C pushes him 50 cm off the wall.
  - 3-hit punch combo.
  - Mouse-wheel zoom from 0 to 1400 cm, switching to first person under 60 cm.
  - Configured in `DefaultGame.ini` `[/Script/COHREBORN.CoHHeroCharacter]` (copy in `unreal/project/Config/`).

### Enemies – Hellions (Meshy API)
- Four variants made with `tools/meshy_make.py`: biker, hood, punk, lieutenant. About 170 credits were spent, with Robert's approval.
- **Blender clean-up:**
  - `fix_meshy_api.py` bakes the 0.01 armature scale.
  - It moves hand weights more than 0.22 m from the hand bones onto Hips; 447 vertices were cleaned on the lieutenant.
  - `bake_clips.py` constraint-bakes the clips.
- **Unreal import:** `setup_enemies.py` imports them. The biker's 10 clips (idle, walk, run, combat stance, punch combo, hit reaction, knockdown, quick-draw, crouch-throw, chair sit) are retargeted to the other three.
- **In the level:** 4 Hellion `SkeletalMeshActor`s are placed in `/Game/AtlasPark4/AtlasPark`.

### MetaHuman Hellion prototype (in progress, not on the map)
- **Plugins:** MetaHumanCharacter, MetaHumanGenerator (toolset), MetaHumanCrowd and MetaHumanSDK are enabled in the `.uproject` (backup `.bak2`).
- **First attempt crashed:**
  - The script created `MH_Hellion_Biker`, then called `set_body_shape`, `set_skin_tone` and `set_eye_color`.
  - The editor crashed with `Assertion failed: BodyTexture` (MetaHumanCharacterBodyTextureUtils.cpp:109).
  - The cause: **MetaHuman Core Data** wasn't installed, and the log said "Optional Content folder not found".
- **Fix:**
  - Robert installed MetaHuman Core Data from the Epic Launcher (engine Options).
  - The warning is gone, and the log shows `[MetaHumanGenerator] Toolset registered successfully`.
- **Current state:**
  - `MH_Hellion_Biker` was recreated **blank** and saved 2026-10-04 06:13 UTC.
  - It has not been opened in MetaHuman Creator, edited or assembled.
  - No MetaHuman actor is in the level (checked 2026-10-04 13:25 UTC via MCP).

### Project settings changed
- **`DefaultEngine.ini`:**
  - `GlobalDefaultGameMode=/Script/COHREBORN.CoHGameMode`
  - `r.SkinCache.Mode=0`
  - `r.VolumetricCloud.ViewRaySampleMaxCount=256`
- **`.uproject`:**
  - C++ module `COHREBORN`.
  - Plugins: ModelingToolsEditorMode, MCPClientToolset, ModelContextProtocol, the four MetaHuman plugins, and (last change) DynamicWind and ProceduralVegetationEditor. Backups: `.bak`, `.bak2`, `.bak3`.
- **Build:** C++ is built with `Build.bat` while the editor is closed. Live Coding only handles function-body edits.

## Problems hit and fixes (short)
| Problem | Fix |
| --- | --- |
| Rotated tiles | `Rot` radians → degrees in `maplayout.py` |
| 5,400 CoH lights froze the editor | CoH fill lights off by default |
| Masked materials not cutting out | `AlphaMode` param, then our own masters |
| Water "requires output node" (Substrate) | SLW BSDF on front material + legacy SLW output |
| Water vanished | `apply_tuning` no longer reparents `oceanbase` to water |
| Statue lights never on | stale `bHiddenInGame`; script forces visible |
| Black shadows | sky light 0.38 → 12 |
| Bricks glowing | AddGlow mask/scale/invert implemented |
| Comic lines on floors | `DepthSensitivity` 4 |
| Floating cars | lane points snapped; life manager uses v5 json |
| Civilians clumping | walk radius 4000, `MinWalkArea` 8, SpreadNode + circuits |
| Hero tiny / T-pose / squashed | `fix_rig_scale`, `add_default_ops`, Root Motion + IK ops off |
| Meshy Hellions stretched / 2 cm tall | `fix_meshy_api.py` + `bake_clips.py` |
| Imports fail silently | stop Play-In-Editor first |
| MetaHuman crash | install MetaHuman Core Data |
| Map "stuck" loading | first-time Nanite build of the 545k-tri Black Poplar; not frozen |

## Open issues
- **Wind plugins:** Dynamic Wind and Procedural Vegetation Editor were just enabled. They need an editor restart, and then the Megaplant leaves should stop rendering black.
- **Lieutenant:** floats 5–13 cm after the retarget.
- **Hellion previews:** need re-placing, snapped to the ground.
- **Water:**
  - There may be a faint grid under the water.
  - VSM warning: the water should be split from the 72 non-Nanite tiles.

## Next
1. **MetaHuman Hellion:**
   - Open `MH_Hellion_Biker` in MetaHuman Creator.
   - Set his build, skin and eyes; the script is safe now that Core Data is installed.
   - Do the face and mohawk, then Assemble.
   - Add the flame-tinted jacket.
   - Retarget the Hellion clips onto him.
   - Compare him with the Meshy biker under the comic filter, and run a crowd performance test.
2. **Enemy AI:**
   - Spawns from the CoH Atlas spawn defs: Hellions about 350, Clockwork 66, Skulls 26, Vahzilok 26.
   - Line-of-sight aggro (about a 120° cone) with group assist, a threat table and leash.
   - Combat against Captain Valor.
3. **"Hero moment" events:** Hellions corner a civilian, the hero saves them and gets a heroic inspiration.
4. **Powers:**
   - A powers/FX converter from the `.pfx` files (4,428 files).
   - Map animation bits to clips.
   - Origin options (hands, eyes, chest, gun) with tints.
   - Start with Fire Blast.
5. **Later:** a slider-based hero creator (MetaHuman + Mutable), texture upscaling, and importing other zones.

## Loading screen (2026-10-07)
- Robert's wide key art (`docs/art/coh_reborn_key_art_wide.png`, 1024x765) is the loading screen, cropped to 16:9 so the Unreal Engine and DLSS logos at the bottom drop out. The first, portrait version is kept as `docs/art/coh_reborn_key_art.png`.
- `unreal/scripts/make_splash.py` crops wide art to 16:9 (taller art gets a blurred fill instead):
  `Content/Splash/LoadingScreen.png` (1920x1080), `Splash.bmp` (game boot splash) and `EdSplash.bmp` (editor splash).
- C++ `UCoHLoadingScreen` (game-instance subsystem) shows it through the MoviePlayer on every map load, with a throbber and "LOADING", for at least 2 s (`DefaultGame.ini` `[/Script/COHREBORN.CoHLoadingScreen]`).
- `Build.cs` gains `MoviePlayer`, `Slate`, `SlateCore`; packaging stages `Content/Splash`.
- **To apply on the PC:** copy `unreal/project/Source`, `Config/DefaultGame.ini` additions and `Content/Splash/*` into the live project, close the editor, run `Build.bat`. The loading screen only shows in Standalone Game or a packaged build (MoviePlayer is off inside the editor).
- **2026-10-07, applied on the PC:** files copied into the live project (backups `*.bak-loadscreen` for `COHREBORN.Build.cs` and `DefaultGame.ini`), `Build.bat COHREBORNEditor Win64 Development` built clean with no code changes, and a `-game` run showed `Splash.bmp` at startup, then the key art with "LOADING" during the first map load. The startup map is still the engine `OpenWorld` template (`GameDefaultMap` in `DefaultEngine.ini`).

## Scripts in this repo
- **`coh2unreal/`:** the converter, plus `coh2unreal/unreal/*.py`, the in-editor setup scripts. They're copied into each export folder and run with Unreal Python.
- **`tools/meshy_make.py`:** a resumable Meshy batch generator.
- **`unreal/scripts/`:** editor helpers.
  - `ue_exec.py`: Python Remote Execution runner.
  - `ue.py` and `ue_view.py`: viewport capture without moving the camera.
  - `raypick.py`.
  - `topdown_full.py`.
  - `swap_to_v5.py` and `fix_tiles.py`.
  - `after_reimport.py`.
  - `lineup.py`.
- **`unreal/project/`:** the project's C++ (`Source/`) and `Config/DefaultGame.ini`, mirrored for review. The live copies are in the Unreal project folder.

## Atlas Park expansion test ("the walls came down"), 2026-10-08 (in progress)

A test of opening the War Wall door at the end of the six-lane avenue (game x 1088, z 1024) and continuing the city one block north. **The real level and meshes are untouched.** Everything lives in two places; deleting them undoes the test:
- level `/Game/AtlasPark4/AtlasPark_ExpansionTest` (a Save As copy of `AtlasPark`, all 1,929 actors), plus its `__ExternalActors__/AtlasPark4/AtlasPark_ExpansionTest` folder;
- assets `/Game/AtlasExpansionTest/` (`WallTiles/`, `Block/`).

### Done
1. **Level copy:** Save As via `EditorLoadingAndSavingUtils.save_map`. The copy has all 1,929 actor files. When it's opened, load every actor with `WorldPartitionBlueprintLibrary.load_actors` (only 11 load by default).
2. **Converter options** (`coh2unreal/coh2unreal/edits.py`):
   - `--drop "PATTERNS@x0,z0,x1,z1"` leaves out pieces whose model or group name matches, with their origin inside the box (game feet).
   - `--ruin "PATTERNS@box@h0:h1"` keeps the pieces but clamps their height from h0 at x0 to h1 at x1.
   - `--tiles auto` writes only the tiles that an edit touched.
   - Wall re-export → `out/atlas_expansion_wall` (command in `atlas_expansion_wall.log`'s run; rules below). Tiles written: `tile_1_-3`, `2_-3`, `3_-3`, `4_-3`, `2_-4` (+ `_water`/`_glass`). `tile_3_-4` is now empty, so its actor must be removed in the test level. Compared with v5, only the War Wall, pulse-panel, tunnel and road-bend materials changed.
   - Rules:
     - door segment (`warwall_base_door|warwall_shield_door`) dropped;
     - tunnel shell beyond the door (`tunnel_*`, crawl blocks, no-teleport boxes) dropped;
     - shields, pulse panels and lips dropped on the segments either side (x 704, 1472);
     - their 1000 ft `_Warwall_straight` cut to stumps: 380→35 ft (west) and 35→420 ft (east). The east stump keeps its pulse emitter and accent.
3. **New block** (`coh2unreal/tools/expansion/gen_block.py` → `atlas_expansion_block.txt`, a normal CoH map file):
   - **Road:** three more `6_strt` (z 1152–1536), `4_4to6` reversed, then a `4_3way` T at z 1664–1792 with two `4_strt` arms each way.
   - **Ground:** `Filler_sidewlk` under the rest of the pocket (x 512–1664, z 1024–1920).
   - **Buildings, west side:** FillerShop_A, ind_ware_08, **Deco1** (deco), **OT_House_lrg** (Oldtown).
   - **Buildings, east side:** ind_ware_07, deco_skyscraper_14, FillerShop_C, FillerShop_J.
   - **Back row:** ind_ware_12, FLRN_BUILDING_B.
   - **Props:**
     - two parking lots with `Lamp_Parkinglot_01` and parked cars;
     - `TrashCan_bag` and `AP_Planter_01` on both curbs;
     - rubble (`WstRbl_*`, `RUIN_WALL_CHUNKS`), pothole and stain decals, and a wrecked `Rn_Compact` at the old wall line;
     - concrete barriers closing the T arms.
   - **Temporary War Wall:** three segments along z 1856 and three on each side (x 512, 1664).
   - Converted with coh2unreal → `out/atlas_expansion_block` (`expansion.gltf`; 0 missing).
4. **Import and materials (partly done):**
   - Both glTFs imported to `/Game/AtlasExpansionTest/{WallTiles,Block}`.
   - `unreal/scripts/expansion/exp_materials.py` linked 682 slots to the tuned `/Game/atlas_park/Materials` and ran `apply_tuning.tune_materials` on the 57 new-only slots.

### Still to do
- In the test level:
  - swap the six wall tile actors to the `WallTiles` meshes and remove `tile_3_-4`;
  - spawn the `Block` tiles at the origin as `exp_tile_*`;
  - set complex-as-simple collision, as `fix_tiles.py` does;
  - spawn modern lamps from `expansion_props.json`.
- Fix sidewalks and curbs at the seam, then run a collision survey over the new street.
- Take screenshots by day and night.

Paused 2026-10-08 19:08 UTC: the editor was closed then. Python crashed on exit inside the MetaHuman plugin's cleanup; the test level had no unsaved actor changes.
