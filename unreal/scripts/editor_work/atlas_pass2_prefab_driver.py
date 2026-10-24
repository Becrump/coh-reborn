import subprocess,json,time,os
runner='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts/ue_exec.py';base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
while not os.path.exists(base+'atlas_pass2_prefab_state.json') or json.load(open(base+'atlas_pass2_prefab_state.json'))['cursor']<8:
 r=subprocess.run(['python',runner,base+'atlas_pass2_prefab_batch.py','--file'],capture_output=True,text=True)
 print(r.stdout,flush=True);assert r.returncode==0 and 'FAILED' not in r.stdout,r.stdout+r.stderr
 time.sleep(2)
print('PREFABS COMPLETE',flush=True)
