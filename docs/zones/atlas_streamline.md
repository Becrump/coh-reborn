# Atlas Park streamline (2026-11-14)

Script: `coh2unreal/unreal/atlas_streamline.py` (headless, UnrealEditor-Cmd). Raw results: `atlas_streamline.json`,
log `atlas_streamline.log`. Backup before changes:
`COHREBORN_backups\atlas_before_streamline_20261114_0931` (umap + 8,349 external actor/object files).

| Pass | Result |
|---|---|
| enemies | 4,646 `CoHOriginal_*` encounter preview figures made **editor-only** (kept as layout reference, never loaded in game). Runtime skeletal actors 4,666 -> 20. Per faction: Hellions 2,604, Clockwork 938, Vahzilok 464, Arachnos 204, Skulls 167, Paragon Police 139, Freedom Corps 90, Praetorian citizens 27. Live enemies still come from ACoHEnemySpawner's original-encounters mode, which already hid these previews at runtime, so no group is lost. |
| trees | the 1.4 km `CoHTrees` actor -> 1,080 trees in 403 chunk actors (256 m, 500 m draw distance) |
| grids | runtime grid "Far" on 217 actors, "Ground" on 165 (299 actors wider than 256 m) |
| skylayer | Sun, Moon, SkyLight, Atmosphere, Fog, Clouds, PostProcess, StarDome, DayNightCycle, CoHLife manager and the 10 PlayerStarts on data layer `DL_AtlasStandaloneSky` (initially active): Atlas alone is unchanged; the one world can switch it off |
| report | 454 car StaticMeshActors; 802 spot lights + 6 point lights, none with a max draw distance (lamp lights are limited at runtime by CoHPerformance's lamp level) - no changes made |

## Fly-through, Atlas alone (same 5.8 km loop, uncooked -game, High, 1920x1080)

| | before | after |
|---|---|---|
| Avg FPS | 33.7 | 35.6 |
| 1% low | 9.4 | 9.4 |
| Worst frame | 363 ms | 2,672 ms (one cluster at X 861-973 m, Y 709-746 m, first time the new tree chunks are drawn: shader compile in an uncooked run) |
| Hitches > 50 ms | 243 | 230 |
| Streaming behind | 64% of frames | 35% |
| RAM peak | 20.0 GB | 17.5 GB |
| VRAM peak | 4.62 GB | 4.74 GB |

Streaming and memory improved (behind 64% -> 35%, 2.5 GB less RAM); frame rate barely moved, so Atlas is
GPU-bound, not streaming-bound. Next: the 802 shadowed spot lights and Lumen cost per frame, the "Far"/"Ground"
grids must still be added in Atlas's World Settings to take effect, and a cooked build removes the shader stalls.

## Lamp culling pass (2026-11-14, `coh2unreal/unreal/atlas_lights.py`)

Backup: `COHREBORN_backups\atlas_before_lights_20261114_1022`. 790 lights (784 spot, 6 point) now have a 200 m
max draw distance with a 30 m fade and no shadows (776 had none already, 32 had shadows); the 18 monorail
station lights (tile_1_3 box + 30 m, light_stations.py) were left untouched; no plaza light kept shadows
(none within 40 m of PlayerStart_AtlasPlaza cast shadows). Folders, tags and lamp glow materials unchanged.

| Atlas fly-through | baseline | after streamline | after lamps |
|---|---|---|---|
| Avg FPS | 33.7 | 35.6 | **38.6** |
| 1% low | 9.4 | 9.4 | 9.8 |
| Worst frame | 363 ms | 2,672 ms | 2,371 ms (same first-draw cluster at X 890-990 m, Y 700-735 m) |
| Hitches > 50 ms / > 200 ms | 243 / ? | 230 / 25 | 215 / 20 |
| Streaming behind | 64% | 35% | 32% |
| RAM / VRAM peak | 20.0 / 4.62 GB | 17.5 / 4.74 | 19.3 / 4.69 |
