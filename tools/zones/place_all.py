"""Place every city zone on the Homecoming reference map.

Run in docs/zones/ with zone_bounds.json, zone_offsets.json (inner ring from
place.py) and stations.json (from stations.py):
    python ../../tools/zones/place_all.py <paragon_city_zones_map_hires.png>
Fits map->world scale on the gate-matched inner ring, places the other zones
at their map box centers, nudges overlaps apart, writes zone_offsets.json and
zone_layout_overlay.jpg. Zones without a map box are listed as separate levels.
"""
import sys
import json, numpy as np
from PIL import Image, ImageDraw, ImageFont
FT=0.3048
B=json.load(open("zone_bounds.json"))
Z=json.load(open("zone_offsets.json"))
# keep only the gate-matched inner ring, so re-running is safe
Z["zones"]={k:v for k,v in Z["zones"].items() if v.get("placed_by","gate").startswith("gate")}
S=1.676  # display->original px
MAP={ # zone id: (map number, display box center)
 "city_01_01":(1,(928,625)),"city_01_03":(2,(692,595)),"city_01_02":(3,(725,725)),
 "hazard_01_01":(4,(802,628)),"city_02_01":(5,(825,492)),"city_02_02":(6,(917,790)),
 "hazard_02_01":(7,(812,245)),"city_02_05":(8,(895,1025)),"city_03_01":(9,(1100,830)),
 "city_03_02":(10,(530,635)),"hazard_03_01":(11,(1337,893)),"city_04_01":(13,(1150,1012)),
 "city_04_02":(14,(718,912)),"hazard_03_02":(15,(465,962)),"hazard_04_01":(16,(980,1168)),
 "trial_05_01":(17,(190,805)),"city_05_01":(19,(1105,520)),"city_03_03":(21,(278,163)),
}
NAMES={1:"Atlas Park",2:"Galaxy City",3:"Kings Row",4:"Perez Park",5:"Steel Canyon",6:"Skyway City",7:"Boomtown",8:"Faultline",9:"Talos Island",10:"Independence Port",11:"Dark Astoria",13:"Founders' Falls",14:"Brickstown",15:"Crey's Folly",16:"Eden",17:"Rikti Crash Site",19:"Peregrine Island",21:"Croatoa"}
def center(z):
    b=B[z]["bounds_ft"]; return ((b[0]+b[2])/2*FT,(b[1]+b[3])/2*FT)
# fit x = a - k*u, z = b + k*v using inner ring world centers
inner=[z for z in Z["zones"]]
U=[];Xs=[]
for z in inner:
    cx,cz=center(z); ox,oz=Z["zones"][z]["offset_m"]
    wx,wz=cx+ox,cz+oz; u,v=MAP[z][1]
    U.append((u,v)); Xs.append((wx,wz))
U=np.array(U,float); X=np.array(Xs,float)
# unknowns k,a,b: rows [-u,1,0]=x ; [v,0,1]=z
A=np.zeros((2*len(U),3)); y=np.zeros(2*len(U))
A[0::2,0]=-U[:,0];A[0::2,1]=1;y[0::2]=X[:,0]
A[1::2,0]=U[:,1];A[1::2,2]=1;y[1::2]=X[:,1]
k,a,b=np.linalg.lstsq(A,y,rcond=None)[0]
res=A@[k,a,b]-y
print("scale %.1f m per display px; residual rms %.0f m, max %.0f m"%(k,np.sqrt((res**2).mean()),abs(res).max()))
out={"units":Z["units"] if "units" in Z else "meters","frame":"game axes; map east = -x, map north = -z; Atlas Park at 0,0",
     "map_fit":{"m_per_display_px":round(k,2),"x":"%.1f - k*u"%a,"z":"%.1f + k*v"%b,"display_scale_to_original":S},
     "zones":{}, "separate_levels":{}}
for z,info in B.items():
    if z in Z["zones"]:
        out["zones"][z]=Z["zones"][z]; out["zones"][z]["placed_by"]="gate match (inner ring)"; continue
    if z not in MAP:
        out["separate_levels"][z]=info["name"]; continue
    u,v=MAP[z][1]; wx,wz=a-k*u,b+k*v; cx,cz=center(z)
    o=(round(wx-cx,1),round(wz-cz,1)); bb=info["bounds_ft"]
    out["zones"][z]={"name":NAMES[MAP[z][0]],"offset_m":list(o),
       "world_rect_m":[round(bb[0]*FT+o[0],1),round(bb[1]*FT+o[1],1),round(bb[2]*FT+o[0],1),round(bb[3]*FT+o[1],1)],
       "placed_by":"reference map box center"}
