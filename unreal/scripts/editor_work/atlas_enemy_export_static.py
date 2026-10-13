"""Export the original health-state library geometry used by the PPD car."""
import glob
import json
import pathlib
import sys
sys.path.insert(0, r'C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal')
from coh2unreal import maplayout as ml
from coh2unreal.pigg import AssetStore
from coh2unreal.export import Exporter

base = pathlib.Path(__file__).parent
root = pathlib.Path(r'C:\Users\rtcru\CoHReborn\out\characters')
tree = json.loads((base / 'atlas_enemy_source_tree.json').read_text())['defs']
store = AssetStore([r'C:\Users\rtcru\CoHReborn\i24\data'], glob.glob(r'C:\Users\rtcru\CoHReborn\piggs\*.pigg'))
lib = ml.Library.__new__(ml.Library)
lib.store, lib.defs, lib.geo_for, lib.tricks, lib.materials = store, {}, {}, {}, {}
loaded, visited = set(), set()
def ensure(name):
    key = ml.short_name(name)
    if key in visited:
        return
    visited.add(key)
    source = tree[key]['source']
    sources = [source]
    if source.endswith('.txt') and source[:-4] + '.rootnames' in store:
        sources = [source[:-4] + '.rootnames', source]
    for path in sources:
        if path in loaded:
            continue
        loaded.add(path)
        geo = path[:-len('.rootnames')] + '.geo' if path.endswith('.rootnames') else path[:-4] + '.geo'
        for d in ml.parse_group_file(store.read(path).decode('latin-1'), path)[0]:
            lib._add(d)
            lib.geo_for.setdefault(d.name.lower(), geo)
            if d.obj:
                lib.geo_for.setdefault(d.obj.lower(), geo)
    for child, _, _ in tree[key]['groups']:
        ensure(child)

ensure('PPD_SquadCar')
instances, missing = ml.resolve(lib, {}, [('PPD_SquadCar', (0,0,0), (0,0,0))])
assert not missing, missing
folder = root / 'objects' / 'PPD_SquadCar'
export = Exporter(store, lib, str(folder))
for instance in instances:
    export.add(instance)
export.write('PPD_SquadCar')
path = folder / 'PPD_SquadCar.gltf'
g = json.loads(path.read_text())
primitives = [p for m in g['meshes'] for p in m['primitives']]
assert primitives
g['meshes'] = [{'name': 'PPD_SquadCar', 'primitives': primitives}]
g['nodes'] = [{'name': 'PPD_SquadCar', 'mesh': 0}]
g['scenes'][0]['nodes'] = [0]
path.write_text(json.dumps(g))
index = json.loads((root / 'index.json').read_text())
entry = {'costume': 'PPD_SquadCar', 'gltf': str(path.relative_to(root)).replace('\\','/'),
         'parts': ['OriginalLibraryPiece'], 'clips': [], 'skeleton': None, 'asset_type': 'StaticMesh',
         'group': 'Objects', 'villains': ['Objects_PPD_Car'], 'ranks': ['Destructible'],
         'level_min': 1, 'level_max': 54, 'source_library_piece': 'PPD_SquadCar'}
index = [e for e in index if e['costume'] != entry['costume']] + [entry]
(root / 'index.json').write_text(json.dumps(index, indent=1))
print('ORIGINAL PPD CAR', len(instances), 'pieces', len(primitives), 'material groups')
