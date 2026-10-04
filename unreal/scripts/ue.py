"""Tiny client for the Unreal MCP HTTP server: python ue.py METHOD JSONPARAMS"""
import json, sys, urllib.request, os
URL = "http://localhost:8000/mcp"
SID = os.path.join(os.environ["TEMP"], "ue_mcp_sid.txt")
def post(body, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(URL, json.dumps(body).encode(), h)
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.headers.get("Mcp-Session-Id"), r.read().decode("utf-8", "replace")
def session():
    if os.path.exists(SID):
        return open(SID).read().strip()
    sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude", "version": "1"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    open(SID, "w").write(sid)
    return sid
def call(method, params):
    _, txt = post({"jsonrpc": "2.0", "id": 2, "method": method, "params": params}, session())
    if txt.startswith("event:") or "data:" in txt[:20]:
        txt = "\n".join(l[5:] for l in txt.splitlines() if l.startswith("data:"))
    return json.loads(txt)
def tool(name, args, toolset=None):
    a = {"tool_name": name, "arguments": args}
    if toolset: a["toolset_name"] = toolset
    r = call("tools/call", {"name": "call_tool", "arguments": a})
    if "result" in r:
        return "\n".join(c.get("text", "") for c in r["result"].get("content", []))
    return json.dumps(r)
if __name__ == "__main__":
    if sys.argv[1] == "tool":
        print(tool(sys.argv[2], json.loads(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None))
    else:
        print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2])), indent=1)[:20000])
