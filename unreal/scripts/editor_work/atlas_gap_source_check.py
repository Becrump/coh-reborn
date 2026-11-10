import json, numpy as np, math,pathlib
cam=json.load(open(r'C:\Users\rtcru\AppData\Local\Temp\claude\C--Users-rtcru-ClaudeProjects-COHReborn\e2d05ff4-06f7-47ea-a6d2-ec597f35ad8c\scratchpad\cam.json'))['returnValue'];loc=np.array([cam['location'][k] for k in 'xyz'])/100;p,y=[math.radians(cam['rotation'][k]) for k in ['pitch','yaw']];f=np.array([math.cos(p)*math.cos(y),math.cos(p)*math.sin(y),math.sin(p)]);right=np.array([-math.sin(y),math.cos(y),0]);up=np.cross(f,right)
for export in ['atlas_park_v5/atlas_park','atlas_upgraded/atlas_upgraded']:
 path=pathlib.Path(r'C:\Users\rtcru\CoHReborn\out')/export;g=json.load(open(str(path)+'.gltf'));buffers=[np.memmap(path.parent/b['uri'],mode='r',dtype=np.uint8) for b in g['buffers']]
 def acc(i):
  a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];dt={5126:np.float32,5125:np.uint32,5123:np.uint16}[a['componentType']];cnt={'VEC3':3,'SCALAR':1}[a['type']];return np.ndarray((a['count'],cnt),dtype=dt,buffer=buffers[v.get('buffer',0)],offset=v.get('byteOffset',0)+a.get('byteOffset',0))
 for sx,sy in [(.735,.448),(.67,.454),(.61,.46)]:
  d=f+(2*sx-1)*right+(1-2*sy)/(2560/1360)*up;d/=np.linalg.norm(d);o=loc[[0,2,1]];dg=d[[0,2,1]];hits=[]
  for mesh in g['meshes']:
   if mesh['name'] not in ['tile_-3_0','tile_-2_0','tile_-3_1','tile_-2_1']:continue
   for pr in mesh['primitives']:
    P=acc(pr['attributes']['POSITION']);I=acc(pr['indices']).reshape(-1,3);v0,v1,v2=P[I[:,0]],P[I[:,1]],P[I[:,2]];e1,e2=v1-v0,v2-v0;h=np.cross(dg,e2);det=(e1*h).sum(1);ok=np.abs(det)>1e-9;ff=1/np.where(ok,det,1);s=o-v0;u=ff*(s*h).sum(1);q=np.cross(s,e1);v=ff*(q*dg).sum(1);t=ff*(e2*q).sum(1);ids=np.where(ok&(u>=0)&(v>=0)&(u+v<=1)&(t>.1))[0]
    for n in ids:hits.append((float(t[n]),g['materials'][pr['material']]['name'],mesh['name'],(o+dg*t[n])[[0,2,1]].tolist()))
  print(export,sx,sy,sorted(hits)[:4])
