# CoH Reborn â€“ Unreal progress log

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
| Converter output | `C:\Users\rtcru\CoHReborn\out\atlas_park_v5` (current; v2â€“v4 + `atlas_park_patch` are older) |
| Character sources | `C:\Users\rtcru\CoHReborn\characters\` (captain_valor, astro_male, atlas_statue, iron_vanguard), `C:\Users\rtcru\CoHReborn\meshy\hellion_*` |
| Meshy API key | `C:\Users\rtcru\.meshy_key` (read by scripts, never printed, never committed) |

## What was built

### Setup
- Python + Pillow installed, i24 cloned, 41 piggs (3.1 GB) downloaded, `coh2unreal` run for Atlas Park.
- Repo `Becrump/coh-reborn` created; converter pushed on `coh2unreal-converter`.
- Unreal MCP: built-in **ModelContextProtocol** plugin. Its server is off by default. Turn on Editor Prefs â†’ Plugins â†’ Model Context Protocol â†’ Auto Start Server, or run the `ModelContextProtocol.StartServer` console command. It's registered in Claude Code as `unreal` â†’ `http://localhost:8000/mcp`. Python Remote Execution is used alongside it (`unreal/scripts/ue_exec.py`).

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
  - Its Meshy hips had a Ã—100 bone scale, fixed by `fix_rig_scale.py`.
  - Its gait looked ape-like, so the playable hero was switched.
- **Captain Valor (Meshy) is the playable hero:** C++ `ACoHHeroCharacter` and `ACoHGameMode`.
  - Retargeted from the UE Mannequin anim set. The IK Retargeter's ops are added with `add_default_ops`, and the Root Motion and Run IK Rig ops are disabled for Meshy rigs.
  - Super Jump on F (velocity 2400, gravity Ã—1.5).
  - Wall climbing with Meshy climb clips. The clips are detrended and height-normalised, and C pushes him 50 cm off the wall.
  - 3-hit punch combo.
  - Mouse-wheel zoom from 0 to 1400 cm, switching to first person under 60 cm.
  - Configured in `DefaultGame.ini` `[/Script/COHREBORN.CoHHeroCharacter]` (copy in `unreal/project/Config/`).

### Enemies â€“ Hellions (Meshy API)
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
| Rotated tiles | `Rot` radians â†’ degrees in `maplayout.py` |
| 5,400 CoH lights froze the editor | CoH fill lights off by default |
| Masked materials not cutting out | `AlphaMode` param, then our own masters |
| Water "requires output node" (Substrate) | SLW BSDF on front material + legacy SLW output |
| Water vanished | `apply_tuning` no longer reparents `oceanbase` to water |
| Statue lights never on | stale `bHiddenInGame`; script forces visible |
| Black shadows | sky light 0.38 â†’ 12 |
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
- **Lieutenant:** floats 5â€“13 cm after the retarget.
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
   - Line-of-sight aggro (about a 120Â° cone) with group assist, a threat table and leash.
   - Combat against Captain Valor.
3. **"Hero moment" events:** Hellions corner a civilian, the hero saves them and gets a heroic inspiration.
4. **Powers:**
   - A powers/FX converter from the `.pfx` files (4,428 files).
   - Map animation bits to clips.
   - Origin options (hands, eyes, chest, gun) with tints.
   - Start with Fire Blast.
5. **Later:** a slider-based hero creator (MetaHuman + Mutable), texture upscaling, and importing other zones.

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

## 2026-10-07: original CoH characters exported as rigged glTF

`coh2unreal/coh2unreal/character.py` (with `anim.py` and `defs.py`) exports villain costumes as skinned, animated glTF, without Unreal open:

```
python -m coh2unreal.character --data <i24/data> --piggs <piggs> --out <out>/characters --group Hellions --all-costumes
```

- **What it follows:** villain def â†’ NPC costume (`.nd`) â†’ `defs/ui/bodyparts.bp` â†’ `player_library/<prefix>_<base>.geo` model `GEO_<bone>[R|L]_<geometry>`.
- **What each character gets:**
  - The ent type's base skeleton (for example `male/skel_ready2`, 68 bones with fingers).
  - Five clips from the sequencer: idle, run, attack, hit and death. Creature sequencers fall back to their own moves, such as a claw swipe for an attack.
  - Every costume piece as its own skinned mesh, named by part and side: `Hand_R`, `Hand_L`, `Foot_R`, `Head`, `Chest` and so on. Each also carries `extras` with the original bone, model and texture names, so hands can be swapped for finger-boned versions later.
  - Colour tints baked into one base-colour PNG per part, with emblems alpha-masked.
