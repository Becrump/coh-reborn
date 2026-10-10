import sys,glob,json
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal')
from coh2unreal.pigg import AssetStore
from coh2unreal.geo import Geo
b='C:/Users/rtcru/CoHReborn'
s=AssetStore(data_dirs=[b+'/i24/data'],pigg_paths=glob.glob(b+'/piggs/*.pigg'))
p='object_library/city_zones/atlas_park_makeover/ap_cityhall_makeover_01.geo'
g=Geo(s.read(p),p)
for m in g.models:
    print(m.name,m.min,m.max,m.tex_ids)
