# Atlas Park streaming audit (2026-11-14)

Read-only audit of `/Game/AtlasPark4/AtlasPark_DressingStudy_Nanite` against the one-world streaming
rules (see the zone fix pass: one sky in the world, everything chunked to 256 m, cull distances, no
always-loaded clutter, shared systems once). Headless editor run (UnrealEditor-Cmd + Python), no assets
changed. Raw numbers: `atlas_audit.json`.

## Summary

| Check | Atlas | Rule | Verdict |
|---|---|---|---|
| World Partition | yes, 8,157 actors | WP level | OK |
| Runtime grid | all actors on the default grid | Far / Ground grids for big and ground pieces | to do |
| Data layers | none | night lights, interiors, events on data layers | to do |
| Not spatially loaded | 21: sky set (Sun, Moon, SkyLight, Atmosphere, Fog, Clouds, PostProcess), DayNightCycle sequence, CoHLife manager, 10 PlayerStarts, MiniMap, WorldDataLayers | only true world singletons | sky/DayNight/Life must be world-level once Atlas sits in L_ParagonCity |
| Placed enemy characters | **4,666 SkeletalMeshActors** `CoHOriginal_<group>_...` (Hellions, Skulls, Vahzilok, Praetorian citizens, Paragon Police) | spawned on demand by the encounter system | **biggest issue**: 57% of all actors are full skeletal meshes standing in the map |
| Actors wider than 256 m | 55: ground aprons 0.5-1.8 km (`AtlasPass2_Apron_*`), CoHTrees 1.4 km (one actor), Monorail_Track 1.0 km, baked Nanite tiles 450-514 m, StarDome | chunk to 256 m, or Far grid | to do (trees: same fix as the zones) |
| Per 256 m cell (51 cells) | actors max 810 / median 103; lights max 61 / median 6; ISM instances max 41,436 / median 6,220 | budget per cell | cell (0,0) is 2x the next densest |
| Cars | 454 vehicle actors | Mass traffic / instanced parked cars | to do |
| Glass / interiors | 62 glass, 567 tile actors | interiors on data layers, loaded near | check with the glass thread |
| Ticking actors | 3 CoHCombatEnemy, CoHLifeManager, RebornMonorail, VolumetricCloud | few world-level managers | OK |
| Packed levels | 256 PackedLevelActors (Atlas upgrade buildings, frontages) | merged buildings | good: already the "one mesh per building" pattern |

## Densest cells (256 m, world metres)

| X | Y | actors | lights | ISM instances |
|---|---|---|---|---|
| 0 | 0 | 810 | 61 | 0 |
| 512 | 256 | 399 | 17 | 24,504 |
| -512 | 256 | 384 | 52 | 41,436 |
| 512 | 512 | 376 | 37 | 2,353 |
| 256 | -256 | 371 | 48 | 26,784 |
| 512 | -256 | 368 | 19 | 11,461 |
| -512 | 0 | 361 | 34 | 2,971 |
| -512 | -256 | 353 | 21 | 30,620 |
| 512 | 0 | 349 | 21 | 40,287 |
| 256 | 512 | 305 | 46 | 26,533 |

## Recommended Atlas fixes (gold standard first)

1. **Enemies:** replace the 4,666 placed `CoHOriginal_*` skeletal actors with spawn points (encounters.json
   / sites from PR #26) and spawn on demand near players. Largest win for memory, streaming and load time.
2. **Trees:** re-plant with the updated `setup_trees.py` (256 m chunk actors, 500 m cull), as done for all zones.
3. **Ground aprons and big pieces:** split the `AtlasPass2_Apron_*` meshes into 256 m tiles or put them on the
   "Ground" grid; Monorail track and big tiles on "Far".
4. **Sky / DayNight / Life manager:** keep in the Atlas map but on a data layer that is active in the Atlas
   map and off in L_ParagonCity (the world has its own), so Atlas can be placed without a second sky.
5. **Cars:** move parked cars to instanced or Mass traffic; drop per-car actors.
6. **Cell (0,0):** 810 actors and 61 lights in one cell (the plaza); thin or pack (PackedLevelActor) the plaza dressing.
7. **Data layers:** night-only lights and interiors (glass rooms) on data layers.

The PackedLevelActor buildings already follow the "merged building" pattern the zones should adopt.

## Fly-through baseline (Atlas alone)

`tools/build/flythrough_atlas.txt`: a 5.8 km loop at 60 m over the plaza, the west/bay side, north and
east, at 30 m/s. Uncooked `-game` run (editor binaries), High preset, 1920x1080, GPU free:

| | Atlas (uncooked) | 18-zone city, uncooked, before the zone fix (run 1) | 18-zone city, packaged, after the fix |
|---|---|---|---|
| Avg FPS | **33.7** | 54.1 | 80.5 |
| 1% low | 9.4 | 18.9 | 31.5 |
| Worst frame | 363 ms | 4,736 ms | 703 ms |
| Hitches > 50 ms | 243 in 193 s | 335 in 592 s | 291 in 592 s |
| Streaming behind | 64% of frames | 76% | 9% |
| VRAM / RAM peak | 4.62 GB / 20.0 GB | 4.41 / 18.9 | 3.63 / 4.1 |

Atlas is currently the heaviest part of the city per square metre: about 40% lower frame rate than the
uncooked zones, mainly from the 4,666 placed enemy skeletal meshes, 802 spot lights and the dense plaza
cell. Worst hitches: 363 ms at X -425 Y -283 m, 314 ms at X -92 Y 753 m, 273 ms at X 711 Y 796 m.
