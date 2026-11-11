# Per-zone source data (from the batch converter)

One folder per converted zone (`<map id>_<name>`), copied from `exports/zones/zones/` on Robert's PC
(converter run 2026-11-10, `tools/zones/convert_all_zones.py`). Zone-local coordinates; see
`docs/zones/zone_offsets.json` for world placement.

- `<name>_trees.json` - every original tree (model + transform), to be replaced by modern trees.
- `<name>_props.json` - street lamps and similar props listed for modern replacement.
- `<name>_spawns_gamefeet.json.gz` - original enemy encounter groups, layouts and spawn slots, in
  zone-local game feet (gzip; `python -c "import gzip,json; json.load(gzip.open(path))"`).

The models, placements and textures themselves are too big for git and stay on the PC.
