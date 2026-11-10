"""Add original models referenced by Atlas layouts but absent from the library."""
import json
import pathlib
import sys
sys.path.insert(0, r'C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal')
from coh2unreal.defs import parse_braces
from coh2unreal.character import main, villain_info
base = pathlib.Path(__file__).parent
data = pathlib.Path(r'C:\Users\rtcru\CoHReborn\i24\data')
plan = json.loads((base / 'atlas_enemy_plan.json').read_text())
missing = [e['missing_model'] for e in plan['errors'] if 'missing_model' in e]
groups = {e['group'].lower() for e in missing if e.get('group')}
explicit = {e['villain'].lower() for e in missing if e.get('villain')}
names = []
for path in sorted((data / 'defs' / 'villains').glob('*.villain')):
    for node in parse_braces(path.read_text(encoding='latin-1')):
        if node.key.lower() != 'villaindef' or not node.args:
            continue
        info = villain_info(node)
        if info['name'].lower() in explicit or (info['group'] or '').lower() in groups:
            names.append(info['name'])
args = ['--data', str(data), '--piggs', r'C:\Users\rtcru\CoHReborn\piggs',
        '--out', r'C:\Users\rtcru\CoHReborn\out\characters', '--all-costumes']
for name in names:
    args += ['--villain', name]
print('EXPORTING', len(names), 'VILLAIN DEFINITIONS', flush=True)
main(args)
