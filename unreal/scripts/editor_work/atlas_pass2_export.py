import json,math,subprocess,sys
rows=json.load(open('C:/Users/rtcru/CoHReborn/out/atlas_park_v5/atlas_park_instances.json'))
coords=sorted({(math.floor(r['matrix'][3][0]/400),math.floor(-r['matrix'][3][2]/400)) for r in rows if '/skyline02_' in r['path']})
cmd=json.load(open('atlas_overhaul_export_manifest.json'))['command'];cmd[0]=sys.executable
cmd[cmd.index('--out')+1]='C:/Users/rtcru/CoHReborn/out/atlas_secondpass'
cmd[cmd.index('--name')+1]='atlas_secondpass'
tile_index=cmd.index('--tiles');cmd[tile_index:tile_index+2]=['--tiles='+';'.join('%d,%d'%c for c in coords)]
cmd+=['--drop','skyline02*@-10000,-10000,10000,10000']
json.dump({'tiles':coords,'command':cmd},open('atlas_pass2_export_manifest.json','w'),indent=2)
print('PERIMETER TILES',len(coords),flush=True)
subprocess.run(cmd,cwd='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal',check=True)
