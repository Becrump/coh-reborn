import json,numpy as np
base='C:/Users/rtcru/CoHReborn/out/atlas_rebuilt_avenue/avenue'
g=json.load(open(base+'.gltf'));buf=open(base+'.bin','rb').read()
def acc(idx):
 a=g['accessors'][idx];v=g['bufferViews'][a['bufferView']];dt={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];n={'VEC3':3,'SCALAR':1}[a['type']]
 return np.frombuffer(buf,dtype=dt,count=a['count']*n,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,n)
x=1088*.3048;z=-1200*.3048
for mesh in g['meshes']:
 for pr in mesh['primitives']:
  p=acc(pr['attributes']['POSITION']);t=p[acc(pr['indices']).reshape(-1,3)]
  a=t[:,0];b=t[:,1];c=t[:,2];den=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2]);safe=np.abs(den)>1e-8
  den=np.where(safe,den,1);u=((b[:,2]-c[:,2])*(x-c[:,0])+(c[:,0]-b[:,0])*(z-c[:,2]))/den;v=((c[:,2]-a[:,2])*(x-c[:,0])+(a[:,0]-c[:,0])*(z-c[:,2]))/den
  mask=safe&(u>=-1e-6)&(v>=-1e-6)&(u+v<=1.000001)
  if np.any(mask):
   heights=(u*a[:,1]+v*b[:,1]+(1-u-v)*c[:,1])[mask]
   print(mesh['name'],g['materials'][pr['material']]['name'],sorted(set(np.round(heights,3))))
