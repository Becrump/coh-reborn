# Paragon City as one seamless world: plan

Date: 2026-11-10. Reference maps: `reference/paragon_city_zones_map_hires.png` (Homecoming, grid A-M / 1-17, used for placement) and `reference/paragon_city_zones_map_labeled.png`.

## Verdict

Yes, one big map works. Unreal 5's World Partition loads only the grid cells near each player and streams the rest in and out, so there are no loading screens and memory stays close to what one zone needs today. Large World Coordinates handle a 30 km world without the jitter older engines had.

Limits to plan for:
- The host loads the area around every player. Seven friends spread over seven zones means seven zones in memory on the host. Fine on a strong PC; later move to a dedicated server.
- Disk and build time grow with every zone (Atlas Park alone is several GB). Build zone by zone, never all at once.
- Original level ranges stop being enforced by loading doors. Keep them as soft rules (warning signs, tougher spawns), as in the original hazard zones.

## Measured zone sizes (original game data)

| Zone | Map file | Size (core, km) |
|---|---|---|
| Atlas Park | city_01_01 | 1.4 x 1.1 |
| Kings Row | city_01_02 | 1.4 x 2.0 |
| Galaxy City | city_01_03 | 1.1 x 1.3 |
| Perez Park | hazard_01_01 | 1.1 x 1.4 |
| Steel Canyon | city_02_01 | 1.1 x 1.9 |
| Skyway City | city_02_02 | 1.5 x 2.4 |

The Homecoming map is close to scale at about 17 m per pixel (its 2000 px view), so the whole city is about 32 x 20 km and the inner ring is about 4 x 8 km.

## Placement

Original zones each have their own coordinates (all centered near 0,0). Each zone gets a world offset read from the zone's box center on the hires map, then nudged so the zone gates line up (e.g. Atlas Park's west gate meets Galaxy City's east side). Offsets go in one table (`zone_offsets.json`) the import scripts read, so moving a zone is a one-line change.

## Gaps between zones

Gaps become "beyond the War Wall": non-playable filler city. The original zones are already ringed by War Walls, so this fits the lore:
- Filler: cheap PCG city blocks (City Sample buildings, HLOD only, no interiors, no traffic), forests or water where the map shows them.
- Barrier: the existing War Walls stay at each zone edge, plus a tall energy field so flyers cannot cross. Zone-to-zone travel goes through the original gates, which become open passages (no loading).
- Later, any filler district can be promoted to a playable zone.

## Monorail

The train becomes a real train running on a visible track through the world, following the light rail lines on the map. The ride level `L_MonorailRide` is no longer needed as a loading screen; keep it only until the real route works.

## Import order

1. Inner ring (yellow line): Galaxy City, Perez Park, Kings Row, Steel Canyon, Skyway City around Atlas Park.
2. Green line: Independence Port, Talos Island, Brickstown, Founders' Falls, Eastgate, Kallisti Wharf.
3. Outer zones: Boomtown, Faultline, Eden, Crey's Folly, Dark Astoria, Croatoa, Peregrine Island; trial zones last.
Galaxy City goes first (smallest neighbor, west of Atlas Park).

## How zones are built (Robert, 2026-11-10)

Recreate each zone as faithfully as possible from the original: buildings, props, enemy placements. Exceptions: plants (to be upgraded), our glass upgrade, and other deliberate upgrades. No civilians for now (that system is being upgraded); cars revisited later. The monorail is the one big change (continuous line). Atlas Park keeps its current map.

## Deliberate upgrades (applied to every zone)

The only planned changes to the original look; everything else stays faithful.

| Upgrade | How it reaches every zone | Status |
|---|---|---|
| Trees and plants | `setup_trees.py` + `docs/zones/tree_replacement.json` | in the import batch |
| Window glass | asset-level glass on the original window materials (`unreal/scripts/glass/glaze_zone.py`) | Atlas done, zones per import |
| Street and parking lamps | `<zone>_props.json` -> modern lamp model + real light (`setup_level.py`) | in the import batch |
| Traffic signals glow and cycle green / amber / red, walk panels show walk / flashing hand | `M_CoH_TrafficSignal` on the original `traffic_light` and `traffic_light_pedestrian` materials (`unreal/scripts/signals/`) | added 2026-11-12 |

