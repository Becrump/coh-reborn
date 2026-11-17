# Indoor mission maps (2026-11-17)

Door missions now go inside the original game's mission maps (warehouses, offices, caves, sewers, tech labs...).

## Data: `tools/missions/mission_maps.py`

`finish_imports.cmd convert` runs it as the `missions` stage (after `story_game`):

    python tools/missions/mission_maps.py <i24>/data <piggs> <out>/missions [--per 2] [--only id,...] [--list]

- Which maps: every map set and length the hero tasks ask for (`MapSet` + `MapLength`; with no MapSet,
  the sets the villain group can use from `defs/generic/randommapselection.def`), with the layouts listed in
  `maps/missions/mission.mapspecs`. `--per` layouts per set and length (2 by default: 102 picks, about 90
  different layouts, about 15 MB each). Nearest length when a set has none of that length.
- Converts each with `coh2unreal --instanced` into `<out>/missions/<id>/`; the editor markers (Omni
  library: spawn beacons, encounter dummies) are left out of the placements.
- `<out>/missions/missions.json`: map sets, the group-to-set table, and per map: the player start
  (`SpawnLocation _lobby`), the exit, rooms ranked Lobby / Front / Middle / Back by distance from the
  start, every encounter group (its spawn kind and villain spots) and the objective spots (ItemFloor,
  ItemAgainstWall, Person), in Unreal cm local to the map.

Needs the stage*.pigg archives too (the mission trays' models are there).

## Unreal: `tools/missions/import_missions.py`

`finish_imports.cmd unreal` runs it as the `ue_missions` stage: each map becomes a plain level
`/Game/Missions/L_<id>` (not World Partition) using the zones' shared model library (`/Game/Zones/Library`):
stages index, filter, level, meshes, mats, link, place, interior (the original lights, clustered, no
shadows; a post process volume for indoor exposure; a nav mesh bounds volume), save. Resumable:
`<out>/missions/import_state.json`, one line per map in `<out>/missions/import_log.txt`.

## In the game (`CoHStory.h`)

- Using a mission door picks an imported layout (`UCoHStory::PickMap`) and loads it as a level instance
  far below the city (`ACoHMissionMap`, replicated: the host and every client stream the same instance).
  One slot per running mission, 1.5 km apart.
- When it is in, the mission fills: the task's own spawns at encounters of their placement (Front,
  Middle, Back, Lobby), the boss on the group's first spot; then up to 14 more groups of the mission's
  villain group at the map's other mission encounters; objectives at spots of their location kind,
  back rooms first. The hero is moved to the start.
- A white **Exit** post at the map's exit takes the hero back to the door. Finishing completes the task at
  once; the map unloads when the hero leaves. Abandoning inside moves the hero out first.
- No imported layout (or it fails to load in 60 s): the mission plays at the door as before.

## Not yet

Team members joining the mission (teams are next), elevators between floors, unique story-arc maps,
villain-side maps, glowing clues and hostage following.
