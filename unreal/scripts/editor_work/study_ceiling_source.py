import sys,glob,json,itertools
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal')
from coh2unreal.pigg import AssetStore
from coh2unreal.geo import Geo
b='C:/Users/rtcru/CoHReborn';s=AssetStore(data_dirs=[b+'/i24/data'],pigg_paths=glob.glob(b+'/piggs/*.pigg'));cache={}
rows=json.load(open(b+'/out/atlas_rebuilt_avenue/avenue_instances.json'))
for r in rows:
 if r['geo'] not in cache:cache[r['geo']]=Geo(s.read(r['geo']),r['geo'])
 g=cache[r['geo']];m=next((m for m in g.models if m.name.lower().split('__')[0]==r['model'].lower()),None)
 if not m or not any('clean_pklot' in str(t).lower() for t in m.tex_ids):continue
 mat=r['matrix'];points=[[sum(v[k]*mat[k][j] for k in range(3))+mat[3][j] for j in range(3)] for v in itertools.product(*zip(m.min,m.max))]
 lo=[min(p[j] for p in points) for j in range(3)];hi=[max(p[j] for p in points) for j in range(3)]
 if lo[0]<=1088<=hi[0] and lo[2]<=1200<=hi[2]:print(r['model'],r['path'],r['matrix'][3],lo,hi)