## Props stay editable

New zones are not baked into merged tiles. They use the repo converter's `--instanced` export (coh-reborn `coh2unreal/`, the source of truth; the copy in the shared folder is older): every unique original model once in `<zone>.gltf`, plus `<zone>_placements.json` with every placed object. `coh2unreal/unreal/import_instanced.py` places them in Unreal as single actors (rare models) or one instance actor per model (common ones), and points each material slot at the existing tuned material of the same name, so Atlas Park fixes and the glass carry over automatically.

Editing later is by type, not by hand: swap a model's mesh or material once and every copy changes; a replacement table can do this for all zones. Destructible versions work the same way: the prop stays a cheap instance until hit, then that one copy is swapped for a Chaos destructible actor.

Atlas Park's current map is baked per tile, so its props cannot be swapped one by one. Material changes (like the glass) still apply everywhere. To make Atlas props swappable, re-run its export with `--instanced` and `import_instanced.py`.

## Galaxy City import brief (PC session)

Files on the PC: `COHReborn\exports\zones\` - run `join_instanced.cmd`; it unpacks to `instanced\galaxy_city`. (The older `join_and_unzip.cmd` / `join_props.cmd` exports are superseded; their parts can be deleted.) Contents: `galaxy_city.gltf/.bin` + `textures`, `galaxy_city_placements.json`, `galaxy_city_props.json` (street lamps for modern replacement), `galaxy_city_trees.json` (877 trees for modern replacement), lights, sky, `galaxy_city_spawns_gamefeet.json` (original encounter groups and slots, zone-local feet), `zone_offsets.json`, and the usual `setup_level.py` / `apply_tuning.py` / `coh_materials.py`.

1. Build from main first (merged C++). Wait until the glass rollout is finished; do not rebuild materials while it runs.
2. New level `/Game/Zones/GalaxyCity/L_GalaxyCity`. Run `import_instanced.py` with CONTENT = `/Game/Zones/GalaxyCity` and MATERIALS = the Atlas material folder, so shared textures reuse Atlas's tuned and glazed materials. New materials only for Galaxy-only textures; then the glass thread's `glaze_zone.py` on the new ones.
3. Replace trees and street lamps with the modern versions as in Atlas. No civilians. Parked cars are in for now (cars to be revisited).
4. Offset the whole zone by Galaxy's `offset_m` in `zone_offsets.json` (game axes x, z in meters; convert like the importer does: glTF z = -game z).
5. Report: actor count, a screenshot from the Perez Park gate side, memory use. Do not merge into the Atlas map yet; that waits on checking whether the Atlas map uses World Partition.

## Filler between zones (plan, 2026-11-11)

Grid: `docs/zones/filler/filler_grid.json` (250 m cells, world meters in the `zone_offsets.json` frame), made by `tools/zones/filler.py` from the reference map; picture `docs/zones/filler/filler_overlay.jpg`. The city area is about 16.5 x 14 km:

| Cell | Area | Fill |
|---|---|---|
| Placed zones | 76 km² | nothing (playable) |
| Water (ocean, Liberty Harbor, canals) | 36 km² | one water plane, matched to each zone's water height |
| Forest / park (green on the map) | 25 km² | forest filler: Megaplant HLOD trees, no undergrowth |
| City | 71 km² | city filler: City Sample buildings, HLOD only, no interiors, no traffic, heights by district |
| War Wall buffer (one cell around each zone) | 24 km² | low city (2-4 floors) so the wall reads; nothing tall at the wall |

Rules:
- Unplayable: the energy barrier sits on each zone's War Wall line (about 149 km of wall in total, all zone rectangles). Flying over it is blocked. Gates open only where two zones meet (inner ring first).
- Filler is HLOD only, so far away it is one cheap mesh per cell. It never streams in at full detail, so it costs almost no memory.
- The monorail track crosses the filler on its own visible line. Stations are only inside zones.
- Build order: water plane first, then city blocks per district, then forest. Each is one PCG graph that reads `filler_grid.json`, so moving a zone means re-running `place_all.py`, `filler.py` and the graph.
- The grid is only as good as the reference map's colors: hatched zone boxes and the map frame can mislabel a few cells. Fix those by hand in the JSON before building.
