import json,collections,pathlib
b=pathlib.Path(__file__).parent;p=json.load(open(b/'atlas_enemy_plan.json'));l=json.load(open(b/'atlas_enemy_import_report.json'))
clusters=collections.defaultdict(list);missing=[]
for r in p['population']:
 clusters[tuple(round(v,1) for v in r['location'])].append(r)
 if not any(k.lower().endswith('idle') for k in l[r['costume']].get('clips',{}).keys()) and l[r['costume']].get('asset_type')!='StaticMesh':missing.append(r)
dups=[{'location':k,'actors':[(r['id'],r['group'],r['spawn'],r['exclusive_vision_phase'],r['vision_phases']) for r in rows]} for k,rows in clusters.items() if len(rows)>1]
report={'coincident_locations':dups,'without_idle':dict(collections.Counter(r['costume'] for r in missing))}
(b/'atlas_animation_placement_source_audit.json').write_text(json.dumps(report,indent=2));print('Coincident positions',len(dups),'no idle actors',len(missing));print('No idle costumes',report['without_idle']);print('Sample overlaps',dups[:2])
