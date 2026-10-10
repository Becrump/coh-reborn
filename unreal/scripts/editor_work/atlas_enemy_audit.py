import sys,json
sys.path.insert(0,r'C:\Users\rtcru\ClaudeProjects\coh-reborn\coh2unreal')
from coh2unreal.pigg import AssetStore
from coh2unreal import maplayout as ml
s=AssetStore([r'C:\Users\rtcru\CoHReborn\i24\data']);l=ml.Library(s);d,refs=ml.load_map(s,l,'maps/city_zones/city_01_01/city_01_01.txt')
print('LIB',len(l.defs),'LOCAL',len(d),'REFS',len(refs));print('EGN',[(k,v.props,v.groups[:3],v.source) for k,v in l.defs.items() if k.startswith('egn_clockwork_l8_10')][:3]);print('LOCALGROUP',[(k,v.props) for k,v in d.items() if 'encountergroup' in v.props][:3]);print('REFS',refs[:5]);json.dump({'defs':{k:{'name':v.name,'groups':v.groups,'props':v.props,'source':v.source} for k,v in {**l.defs,**d}.items()},'refs':refs},open(r'C:\Users\rtcru\ClaudeProjects\COHReborn\atlas_enemy_source_tree.json','w'))
