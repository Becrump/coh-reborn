import json
G = json.load(open("gates.json"))
N = {"city_01_01":"Atlas Park","city_01_03":"Galaxy City","hazard_01_01":"Perez Park","city_02_01":"Steel Canyon","city_02_02":"Skyway City","city_01_02":"Kings Row"}
GAP = 200.0  # ft of connecting road between facing gates
def side(z, g):
    x0,z0,x1,z1 = G[z]["bounds_ft"]; x,y = g
    d = {(-1,0):abs(x-x0),(1,0):abs(x-x1),(0,-1):abs(y-z0),(0,1):abs(y-z1)}
    return min(d, key=d.get)
off = {"city_01_01":(0.0,0.0)}
def attach(placed, gsign, new, nsign):
    ga = G[placed]["signs"][gsign]; gb = G[new]["signs"][nsign]; o = off[placed]
    dx,dz = side(placed, ga)
    off[new] = (o[0]+ga[0]-gb[0]+GAP*dx, o[1]+ga[1]-gb[1]+GAP*dz)
attach("city_01_01","ATLAS_SKYWAYCITY","city_02_02","SKYWAYCITY_ATLAS")
attach("city_01_01","HAZARD_PEREZPARK","hazard_01_01","HAZARD_ATLASPARK")
attach("city_01_01","atlas_steelcanyon","city_02_01","STEEL_ATLAS")
attach("hazard_01_01","HAZARD_GALAXYCITY","city_01_03","HAZARD_PEREZPARK")
# Kings Row: no gate signs found; put its min-x (map east) edge GAP beyond Skyway's Kings Row gate, centered on it
sx,sz = G["city_02_02"]["signs"]["SKYWAYCITY_KINGSROW"]; o=off["city_02_02"]
kx0,kz0,kx1,kz1 = G["city_01_02"]["bounds_ft"]
off["city_01_02"] = (o[0]+sx+GAP-kx0, o[1]+sz-(kz0+kz1)/2)
def R(z): b=G[z]["bounds_ft"]; return (b[0]+off[z][0],b[1]+off[z][1],b[2]+off[z][0],b[3]+off[z][1])
# Steel Canyon's gates do not line up with both Atlas and Perez; push it north (-z) until clear of both
s_=R("city_02_01"); zmin=min(R("city_01_01")[1],R("hazard_01_01")[1]); 
if s_[3] > zmin-GAP: off["city_02_01"]=(off["city_02_01"][0], off["city_02_01"][1]-(s_[3]-(zmin-GAP)))
rect = {z:(G[z]["bounds_ft"][0]+off[z][0],G[z]["bounds_ft"][1]+off[z][1],G[z]["bounds_ft"][2]+off[z][0],G[z]["bounds_ft"][3]+off[z][1]) for z in off}
print("overlaps (ft):")
ks=list(rect)
for i,a in enumerate(ks):
    for b in ks[i+1:]:
        A,B=rect[a],rect[b]; w=min(A[2],B[2])-max(A[0],B[0]); h=min(A[3],B[3])-max(A[1],B[1])
        if w>0 and h>0: print("  %s / %s: %.0f x %.0f" % (N[a],N[b],w,h))
print("cross-check gate gaps (ft):")
def gw(z,s): g=G[z]["signs"][s]; return (g[0]+off[z][0], g[1]+off[z][1])
for a,sa,b,sb in [("hazard_01_01","HAZARD_STEELCANYON","city_02_01","HAZARD_PEREZPARK"),("hazard_01_01","HAZARD_SKYWAYCITY","city_02_02","HAZARD_PEREZPARK"),("city_01_01","atlas_steelcanyon","city_02_01","STEEL_ATLAS")]:
    p=gw(a,sa)
    if sb: q=gw(b,sb); print("  %s-%s: %.0f" % (N[a],N[b],((p[0]-q[0])**2+(p[1]-q[1])**2)**.5))
out={"units":"meters","frame":"game axes; map east = -x, map north = -z; Atlas Park at 0,0","zones":{}}
for z in off:
    out["zones"][z]={"name":N[z],"offset_m":[round(off[z][0]*0.3048,1),round(off[z][1]*0.3048,1)],
      "world_rect_m":[round(v*0.3048,1) for v in rect[z]],
      "gates_world_m":{s:[round((g[0]+off[z][0])*0.3048,1),round((g[1]+off[z][1])*0.3048,1)] for s,g in G[z]["signs"].items()}}
    print(N[z], out["zones"][z]["offset_m"], out["zones"][z]["world_rect_m"])
json.dump(out, open("zone_offsets.json","w"), indent=1)
