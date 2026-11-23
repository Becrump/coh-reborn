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

## Mission variety (2026-11-23)

`story_game.py` now reads each mission spawn's included encounter (`spawnincs.json`, the original's
`SpawnDefs/TaskIncluded/MissionMap/*.spawninc`) and exports per spawn:

- `kind`: **rescue** (a `LeadToPlace` script, succeed on rescue), **escort** (`LeadToPlace`, succeed on
  delivery), **ambush** (`WaveAttackEncounter`), **destroy** (an object villain such as
  `Objects_Exploding_Crate_Warehouse`) or **fight**. In the Paragon City tasks: 165 ambushes, 100 rescues,
  50 escorts, 123 destroy spawns, about 3,100 fights.
- `actors`: the encounter's villain slots (role foe / hostage / object, villain or group and rank, name,
  number, and the team sizes it appears for), with the task's vars filled in.
- `objective` (the spawn's own objective name, its text, reward line and clues), `create_on` and
  `activate_on` (CreateOnObjectiveComplete / ActivateOnObjectiveComplete triggers).

Objectives to click gained `placement` (the room the original asks for), `delay` (InteractDelay
seconds), `desc`, `activate_on` and `clues`. Missions gained `fail_with`. Tasks gained `clues` (begin,
complete, return: AddClues, RemoveClues, SouvenirClue), and the file gained `clues` (the ClueDefs, keyed
`<task or arc file>#<clue>`) and `souvenirs` (souvenirs.json). 1,528 clues and 284 souvenirs.

In the game (`ACoHStoryDirector`, `CoHStory.cpp`):

- Each copy of a task spawn is a **run**. It is placed when the mission fills, or once an objective it
  waits for is done. A trigger that only one of the original's mission scripts could fire places it at
  once (an ambush: after the first objective). A run never keeps a mission stuck: when everything else
  is done, waiting runs come anyway.
- Encounters put out the original's actors for the **team size** (MinimumHeroesRequired /
  MaximumHeroesRequired), so a team of four meets more than a solo hero.
- **Hostages** stand among their captors (a story NPC with the hostage's villain model when it is
  imported, else a marker). E on a hostage once the captors near it are down frees it and it follows
  that hero. A rescue completes then; an escort completes when the hostage reaches the exit (or the door
  outdoors). A teammate can take the lead with E. Hostages can't be hurt yet, so CanFailWith is not used.
- **Ambushes** shout "Ambush!" and run at the hero when they come.
- **Destroy**: the object spawns as a villain when its model exists; otherwise a marker stands in that
  is smashed with E.
- Objectives to click go to the room the original names, can wait for another objective, and take
  their InteractDelay seconds (step away and it is interrupted).
- The mission completes by **CanCompleteWith**: any one line whose names are all done
  (DefeatAllVillains, DefeatAllVillainsInEndRoom = the Back room's spawns, objectives and spawns by
  name). Names of scripts we can't run are left out; a line of only those means defeat all and finish
  every objective.
- **Clues and souvenirs** are kept in the hero record (`story.Clues`, `story.Souvenirs`) and announced
  when gained. `/clues` and `/souvenirs` in chat list them (a clue window comes with the UI windows).

## Not yet

Elevators between floors, unique story-arc maps, villain-side maps, hostages that villains attack
(and missions that fail when they fall), timed missions, the original's mission scripts (cut scenes,
boss health triggers), and a clue window.
