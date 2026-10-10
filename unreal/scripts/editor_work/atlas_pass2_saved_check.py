import subprocess,pathlib,time
base=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn');runner='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts/ue_exec.py'
for name in ['reload','verify']:
 print('START',name,flush=True);p=subprocess.run(['python',runner,str(base/('atlas_pass2_'+name+'.py')),'--file'],capture_output=True,text=True);(base/('atlas_pass2_'+name+'_saved.log')).write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');print(p.stdout[-3500:],flush=True);assert p.returncode==0 and 'FAILED' not in p.stdout,p.stdout[-3000:]+p.stderr;time.sleep(2)
print('SAVED MAP CHECK COMPLETE',flush=True)
