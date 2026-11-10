"""Export expansion infrastructure with its ten legacy building groups removed."""
from pathlib import Path
import re, subprocess, sys, json
base=Path('C:/Users/rtcru/CoHReborn')
src=base/'expansion/data/maps/expansion/atlas_expansion_block.txt'
dest=base/'expansion/data/maps/expansion/atlas_rebuilt_block.txt'
names={'fillershop_a','ind_ware_08_ware_final','deco1','ot_house_lrg','ind_ware_07_final','deco_skyscraper_14','fillershop_c','fillershop_j','ind_ware_12_final','flrn_building_b'}
text=src.read_text()
removed=[]
def filter_group(m):
    name=m.group(1).split('/')[-1].lower()
    if name in names:
        removed.append(m.group(0)); return ''
    return m.group(0)
text=re.sub(r'\tGroup ([^\n]+)\n.*?\tEnd\n',filter_group,text,flags=re.S)
assert len(removed)==10, len(removed)
dest.write_text(text)
Path('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_removed_groups.txt').write_text(''.join(removed))
cmd=[sys.executable,'-m','coh2unreal','--data',str(base/'expansion/data'),'--data',str(base/'i24/data'),'--piggs',str(base/'piggs'),'--map','maps/expansion/atlas_rebuilt_block.txt','--out',str(base/'out/atlas_rebuilt_block'),'--name','rebuilt']
print('Removing only these building groups:',sorted(names),flush=True)
subprocess.run(cmd,cwd='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/coh2unreal',check=True)
