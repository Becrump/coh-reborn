import json,pathlib
b=pathlib.Path(__file__).parent;source=json.load(open(b/'atlas_enemy_import_report.json'));p=json.load(open(b/'atlas_enemy_plan.json'));required={r['costume'] for r in p['population']}
catalog={}
for name in sorted(required):
 r=source[name];states={}
 for k,path in r.get('clips',{}).items():
  state=next((s for s in ['idle','run','attack','hit','death'] if k.lower().endswith(s)),None)
  if state:states[state]=path
 if name=='Rikti_Pylon' and r.get('clips'):states['idle']=next(iter(r['clips'].values()))
 catalog[name]={'mesh':r['mesh'],'states':states,'missing_states':[s for s in ['idle','run','attack','hit','death'] if s not in states],'note':'Animation asset mapping only; gameplay transitions and damage events are not implemented.'}
(b/'atlas_enemy_animation_catalog.json').write_text(json.dumps(catalog,indent=2))
r=json.load(open(b/'atlas_enemy_animation_ground_report.json'))
print('Large ground differences',[(k,round(v.get('ground_delta_cm',0)),v['original_location']) for k,v in r.items() if v.get('placement_review')=='height_difference_over_75cm'][:8])
print('Current checkpoint',len(r))
