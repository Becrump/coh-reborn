import unreal,json,pathlib
base=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn');out=base/'exports'/'hero-foundation-reference';out.mkdir(parents=True,exist_ok=True)
rows=json.loads((base/'hero_creator_inventory.json').read_text());exported=[]
for r in rows:
 if r['class']!='SkeletalMesh' or '/MetaHumans/' in r['path']:continue
 m=unreal.load_asset(r['path']);assert m
 group=r['path'].split('/')[3];folder=out/group;folder.mkdir(exist_ok=True);filename=folder/(m.get_name()+'.fbx');assert not filename.exists(),'Preserve previous export: '+str(filename)
 task=unreal.AssetExportTask();task.object=m;task.filename=str(filename);task.automated=True;task.prompt=False;task.replace_identical=False
 options=unreal.FbxExportOption();options.set_editor_property('ascii',False);options.set_editor_property('level_of_detail',False);task.options=options
 assert unreal.Exporter.run_asset_export_task(task),r['path'];assert filename.exists() and filename.stat().st_size>1000
 exported.append(dict(r,file=str(filename),bytes=filename.stat().st_size))
manifest={'scope':'Existing UE prototype hero meshes and rigs, not original CoH costume/body exports. Reference FBX exports only; source assets and playable characters unchanged. FBX is not a complete material/texture or gameplay backup.','exports':exported}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps([{'file':r['file'],'bytes':r['bytes']} for r in exported],indent=2))
