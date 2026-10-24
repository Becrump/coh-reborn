import math,json,struct,pathlib
out=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn\fountain_spray');out.mkdir(exist_ok=True)
p=[];n=[];uv=[];idx=[]
for d in range(32):
 base=len(p)//3
 for i in range(7):
  t=math.pi*i/6
  for j in range(9):
   a=math.tau*j/8;nx=math.sin(t)*math.cos(a);ny=math.sin(t)*math.sin(a);nz=math.cos(t)
   p.extend((nx*.007,nz*.011,ny*.007));n.extend((nx,nz,ny));uv.extend((d/32,((d*13)%31)/31))
 for i in range(6):
  for j in range(8):
   a=base+i*9+j;b=a+9;idx.extend((a,a+1,b,a+1,b+1,b))
blob=bytearray();views=[];acc=[]
for v,fmt,typ,size in [(p,'f','VEC3',3),(n,'f','VEC3',3),(uv,'f','VEC2',2),(idx,'I','SCALAR',1)]:
 while len(blob)%4:blob.append(0)
 start=len(blob);blob.extend(struct.pack('<'+fmt*len(v),*v));views.append({'buffer':0,'byteOffset':start,'byteLength':len(blob)-start})
 a={'bufferView':len(views)-1,'componentType':5126 if fmt=='f' else 5125,'count':len(v)//size,'type':typ}
 if not acc:a.update(min=[min(p[k::3]) for k in range(3)],max=[max(p[k::3]) for k in range(3)])
 acc.append(a)
g={'asset':{'version':'2.0'},'buffers':[{'uri':'spray.bin','byteLength':len(blob)}],'bufferViews':views,'accessors':acc,'meshes':[{'name':'SM_CoH_SplashDroplets','primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3}]}],'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
(out/'spray.bin').write_bytes(blob);(out/'spray.gltf').write_text(json.dumps(g))
print('Spray generated:',len(p)//3,'vertices')
