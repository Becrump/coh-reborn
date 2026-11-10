import json,collections,pathlib
root=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion')
m=json.load(open(root/'docs/atlas-upgraded-manifest.json'));b=m['buildings']
inv=json.load(open('atlas_second_pass_inventory.json'))
sources=json.load(open('atlas_overhaul_sources.json'));sel={r['id'] for r in json.load(open('atlas_overhaul_selected.json'))}
used=collections.Counter(r['name'] for r in b)
priorities=[
('P1','Original perimeter skyline',[], 'The repeated box buildings visible behind the upgraded city are still the old skyline02 assemblies. Replace the most visible runs with varied silhouettes and, where expansion makes them accessible, complete street-facing buildings. Preserve the breach remnants and distinguish backdrop geometry from playable blocks.'),
('P1','Adjacent twin towers: plot 037',[37], 'Two neighboring CHJ B towers repeat the same silhouette. Change one to a different tower family; assess the adjoining CHJ A tower as part of the whole block.'),
('P1','Adjacent twin towers: plot 072',[72], 'Another pair of CHJ B towers shares one long plot. Break up the pair with a different crown, setback and height rather than only a tint.'),
('P1','Three repeated modern towers: plots 039–041',[39,40,41], 'Three nearby CHC/CHD modern towers form a run around X=568–570 m. Replace at least one and consider a lower stepped building to vary the street and skyline.'),
('P1','Neighboring square buildings: plots 007–008',[7,8], 'Both use NYG Modern Square. Keep one; replace the other with a different footprint or roofline. Give brick and trim variants to retained frontage.'),
('P1','Repeated reference buildings: plots 102 and 104',[102,104], 'Both use CHI reference at X≈−335 m, separated by about 24 m in Y, with another building between them. Review the three-building run and replace one CHI facade with a new family.'),
('P2','Repeated CHA buildings in the outer industrial plots',[1,2,5,28,29], 'Five plots use the same CHA design. Rework selected street-visible examples into mixed-use or apartment blocks while retaining a few industrial survivors.'),
('P2','Northern outer blocks (positive editor Y)',[79,85,86,103,110], 'The outer row mixes only a few familiar designs. Vary residential/commercial frontage, corners, heights and muted brick colors; avoid turning every plot into another tower.'),
('P2','Retained large warehouse complexes',[6,26,32,33], 'These were excluded from the first swap because of their size, not because they were named civic landmarks. Review full complexes for adaptive reuse or redevelopment. Their position and significance need a close street-level check before replacement.'),
('P2','Repeated retained garages',[3,18,46,50,51,52,53,65,66,67,83,96,97,122,123], 'Modernize selected frontage, entrances and rooflines. Repeated small garage pieces may belong to one complex, so review together rather than count each as a separate building.'),
('P3','Study storefronts and retained pyramid towers',[58,59,60,115,117], 'Keep initially: storefronts 058–060 were already upgraded in the earlier study, and 115/117 are retained distinctive pyramid towers. Revisit only after the higher-priority repetition is resolved.')]
items=[]
for p,title,ids,reason in priorities:
 targets=[]
 for sid in ids:
  matches=[r for r in b if r['source_id']==sid]
  if matches:
   for r in matches:targets.append({'actor':r['label'],'source_id':sid,'design':r['name'],'location_cm':r['location'],'action':'review'})
  else:
   r=next(x for x in sources if x['id']==sid)
   targets.append({'source_id':sid,'source_group':r['group'],'source_path':r['path'],'source_center_editor_cm':[(r['min'][0]+r['max'][0])*15.24,-(r['min'][2]+r['max'][2])*15.24,(r['min'][1]+r['max'][1])*15.24],'action':'keep' if p=='P3' else 'review'})
 items.append({'priority':p,'title':title,'reason':reason,'targets':targets})
report={'map':m['map'],'review_basis':'Existing overview, north-blocks, plaza and dusk captures; saved replacement manifest; original source instance paths; installed asset filenames. No buildings edited in this review. Backdrop group identification is source-backed; street visibility of retained warehouses/garages still needs close inspection.','items':items,'perimeter_backdrop_source_groups':inv['groups'],'design_usage_in_111_replacements':dict(used),'installed_prefab_files':inv['installed_prefabs']}
(root/'docs/atlas-second-pass-review.json').write_text(json.dumps(report,indent=2))
lines=['# Atlas Park: second building pass review','',
'The highest-priority change is the original perimeter skyline. The generic box buildings behind the upgraded city come from repeated `skyline02` assemblies, which the first replacement selection did not cover. The source contains 18 assembly placements across nine assembly types; these counts are assemblies, not individual buildings or distinct architectural designs.','',
'This review combines the existing daytime and dusk captures with the saved placement manifest, source geometry paths and installed asset filenames. It is a proposed change list, not another completed replacement pass. Warehouse/garage street visibility and candidate prefab geometry still need closer inspection. City Hall, Atlas, hospital, named civic buildings and old breach remnants remain protected.','',
'## Recommended order','', '| Priority | Buildings or area | Proposed change |','|---|---|---|']
for item in items:lines.append('| '+item['priority']+' | '+item['title']+' | '+item['reason']+' |')
lines+=['','## Exact targets','', 'Actor labels below can be found in the Outliner. Retained legacy buildings are combined into tile meshes, so their source IDs/paths are the reliable replacement references. Coordinates are editor X/Y in metres; positive Y is a map axis, not a verified compass direction.','']
for item in items[1:]:
 lines+=['### '+item['title'],'','| Target | Current building | X / Y (m) |','|---|---|---|']
 for t in item['targets']:
  xyz=t.get('location_cm',t.get('source_center_editor_cm'))
  lines.append('| `'+t.get('actor',f"Legacy source {t['source_id']:03d}")+'` | `'+t.get('design',t.get('source_group'))+'` | '+f'{xyz[0]/100:.1f} / {xyz[1]/100:.1f}'+' |')
 lines.append('')