for z,v in out["zones"].items(): v["map_number"]=MAP[z][0]
st=json.load(open("stations.json"))
for z,v in out["zones"].items():
    if "station" not in v and z in st:
        s=st[z]; o=v["offset_m"]; v["station"]={"local_m":s["local_m"],"world_m":[round(s["local_m"][0]+o[0],1),s["local_m"][1],round(s["local_m"][2]+o[1],1)],"game_yaw_deg":s["game_yaw_deg"]}
# separate overlaps: inner ring and Talos stay, others move along the
# shorter overlap axis, away from the fixed zone, plus a 100 m road gap
FIXED=set(Z["zones"])|{"city_03_01"}
GAP=100.0
for it in range(50):
    moved=False
    ks=list(out["zones"])
    for p in ks:
        for q in ks:
            if p==q or q in FIXED and p in FIXED: continue
            if p in FIXED or (q not in FIXED and ks.index(q)<ks.index(p)): continue
            A_=out["zones"][q]["world_rect_m"];B_=out["zones"][p]["world_rect_m"]
            w=min(A_[2],B_[2])-max(A_[0],B_[0]); h=min(A_[3],B_[3])-max(A_[1],B_[1])
            if w>-GAP and h>-GAP:
                ca=((A_[0]+A_[2])/2,(A_[1]+A_[3])/2); cb=((B_[0]+B_[2])/2,(B_[1]+B_[3])/2)
                if w<h: d=((w+GAP) if cb[0]>=ca[0] else -(w+GAP),0)
                else: d=(0,(h+GAP) if cb[1]>=ca[1] else -(h+GAP))
                v=out["zones"][p]; v["offset_m"]=[round(v["offset_m"][0]+d[0],1),round(v["offset_m"][1]+d[1],1)]
                v["world_rect_m"]=[round(B_[0]+d[0],1),round(B_[1]+d[1],1),round(B_[2]+d[0],1),round(B_[3]+d[1],1)]
                v["placed_by"]="reference map box center, nudged %.0f m to clear %s"%(abs(d[0])+abs(d[1]),out["zones"][q]["name"])
                moved=True
    if not moved: break
for z,v in out["zones"].items():
    if v.get("station") and not v["placed_by"].startswith("gate"):
        s_=st[z]; o=v["offset_m"]; v["station"]["world_m"]=[round(s_["local_m"][0]+o[0],1),s_["local_m"][1],round(s_["local_m"][2]+o[1],1)]
json.dump(out,open("zone_offsets.json","w"),indent=1)
# overlaps
ks=list(out["zones"])
for i,p in enumerate(ks):
    for q in ks[i+1:]:
        A_=out["zones"][p]["world_rect_m"];B_=out["zones"][q]["world_rect_m"]
        w=min(A_[2],B_[2])-max(A_[0],B_[0]); h=min(A_[3],B_[3])-max(A_[1],B_[1])
        if w>0 and h>0: print("STILL overlap %s / %s: %.0f x %.0f m"%(out["zones"][p]["name"],out["zones"][q]["name"],w,h))
# overlay
im=Image.open('/mnt/project-files/reference/paragon_city_zones_map_hires.png').convert('RGB')
d=ImageDraw.Draw(im,'RGBA')
try: f=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",34)
except: f=None
def topix(x,zz): return ((a-x)/k*S,(zz-b)/k*S)
for z,v in out["zones"].items():
    x0,z0,x1,z1=v["world_rect_m"]; p0=topix(x1,z0); p1=topix(x0,z1)
    col=(220,30,30,255) if v["placed_by"].startswith("gate") else (20,20,200,255)
    d.rectangle([p0,p1],outline=col,width=7,fill=col[:3]+(40,))
    cxp=(p0[0]+p1[0])/2; cyp=(p0[1]+p1[1])/2
    d.text((cxp,cyp),v["name"],fill=(0,0,0,255),font=f,anchor="mm",stroke_width=3,stroke_fill=(255,255,255,255))
    if v.get("station"):
        sx,sy=topix(v["station"]["world_m"][0],v["station"]["world_m"][2]); d.ellipse([sx-14,sy-14,sx+14,sy+14],fill=(0,160,0,255))
im.crop((0,0,int(1470*S),im.size[1])).resize((int(1470*S)//2,im.size[1]//2)).save("zone_layout_overlay.jpg",quality=85)
