import json,math,hashlib,collections
b='C:/Users/rtcru/CoHReborn/out/'
new=json.load(open(b+'atlas_upgraded/atlas_upgraded_instances.json'))
tiles={(math.floor(r['matrix'][3][0]/400),math.floor(-r['matrix'][3][2]/400)) for r in new}
def signature(r):return hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def protected(r):return any(t in r['path'].lower() for t in ['cityhall','hospital','police','monorail','tram','atlas_statue','ap_statue','ap_cityhall_plaza'])
newprotected={signature(r) for r in new if protected(r)}
original=json.load(open(b+'atlas_park_v5/atlas_park_instances.json'))
oldprotected=[r for r in original if protected(r) and (math.floor(r['matrix'][3][0]/400),math.floor(-r['matrix'][3][2]/400)) in tiles]
missing=[r for r in oldprotected if signature(r) not in newprotected]
report={'protected_source_pieces':len(oldprotected),'missing':len(missing),'missing_paths':list(set(r['path'] for r in missing))[:20],'tiles':len(tiles)}
json.dump(report,open('atlas_overhaul_landmark_audit.json','w'),indent=2)
print(report)
assert not missing,'Protected source geometry changed'