lines+=['## City Sample buildings to explore','',
'The installed project contains 75 BPP asset files, including alternate Level01 assemblies and rooftop pieces; this is not 75 unique buildings and does not establish that the complete Matrix demo city is installed. The first 111 replacements use 15 designs. Earlier study buildings use additional designs. The following locally installed candidates were not used in those 111 placements; inspect their real geometry, materials and fit before choosing them.','',
'| Candidate | Reason to inspect |','|---|---|',
'| `BPP_Bldg_Hero_CHC_BlockThreeBuilding_A01_N1` | A multi-building assembly could break up repeated frontage; verify separability and plot size. |',
'| `BPP_Bldg_Hero_Mid_NYG_Triangle_B01_N1` | Explore a different corner/footprint family. |',
'| `BPP_Bldg_Hero_Mid_SFA_Triangle_N1` / `Mid_SFC_Triangle_N1` | Additional corner candidates; verify shape and street-facing entrances. |',
'| `BPP_Bldg_Hero_Low_SFD_Long_N1` | Measured about 184 × 28 × 19 m: potentially useful for long, low street frontage, unsuitable for a small plot without recomposition. |',
'| `BPP_Bldg_Hero_Mid_CHG_Long_A01_N1` | Measured about 27 × 211 × 110 m: a large block candidate, not a small storefront. |',
'| `BPP_CHD_Ref_A1_N1` | Measured about 85 × 110 × 61 m: inspect as a broader, lower alternative to slender towers. |',
'| `BPP_Bldg_Hero_Tower_CHC_A01_N1` / `BPP_SFD_RoundSplitTower_N1` | Investigate new tower silhouettes for the duplicated pairs. |',
'| `BPP_Bldg_Hero_CHH_N1`, `BPP_Bldg_Hero_SFB_N1`, `BPP_Hero_SFJ_C01_N1` | Additional families to inspect and potentially reserve for the next two cities. |','',
'Previous tiny catalog bounds for NYH, SFE, SFA and several assemblies are unresolved. They cannot be treated as actual building dimensions or proof those designs are unusable. Correct the inventory from mesh instance geometry before using them.','',
'## Materials and city identity','',
'Use warm red, brown, muted tan and charcoal brick, varied by building rather than alternating mechanically. Keep mortar/detail restrained, and coordinate window frames, cornices and storefront trim. Preserve brick scale when changing color. Geometry changes come first for repeated silhouettes; color variation supports them.','',
'Atlas should favor rebuilt mixed-use streets around its historic civic core. For the next two cities, select distinct mixes of building families, height ranges, frontage and material palettes once their identities are settled. Share the library, but avoid repeating the same arrangements across all three zones.','',
'## Before each replacement','',
'Check street-facing doors and storefront orientation, sidewalk setbacks, believable scale and heights, plot fit, roofline from both ground and skyline views, and consistent day/dusk comic shading. Review mission entrances before removing a legacy exterior. Retain a few old industrial structures and the agreed wall remnants as rebuilding history.','',
'## Evidence and references','',
'- [Overview](images/atlas-upgraded/overview.png), [street view](images/atlas-upgraded/north-blocks.png), [plaza](images/atlas-upgraded/plaza.png), [dusk](images/atlas-upgraded/dusk-skyline.png).',
'- [Exact target records and backdrop source paths](atlas-second-pass-review.json).',
'- [Saved replacement manifest](atlas-upgraded-manifest.json).','',
'### Original perimeter assembly types','']
counts=collections.Counter(g['path'].rsplit('/',1)[-1] for g in inv['groups'])
for name,count in sorted(counts.items()):lines.append(f'- `{name}`: {count} source placements.')
(root/'docs/atlas-second-pass-review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('WROTE',root/'docs/atlas-second-pass-review.md')
print('TARGETS',sum(len(i['targets']) for i in items),'BACKDROP ASSEMBLIES',len(inv['groups']))
