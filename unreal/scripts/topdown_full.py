import json, sys, numpy as np
from PIL import Image, ImageDraw
d=sys.argv[1]; name=sys.argv[2]
g=json.load(open(d+"/"+name+".gltf")); b=open(d+"/"+name+".bin","rb").read()
def acc(i,n):
    a=g["accessors"][i]; v=g["bufferViews"][a["bufferView"]]
    dt={5126:np.float32,5125:np.uint32,5123:np.uint16}[a["componentType"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*n,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).reshape(-1,n)
tris=[]
for node in g["nodes"]:
    if "mesh" not in node or node["name"].endswith(("_night","_glass")): continue
    for p in g["meshes"][node["mesh"]]["primitives"]:
        name_=g["materials"][p["material"]]["name"].lower()
        if "__add" in name_: continue
        pos=acc(p["attributes"]["POSITION"],3); idx=acc(p["indices"],1).reshape(-1,3)
        t=pos[idx]
        # ground-ish: below 30 m, roughly horizontal
        n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]); ln=np.linalg.norm(n,axis=1)+1e-9
        keep=(t[:,:,1].max(1)<30)&(np.abs(n[:,1])/ln>0.7)
        t=t[keep]
        col=(150,150,140)
        if any(k in name_ for k in ("street","road","asph","lane","manhole","drain")): col=(60,60,65)
        if any(k in name_ for k in ("grass","turf","dirt","plate")): col=(70,120,50)
        if "water" in name_: col=(30,140,150)
        tris.append((t,col))
allp=np.concatenate([t.reshape(-1,3) for t,_ in tris])
x0,z0=np.percentile(allp[:,0],0.5),np.percentile(allp[:,2],0.5); x1,z1=np.percentile(allp[:,0],99.5),np.percentile(allp[:,2],99.5)
W=2400; sc=W/(x1-x0); H=int((z1-z0)*sc)
im=Image.new("RGB",(W,H),(135,190,230)); dr=ImageDraw.Draw(im)
flat=[(tri[:,1].mean(),tri,col) for t,col in tris for tri in t]
flat.sort(key=lambda r:r[0])
for _,tri,col in flat:
    dr.polygon([((x-x0)*sc,(z-z0)*sc) for x,y,z in tri],fill=col)
# grid lines every 400 ft tile
for gx in np.arange(np.floor(x0/121.92)*121.92,x1,121.92): dr.line([((gx-x0)*sc,0),((gx-x0)*sc,H)],fill=(255,255,255),width=1)
for gz in np.arange(np.floor(z0/121.92)*121.92,z1,121.92): dr.line([(0,(gz-z0)*sc),(W,(gz-z0)*sc)],fill=(255,255,255),width=1)
im.save(name+"_full_top.png"); print(len(flat),"tris", W,H, "x",x0,x1,"z",z0,z1)
