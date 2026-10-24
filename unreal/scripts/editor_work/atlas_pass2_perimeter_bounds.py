import sys,glob,json,itertools
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal')
from coh2unreal.pigg import AssetStore
from coh2unreal.geo import Geo
s=AssetStore(data_dirs=['C:/Users/rtcru/CoHReborn/i24/data'],pigg_paths=glob.glob('C:/Users/rtcru/CoHReborn/piggs/*.pigg'))
rows=json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/atlas_park_instances.json'));cache={};groups={}
for r in rows:
 if '/skyline02_' not in r['path']:continue
 if r['geo'] not in cache:cache[r['geo']]={m.name.lower().split('__')[0]:m for m in Geo(s.read(r['geo']),r['geo']).models}
 model=cache[r['geo']].get(r['model'].lower().split('__')[0]);assert model,r['model']
 points=[];t=r['matrix']
 for v in itertools.product(*zip(model.min,model.max)):
  p=[sum(v[k]*t[k][j] for k in range(3))+t[3][j] for j in range(3)]
  points.append([p[0]*30.48,-p[2]*30.48,p[1]*30.48])
 group=r['path'].rsplit('/',1)[0];groups.setdefault(group,[]).extend(points)
out=[]
for path,pts in groups.items():
 lo=[min(p[j] for p in pts) for j in range(3)];hi=[max(p[j] for p in pts) for j in range(3)]
 out.append({'path':path,'bounds':[lo,hi]});print(path.rsplit('/',1)[-1],[round(v/100) for v in lo],[round(v/100) for v in hi])
json.dump(out,open('atlas_pass2_perimeter_bounds.json','w'),indent=2)
