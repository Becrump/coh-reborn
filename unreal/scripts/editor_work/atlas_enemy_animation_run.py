import json,pathlib,subprocess,sys,time
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
helper=r'C:\Users\rtcru\AppData\Local\Temp\claude\C--Users-rtcru-ClaudeProjects-COHReborn\e2d05ff4-06f7-47ea-a6d2-ec597f35ad8c\scratchpad\ue_exec.py'
for batch in range(50):
 report=json.load(open(base/'atlas_enemy_animation_ground_report.json'))
 print('Configured',len(report),'of 4659',flush=True)
 if len(report)==4659:break
 result=subprocess.run([sys.executable,helper,str(base/'atlas_enemy_animation_batch.py'),'--file'],capture_output=True,text=True)
 print(result.stdout[-1000:],result.stderr[-500:],flush=True)
 if result.returncode or 'FAILED' in result.stdout or 'success' not in result.stdout:sys.exit('Stopped at saved checkpoint')
 time.sleep(1)
else:sys.exit('Batch limit')
