"""Capture the actual editor viewport through its existing MCP HTTP endpoint."""
import sys,json,base64,pathlib
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts')
import ue
sid,_=ue.post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'codex-atlas25-review','version':'1'}}})
ue.post({'jsonrpc':'2.0','method':'notifications/initialized'},sid)
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/docs/images/atlas25');out.mkdir(parents=True,exist_ok=True)
views=[('entrance',33162,-29000,4000,-20,-90),('district',33162,-32000,250,5,-90),('overview',43000,-28000,11500,-32,-125),('city-hall',-10000,13000,9000,-24,28)]
for name,x,y,z,pitch,yaw in views:
    args={'captureTransform':{'location':{'x':x,'y':y,'z':z},'rotation':{'pitch':pitch,'yaw':yaw,'roll':0}},'annotations':None,'bShowUI':False}
    _,raw=ue.post({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'call_tool','arguments':{'toolset_name':'EditorToolset.EditorAppToolset','tool_name':'CaptureViewport','arguments':args}}},sid)
    if 'data:' in raw[:20]:raw='\n'.join(l[5:] for l in raw.splitlines() if l.startswith('data:'))
    res=json.loads(raw)
    saved=False
    for c in res.get('result',{}).get('content',[]):
        if c.get('type')=='image':data=c['data']
        elif c.get('type')=='text':
            try:data=json.loads(c['text'])['returnValue']['image']['data']
            except (KeyError,ValueError):continue
        else:continue
        (out/(name+'.png')).write_bytes(base64.b64decode(data));saved=True;break
    assert saved,(name,str(res)[:500])
    print(out/(name+'.png'),flush=True)
