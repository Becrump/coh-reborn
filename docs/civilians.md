# Original civilians and traffic

The original game's pedestrians, cars, boats, helicopters and blimps, run the
way its server ran them. They sit beside the upgraded city life
(`ACoHLifeManager`, the rebuilt Atlas Park), which keeps its own crowds; the
original ones fill every other zone of the ParagonCity world.

## Data: `tools/zones/civilians.py`

    python tools/zones/civilians.py <i24>/data <out>/civilians [zone ...]

Reads, for every zone in `maps/city_zones` (56 have civilians or traffic):

* `server/spawnarea/globals.txt`, then `<zone>.txt` over it: the NPC and Car
  types (costume lists, `MaxActiveEntities`, `RunSpeed` +
  `RunSpeedVariation`, `ScaredType`, `BeaconTypeNumber`), the Generators
  (`MaxActiveEntities` alive at a time, `MaxSpawnCount`, `GeneratedTypes`) and
  the zone's `MaxNPCCount` (people and vehicles together, 600 in most zones).
* Every map object with a `Generator` property (Omni/NPC `NPCGenerator`,
  Omni/CAR `CarGenerator`, boats, helicopters, the blimp, themed generators
  such as `PraetorianNeatNPCGenerator`), including the ones built into
  streetlights and road pieces: the spawn points.
* Every `BasicBeacon` (Omni/NAV): the walking wire. Two beacons link when they
  are within max(r1, r2) + 3 ft (beaconConnection.c).
* Every `TrafficBeacon` (the lane arrows inside road pieces): linked with the
  original rules (ahead within 80 degrees, facing within 120, reached from
  behind within 90, BeaconGroup curve heads, TypeNumber), plus the
  contingency link for arrows with no way on. `KillerBeacon` arrows end a car.

Writes `<out>/civilians/<zone>.json` per zone, `civilians.json` (the index)
and `models.json` (497 civilian and vehicle costumes).

Models: the `civilian_models` stage of `tools/imports/finish_imports.py`
exports those costumes with the character exporter (`coh2unreal.player models
--add --npc-list`), adding them to `out/player/models.json` without
re-exporting the rest. They carry `idle`, `walk`, `run`, `fear` (cower) and
`fear_run` clips (cars: `idle` and `walk`, the wheels turning). The `ue_npcs`
stage imports them to `/Game/CoH/NPCs/<costume>`.

## Game: `ACoHCivilians` (CoHCivilians.h/.cpp)

One per PC, cosmetic and not replicated, like the life manager. Spawned by
the hero on any map but the HQ lobby; it runs only on the ParagonCity world.

* A zone wakes when the camera comes within 300 m of it (its rectangle from
  the zone offsets) and sleeps 30 s after everyone has left; its data loads
  on a worker thread the first time.
* Once a second every generator of a waking zone, in random order, makes one
  entity if it is under its own cap, its type's cap and the zone's
  `MaxNPCCount` (entgenProcess and its limiters). Type and costume are random.
* People start at the nearest wire beacon and walk from beacon to beacon,
  each time a random linked one other than the one they came from, aiming at
  a random point within 3 ft of it (aiNPCMoveWire). They walk at run speed /
  4.8. A person with nowhere to go is removed and the generator makes another.
  Near the camera, a link that a line trace finds blocked is dropped (the
  original only linked beacons with a clear way between them).
* Danger (`ACoHLifeManager::ReportDanger`, called by fights and powers)
  frightens people within its radius: they face it for a second, then turn
  back the way they came. ScaredType 1 (Atlas Park's crowd) keeps walking and
  calms down after 5 s; the others cower, then run for 20 s.
* Vehicles drive the lane arrows at `RunSpeed` (1 ft a tick is 30 ft/s), on a
  curve from arrow to arrow, and vanish at killer arrows or dead ends.
  The monorail type is left out (`SkipTypes`): the monorail runs as its own
  train.
* Only the nearest are drawn, within the original fade distances (270 ft
  people, 950 ft cars; at most 150 people and 60 vehicles), stood on the
  ground with a line trace.

Settings (`[/Script/COHREBORN.CoHCivilians]` in the game ini): `bEnabled`,
`ModernZones` (default `city_01_01`, the rebuilt Atlas Park), `SkipTypes`,
`WakeDistance`, `PeopleDrawDistance`, `CarDrawDistance`, `MaxDrawnPeople`,
`MaxDrawnCars`, `MeshYaw`.

Chat: `/civilians` says how many are about, `/civilians off` and
`/civilians on` switch them on this PC.

Left out for now: the original's anti-island beacon linking, civilians'
emotes and hostage/thank-hero activities (the encounter system has its own),
and line-of-sight for wire links far from the camera.
