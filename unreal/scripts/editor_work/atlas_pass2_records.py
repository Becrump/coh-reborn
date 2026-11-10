import json,pathlib
root=pathlib.Path('C:/Users/rtcru/ClaudeProjects/coh-reborn-expansion');base=pathlib.Path('C:/Users/rtcru/ClaudeProjects/COHReborn')
m=json.load(open(base/'atlas_pass2_manifest.json'));p=json.load(open(base/'atlas_pass2_prefab_state.json'));s=json.load(open(base/'atlas_pass2_source_audit.json'))
text='''# Atlas Park second building pass

Working map: `/Game/AtlasPark4/AtlasPark_SecondPass`. The first upgraded map remains the comparison and recovery copy.

This pass replaces seven repeated street buildings with four additional City Sample designs, applies four restrained facade palettes to twelve shop-row buildings, and replaces the old perimeter backdrop with forty-six buildings using ten designs. The outer buildings are visual scenery with collision disabled; they do not add playable streets or interiors.

The street swaps break up the tower pairs on plots 037 and 072, the repeated modern-tower run at 039–041, and repeated neighborhood designs at 008 and 104. A rounded modern building is also used at 029, and a different low building at 079.

Brown, warm-red, tan and charcoal material copies tint selected wall materials while retaining their original textures, scale and alpha. The comic filter and softened normal detail remain. Material overrides are saved in dedicated prefab component templates so the packed buildings retain them on reload. Some unsupported material channels retain their original colors.

The perimeter source export retains the previous building removals and breach edits, and removes `skyline02` assemblies from twenty-eight source tile coordinates. Thirty-four existing tile actors are rebound or removed as appropriate. The affected export retains all sixteen protected civic/transport pieces present in these outer tiles. Central landmark geometry is outside this export's changed area. City Hall, Atlas, named civic buildings, the retained pyramid towers and the agreed wall remnants are preserved.

## Review images

- [Before overview](images/atlas-second-pass/before-overview.png) / [After overview](images/atlas-second-pass/after-overview.png).
- [Before outer street](images/atlas-second-pass/before-outer-street.png) / [After outer street](images/atlas-second-pass/after-outer-street.png).
- [Before dusk skyline](images/atlas-second-pass/before-dusk-skyline.png) / [After dusk skyline](images/atlas-second-pass/after-dusk-skyline.png).

## Records

- [Placement manifest](atlas-second-pass-manifest.json).
- [Source audit](atlas-second-pass-source-audit.json).
- [Saved-map validation](atlas-second-pass-validation.json).

The existing streets remain the gameplay basis. Mission-door integration, navigation, HLODs and performance validation are separate work; the perimeter scenery must be redesigned and grounded as playable blocks before future expansion opens it to players.
'''
(root/'docs/atlas-second-pass.md').write_text(text,encoding='utf-8')
for file,new in [('atlas_pass2_manifest.json','atlas-second-pass-manifest.json'),('atlas_pass2_source_audit.json','atlas-second-pass-source-audit.json')]:
 (root/'docs'/new).write_text((base/file).read_text(),encoding='utf-8')
print('Second-pass records written')
