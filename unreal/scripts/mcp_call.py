"""Call a tool on the Unreal editor's MCP server directly (streamable HTTP).
usage: python mcp_call.py <toolset> <tool> '<json args>' [--out file]"""
import json
import sys
import urllib.request

URL = "http://localhost:8000/mcp"


def post(body, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid:
        h["Mcp-Session-Id"] = sid
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), h), timeout=600)
    txt = r.read().decode("utf-8", "replace")
    if txt.startswith("event:") or "\ndata:" in txt or txt.startswith("data:"):
        txt = "\n".join(l[5:].strip() for l in txt.splitlines() if l.startswith("data:"))
    return r.headers.get("Mcp-Session-Id"), (json.loads(txt) if txt.strip() else None)


sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                          "clientInfo": {"name": "coh-reborn", "version": "1"}}})
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
toolset, tool, args = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
_, res = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "call_tool", "arguments": {"toolset_name": toolset, "tool_name": tool, "arguments": args}}}, sid)
out = json.dumps(res)
if "--out" in sys.argv:
    open(sys.argv[sys.argv.index("--out") + 1], "w").write(out)
    print("written", len(out))
else:
    print(out[:4000])
