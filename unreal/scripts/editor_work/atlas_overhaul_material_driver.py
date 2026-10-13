import sys,time,json
sys.path.insert(0,r'C:/Program Files/Epic Games/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python')
import remote_execution as rx
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
r=rx.RemoteExecution();r.start()
try:
    deadline=time.time()+15
    while not r.remote_nodes and time.time()<deadline:time.sleep(.2)
    assert r.remote_nodes,'No editor found'
    r.open_command_connection(r.remote_nodes[0]['node_id'])
    total=len(json.load(open(base+'atlas_overhaul_material_sources.json')))
    while True:
        result=r.run_command(base+'atlas_overhaul_material_batch.py',unattended=True,exec_mode=rx.MODE_EXEC_FILE,raise_on_failure=False)
        for o in result.get('output',[]):print(o['output'].strip(),flush=True)
        assert result.get('success'),result.get('result')
        state=json.load(open(base+'atlas_overhaul_material_batch_state.json'))
        if state['cursor']>=total:break
        # Return control to the editor so jobs and garbage collection can finish.
        time.sleep(2)
finally:r.stop()
