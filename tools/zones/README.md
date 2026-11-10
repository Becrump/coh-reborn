# Zone placement tools (one seamless Paragon City)

Plan and current output: `docs/zones/one-world-plan.md`, `docs/zones/zone_offsets.json`.
Set `I24_DATA` to an i24 `data` folder (sparse: maps/city_zones, object_library, tricks).

- `bounds.py ZONE...` - each zone's footprint (1st-99th percentile of placed objects).
- `gates.py ZONE...` - footprint plus zone-gate sign positions (TexWordLayout props) -> gates.json.
- `place.py` - places the inner ring from gates.json by matching gate pairs -> zone_offsets.json.
- `stations.py [city_zones dir]` - original monorail arrival points per zone.
- `spawns.py I24_DATA ZONE OUT.json` - original encounter groups/layouts/slots (zone-local feet).

Axes: all zones share one orientation; map east = game -x, map north = game -z.
