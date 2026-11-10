import unreal,json,pathlib
reg=unreal.AssetRegistryHelpers.get_asset_registry();rows=[]
for root in ['/Game/Characters/AstroMale','/Game/Characters/CaptainValor','/Game/Characters/IronVanguard','/Game/Characters/IronVanguardHero','/Game/Characters/MetaHumans']:
 for d in reg.get_assets_by_path(root,True):
  cls=str(d.asset_class_path.asset_name)
  if cls not in ['SkeletalMesh','Skeleton','MetaHumanCharacter','CustomizableObject']:continue
  r={'path':d.get_full_name().split(' ',1)[-1],'class':cls}
  if cls=='SkeletalMesh':
   m=d.get_asset();r.update(skeleton=m.skeleton.get_path_name() if m.skeleton else None,materials=[s.material_interface.get_path_name() if s.material_interface else None for s in m.materials])
   try:r['morphs']=[x.get_name() for x in m.get_editor_property('morph_targets')]
   except Exception:r['morphs']='not exposed through this Python API'
  rows.append(r)
out=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn/hero_creator_inventory.json');out.write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
