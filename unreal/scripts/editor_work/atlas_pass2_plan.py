import json,pathlib,collections
b='C:/Users/rtcru/ClaudeProjects/COHReborn/'
m=json.load(open(b+'atlas_overhaul_manifest.json'));cat=json.load(open(b+'atlas_pass2_catalog.json'))
changes={'AtlasUpgrade_037_1_deco_skyscraper_06':4,'AtlasUpgrade_072_0_deco_skyscraper_06':3,'AtlasUpgrade_040_0_deco_skyscraper_14':1,'AtlasUpgrade_008_0_fillershop_e':2,'AtlasUpgrade_104_0_fillershop_a':2,'AtlasUpgrade_029_0_ind_ware_12_final':4,'AtlasUpgrade_079_0_flrn_building_b':2}
plan=[]
for r in m['buildings']:
 if r['label'] in changes:
  item=dict(r);item['new_path']=cat[changes[r['label']]]['path'];item['candidate_index']=changes[r['label']];plan.append(item)
json.dump(plan,open(b+'atlas_pass2_changes.json','w'),indent=2)
old=json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/atlas_park_instances.json'));new=json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_secondpass/atlas_secondpass_instances.json'))
import hashlib,math
def key(r):return hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
coords={tuple(c) for c in json.load(open(b+'atlas_pass2_export_manifest.json'))['tiles']}
protected=[r for r in old if any(t in r['path'].lower() for t in ['cityhall','hospital','police','monorail','tram','atlas_statue','ap_statue','ap_cityhall_plaza']) and (math.floor(r['matrix'][3][0]/400),math.floor(-r['matrix'][3][2]/400)) in coords]
newkeys={key(r) for r in new};missing=[r['path'] for r in protected if key(r) not in newkeys]
assert not missing,missing
assert not any('/skyline02_' in r['path'] for r in new)
json.dump({'protected_pieces':len(protected),'missing':missing,'perimeter_tiles':len(coords),'skyline02_remaining_in_export':0},open(b+'atlas_pass2_source_audit.json','w'),indent=2)
print('CHANGES',len(plan),'CIVIC SOURCE AUDIT',len(protected),'missing',len(missing))
