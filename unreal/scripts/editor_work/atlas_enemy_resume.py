import json,pathlib,subprocess,sys,time
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
helper=r'C:\Users\rtcru\AppData\Local\Temp\claude\C--Users-rtcru-ClaudeProjects-COHReborn\e2d05ff4-06f7-47ea-a6d2-ec597f35ad8c\scratchpad\ue_exec.py'
required=set(json.loads((base/'atlas_enemy_remaining.json').read_text()))
for batch in range(30):
    report=json.loads((base/'atlas_enemy_import_report.json').read_text())
    remaining=required-{k for k,v in report.items() if 'mesh' in v}
    print('remaining',len(remaining),flush=True)
    if not remaining: break
    result=subprocess.run([sys.executable,helper,str(base/'atlas_enemy_batch.py'),'--file'],capture_output=True,text=True)
    print(result.stdout[-3500:],result.stderr[-1000:],flush=True)
    if result.returncode or 'FAILED' in result.stdout or 'success' not in result.stdout: sys.exit('Import batch failed; checkpoint retained')
    time.sleep(2)
else: sys.exit('Batch limit reached')
