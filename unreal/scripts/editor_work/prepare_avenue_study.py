"""Remove three storefronts on the avenue, retaining all other tile geometry."""
import subprocess,sys
b='C:/Users/rtcru/CoHReborn'
cmd=[sys.executable,'-m','coh2unreal','--data',b+'/i24/data','--piggs',b+'/piggs','--map','maps/city_zones/city_01_01/city_01_01_layer_geometry.txt','--out',b+'/out/atlas_rebuilt_avenue','--name','avenue','--drop','fillershop_a|fillershop_c|fillershop_g@900,750,1030,1030','--tiles','auto']
for rule in ['warwall_base_door|warwall_shield_door@900,980,1280,1300','tunnel_strt|tunnel_bend|tunnel_blocker|tunnel_6_strt|tunnel_6_bend|_tunnel_trigger|noteleport_box*|_road_crawlblock*@1000,1050,1700,1700','warwall_shield_straight@600,980,800,1060','_nbrhood_wall_panel_32|_warwall_lip*|_warwall_epulse*|_warwall_straight_accnt@512,980,896,1070','warwall_shield_straight@1400,980,1550,1060','_nbrhood_wall_panel_32|_warwall_lip*@1280,980,1664,1070']:
    cmd+=['--drop',rule]
for rule in ['_warwall_straight@512,980,896,1060@28:10','_warwall_straight|_warwall_epulse_straight|_warwall_straight_accnt@1280,980,1664,1060@10:32']:
    cmd+=['--ruin',rule]
cmd+=['--drop','skyline*|_skyln*@400,980,1800,2000']
subprocess.run(cmd,cwd='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal',check=True)
