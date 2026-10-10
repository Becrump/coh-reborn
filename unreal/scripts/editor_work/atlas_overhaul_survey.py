import json,collections
rows=json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/atlas_park_instances.json'))
print('COUNT',len(rows),'SAMPLE',rows[0])
c=collections.Counter()
for r in rows:
    for p in r['path'].split('/'):
        if any(s in p.lower() for s in ['skyscraper','building','fillershop','cityhall','hospital','police','deco']):c[p]+=1
for k,v in c.most_common():print(k,v)
