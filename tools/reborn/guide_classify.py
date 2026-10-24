"""Classify the top-down guide renders of the original Atlas Park.

    python tools/reborn/guide_classify.py <guide dir>

Reads matid_top.npy / z_top.npy (render_guide.py + exr2npy.py) and writes
ground_z.npy (terrain height under everything), base_class.npy (ground type:
1 road, 2 paved, 3 grass, 5 water, 7 parking, 8 rock), bld.npy (building
pixels), veg.npy (tree/bush pixels), rel.npy (height above ground) and a
preview, classes_small.png. Grid: 0.5 m per pixel, UE X = -870 + (col+0.5)/2,
UE Y = (row+0.5)/2 - 636 (metres).
"""
import sys, os
os.chdir(sys.argv[1])
import numpy as np, json, re
from scipy import ndimage
from PIL import Image
o=''; m=json.load(open(o+'meta.json')); names=[re.sub(r'\.\d{3}$','',n) for n in m['names']]
mid=np.load(o+'matid_top.npy')[...,0].astype(int); zt=np.load(o+'z_top.npy')[...,0]-1000
H,W=mid.shape
def cls(n):
    l=n.lower()
    if 'watertank' in l: return 6
    if 'newwater' in l or 'oceanbase' in l: return 5
    if 'calmwater' in l: return 2
    if re.search(r'(?<!s)tree|bush|shrub|treeleaf|trunk|branch|walnut|oak|maple|birch|hedge|pine|palm', l): return 4
    if re.search(r'pklot|parking', l): return 7
    if re.search(r'sidewalk', l): return 2
    if re.search(r'^street_|4lane|asphalt|dirtroad|graf_2to1|whiteline|yellowline|crosswalk|road', l) and 'squaremask' not in l and 'skyscraper' not in l and 'deco_' not in l: return 1
    if re.search(r'grass|leaf_shp|dirt_|_ground|ground_|ivy|agapanthus|flower|mulch|soil|lawn', l): return 3
    if re.search(r'shoreline|cliff|rock', l): return 8
    if re.search(r'concrete|plaza|tile|brick_floor|bricktile|slab|grime|stain|decal|trims|paver|cobble|cityhall_border|pavement|floor', l) and 'skyscraper' not in l and 'deco_building' not in l: return 2
    return 6
lut=np.array([0]+[cls(n) for n in names]); C=lut[mid]
def fill(mask,val):
    i=ndimage.distance_transform_edt(~mask,return_distances=False,return_indices=True); return val[i[0],i[1]]
rel0=zt-ndimage.median_filter(fill(np.isin(C,[1,3,5,7,8]),zt),15)
C[(C==2)&(rel0>6)]=6
ground=np.isin(C,[1,2,3,5,7,8])
# ground height from ground pixels, filled into the rest by nearest ground pixel, then smoothed
gz=np.where(ground,zt,np.nan)
idx=ndimage.distance_transform_edt(~ground,return_distances=False,return_indices=True)
G=gz[idx[0],idx[1]]
G=ndimage.median_filter(G,9)
rel=zt-G
bld=(C==6)&(rel>4)
veg=(C==4)
# low props / fences count as the ground around them
low=(C==6)&~bld
Cg=C.copy(); Cg[low]=0; Cg[veg]=0
gm=np.isin(Cg,[1,2,3,5,7,8]); idx=ndimage.distance_transform_edt(~gm,return_distances=False,return_indices=True)
base=Cg[idx[0],idx[1]]   # ground class everywhere (under buildings/trees too)
np.save('ground_z.npy',G.astype(np.float32)); np.save('base_class.npy',base.astype(np.uint8)); np.save('bld.npy',bld); np.save('veg.npy',veg); np.save('rel.npy',rel.astype(np.float32))
pal=np.array([[0,0,0],[40,40,45],[170,170,165],[90,160,70],[20,90,30],[40,110,200],[200,120,60],[110,110,140],[140,110,80]],np.uint8)
vis=pal[base].copy(); vis[veg]=pal[4]; vis[bld]=(np.clip(rel[bld][:,None]/120,0,1)*np.array([255,120,0])+np.array([200,60,40])*0).clip(0,255).astype(np.uint8)
vis[bld]=np.stack([np.full(bld.sum(),230),(230-np.clip(rel[bld],0,300)/300*200).astype(np.uint8),np.full(bld.sum(),60)],1)
Image.fromarray(vis).resize((W//3,H//3),Image.NEAREST).save('classes_small.png')
print({k:int((base==k).sum()) for k in range(9)}, int(bld.sum()), 'ground z range', np.percentile(G,[1,50,99]))
