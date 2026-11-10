# Zone placement tools (one seamless Paragon City)

Plan and current output: `docs/zones/one-world-plan.md`, `docs/zones/zone_offsets.json`.
Set `I24_DATA` to an i24 `data` folder (sparse: maps/city_zones, object_library, tricks).

- `bounds.py ZONE...` - each zone's footprint (1st-99th percentile of placed objects).
- `gates.py ZONE...` - footprint plus zone-gate sign positions (TexWordLayout props) -> gates.json.
- `place.py` - places the inner ring from gates.json by matching gate pairs -> zone_offsets.json.
- `stations.py [city_zones dir]` - original monorail arrival points per zone.
- `spawns.py I24_DATA ZONE OUT.json` - original encounter groups/layouts/slots (zone-local feet).

Axes: all zones share one orientation; map east = game -x, map north = game -z.

## Converting all zones unattended (no Claude needed)

`convert_all_zones.cmd` (Windows, double-click) runs `convert_all_zones.py` over every zone in its list:
repo converter with `--instanced`, original parked cars left out, trees listed for replacement, original
enemy spawn points exported. It clones a sparse i24 and downloads the game archives on first run.
Each zone lands in `zones/<id>_<name>/`; `convert_log.txt` and `status.json` record OK/FAIL per zone.
Finished zones are skipped on re-run, so re-running retries only failures (`--redo` forces, `--only id,id` limits).
On Robert's PC it lives in `COHReborn\exports\zones\` next to `converter_kit.zip` (this repo's `coh2unreal/` + `tools/zones/`).
