# coh-reborn

Tools for bringing City of Heroes zones into Unreal Engine 5.8.

- `coh2unreal/` - converter: CoH geometry/textures (.pigg + i24 data) -> glTF for Unreal import

Game data lives outside this repo in `%USERPROFILE%\CoHReborn`:
- `i24/` - clone of https://github.com/Thunderspies/i24
- `piggs/` - archives from https://dists.thunderspy.org/piggs/

Convert Atlas Park:

    python -m coh2unreal --data %USERPROFILE%\CoHReborn\i24\data --piggs %USERPROFILE%\CoHReborn\piggs --map maps/city_zones/city_01_01/city_01_01_layer_geometry.txt --out out\atlas_park --name atlas_park
