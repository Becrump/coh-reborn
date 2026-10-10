import struct,json,pathlib
# A reusable bench with wood slats, metal supports and armrests, in glTF metres.
parts=[[],[]]
def box(mat,center,size):
 x,y,z=center;w,h,d=[v/2 for v in size]
 verts=[(x-w,y-h,z-d),(x+w,y-h,z-d),(x+w,y+h,z-d),(x-w,y+h,z-d),(x-w,y-h,z+d),(x+w,y-h,z+d),(x+w,y+h,z+d),(x-w,y+h,z+d)]
 # Each face has its own normals for crisp, restrained edges.
 for face,n in [((0,3,2,1),(0,0,-1)),((4,5,6,7),(0,0,1)),((0,4,7,3),(-1,0,0)),((1,2,6,5),(1,0,0)),((0,1,5,4),(0,-1,0)),((3,7,6,2),(0,1,0))]:
  parts[mat].append(([verts[i] for i in face],n))
for z in [-.24,-.12,0,.12,.24]:box(0,(0,.46,z),(2.02,.045,.095))
for y in [.60,.72,.84,.96]:box(0,(0,y,.285),(2.02,.085,.045))
for x in [-.77,.77]:
 for z in [-.20,.22]:box(1,(x,.22,z),(.055,.44,.055))
 box(1,(x,.415,0),(.065,.065,.64));box(1,(x,.73,.32),(.05,.48,.05))
for x in [-.95,.95]:
 box(1,(x,.61,.01),(.055,.05,.58));box(1,(x,.535,-.20),(.045,.15,.045))
blob=bytearray();views=[];accessors=[];prims=[]
def acc(vals,fmt,ctype,typ,target=None):
 while len(blob)%4:blob.append(0)
 start=len(blob)
 for v in vals:blob.extend(struct.pack('<'+fmt,*(v if isinstance(v,tuple) else (v,))))
 view={'buffer':0,'byteOffset':start,'byteLength':len(blob)-start}
 if target:view['target']=target
 views.append(view);a={'bufferView':len(views)-1,'componentType':ctype,'count':len(vals),'type':typ}
 if typ=='VEC3':a.update(min=[min(v[i] for v in vals) for i in range(3)],max=[max(v[i] for v in vals) for i in range(3)])
 accessors.append(a);return len(accessors)-1
for m,faces in enumerate(parts):
 ps=[];ns=[];ix=[]
 for vs,n in faces:
  k=len(ps);ps.extend(vs);ns.extend([n]*4);ix.extend([k,k+1,k+2,k,k+2,k+3])
 prims.append({'attributes':{'POSITION':acc(ps,'fff',5126,'VEC3',34962),'NORMAL':acc(ns,'fff',5126,'VEC3',34962)},'indices':acc(ix,'I',5125,'SCALAR',34963),'material':m})
g={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors,'materials':[{'name':'Seat','pbrMetallicRoughness':{'baseColorFactor':[.13,.085,.052,1],'metallicFactor':0,'roughnessFactor':.85}},{'name':'Metal','pbrMetallicRoughness':{'baseColorFactor':[.018,.024,.025,1],'metallicFactor':.4,'roughnessFactor':.7}}],'meshes':[{'name':'SM_AtlasModernBench','primitives':prims}],'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
j=json.dumps(g,separators=(',',':')).encode();j+=b' '*((-len(j))%4);blob+=b'\0'*((-len(blob))%4)
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn/atlas_modern_bench.glb');out.write_bytes(struct.pack('<III',0x46546c67,2,12+8+len(j)+8+len(blob))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(blob),0x004e4942)+blob)
print(out)
