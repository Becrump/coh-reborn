"""Resolve original Atlas encounters into a deterministic one-player preview.

Keeps alternative spawn definitions and source transforms for later runtime use.
Never combines seasonal event layers with the normal city population.
"""
import collections
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, r'C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal')
from coh2unreal import maplayout as ml
from coh2unreal.defs import parse_braces
from coh2unreal.export import ue_transform

BASE = pathlib.Path(__file__).parent
DATA = pathlib.Path(r'C:\Users\rtcru\CoHReborn\i24\data')
source = json.loads((BASE / 'atlas_enemy_source_tree.json').read_text())
defs = source['defs']
index = json.loads(pathlib.Path(r'C:\Users\rtcru\CoHReborn\out\characters\index.json').read_text())
sites, errors, population, effects = [], [], [], []
villain_defs = []
for villain_file in sorted((DATA / 'defs' / 'villains').glob('*.villain')):
    for villain in parse_braces(villain_file.read_text(encoding='latin-1')):
        if villain.key.lower() == 'villaindef' and villain.args:
            villain_defs.append((villain, str(villain_file.relative_to(DATA))))
by_group_rank = collections.defaultdict(list)
by_name = {}
for villain, filename in villain_defs:
    by_group_rank[((villain.arg('VillainGroup') or '').lower(),
                   (villain.arg('Rank') or '').lower())].append((villain, filename))
    by_name[villain.args[0].lower()] = (villain, filename)

def stable(text):
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)

def collect(name, matrix, path, site=None, depth=0):
    if depth > 64:
        raise RuntimeError('Encounter hierarchy exceeds 64 levels: ' + path)
    key = ml.short_name(name)
    d = defs.get(key)
    if not d:
        errors.append({'path': path, 'missing_definition': name})
        return
    props = d['props']
    if 'encountergroup' in props:
        site = {'id': hashlib.sha256(path.encode()).hexdigest()[:14],
                'path': path, 'source': d['source'], 'matrix': matrix,
                'properties': dict(props), 'layouts': [], 'positions': {}}
        sites.append(site)
    if site is not None:
        if any(k.startswith('canspawn') for k in props):
            site['layouts'].append({'path': path, 'properties': dict(props)})
        if 'encounterposition' in props:
            pos = props['encounterposition']
            loc, rot, scale = ue_transform(matrix)
            value = {'location': loc, 'rotation': rot, 'scale': scale, 'source_path': path}
            if pos in site['positions']:
                # Distinct layouts can legitimately reuse numbered locations.
                site['positions'][pos].append(value)
            else:
                site['positions'][pos] = [value]
    for n, (child, pos, pyr) in enumerate(d['groups']):
        collect(child, ml.mat_mul(matrix, ml.mat_from_pyr(pos, pyr)),
                path + '/' + str(n) + ':' + ml.short_name(child), site, depth + 1)

for name, pos, pyr in source['refs']:
    if name.lower() not in ('grp_makeover_spawndefs', 'grp_spawndefs'):
        continue
    collect(name, ml.mat_from_pyr(pos, pyr), name)

def number(node, key, default):
    try:
        return int(node.arg(key, str(default)))
    except (TypeError, ValueError):
        return default

def eligible(actor):
    return (number(actor, 'ExactHeroesRequired', 1) == 1 and
            number(actor, 'MinimumHeroesRequired', 1) <= 1 and
            number(actor, 'MaximumHeroesRequired', 99) >= 1)

