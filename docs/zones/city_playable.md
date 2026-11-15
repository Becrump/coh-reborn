# One playable city: steps 1-3 (2026-11-15)

Scripts: `coh2unreal/unreal/world_step1.py` (editor), `coh2unreal/unreal/world_step23.py` (headless), `place_world.py`
(ATLAS_LEVEL set; moves now call modify() so they are saved). Results: `city_playable.json` / `.log`.

## Step 1: Atlas in the world
- `zone_offsets.json`: Perez Park +600 x, Galaxy City +600 x, Skyway City +200 z, The Hollows -220 x, Talos Island -230 x,
  Dark Astoria -230 x (game metres; offset, rect, gates and stations shifted; `atlas_rebuilt_rect_m` added).
  Overlap check against Atlas's rebuilt area and every zone rect: none.
- L_ParagonCity: Atlas Park placed at 0,0 as a Partitioned Level Instance (19 zones); the six shifted zones moved.
- Data layer `DL_AtlasStandaloneSky` added to the world as **Unloaded**: Atlas's own sky, DayNight, life manager and
  PlayerStarts stay off in the world (on when Atlas runs alone).
- Lesson: loading all 19 zone instances in the editor pulls every zone's content in (38 GB, RAM 95-97%). World edits
  now run headless and load only the instances they change.

## Step 2: base and corridors
- 2,439 gap cells (250 m) filled: 565 water (`calmwater_1_tga`, -2 m), 1,874 ground (`concrete_dirty_tga`, -0.3 m),
  in 247 actors (`CityBase_*`, one per 1 km block and kind, runtime grid "Ground").
- Road corridors (24 m, `4lane_2to4_tga`) between gate pairs now apart: Galaxy-Perez 61 m, Perez-Atlas 661 m,
  Perez-Steel 1,054 m, Perez-Skyway 1,198 m. Galaxy-Kings Row has no gate sign on the Kings Row side (none added).
- No new War Walls: every original zone keeps its own ring of War Walls.

## Step 3: start and enemies
- One world PlayerStart at Atlas's plaza (X 40.7 m, Y 75.1 m, Z 59 m); the old Galaxy City start (now in a gap)
  removed. The game picks randomly among non-monorail starts, so gate starts are not added (see below).
- Enemies: the hero spawns an ACoHEnemySpawner if the map has none, so the world already gets enemies. But the
  encounter list is one global list (encounters.json), so every zone gets the same mix.

## Needs C++ (not built; needs Robert's OK)
1. Per-zone encounters: pick the encounter list by the zone the player is in (zone rects from zone_offsets.json,
   per-zone data from docs/zones/encounters) in ACoHEnemySpawner::SpawnEncounter.
2. Gate arrivals: an `Arrive=<gate>` option in ACoHGameMode::ChoosePlayerStart (tag gate starts), so gate starts
   don't make normal spawns random.

## By hand (World Settings of L_ParagonCity)
Runtime partitions "Far" (cell 102400, loading range 204800) and "Ground" (cell 25600, loading range 102400).
Until then the map check reports "invalid runtime grid Ground/Far" and those actors use the main grid.
