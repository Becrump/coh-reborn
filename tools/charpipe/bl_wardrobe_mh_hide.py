import bpy,sys,json,os,bmesh
a=sys.argv[sys.argv.index('--')+1:]
W,items,out=a[0],a[1].split(','),a[2]
wd=json.load(open(os.path.join(W,'wardrobe_mh.json')))
hid=set()
for i in items: hid|=set(wd['items'][i]['hides_body_verts'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(W,'body','mh_base.glb'))
ms=[o for o in bpy.data.objects if o.type=='MESH' and not o.name.startswith('Ico')]
# same order as the transfer script used: import order
off=0; n=0
for o in ms:
    bm=bmesh.new(); bm.from_mesh(o.data)
    kill=[f for f in bm.faces if all((off+v.index) in hid for v in f.verts)]
    n+=len(kill); bmesh.ops.delete(bm,geom=kill,context='FACES'); bm.to_mesh(o.data); bm.free()
    off+=len(o.data.vertices)
print('HIDDEN_FACES',n,[o.name for o in ms])
for o in bpy.data.objects: o.select_set(o.type in('MESH','ARMATURE') and not o.name.startswith('Ico'))
bpy.ops.export_scene.gltf(filepath=out,export_format='GLB',use_selection=True,export_skins=True,export_animations=False)
