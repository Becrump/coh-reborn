"""Survey replaceable exterior building groups; never select landmark groups."""
import sys,glob,json,re,itertools
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal')
from coh2unreal import maplayout as ml
from coh2unreal.pigg import AssetStore
from coh2unreal.geo import Geo
b='C:/Users/rtcru/CoHReborn'
s=AssetStore(data_dirs=[b+'/i24/data'],pigg_paths=glob.glob(b+'/piggs/*.pigg'))
lib=ml.Library(s);local,refs=ml.load_map(s,lib,'maps/city_zones/city_01_01/city_01_01_layer_geometry.txt')
cache={};buildings=[]
def bounds(inst):
    if inst.geo not in cache:
        g=Geo(s.read(inst.geo),inst.geo);cache[inst.geo]={m.name.lower().split('__')[0]:m for m in g.models}
    m=cache[inst.geo].get(inst.model.lower().split('__')[0])
    if not m or any(k in inst.model.lower() for k in ['beacon','spawn','cubemap','trigger','window_cube','shadow']):return []
    mat=inst.matrix
    return [[sum(v[k]*mat[k][j] for k in range(3))+mat[3][j] for j in range(3)] for v in itertools.product(*zip(m.min,m.max))]
def walk(name,mat,path,depth):
    if depth>64:return
    key=ml.short_name(name);d=local.get(key) or lib.defs.get(key)
    if not d:return
    if re.fullmatch(r'(?:upgraded_)?deco_skyscraper_\d+|fillershop_[a-z]+|flrn_building_[a-z]+|ind_ware_\d+.*',key) and not any(k in path for k in ['hospital','cityhall','police','plaza']):
        insts,missing=ml.resolve(lib,local,[(name,(0,0,0),(0,0,0))])
        points=[];origins=[]
        for inst in insts:
            inst.matrix=ml.mat_mul(mat,inst.matrix);points+=bounds(inst);origins.append(inst.matrix[3])
        if not points:return
        lo=[min(p[j] for p in points) for j in range(3)];hi=[max(p[j] for p in points) for j in range(3)]
        ol=[min(p[j] for p in origins) for j in range(3)];oh=[max(p[j] for p in origins) for j in range(3)]
        buildings.append({'id':len(buildings),'group':key,'path':path,'matrix':mat,'min':lo,'max':hi,'origin_min':ol,'origin_max':oh,'pieces':len(insts)})
        return
    for child,pos,pyr in d.groups:walk(child,ml.mat_mul(mat,ml.mat_from_pyr(pos,pyr)),path+'/'+ml.short_name(child),depth+1)
for name,pos,pyr in refs:walk(name,ml.mat_from_pyr(pos,pyr),ml.short_name(name),0)
json.dump(buildings,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_sources.json','w'),indent=2)
for r in buildings:
    lo=r['min'];hi=r['max'];print(r['id'],r['group'],'center',*[round((lo[j]+hi[j])/2) for j in [0,2]],'size',*[round(hi[j]-lo[j]) for j in [0,2,1]],'base',round(lo[1]),'pieces',r['pieces'])
