import unreal,json,pathlib,collections
base=pathlib.Path(r'C:\Users\rtcru\ClaudeProjects\COHReborn')
reg=unreal.AssetRegistryHelpers.get_asset_registry()
fx=[{'path':str(d.package_name),'class':str(d.asset_class_path.asset_name)} for d in reg.get_assets_by_path('/Game/FireEffectVFX',True)]
f=unreal.load_asset('/Game/FireEffectVFX/VFX/NS_FireEffect')
print('FIRE',f)
print('FIRE API',[n for n in dir(f) if any(s in n for s in ('valid','compile','parameter','emitter'))])
print('FX ASSETS',json.dumps(fx))
r=json.load(open(base/'atlas_enemy_import_report.json'))
clips=collections.Counter(k.removeprefix(name) for name,v in r.items() for k in v.get('clips',{}))
print('CLIPS',dict(clips))
print('WORLD',unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name())
