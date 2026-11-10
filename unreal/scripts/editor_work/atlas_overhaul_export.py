import json,sys,subprocess,runpy
b='C:/Users/rtcru/CoHReborn'
rows=json.load(open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_sources.json'))
selected=[r for r in rows if r['group']!='fillershop_garage' and r['id'] not in [58,59,60] and not r['group'].startswith('upgraded_') and not (r['group'].startswith('ind_ware') and max(r['max'][j]-r['min'][j] for j in [0,2])>400)]
json.dump(selected,open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_selected.json','w'),indent=2)
cmd=[sys.executable,'-m','coh2unreal','--data',b+'/i24/data','--piggs',b+'/piggs','--map','maps/city_zones/city_01_01/city_01_01_layer_geometry.txt','--out',b+'/out/atlas_upgraded','--name','atlas_upgraded','--tiles','auto']
for r in selected:
    lo=r['origin_min'];hi=r['origin_max'];box=[lo[0]-.1,lo[2]-.1,hi[0]+.1,hi[2]+.1]
    cmd+=['--drop',r['group']+'@'+','.join(str(round(v,3)) for v in box)]
# Keep the existing opened avenue and its small memorial remnants.
cmd+=['--drop','fillershop_a|fillershop_c|fillershop_g@900,750,1030,1030']
for rule in ['warwall_base_door|warwall_shield_door@900,980,1280,1300','tunnel_strt|tunnel_bend|tunnel_blocker|tunnel_6_strt|tunnel_6_bend|_tunnel_trigger|noteleport_box*|_road_crawlblock*@1000,1050,1700,1700','warwall_shield_straight@600,980,800,1060','_nbrhood_wall_panel_32|_warwall_lip*|_warwall_epulse*|_warwall_straight_accnt@512,980,896,1070','warwall_shield_straight@1400,980,1550,1060','_nbrhood_wall_panel_32|_warwall_lip*@1280,980,1664,1070','skyline*|_skyln*@400,980,1800,2000']:
    cmd+=['--drop',rule]
for rule in ['_warwall_straight@512,980,896,1060@28:10','_warwall_straight|_warwall_epulse_straight|_warwall_straight_accnt@1280,980,1664,1060@10:32']:cmd+=['--ruin',rule]
json.dump({'selected_count':len(selected),'command':cmd},open('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_overhaul_export_manifest.json','w'),indent=2)
print('SELECTED',len(selected),flush=True)
subprocess.run(cmd,cwd='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal',check=True)