cache = {}
for site in sites:
    alternatives = []
    for layout in site['layouts']:
        alternatives.extend((layout['path'], v) for k, v in layout['properties'].items()
                            if k.startswith('canspawn') and v.lower().endswith('.spawndef'))
    site['spawn_alternatives'] = [v for _, v in alternatives]
    if not alternatives:
        continue
    layout_path, rel = sorted(alternatives)[stable(site['id']) % len(alternatives)]
    disk = DATA / 'scripts.loc' / rel.lower()
    if not disk.is_file():
        errors.append({'site': site['id'], 'missing_spawn': str(disk)})
        continue
    if rel not in cache:
        parsed = parse_braces(disk.read_text(encoding='latin-1'))
        cache[rel] = next((n for n in parsed if n.key.lower() == 'spawndef'), None)
    spawn = cache[rel]
    if not spawn:
        errors.append({'site': site['id'], 'unparsed_spawn': rel})
        continue
    site['selected_spawn'] = rel
    site['level_min'] = number(spawn, 'VillainMinLevel', 1)
    site['level_max'] = number(spawn, 'VillainMaxLevel', site['level_min'])
    site['actors'] = []
    site['team_min'] = number(spawn, 'MinTeamSize', 1)
    site['team_max'] = number(spawn, 'MaxTeamSize', 8)
    if not site['team_min'] <= 1 <= site['team_max']:
        site['preview_excluded_reason'] = 'Outside one-player preview team range'
        continue
    variables = {v.args[0].lower(): [a for a in v.args[1:] if a != '=']
                 for v in spawn.all('var') if len(v.args) > 1}
    for n, actor in enumerate(spawn.all('Actor')):
        if not eligible(actor) or (actor.arg('Type') or '').lower() != 'evillain':
            continue
        location = actor.arg('Location')
        positions = [p for p in site['positions'].get(location, [])
                     if p['source_path'].startswith(layout_path + '/')]
        if not positions:
            positions = site['positions'].get(location, [])
        if len(positions) != 1:
            errors.append({'site': site['id'], 'actor': actor.arg('ActorName'),
                           'location': location, 'position_count': len(positions), 'spawn': rel})
            continue
        group = actor.arg('VillainGroup')
        rank = actor.arg('VillainType')
        explicit = actor.arg('Villain') or actor.arg('VillainDef')
        if explicit and explicit.lower() in variables:
            values = variables[explicit.lower()]
            explicit = values[stable(site['id'] + ':var:' + str(n)) % len(values)]
        allowed = {}
        possible = ([by_name[explicit.lower()]] if explicit and explicit.lower() in by_name
                    else by_group_rank.get(((group or '').lower(), (rank or '').lower()), []))
        for villain, villain_file in possible:
            if explicit and villain.args[0].lower() != explicit.lower():
                continue
            if group and (villain.arg('VillainGroup') or '').lower() != group.lower():
                continue
            if rank and (villain.arg('Rank') or '').lower() != rank.lower():
                continue
            levels = villain.all('Level')
            if site['level_min'] == site['level_max'] == 0 and levels:
                # Preserve the zero sentinel in the manifest. A visual preview
                # uses the definition's lowest explicit costume level.
                levels = [min(levels, key=lambda l: int(l.args[0]))]
            elif explicit and levels and not any(site['level_min'] <= int(l.args[0]) <= site['level_max'] for l in levels):
                # An explicit entity can request a level outside its costume
                # table (Atlas pylon requests 1, table starts at 5). The preview
                # keeps the requested range and uses the nearest costume row.
                levels = [min(levels, key=lambda l: abs(int(l.args[0]) - site['level_min']))]
            for level in levels:
                level_number = int(level.args[0]) if level.args else -1
                if not explicit and site['level_max'] != 0 and not site['level_min'] <= level_number <= site['level_max']:
                    continue
                costumes = level.get('Costumes')
                for costume in costumes.args if costumes else []:
                    allowed.setdefault(costume.lower(), []).append({
                        'villain': villain.args[0], 'source': villain_file,
                        'level': level_number,
                        'ally': villain.arg('Ally'),
                        'rank': villain.arg('Rank'),
                        'powers': [p.args for p in villain.all('Power')]})
        candidates = [e for e in index
                      if e['costume'].lower() in allowed
                      and (not explicit or explicit.lower() in [v.lower() for v in e.get('villains', [])])
                      and (not group or e.get('group', '').lower() == group.lower())
                      and (not rank or rank.lower() in [r.lower() for r in e.get('ranks', [])])]
        if not candidates:
            if explicit == 'Objects_Surface_Fire_Weak_Unselectable':
                effects.append({'id': site['id'] + '_' + str(n), 'encounter_id': site['id'],
                                'villain': explicit, 'spawn': rel,
                                'actor_properties': {c.key: c.args for c in actor.children},
                                **positions[0]})
                continue
            errors.append({'site': site['id'], 'missing_model': {'group': group, 'rank': rank, 'villain': explicit}, 'spawn': rel})
            continue
        entry = sorted(candidates, key=lambda e: e['costume'])[stable(site['id'] + ':' + str(n)) % len(candidates)]
        identities = allowed[entry['costume'].lower()]
        identity = identities[stable(site['id'] + ':identity:' + str(n)) % len(identities)]
        count = number(actor, 'Number', 1)
        if count != 1:
            errors.append({'site': site['id'], 'unsupported_actor_count': count, 'spawn': rel})
            continue
        row = {'id': site['id'] + '_' + str(n), 'encounter_id': site['id'],
               'costume': entry['costume'], 'group': entry.get('group'), 'rank': rank or identity.get('rank'),
               'selected_villain': identity,
               'villains': entry.get('villains', []), 'level_min': site['level_min'],
               'level_max': site['level_max'], 'spawn': rel,
               'actor_name': actor.arg('ActorName'), 'location_number': location,
               'inactive_ai': actor.arg('AI_InActive'),
               'ally': actor.arg('Ally') or identity.get('ally'),
               'vision_phases': (actor.get('VisionPhases').args if actor.get('VisionPhases') else []),
               'exclusive_vision_phase': actor.arg('ExclusiveVisionPhase'),
               'actor_properties': {c.key: c.args for c in actor.children},
               'spawn_properties': {c.key: c.args for c in spawn.children if c.key.lower() != 'actor'},
               'spawn_probability': int(site['properties'].get('spawnprobability', '100')),
               **positions[0]}
        population.append(row)
        site['actors'].append(row['id'])

result = {'source_map': 'maps/city_zones/city_01_01/city_01_01.txt',
          'preview_team_size': 1, 'selection': 'deterministic alternatives; all sites shown for layout review; runtime spawn probabilities retained',
          'sites': sites, 'population': population, 'effects': effects, 'errors': errors,
          'summary': {'sites': len(sites), 'enemies': len(population),
                      'groups': dict(collections.Counter(r['group'] for r in population)),
                      'costumes_used': len(set(r['costume'] for r in population)), 'effects': len(effects), 'errors': len(errors)}}
(BASE / 'atlas_enemy_plan.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result['summary']))
print('ISSUES', json.dumps(errors[:12]))
