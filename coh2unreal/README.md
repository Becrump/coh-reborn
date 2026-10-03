# coh2unreal

Exports a City of Heroes zone (map layout, models, textures) to glTF 2.0 so it
can be imported into Unreal Engine. Written from the formats in the
Thunderspies/CityOfHeroes source. It is pure Python 3; Pillow is needed only
for textures (`python -m pip install pillow`).

## Inputs

1. The i24 text data: `git clone --depth 1 https://github.com/Thunderspies/i24`
2. The asset archives (.pigg) from https://dists.thunderspy.org/piggs/
   (the same files `i24/tools/fetch_data.ps1` downloads). The tool reads
   .pigg files directly, so Pig.exe is not needed.

## Export Atlas Park

```
python -m coh2unreal --data i24/data --piggs path/to/piggs \
    --map maps/city_zones/city_01_01/city_01_01_layer_geometry.txt \
    --out out/atlas_park --name atlas_park
```

Outputs in `out/atlas_park/`:

- `atlas_park.gltf` + `atlas_park.bin` + `textures/*.png`: the whole zone,
  merged into 400 ft tiles (one Unreal actor per tile).
- `atlas_park_instances.json`: every placed object with its game-space
  transform (feet), for rebuilding the zone piece by piece later.
- `atlas_park_report.txt`: anything that could not be found.

## Import into Unreal 5.x

1. Copy the whole `out/atlas_park` folder somewhere on the PC running Unreal.
2. In a new level: **File > Import Into Level**, pick `atlas_park.gltf`.
3. Choose a content folder (for example `/Game/AtlasPark`) and accept the
   defaults. Unreal creates one static mesh actor per tile plus materials.

Units are meters. X and height match the game; the game's Z axis is negated
because the game is left-handed and glTF is right-handed. City Hall ends up
near (38, 10, 203) in glTF meters.

## Known limits (first version)

- Materials use only each surface's base texture. The game's blended
  materials (detail textures, multiply layers) and lighting are not carried
  over yet.
- Far-distance LOD models and editor-only markers are skipped when the
  game data marks them; anything unmarked is exported.
- Only the Geometry layer is exported by default. Other layers (event
  decorations, doors, NPC spawns) can be passed with `--map`.