- **Output** (not in git): `C:\Users\rtcru\CoHReborn\out\characters\<group>\<costume>\`, plus `index.json` listing each costume with its glTF, parts, clips, villains, ranks and level range.
- **Groups exported:**
  - All Hellions (16 costumes).
  - Up to level 10: Skulls, Clockwork, Vahzilok, Outcasts, The Lost, Trolls, Circle of Thorns, 5th Column and Council.
  - 270 costumes in total.
- **Skipped on purpose:** FX-only critters (fire puddles, runes, window fires). Some 5th Column "Night" pieces are not in the i24 piggs.
- **Seam check:** `tools/check_seams.py <out>/characters` skins every character on the CPU at rest and across each clip, then measures the wrist and ankle rims against the neighbouring pieces.
- **Not done yet:**
  - Per-bone body scaling (BoneScale, ShoulderScale and so on) and RandomBoneScale.
  - Fallback default-body geometry from an ent type's `Graphics` geo.
  - FX attached to costume parts.
  - Weapons.
  - Importing into Unreal.

## 2026-10-19: monorail ported into the Nanite dressing map (in progress)

Atlas Park's one working map is now `/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite` (EditorStartupMap and GameDefaultMap point at it).

- **Backup first:** `C:\Users\rtcru\COHReborn_Backups\2026-10-19_pre_monorail.zip`.
- **`tools/reborn/ue/port_monorail_nanite.py`:** places the track spline, the `ARebornMonorail` train, the Atlas Park stop, the destinations (round trip goes back to this map), the ride map `L_MonorailRide` and the MonorailArrival PlayerStarts.
  - The track follows the original CoH route, corner-rounded. That sits on the original beam 84% of the way; Reborn's spline managed 43%.
  - Both ends are trimmed short of the War Wall.
  - The CoHLife decorative train is switched off.
- **`tools/reborn/ue/nanite_daynight.py`:** the copied DayNightCycle was bound to the dressing study's actors, so nothing moved. It now uses its own copy, `/Game/CoH/DayNight_AtlasPark_Nanite`, with all 744 root bindings pointing at this map. Sun, moon and sky now move.
- **`tools/reborn/ue/nanite_monorail_clearance.py`:** removes the original tiles' collision triangles that sit inside the train's space (station end-wall lintels, a shop facade, glass) on copies under `/Game/AtlasNanite/Monorail`.
  - Copies need `allow_cpu_access` before `build_from_static_mesh_descriptions`, or they lose all collision.
- **Tested in PIE (the editor must be in the foreground; in the background it runs at 3 fps):**
  - The train arrives, dwells and departs.
  - A rider rides through the station and about 400 m of track.
  - The destination menu shows.
- **Not yet verified:**
  - Choosing the destination with a scripted click did not register (dest stayed -1).
  - The full ride-level round trip.
  - The last clearance pass (tile_3_-1_glass, tile_-2_6) was still running.


## 2026-10-20 City Sample cars for AtlasPark_DressingStudy_Nanite

All parked cars in the Nanite map are now City Sample cars with collision, and the traffic drives City Sample cars with collision.

- **Inventory (before):** 455 parked CoH cars baked into the tile meshes (Truck_1 93, Lux1 90, Compact1 83, Sport2 69, Sport1 65, Lux2 55; their materials belong to these 6 models only), the PPD squad car prop, and the CoHLifeManager traffic (instanced Vehicle Variety Pack meshes). No Mass/ZoneGraph traffic or car blueprints.
- **City Sample content:** already in the project at /Game/CitySampleVehicles. No migration.
- **Kit** (`cs_build_kit.py`): each City Sample car (Nanite body, 4 wheels, brake pads, windows with City Sample's opaque dark glass) merged into one Nanite mesh with a box collision: /Game/AtlasPark4/CitySampleCars/Meshes/SM_CSCar_vehicle01..13 (10 models, 4.4-6.4 m). 81 paint colours in .../Paint: children of each car's paint MI with BaseColor set, "Paint Variation"/"Albedo Variation" switched off (that palette ignores BaseColor), dirt turned down. The 1.3-3.2 M triangle `_LOD` meshes and the Chaos blueprints are not used (455 of them would not fit an 8 GB 3070).
- **Old cars out** (`cs_hide_coh_cars.py`): 109 render tile actors get an invisible material on their car slots only; 60 collision tiles point at car-free copies in .../CitySampleCars/Tiles (collision switched off on the car sections; tile_1_3 and tile_3_-1 built from the monorail's _Mono copies). Traces: 453/455 car spots reach the road, 0 floor points changed. `hide_report.json` has every actor before/after; `cs_revert_hide.py` undoes an unsaved pass. Left for later: Nanite_tile_2_3_Solid_00/01 still show their old cars (glass test overrides on them; their collision is already gone).
- **New cars** (`cs_place_cars.py`): 453 cars on the old spots (same heading: City Sample yaw = CoH yaw - 90, centred on the old car), model by size, colour by fixed seed. PhysicsActor collision (blocks players, enemies, camera, visibility), physics simulated but asleep until hit, 1.35-2.4 t, replicated movement. The squad car prop is now the City Sample police car (old prop hidden, collision off). Fit checks against buildings/poles/walls, the other new cars and 5,418 traffic-lane points.
- **Road / parking changes:** 2 box-truck spots dropped at tile_6_2 (~83,100-83,500 / 34,700): the old trucks were sunk into a solid 1.5 m loading platform. 3 cars nudged in their bays: #0 60 cm along, #323 40 cm across, #438 120 cm along. No road geometry needed changing.
- **Traffic** (`cs_traffic_cars.py`): CoHLifeManager CarMeshes = 29 weighted City Sample meshes (6 cars x4, 2 vans x2, pickup x1). Its instanced cars already collide (BlockAllDynamic, QueryAndPhysics, compiled 2026-10-18). The LifeManager was spatially loaded at the map origin and so never streamed in near play: now always loaded, so traffic actually runs (30 instances, moving).
- **Powers:** CoHPowers.cpp `PushProps()`: damaging powers rock physics props within 3 m of the target (area powers: their radius), knockback throws them. Live Coding patch compiled; a full build makes it permanent.
- **PIE checks:** hero blocked at the car's side (stops at half width + capsule radius); Foot Stomp next to a car woke it and shoved it ~2.9 m at 5 m/s, then it settled; 98-123 cars streamed near the hero, none fell or drifted; traffic 30 City Sample instances, 21 moved >1 m in 5 s. Frame cost (FPS chart, 2560x1440, editor throttled to 3 fps in background so FPS itself is meaningless): before GPU 62.7 / RT 14.9 / GT 15.2 ms, after GPU 66.5 / RT 14.2 / GT 14.0 ms (+3.8 ms GPU, ~6%). Editor+PIE shows "video memory exhausted (~350 MB over)" on the 8 GB card; the car textures are virtual textures (streamed pages), so a mip bias on them is the lever if a standalone build still runs short.
- **Log:** no new errors. New warnings: translucent water/forcefield materials on the invisible Nanite collision copies (harmless), and the LifeManager's blimp/drone materials (M_CoH_Surface children) lack the Nanite usage flag, now visible because the LifeManager loads; fix by enabling "Used with Nanite" on M_CoH_Surface (shared master, left alone).
- Screenshots: docs/cars_citysample_lot.png, docs/cars_citysample_street.png, docs/cars_citysample_hero.png.
- 2026-10-20 (Robert approved): "Used with Nanite" turned on for the shared /Game/CoH/Materials/M_CoH_Surface (444 users), compiled, only that material saved. PIE: the 11 police drones render their own Drone_Shell/Blue/Red materials (no more "missing usage flag Nanite" warnings); roads, sidewalks, lot surface and buildings unchanged against the earlier capture. The blimp has no route in this map, so it doesn't spawn. Screenshot: docs/drone_nanite_material.png.
- 2026-10-20: car damage stages (option B) put on hold by Robert. The uncompiled draft component is kept in unreal/drafts/car_damage (not in the project source); no map actors or assets were changed for it.
