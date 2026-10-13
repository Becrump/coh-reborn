"""Capture the actual editor viewport through its existing MCP HTTP endpoint."""
import sys,json,base64,pathlib
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts')
import ue
sid,_=ue.post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'codex-atlas25-review','version':'1'}}})
ue.post({'jsonrpc':'2.0','method':'notifications/initialized'},sid)
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/docs/images/atlas-second-pass');out.mkdir(parents=True,exist_ok=True)
views=[('candidate-0', 186068.59683174093, 215831.16380337524, 14147.40087715149, -17, -45), ('candidate-1', 234981.92387185147, 213844.45194340724, 13562.980144348145, -17, -45), ('candidate-2', 291508.1718719573, 208226.80798644945, 8120.530575546192, -17, -45), ('candidate-3', 312368.22935041325, 238608.79721662676, 33297.166706137585, -17, -45), ('candidate-4', 385992.34932062373, 214007.6327324697, 12659.724464950563, -17, -45), ('candidate-5', 437423.32618969027, 212576.67137705948, 9142.486686295728, -17, -45), ('candidate-6', 486932.9662313335, 213067.03367061767, 11493.539811378598, -17, -45), ('candidate-7', 524339.5421406038, 225635.46045999395, 23483.626813812258, -17, -45)]
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
