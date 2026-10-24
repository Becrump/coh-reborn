import subprocess,pathlib,time
base=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn');runner='C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts/ue_exec.py'
steps=[('before capture',['python',str(base/'atlas_pass2_before_capture.py')])]+[(name,['python',runner,str(base/('atlas_pass2_'+name+'.py')),'--file']) for name in ['import','bind_tiles','apply','verify']]
for name,cmd in steps:
 print('START',name,flush=True)
 p=subprocess.run(cmd,capture_output=True,text=True)
 (base/('atlas_pass2_'+name+'.log')).write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
 print(p.stdout[-2500:],flush=True)
 assert p.returncode==0 and 'FAILED' not in p.stdout,p.stdout[-3000:]+p.stderr
 time.sleep(2)
print('PLACEMENT PIPELINE COMPLETE',flush=True)
