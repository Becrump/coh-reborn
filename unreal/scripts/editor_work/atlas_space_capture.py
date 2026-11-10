import sys,json,base64,pathlib
sys.path.insert(0,'C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/unreal/scripts')
import ue
sid,_=ue.post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'codex-atlas-dressing','version':'1'}}})
ue.post({'jsonrpc':'2.0','method':'notifications/initialized'},sid)
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion/docs/images/atlas-dressing-study');out.mkdir(parents=True,exist_ok=True)
for name,x,y,z,pitch,yaw in [('street',-61000,65000,2400,1,-100),('pocket',-61400,57000,2650,-8,-143)]:
 args={'captureTransform':{'location':{'x':x,'y':y,'z':z},'rotation':{'pitch':pitch,'yaw':yaw,'roll':0}},'annotations':None,'bShowUI':False}
 _,raw=ue.post({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'call_tool','arguments':{'toolset_name':'EditorToolset.EditorAppToolset','tool_name':'CaptureViewport','arguments':args}}},sid)
 if 'data:' in raw[:20]:raw='\n'.join(l[5:] for l in raw.splitlines() if l.startswith('data:'))
 res=json.loads(raw);saved=False
 for c in res.get('result',{}).get('content',[]):
  if c.get('type')=='image':data=c['data']
  elif c.get('type')=='text':
   try:data=json.loads(c['text'])['returnValue']['image']['data']
   except (KeyError,ValueError):continue
  else:continue
  (out/(name+'.png')).write_bytes(base64.b64decode(data));saved=True;break
 assert saved,str(res)[:400]
 print(out/(name+'.png'),flush=True)
