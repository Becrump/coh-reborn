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
- `atlas_park_lights.json`: the zone's CoH point lights (also in the glTF as
  `KHR_lights_punctual` lights named `omni_<n>`).
- `atlas_park_sky.json`: the zone's time-of-day keys (sun, ambient and fog
  colours, fog distance) and lamp-light hours, from its scene/sky files.
- `masked_materials.json`: the cutout (alpha-tested) materials.
- `setup_level.py`: the Unreal setup script (copied from `unreal/`).

Materials follow each model's CoH trick flags: `FullBright` surfaces glow
(`__GLOW`), `Additive` ones add light (`__ADD`: War Walls, lamp pools,
flares), and `NightLight` ones (lit windows) go into separate
`tile_x_y_night` actors so they can switch on at night. `ReflectTex` and
`Subtractive` layers were fake reflections and shadows and are skipped;
Lumen does those for real.

## Import into Unreal 5.x

1. Copy the whole `out/atlas_park` folder somewhere on the PC running Unreal.
2. In a new level: **File > Import Into Level**, pick `atlas_park.gltf`.
3. Choose a content folder (for example `/Game/AtlasPark`) and accept the
   defaults. Unreal creates one static mesh actor per tile plus materials.
4. In the editor's Cmd box run `py "<out folder>/setup_level.py"`. It
   needs the Python Editor Script Plugin and:
   - sets cutout materials to Masked and `__ADD` ones to Additive;
   - if `turf.json` is present, swaps the lawn materials' texture for a
     real turf set tiled at 1.5 m. Make it with
     `python unreal/make_turf.py <out folder> --source <folder>` from a
     downloaded PBR set (we use ambientCG Grass005, CC0), or without
     `--source` for a generated one;
   - replaces CoH street lamps (listed in `<name>_props.json`) with
     `modern_streetlight.glb` / `modern_parkinglight.glb` (built by
     `unreal/make_streetlights.py` in Blender) and real spotlights;
   - adds sun, sky atmosphere, sky light, height fog, clouds and a Lumen
     post-process volume;
   - spawns the CoH point lights if the import did not create them;
   - builds `/Game/CoH/DayNight`, a looping Level Sequence (one game hour
     per real minute) from the zone's time-of-day keys, played by the
     `DayNightCycle` actor.
   Preview a time in the editor with `py "<out folder>/setup_level.py"
   --hour 21`.

Units are meters. X and height match the game; the game's Z axis is negated
because the game is left-handed and glTF is right-handed. City Hall ends up
near (38, 10, 203) in glTF meters.

## Known limits (first version)

- Materials use only each surface's base texture. The game's blended
  materials (detail textures, multiply layers) are not carried over yet.
- Sky domes (clouds, stars) come from Unreal's sky atmosphere and clouds,
  not the game's sky models.
- Far-distance LOD models and editor-only markers are skipped when the
  game data marks them; anything unmarked is exported.
- Only the Geometry layer is exported by default. Other layers (event
  decorations, doors, NPC spawns) can be passed with `--map`.
