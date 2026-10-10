import unreal
el=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary;tools=unreal.AssetToolsHelpers.get_asset_tools()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
def material(name):
 path='/Game/CoH/Materials/'+name
 m=unreal.load_asset(path)
 if not m:m=tools.create_asset(name,'/Game/CoH/Materials',unreal.Material,unreal.MaterialFactoryNew())
 else:mel.delete_all_material_expressions(m)
 m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
 m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
 m.set_editor_property('two_sided',True)
 return m
def expr(m,cls):return mel.create_material_expression(m,cls,0,0)
def custom(m,code,out):
 c=expr(m,unreal.MaterialExpressionCustom);c.set_editor_property('code',code);c.set_editor_property('output_type',out)
 ins=[]
 for name in ['UV','T']:
  i=unreal.CustomInput();i.set_editor_property('input_name',name);ins.append(i)
 c.set_editor_property('inputs',ins)
 assert mel.connect_material_expressions(expr(m,unreal.MaterialExpressionTextureCoordinate),'',c,'UV')
 assert mel.connect_material_expressions(expr(m,unreal.MaterialExpressionTime),'',c,'T')
 return c
def prop(n,p):assert mel.connect_material_property(n,'',p)
m=material('M_CoH_ImpactRipples')
c=custom(m,r'''
float2 q=(UV-.5)*2;
float r=length(q);float a=atan2(q.y,q.x);
float rings=0;
for(int i=0;i<3;i++){
 float age=frac(T*.65+i/3.0);
 float radius=.08+age*.84;
 float wobble=.006*sin(a*11+T*4+i);
 rings+=exp(-pow((r-radius-wobble)/.014,2))*(1-age)*(1-age);
}
float foam=exp(-r*r/0.025)*(.35+.18*sin(T*9+a*7+r*35));
float edge=saturate((1-r)*12);
float alpha=saturate((rings*.5+foam)*edge);
return float4(float3(.62,.79,.83),alpha);
''',unreal.CustomMaterialOutputType.CMOT_FLOAT4)
rgb=expr(m,unreal.MaterialExpressionComponentMask);rgb.set_editor_properties({'r':True,'g':True,'b':True,'a':False});mel.connect_material_expressions(c,'',rgb,'');prop(rgb,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
a=expr(m,unreal.MaterialExpressionComponentMask);a.set_editor_properties({'r':False,'g':False,'b':False,'a':True});mel.connect_material_expressions(c,'',a,'');prop(a,unreal.MaterialProperty.MP_OPACITY)
mel.recompile_material(m);assert el.save_loaded_asset(m,False)
spraymat=material('M_CoH_SplashDroplets')
wpo=custom(spraymat,r'''
float t=frac(T*(1.1+UV.y*.65)+UV.x);
float angle=UV.x*6.2831853*2.39996;
float radius=t*(18+UV.y*30);
return float3(cos(angle)*radius,sin(angle)*radius,4*t*(1-t)*(12+UV.y*25));
''',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
prop(wpo,unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
color=expr(spraymat,unreal.MaterialExpressionConstant3Vector);color.set_editor_property('constant',unreal.LinearColor(.65,.84,.9,1));prop(color,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
opacity=expr(spraymat,unreal.MaterialExpressionConstant);opacity.set_editor_property('r',.55);prop(opacity,unreal.MaterialProperty.MP_OPACITY)
mel.recompile_material(spraymat);assert el.save_loaded_asset(spraymat,False)
task=unreal.AssetImportTask();task.set_editor_properties({'filename':r'C:\Users\rtcru\ClaudeProjects\COHReborn\fountain_spray\spray.gltf','destination_path':'/Game/CoH/FX/Spray','automated':True,'save':True,'replace_existing':True})
tools.import_asset_tasks([task]);print('IMPORTED',task.get_editor_property('imported_object_paths'))
print('MATERIALS SAVED',m.get_path_name(),spraymat.get_path_name())
