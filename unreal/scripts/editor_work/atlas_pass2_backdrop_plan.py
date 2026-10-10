import json,pathlib,shutil
base=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn');m=json.load(open(base/'atlas_overhaul_manifest.json'));cat=json.load(open(base/'atlas_pass2_catalog.json'))
used={r['name']:r for r in m['buildings']};pool=[]
for i in [1,2,3,4]:pool.append({'name':cat[i]['name'],'path':cat[i]['path'],'dimensions':cat[i]['dimensions'],'new':True})
for name in ['BPP_NYAA_Ref_N1','BPP_NYAB_Ref_N1','BPP_Bldg_Hero_NYG_Modern_Square_A01_N1','BPP_CHI_Ref_A1_N1','BPP_Bldg_Hero_Tower_SFJ_A01_N1','BPP_Bldg_Hero_Tower_CHE_B01_N1']:
 r=used[name];pool.append({'name':name,'path':r['upgraded_prefab'],'dimensions':[(r['bounds'][1][j]-r['bounds'][0][j])/r['final_scale'] for j in range(3)],'new':False})
slots=[]
for k,y in enumerate(range(-35000,85001,11000)):slots.append(('west',-69000,y,90))
for k,y in enumerate(range(-35000,85001,11000)):slots.append(('east',100000,y,90))
for x in range(-55000,90001,11000):slots.append(('top',x,94000,0))
for x in range(-55000,90001,11000):
 if 12000<=x<=55000:continue
 slots.append(('bottom',x,-47000,0))
rows=[]
for i,(side,x,y,yaw) in enumerate(slots):
 design=pool[(i*3+i//7)%len(pool)]
 bw,bd,bh=design['dimensions'];s=min(8000/bw,8000/bd,1.1)
 target_height=[8000,11000,16000,6000,18000,9500,13000][i%7]
 s=min(s,target_height/bh)
 rows.append(dict(design,label='AtlasPass2_Backdrop_%02d_%s'%(i,side),x=x,y=y,yaw=yaw,scale=s,base=2100,side=side))
json.dump(rows,open(base/'atlas_pass2_backdrop_plan.json','w'),indent=2)
print('PERIMETER BUILDINGS',len(rows),'DESIGNS',len({r['name'] for r in rows}))
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/docs/images/atlas-second-pass');out.mkdir(parents=True,exist_ok=True)
for name in ['overview','north-blocks','plaza','skyline','dusk-skyline']:
 shutil.copy2(out.parent/'atlas-upgraded'/(name+'.png'),out/('before-'+name+'.png'))
