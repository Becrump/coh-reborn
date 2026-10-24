import math,json,struct,pathlib
out=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn\fountain_arc');out.mkdir(exist_ok=True)
p=[];n=[];uv=[];idx=[]
for i in range(65):
 t=i/64; x=6*t; z=4*2.0*t*(1-t); dz=(8-16*t)/6; den=math.sqrt(1+dz*dz)
 for j in range(13):
  a=j/12*math.tau; r=.035*(1-.25*t); nx=-dz/den*math.cos(a);ny=math.sin(a);nz=math.cos(a)/den
  p.extend((x+r*nx,z+r*nz,r*ny));n.extend((nx,nz,ny));uv.extend((j/12,t))
for i in range(64):
 for j in range(12):
  a=i*13+j;b=a+13;idx.extend((a,b,a+1,a+1,b,b+1))
blob=bytearray();views=[];acc=[]
for v,fmt,typ,size in [(p,'f','VEC3',3),(n,'f','VEC3',3),(uv,'f','VEC2',2),(idx,'I','SCALAR',1)]:
 while len(blob)%4:blob.append(0)
 start=len(blob);blob.extend(struct.pack('<'+fmt*len(v),*v));views.append({'buffer':0,'byteOffset':start,'byteLength':len(blob)-start})
 a={'bufferView':len(views)-1,'componentType':5126 if fmt=='f' else 5125,'count':len(v)//size,'type':typ}
 if len(acc)==0:a.update(min=[min(p[k::3]) for k in range(3)],max=[max(p[k::3]) for k in range(3)])
 acc.append(a)
g={'asset':{'version':'2.0'},'buffers':[{'uri':'arc.bin','byteLength':len(blob)}],'bufferViews':views,'accessors':acc,'meshes':[{'name':'SM_CoH_ArcJet','primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3}]}],'nodes':[{'mesh':0,'name':'SM_CoH_ArcJet'}],'scenes':[{'nodes':[0]}],'scene':0}
(out/'arc.bin').write_bytes(blob);(out/'arc.gltf').write_text(json.dumps(g));print('ARC',len(p)//3,'vertices',len(idx)//3,'triangles')
