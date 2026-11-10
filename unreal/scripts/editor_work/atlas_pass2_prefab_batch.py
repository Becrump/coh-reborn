import unreal,json,hashlib,os
base='C:/Users/rtcru/ClaudeProjects/COHReborn/'
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary;ss=unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem);lib=unreal.SubobjectDataBlueprintFunctionLibrary
catalog=json.load(open(base+'atlas_pass2_catalog.json'));state=json.load(open(base+'atlas_pass2_material_state.json'))
targets=json.load(open(base+'atlas_overhaul_materials.json'))['targets'];targets.update(state['targets'])
work=[{'path':catalog[i]['path'],'palette':None} for i in [1,2,3,4]]
for name,palette,tint in [('NYAA','Brown',[.78,.64,.54]),('NYAB','WarmRed',[1.08,.78,.66]),('NYAC','Tan',[1.12,1.04,.88]),('NYAD','Charcoal',[.56,.59,.62])]:work.append({'path':'/Game/AtlasUpgraded/Buildings/BPP_Comic_BPP_'+name+'_Ref_N1','palette':palette,'tint':tint})
sp=base+'atlas_pass2_prefab_state.json';saved=json.load(open(sp)) if os.path.exists(sp) else {'cursor':0,'prefabs':{},'palette_prefabs':{},'tints':[]}
if saved['cursor']<len(work):
 r=work[saved['cursor']];original=el.load_asset(r['path']);assert original,r['path']
 root='/Game/AtlasSecondPass/Buildings';el.make_directory(root)
 name='BPP_Pass2_'+original.get_name()+(('_'+r['palette']) if r['palette'] else '')
 dest=root+'/'+name;bp=el.load_asset(dest) if el.does_asset_exist(dest) else unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(name,root,original);assert bp
 bp.modify();changed=0;cache={};packages=[]
 for h in ss.k2_gather_subobject_data_for_blueprint(bp):
  c=lib.get_object_for_blueprint(lib.get_data(h),bp)
  if not isinstance(c,unreal.StaticMeshComponent):continue
  mats=[c.get_material(i) for i in range(c.get_num_materials())]
  for j,mat in enumerate(mats):
   if not mat:continue
   if not r['palette']:
    if mat.get_path_name() in targets:mats[j]=el.load_asset(targets[mat.get_path_name()]);changed+=1
   elif '_Wall_' in mat.get_name():
    key=mat.get_path_name()
    if key not in cache:
     params={str(p) for p in mel.get_vector_parameter_names(mat)}
     param=next((p for p in ['Color Tint GT','Color Tint M1','Color Tint/Mult(A) M1'] if p in params),None)
     if not param:cache[key]=mat;continue
     orig=mel.get_material_instance_vector_parameter_value(mat,param)
     tint=unreal.LinearColor(orig.r*r['tint'][0],orig.g*r['tint'][1],orig.b*r['tint'][2],orig.a)
     mr='/Game/AtlasSecondPass/PaletteMaterials';el.make_directory(mr);mn='MI_'+r['palette']+'_'+hashlib.sha256(key.encode()).hexdigest()[:10]
     dst=el.load_asset(mr+'/'+mn) if el.does_asset_exist(mr+'/'+mn) else unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(mn,mr,mat);assert dst
     mel.set_material_instance_vector_parameter_value(dst,param,tint)
     packages.append(dst.get_outer());cache[key]=dst
     saved['tints'].append({'source':key,'target':dst.get_path_name(),'parameter':param,'before':[orig.r,orig.g,orig.b,orig.a],'after':[tint.r,tint.g,tint.b,tint.a]})
    mats[j]=cache[key];changed+=mats[j]!=mat
  c.modify();c.set_editor_property('override_materials',mats)
 if packages:assert unreal.EditorLoadingAndSavingUtils.save_packages(packages,True)
 assert unreal.BlueprintEditorLibrary.compile_blueprint(bp),dest
 assert el.save_loaded_asset(bp,False),dest
 if r['palette']:saved['palette_prefabs'][r['palette']]=dest
 else:saved['prefabs'][r['path']]=dest
 saved['cursor']+=1;json.dump(saved,open(sp,'w'),indent=2)
 print('PREFAB',saved['cursor'],len(work),name,'changedslots',changed,'variants',len(cache))
 unreal.SystemLibrary.collect_garbage()
