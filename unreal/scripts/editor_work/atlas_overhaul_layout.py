"""Fit distinct City Sample designs inside original exterior building plots."""
import json,math,collections
rows=json.load(open('atlas_overhaul_selected.json'))
cat={r['name']:r for r in json.load(open('atlas_overhaul_catalog.json')) if max(r['extent'])>300}
towers=['BPP_Bldg_Hero_Tower_CHJ_A01_N1','BPP_Bldg_Hero_Tower_CHJ_B01_N1','BPP_Bldg_Hero_Tower_CHC_CHD_Modern_A01_N1','BPP_Bldg_Hero_Tower_CHE_B01_N1','BPP_SFC_Ref_N1','BPP_Bldg_Hero_Tower_SFJ_A01_N1']
strips=['BPP_NYAA_Ref_N1','BPP_NYAB_Ref_N1','BPP_NYAC_Ref_N1','BPP_NYAD_Ref_N1','BPP_NYAE_Ref_N1','BPP_NYAF_Ref_N1']
mids=['BPP_Bldg_Hero_NYG_Modern_Square_A01_N1','BPP_CHI_Ref_A1_N1','BPP_Bldg_Hero_CHA_A01_N1']
usage=collections.Counter();plan=[]
for row in rows:
    lo=row['min'];hi=row['max'];w=(hi[0]-lo[0])*30.48;d=(hi[2]-lo[2])*30.48;h=(hi[1]-lo[1])*30.48
    cx=(hi[0]+lo[0])*15.24;cy=-(hi[2]+lo[2])*15.24
    tower='skyscraper' in row['group'];n=3 if tower and max(w,d)/min(w,d)>3 and max(w,d)>18000 else 1
    for part in range(n):
        pw=w/n if w>d else w;pd=d/n if d>w else d
        x=cx+(part-(n-1)/2)*pw if w>d else cx;y=cy+(part-(n-1)/2)*pd if d>w else cy
        if tower:pool=towers
        elif row['group'].startswith('ind_ware'):
            pool=mids+['BPP_Bldg_Hero_Low_SFD_Long_N1']
        elif max(pw,pd)/min(pw,pd)>1.7:pool=strips
        else:pool=mids
        options=[]
        for name in pool:
            a=cat[name];bw=a['extent'][0]*2;bd=a['extent'][1]*2;bh=a['extent'][2]*2
            for yaw in [0,90]:
                fw,fd=(bw,bd) if yaw==0 else (bd,bw)
                scale=min(pw*.89/fw,pd*.89/fd,1.35)
                target=h*(1.05 if tower else 1.55)
                coverage=(fw*fd*scale*scale)/(pw*pd)
                cost=abs(math.log(max(bh*scale,1)/max(target,1)))*.65+(1-coverage)*.7+usage[name]*.045
                if scale<.28:cost+=2
                options.append((cost,name,yaw,scale))
        _,name,yaw,scale=min(options);usage[name]+=1
        plan.append({'source_id':row['id'],'source_group':row['group'],'source_bounds':[lo,hi],'label':'AtlasUpgrade_%03d_%d_%s'%(row['id'],part,row['group']),'path':cat[name]['path'],'name':name,'x':x,'y':y,'ground_hint':max(-1600,lo[1]*30.48),'yaw':yaw,'scale':scale,'plot':[pw,pd],'tower':tower})
json.dump(plan,open('atlas_overhaul_layout.json','w'),indent=2)
print('REPLACEMENTS',len(plan),'TOWERS',sum(p['tower'] for p in plan),'DESIGNS',len(usage))
print(json.dumps(dict(usage),indent=2))
