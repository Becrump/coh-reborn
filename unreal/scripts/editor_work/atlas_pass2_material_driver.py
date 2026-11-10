import subprocess,json,time
runner='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts/ue_exec.py'
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
while True:
 state=json.load(open(base+'atlas_pass2_material_state.json'));sources=json.load(open(base+'atlas_pass2_material_sources.json'))
 if state['cursor']>=len(sources):break
 result=subprocess.run(['python',runner,base+'atlas_pass2_material_batch.py','--file'],capture_output=True,text=True)
 print(result.stdout,flush=True)
 assert result.returncode==0 and 'FAILED' not in result.stdout,result.stderr+result.stdout
 time.sleep(2)
print('NEW SOFT MATERIALS COMPLETE',flush=True)
