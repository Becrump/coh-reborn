import glob
import json
import pathlib
import sys
sys.path.insert(0, r'C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal')
from coh2unreal.character import GameData, export_npc
root = pathlib.Path(r'C:\Users\rtcru\CoHReborn\out\characters')
gd = GameData(r'C:\Users\rtcru\CoHReborn\i24\data', glob.glob(r'C:\Users\rtcru\CoHReborn\piggs\*.pigg'))
index = json.loads((root / 'index.json').read_text())
for entry in index:
    if entry['costume'] != 'Rikti_Pylon':
        continue
    folder = (root / entry['gltf']).parent
    result = export_npc(gd, entry['costume'], str(folder))
    entry['parts'], entry['clips'], entry['skeleton'] = result['parts'], result['clips'], result['skeleton']
    gltf = json.loads((root / entry['gltf']).read_text())
    models = [n['extras']['cohModel'] for n in gltf['nodes'] if 'mesh' in n]
    assert not any('_lod' in n.lower() for n in models)
    assert gltf.get('images'), 'Native pylon textures missing'
    print('VALIDATED', entry['costume'], len(models), 'parts', len(gltf['images']), 'textures')
(root / 'index.json').write_text(json.dumps(index, indent=1))
