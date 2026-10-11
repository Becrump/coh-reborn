# Atlas Park Reborn (PCG rebuild)

Rebuilds Atlas Park in Unreal from scratch with the landscape, the Water
plugin, PCG and the City Sample building kit. The original zone is only used
as a guide (ground heights, streets, parks, ponds, building plots); nothing
from the original game ends up in the level.

## Offline (any Python with numpy/scipy/shapely/opencv)

1. `render_guide.py` (Blender, headless): top-down renders of the converted
   Atlas Park glTF: colour, material id and top/bottom heights.
   `blender -b --factory-startup -P render_guide.py -- atlas_park.gltf <guide dir>`
2. `exr2npy.py` (Blender): EXR renders to numpy.
3. `guide_classify.py <guide dir>`: ground classes (road, paving, grass,
   water, parking, rock), building pixels with height, tree pixels, ground
   height under everything.
4. `atlas_layout.py <guide dir> <out dir>`: the new map. Keeps the old zone
   as the core, replaces the War Wall with a ring boulevard, adds a north
   waterfront district down to a bay (shoreline, piers, inlet) and wooded
   hills around. Writes `heightmap.png` (2017², 1 m), `surface.png`
   (ground mask), `layout.json` and `layout_plan.png`.
5. `plan_lots.py <out dir>`: building lots (original plots plus parcels in
   the new district), the City Sample buildings that fit each lot, lot
   buckets, and planting zones. Needs `buildings_catalog.json` from
   `ue/measure_buildings.py`.

## In the editor (`ue/`, run with `python ue/run.py <step>.py`)

Open `/Game/AtlasReborn/AtlasPark_Reborn` first.

| step | what |
| --- | --- |
| `build_landscape.py` | moves/rescales the landscape and writes the heights |
| `build_ground_material.py` | landscape material from `surface.png` |
| `build_water.py` | bay (ocean, own zone, no far mesh) and the two ponds |
| `measure_buildings.py` | footprint/height of every packed City Sample building |
| `build_zones.py` | lot markers (TargetPoints) and planting zone splines |
| `build_pcg.py` | PCG graphs: buildings per lot bucket, trees and shrubs |
| `check_water.py` | fails if any building footprint (plus margin) touches water |
| `window_lights.py` | City Sample windows dark by day, lit by `MPC_Reborn.Night` |
| `build_lighting.py` | physical daylight and exposure range |
| `save_map.py` | saves the level |

PCG decides which building goes on each lot (random among those that fit
the lot's size and height class), turns it, and spawns it; the planting
graph scatters Megaplant trees and shrubs over the woods and parks.
Re-running `build_pcg.py` regenerates everything.
