"""Run Python in the open Unreal editor via Python Remote Execution.
usage: python ue_exec.py "<python statement or file path>" [--file] [--timeout S]"""
import sys, time
sys.path.insert(0, r"C:\Program Files\Epic Games\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python")
import remote_execution as rx
cmd = sys.stdin.read() if sys.argv[1] == "-" else sys.argv[1]
mode = rx.MODE_EXEC_FILE if ("--file" in sys.argv or sys.argv[1] == "-") else rx.MODE_EXEC_STATEMENT
timeout = float(sys.argv[sys.argv.index("--timeout") + 1]) if "--timeout" in sys.argv else 600
r = rx.RemoteExecution()
r.start()
try:
    t0 = time.time()
    while not r.remote_nodes and time.time() - t0 < 10:
        time.sleep(0.2)
    if not r.remote_nodes:
        sys.exit("no Unreal editor found (is Remote Execution enabled?)")
    # several nodes when a Standalone Game runs next to the editor: use the
    # one that has the editor subsystems
    time.sleep(1.0)
    node = r.remote_nodes[0]
    for cand in list(r.remote_nodes):
        r.open_command_connection(cand["node_id"])
        probe = r.run_command("print(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem) is not None)",
                              unattended=True, exec_mode=rx.MODE_EXEC_STATEMENT, raise_on_failure=False)
        r.close_command_connection()
        if any("True" in o["output"] for o in probe.get("output", [])):
            node = cand
            break
    r.open_command_connection(node["node_id"])
    res = r.run_command(cmd, unattended=True, exec_mode=mode, raise_on_failure=False)
    for o in res.get("output", []):
        print(("[%s] " % o["type"]) if o["type"] != "Info" else "", o["output"].rstrip(), sep="")
    if res.get("result") not in (None, "None", ""):
        print("result:", res["result"])
    print("success" if res.get("success") else "FAILED")
finally:
    r.stop()
