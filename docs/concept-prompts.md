# Concept prompt kit (Gemini) for City of Heroes Reborn enemies

Goal: concept images in the same style as `full hellion1.jpg` / `Headless hellion1.jpg`, which work very well for 3D generation (local Hunyuan3D, Tripo, Meshy). Default deliverable per character: a **headless, bare-handed body** in the MetaHuman A-pose (faces come from MetaHuman), plus left/back/right views for multi-view. Headwear, face coverings and weapons are separate gear pieces: the character lines below still describe the full look, the style block strips the gear, and the gear prompts make it separately.

## MAIN ROUTE (16 Nov 2026, evening): COMPLETE characters only

Supersedes the "outfit bodies + heads" route above: automatic assembly (head swap, auto gear, skin recolouring,
random assembly) looked wrong at close range and is shelved as experimental (kept in the repo, off by default).

1. **One complete Tripo character per variant**: head, outfit and integrated gear in one export; full body,
   A-pose (MetaHuman bind pose), plain grey background. Gemini: the style block (with "bare face" removed if the
   character should wear its mask / bandana / cap as part of the model) + one character line; no headless follow-up.
2. **Rigging**: either Robert rigs in AccuRig 2 and exports FBX to `Tripo Exports\Rigged\` (never re-rigged:
   `tripo_watch` only copies it to `ue_ready`, checks size / facing / skeleton with `bl_rig_check.py`, detects the
   bone names with `skeleton_detect.py` (AccuRig CC_Base_, UE / MetaHuman, Mixamo, charpipe) and runs the CoH
   clip tests + close-ups), or `tripo_watch` auto-rigs complete models dropped elsewhere in `Tripo Exports`.
3. **Checks before anything is called good**: idle / run / Brawl / hit / death plus close-ups of the face, both
   hands, the Brawl fist and the shoulders at Brawl (`ue_ready\previews\<name>.jpg`).
4. **Variety**: more complete characters; optional manual colour tint per character with a before/after preview
   (`bl_tint_preview.py --hue --sat --val [--protect-skin]`, only colours change); animation / idle sets.
5. Gear: weapons on hand sockets set up once per character in Unreal; no automatic placement.

`tripo_watch --all-types` re-enables the experimental head / gear / clothing processing.

## Superseded: outfit bodies + swappable heads (shelved 16 Nov)

Separate clothing pieces did not fit reliably on other bodies (fit report: 34/66 pass, jackets worst), so the
production route is:

1. **Outfit bodies**: one **headless, fully dressed** Tripo export per outfit x build (clothes baked in, so they
   always fit). Gemini: style block + character line from the variation sheet + the **headless** follow-up.
   Name the download after its line, e.g. `hellions_heavy_trench_headless.glb`, drop it in `Tripo Exports\Hellions\`.
2. **Heads**: the **head library** (24 bust prompts). Name downloads `head_<id>.glb` (e.g. `head_H07.glb`) in
   `Tripo Exports\Heads\`. Attached at the neck by `bl_head_swap.py`.
3. **Skin tone**: one SkinTone colour for body + head (`bl_skin_tone.py`), so any head works on any body.
4. **Gear**: rigid socket items only (caps, masks, face/neck bandanas, hair, chains, weapons): `gear_<item>.glb`.
5. **Free variety**: outfit palette tints on the non-skin texture (`--outfit-tint h:s:v`), later bone-scale
   heavier/thinner variants.

`tripo_watch` rigs bodies (fingers, CoH tests, `ue_ready`), files heads into the head library and gear into the
gear list, all registered in `charpipe_test/characters_lib.json`; `random_character.py <lib> <out> --count N
--render` assembles random characters (body + head + tone + tint + gear) with idle/Brawl previews.

Experimental / shelved (kept in the repo): `bl_cloth_autofit.py`, `bl_fit_report.py`, `bl_wardrobe_make.py`,
`bl_wardrobe_assemble.py`, `bl_wardrobe_to_mh.py`, `bl_kitbash_*`: separate clothing pieces. `tripo_watch` logs and
skips clothing pieces.

## How to use

1. Start a new Gemini chat. Attach `full hellion1.jpg` as the style reference and, for the pose, one of the original-costume A-pose renders from `model-upgrade-samples/gemini_refs/hellions/` (e.g. `hellions_minion_01_front.png`; the `nogear/` copies have the cap/goggles removed).
2. Paste the **style block**, then one **character line** from below.
3. Ask for the **headless** follow-up in the same chat. **Headless is the default deliverable**: faces come from MetaHuman Creator (or a separate head generation), so the body image is what goes to Tripo / Hunyuan3D.
4. For multi-view 3D (Tripo front/left/back/right), ask for the **left**, **back** and **right** follow-ups.
5. Gear (bandanas, hats, masks, goggles, helmets, weapons) is generated separately with the **gear prompts** below and attached as rigid pieces.
6. Save as `<group>_<tier>_<n>_headless.jpg` (`_full`, `_left`, `_back`, `_right`) in `C:\Users\rtcru\charpipe_test\in\<group>_<tier>_<n>\`.

Tips: keep each prompt to one character. If Gemini adds a weapon, a hat or a mask, repeat "bare face, empty hands, no props, no headwear". If the arms come out too close to the body or the palms face forward, repeat "MetaHuman A-pose: upper arms about 40 degrees out from the body, palms facing down and inward toward the thighs".

## Style block (paste first, every time)

> Use the attached images as references: the first for the rendering style, the second for the exact pose. Create a NEW character in exactly this style: photoreal modern video game character render (Unreal Engine 5 quality), full body from the top of the head to the soles of the boots, front view facing the camera, straight-on camera at chest height. Pose: the standard MetaHuman bind A-pose, both upper arms lowered about 52 degrees below horizontal (about 38-40 degrees out from the body), elbows almost straight, palms facing down and slightly inward toward the thighs, fingers relaxed and slightly spread and not touching the body or clothing, legs straight and slightly apart (feet a little wider than the hips). Bare face, no headwear, masks, bandanas, goggles, helmets or face coverings; hair visible. No weapons or held items, empty hands. Keep all clothing, gloves and boots. Plain flat mid-grey background, soft even studio lighting, no shadows on the background, no text, no logo watermark, realistic adult proportions (about 7.5 heads tall). The character:

## Follow-ups (same chat)

- **Headless (default):** "Now the exact same character, same pose, clothing and lighting, but without the head: show a clean neck stump at the collar, nothing above the neck. Keep everything else identical."
- **Left:** "Now the exact same character seen from its left side (camera rotated 90 degrees), same A-pose, clothing and lighting, plain mid-grey background, same framing and height."
- **Back:** "Now the exact same character from behind (back view), same A-pose, clothing and lighting, plain mid-grey background, same framing and height."
- **Right:** "Now the exact same character seen from its right side (camera rotated 90 degrees the other way), same A-pose, clothing and lighting, plain mid-grey background, same framing and height."
- **Head close-up (only if not using MetaHuman faces):** "Now a head-and-shoulders portrait of the same character, front view, bare face, neutral expression, plain mid-grey background, same lighting."

## Gear prompts (separate rigid pieces)

Paste once: "Isolated single object, product shot, three-quarter view, plain flat mid-grey background, soft even studio lighting, photoreal Unreal Engine 5 game asset, no person, no mannequin, no text. The object:" then one line:

- Hellions: red-and-white paisley bandana tied as a face mask (lower face) / worn red baseball cap / black leather biker cap / red horned leather demon mask / flame-painted metal shoulder pad.
- Skulls: white bone skull mask / skull-faced helmet.
- Outcasts: knitted beanie / elemental goggles.
- Family: grey fedora.
- Tsoo: carved red demon mask / painted opera mask.
- Freakshow: welding-style goggles / metal jaw piece.
- Council: helmet with visor / officer beret.
- Circle of Thorns: black leather face mask / tall horned headdress.
- Vahzilok: white plague-doctor mask / surgical goggles mask.
- Banished Pantheon: carved wooden tribal mask.
- Warriors: crested bronze helmet.
- Sky Raiders: flight goggles / helmet with visor.
- Nemesis: spiked Prussian helmet with gas mask.
- Crey: tactical visor helmet.
- Carnival of Shadows: white porcelain mask / mirror mask / top hat.
- Malta: balaclava / helmet with night-vision goggles.
- Arachnos: full-face helmet with red lenses.
- 5th Column: steel helmet with gas mask.
- Weapons (all groups): baseball bat / fire axe / sledgehammer / combat knife / pump shotgun / compact submachine gun / pistol.

## Character lines

Each group keeps its original 2004 colours and motifs, updated to how the gang would dress about 25 years later. Tiers: **Minion** (common thug), **Lieutenant** (tougher, more gear), **Boss** (iconic, big, distinctive). Make 2-3 variants per tier by changing build, age, ethnicity, hair and one clothing item.

### Hellions (Atlas Park street gang, demon worship)
- Minion: young street thug, ochre or red sleeveless vest over a white tank top printed with a red demon-goat emblem, red camo cargo pants, worn combat boots, paisley bandana over the lower face, fingerless gloves.
- Lieutenant: muscular biker, black leather jacket with orange flame decals and the red goat-head patch on the back, chains, studded belt, bandana around the neck, shaved head with flame tattoos.
- Boss: huge gang leader, red demon face paint or horned leather mask, black leather vest with flame-painted metal shoulder armour, red pentagram tattoos, chains, heavy boots.

### Skulls (death-obsessed street gang)
- Minion: lean punk in black leather and denim, white skull face paint, black hoodie with a white skull print, ripped black jeans, boots.
- Lieutenant: muscular thug, skull-faced bone mask, black leather jacket covered in silver skull studs, bone-white arm wraps.
- Boss: imposing leader, full skull helmet or carved bone mask, black long coat, bone necklace, silver skull rings.

### Outcasts (elemental-powered street gang)
- Minion: young gang member in a colourful track jacket with a stylised elemental symbol (fire, ice or lightning) on the back, baggy pants, sneakers, beanie.
- Lieutenant: elemental specialist with glowing elemental markings on the arms (orange fire / pale blue ice / yellow lightning), sleeveless jacket, arm wraps.
- Boss: charismatic gang boss, long coat with the gang's elemental insignia, elemental-coloured hair, jewellery, intense eyes.

### Trolls (Superadine-addicted brutes)
- Minion: hulking man with green-tinted skin and visible veins, ripped tank top, cargo shorts, crude metal piercings, mohawk.
- Lieutenant: even bigger green-skinned brute, scrap-metal shoulder plate, spiked wristbands, torn jeans, chains.
- Boss: massive green-skinned troll leader, crude scrap armour, giant spiked bracers, war paint, tusk-like teeth.

### Family (organised crime)
- Minion: mob soldier in a dark pinstripe suit, open collar, gold chain, fedora, polished shoes.
- Lieutenant: enforcer in a long dark overcoat over a three-piece suit, leather gloves, scar.
- Boss: older mob boss, tailored double-breasted suit, silk tie, slicked-back silver hair, signet ring.

### Tsoo (tattooed martial-arts gang, ink magic)
- Minion: martial artist with pale blue-tinted skin covered in black ink tattoos, red and black sleeveless kung-fu top, loose black trousers, cloth shoes.
- Lieutenant: ink-man sorcerer with glowing tattoos, red sash, carved demon mask pushed up on the head.
- Boss: Tsoo sorcerer in ornate red and black robes, full painted opera-style mask, long sleeves with ink patterns.

### The Lost (Rikti-mutated cultists)
- Minion: gaunt homeless cultist in a ragged hooded robe and layered rags, pale bluish skin, sunken eyes.
- Lieutenant: partially mutated cultist with grey-blue alien skin patches and enlarged forehead, tattered robes.
- Boss: heavily mutated leader, alien grey-blue skin, bald domed head, robes with alien glyphs.

### Freakshow (cyborg punks)
- Minion: punk with a bright mohawk, many piercings, ripped clothes, one crude mechanical arm, goggles.
- Lieutenant: bulkier cyborg punk with a metal jaw, pistons in both arms, studded leather, tubing.
- Boss: towering heavily augmented cyborg (Freakshow "tank"), huge mechanical arms, exposed hydraulics, punk hair.

### Council (military cult, successors of the 5th Column)
- Minion: soldier in a dark red and black military uniform with the Council emblem, combat vest, helmet with visor.
- Lieutenant: officer with a long red-trimmed coat, beret, insignia, armoured gloves.
- Boss: elite commander in powered armour plates in red and black, cape, Council crest on the chest.

### Circle of Thorns (ancient mystic cult)
- Minion: cultist in a dark red hooded robe with a black leather mask, ritual sash, bare feet or wraps.
- Lieutenant: mage in layered red and black robes with glowing runes, horned mask, staff-less hands glowing.
- Boss: high priest in ornate crimson robes, tall horned headdress, ancient Oranbegan jewellery.

### Clockwork (brass automatons)
- Minion: small humanoid brass robot of gears and springs, exposed clockwork, round head with a single lens.
- Lieutenant: larger clockwork automaton with brass plating, steam vents, articulated claws.
- Boss: towering clockwork construct, layered brass armour, glowing core, big gear shoulders.

### Vahzilok (surgeon cult and corpse-men)
- Minion: patchwork reanimated corpse in surgical scrubs, stitched grey-green skin, metal staples.
- Lieutenant: cultist surgeon in a white plague-doctor style mask, stained surgical gown and apron.
- Boss: mad doctor in a long surgical coat, mask with goggles, surgical tools on a bandolier.

### Banished Pantheon (spirit mask cult)
- Minion: possessed cultist with a carved wooden tribal mask, rough robes, painted skin.
- Lieutenant: shaman with a larger painted mask, feathers and bones, ritual body paint.
- Boss: towering mask-spirit giant, huge carved mask face, bark-like skin, totem decorations.

### Devouring Earth (eco-monsters)
- Minion: humanoid made of rock and moss, glowing green cracks.
- Lieutenant: crystal-encrusted plant creature, vines and mushrooms growing from the shoulders.
- Boss: huge rock-and-root titan, crystals, glowing green core.

### Warriors (classical warrior gang)
- Minion: street fighter in red and gold Greek-style chest armour over a hoodie, sandal-boots, leather skirt plates.
- Lieutenant: centurion-style enforcer, crested helmet, red cape, bronze bracers.
- Boss: gladiator champion, ornate bronze armour, red plume, scars.

### Sky Raiders (jetpack mercenaries)
- Minion: mercenary in a blue and white flight suit, goggles, small jetpack on the back.
- Lieutenant: engineer with a bigger jetpack, tool belt, armoured vest, helmet with visor.
- Boss: Sky Raider commander, armoured flight suit with wing-like jetpack, rank insignia.

### Nemesis (steampunk army)
- Minion: Nemesis soldier in a dark green and brass steampunk uniform, spiked Prussian helmet, gas mask.
- Lieutenant: officer in a long green greatcoat with brass buttons, monocle, mechanical arm.
- Boss: Nemesis automaton general, brass and steel body inside a green military coat, glowing eyes.

### Crey (corporate private military)
- Minion: corporate security agent in sleek white and dark grey tactical armour with the Crey Industries logo, visor helmet.
- Lieutenant: cyber-enhanced Crey agent, glowing implants, armoured coat.
- Boss: Crey super-soldier, powered armour, corporate insignia, energy conduits.

### Carnival of Shadows (masked performers)
- Minion: harlequin performer in a black and white diamond-pattern costume, white porcelain mask, ruffled collar.
- Lieutenant: illusionist in a tailcoat with a mirror mask, gloves, top hat.
- Boss: ringmaster or master illusionist in an ornate dark purple coat, golden mask, cape.

### Rikti (alien invaders)
- Minion: Rikti soldier, grey-skinned alien with a large bony head, dark armour with breathing apparatus.
- Lieutenant: Rikti mentalist in robes with a glowing headpiece.
- Boss: Rikti war commander in heavy armour plates, tall head crest.

### Malta (covert anti-super agents)
- Minion: black-ops operative in black tactical gear, balaclava, night-vision goggles on the helmet.
- Lieutenant: specialist with an armoured vest, gadget belt, gauntlets.
- Boss: Malta commander in heavy black tactical armour, long coat.

### Arachnos (Rogue Isles spider army)
- Minion: Arachnos soldier in black armour with gold trim, red spider insignia, full-face helmet with red lenses.
- Lieutenant: Fortunata or Widow agent in a sleek black and purple bodysuit with spider motifs, long hair.
- Boss: Arachnos officer with mechanical spider legs on the back, gold and black armour.

### 5th Column (Nazi-styled precursor army; keep it non-specific)
- Minion: soldier in a dark grey and red military uniform with a generic numeral 5 emblem, helmet, gas mask.
- Lieutenant: officer with a long coat, cap and red armband (emblem only, no real-world symbols).
- Boss: heavily armoured trooper or werewolf-soldier hybrid.

## Notes

- Keep the same grey background and MetaHuman A-pose for every image so the 3D generator and the auto-rig behave the same for all characters.
- The headless image plus a separate head close-up gives the best faces (the pipeline attaches the head at the neck).
- Gear, weapons, hats and masks are generated separately with the gear prompts and attached as rigid pieces (charpipe `bl_accessory.py`: head / hand_r / belt sockets).

## Hellion variations

The 2004 Hellions are one outfit template with skin and head swaps. This section builds variety in layers that mix freely on one skeleton: **build × outfit pieces × palette × MetaHuman head × gear × idle**. Use the style block above (bare face, no headwear or weapons, MetaHuman A-pose, mid-grey). Ask for the **headless** follow-up by default, plus left/back/right for multi-view.

Identity to keep in every line: Atlas Park street gang of demon-worshipping wannabes; ochre/mustard, blood red and black; flame motifs; the red goat-head (Baphomet-style) emblem and pentagram sigils; worn, cheap, DIY street clothes rather than real armour.

### Body builds (one generation each, reused under many outfits)

Paste after the style block: "Plain base outfit for a body-shape reference: grey fitted tank top, grey fitted jeans, black boots. The character: ..." (the base build is what the outfit pieces are fitted to).

- **B1 lean street kid:** 19-year-old, wiry and thin, narrow shoulders, slightly hunched, about 1.75 m.
- **B2 average thug:** mid-20s, medium athletic build, about 1.80 m.
- **B3 heavy brawler:** stocky and broad, thick neck and arms, beer belly over strong muscle, about 1.82 m.
- **B4 big biker:** tall and massive, very broad shoulders, heavy forearms, about 1.92 m.
- **B5 wiry veteran:** late 40s, lean and sinewy, weathered skin, about 1.78 m.
- **BF1 / BF2 female builds (pending Robert's decision; do not generate yet):** BF1 lean, athletic, about 1.68 m; BF2 strong and solid, broad shoulders, about 1.72 m.

### Role-tied outfits (full looks; also the source of the per-slot pieces)

Paste after the style block: "The character: a Hellion street-gang member, [build], wearing ..."

- **O1 Brawler (minion, melee):** open ochre leather biker vest over a white tank top printed with the red goat-head emblem, red camo cargo pants, worn black combat boots, fingerless black gloves.
- **O2 Gunner (minion, ranged):** black zip hoodie with a red pentagram printed on the back, sleeves pushed up, olive cargo pants with knee patches, high-top sneakers, black tactical gloves.
- **O3 Fire-blaster (minion/lieutenant, fire powers):** long dark brown leather trench coat with scorched hem and orange flame decals rising from the bottom, black tank top, black jeans, steel-toe boots, heat-scorched leather gloves.
- **O4 Wrench (minion, melee):** grease-stained red mechanic coverall with the top half tied around the waist, black ribbed tank top, a hand-painted goat-head patch on the chest pocket, work boots, rubber work gloves.
- **O5 Street punk (minion):** sleeveless red-and-black flannel shirt, open over a black band T-shirt with a flaming skull print, ripped black jeans, studded belt, scuffed biker boots.
- **O6 Ink-sleeve thug (minion):** bare chest under an open black denim vest, full arm and chest tattoos of flames and demon sigils, red cargo shorts over black leggings, combat boots.
- **O7 Lieutenant enforcer:** black leather biker jacket with orange flame decals and a large red goat-head back patch, studded leather shoulder guards, black jeans with a chain, heavy biker boots, studded gloves.
- **O8 Boss armoured-spiked:** sleeveless black leather vest with flame-painted metal shoulder plates and spikes, red demon-sigil tattoos on the arms, chains across the chest, black leather pants, heavy buckled boots, spiked bracers.

### Per-slot pieces (swap with `bl_split_by_texture.py`; same skeleton)

Generate a piece by asking for the outfit with the other slots in plain grey ("...; everything else plain grey: grey tank top, grey jeans, black boots"), then split.

- **Tops:** open ochre biker vest / sleeveless denim vest / black leather jacket / zip hoodie / sleeveless flannel / mechanic coverall top / trench coat / bare chest with tattoos / goat-head print tank / flaming-skull band T-shirt.
- **Bottoms:** red camo cargos / ripped jeans / black biker leathers / track pants with a red stripe / olive work cargos / coverall bottom / cargo shorts over leggings.
- **Footwear:** combat boots / high-top sneakers / biker boots with buckles / steel-toe work boots.
- **Hands:** fingerless gloves / tactical gloves / rubber work gloves / studded gloves / spiked bracers / bare hands with knuckle tattoos.

### Palette swaps (in-engine material parameters, no new generation)

Keep to the Hellion colours. Each piece gets 3-4 tints plus wear:
- **Ochre/mustard** (classic vest), **blood red** (camo, coveralls), **black** (leather, denim), **charcoal** (hoodies), **olive** (cargos, accent only).
- **Flames:** orange-to-yellow decals; variants: none, hem flames, sleeve flames, full back piece.
- **Sigils:** red goat-head emblem; pentagram; demon-horn skull; hand-painted vs printed vs patch.
- **Wear:** new, faded, grease-stained, scorched (fire-blasters only).

### Gear (rigid pieces on sockets; gear prompts section)

- **Minion:** paisley bandana (face mask or neck), red baseball cap (forward or backward), black beanie, wallet chain, wristbands; weapons: baseball bat, fire axe, lead pipe, combat knife, sledgehammer.
- **Lieutenant:** biker cap, chain over the shoulder, studded belt, goggles on the forehead; weapons: pump shotgun, compact submachine gun, pistol.
- **Boss:** horned leather demon mask, spiked shoulder plate, chains, a large goat-skull belt buckle; weapons: heavy chain, flame-painted shotgun.

### Idle personality per build (CoH idle replaced per build)

- **B1 lean kid:** twitchy, weight shifting, glancing around, bouncing on the toes.
- **B2 average thug:** cocky slouch, cracking the neck, rolling the shoulders.
- **B3 heavy brawler:** slow heavy sway, cracking the knuckles, chest out.
- **B4 big biker:** still and planted, arms crossed or thumbs in the belt, slow head turns.
- **B5 wiry veteran:** relaxed lean, smoking gesture, unimpressed.
- **Fire-blasters (any build):** idle with small hand flame flicks (VFX, not mesh).

### Variety maths

5 builds × 6-8 outfits (or about 10 tops × 7 bottoms × 4 footwear) × 4 palettes × MetaHuman heads × gear gives hundreds of distinct Hellions from about 20-25 generated pieces. Recommended first batch: B2, B3, B4 × O1, O2, O3, O7 (12 headless images), then split and mix.

## Head library (swappable heads)

Bodies are generated **headless**; heads come from this library and are attached with `tools/charpipe/bl_head_swap.py` (sized to the neck ring, weighted neck to Head). Skin tone is NOT baked into the choice of head: `bl_skin_tone.py` finds the skin and re-tints body and head with one SkinTone colour, so any head works on any body. Make each head once, reuse it everywhere.

**Head style block (paste first, every time):**

> Use the attached image as the style reference. Create a head-and-neck bust of a NEW character in exactly this style: photoreal modern video game character (Unreal Engine 5 quality), head and neck down to the collarbones, front view, looking straight at the camera, straight-on camera at eye height, neutral-to-tough expression with the mouth closed, bare head or hair only (no hats, caps, hoods, masks, bandanas, goggles, glasses or face coverings), no clothing visible except a plain grey crew-neck collar at the very bottom, plain flat mid-grey background, soft even studio lighting, no text, no watermark, realistic adult proportions. The character:

**Side follow-up (same chat):** "Now the exact same head from its left side (profile, camera rotated 90 degrees), same lighting, same framing and height, plain mid-grey background."
(Optional back: "Now the exact same head from behind, same framing.")

Save as `heads/<id>_front.png` (and `_left.png`). Tripo: upload the front (and side) image, texture + PBR, no rig.

| # | Character line |
|---|---|
| H01 | Hispanic man, mid-20s, buzz cut, thin moustache, small scar through the left eyebrow |
| H02 | Black man, early 30s, short dreadlocks tied back, trimmed beard |
| H03 | White man, late 40s, shaved bald head, heavy grey stubble, broken nose |
| H04 | East Asian man, early 20s, bleached mohawk with shaved sides, ear piercings |
| H05 | Middle Eastern man, mid-30s, short wavy black hair, full black beard, neck tattoo of flames |
| H06 | White man, early 20s, ginger buzz cut, freckles, split lip scar |
| H07 | Black man, late 40s, bald, grey goatee, deep forehead lines |
| H08 | South Asian man, late 20s, slicked-back black hair, sharp jawline, faint stubble |
| H09 | Native American man, mid-30s, long black braids, stern expression |
| H10 | White man, mid-30s, shaved head with a red pentagram tattoo behind the ear, blond beard |
| H11 | Pacific Islander man, early 30s, curly hair in a top knot, broad face, chin tattoo lines |
| H12 | Hispanic man, late 40s, grey-streaked slicked hair, scar across the cheek, moustache |
| H13 | Black man, early 20s, high-top fade, small diamond stud earring |
| H14 | White man, early 50s, receding long grey hair, long biker beard |
| H15 | East Asian man, mid-30s, undercut with a long top, thin scar on the chin |
| H16 | Mixed-race man, late 20s, short twists, light beard, demon-horn tattoo on the temple |
| H17 | White man, late 20s, black mohawk, eyebrow piercings, sunken tired eyes |
| H18 | Middle Eastern man, early 40s, buzz cut, heavy brow, salt-and-pepper beard |
| H19 | Black man, mid-30s, long dreadlocks to the shoulders, full beard |
| H20 | Hispanic man, early 20s, shaved head, teardrop tattoo under the eye |
| H21 | White man, mid-40s, messy shoulder-length brown hair, bags under the eyes, scar on the nose |
| H22 | South Asian man, early 50s, bald with a grey horseshoe of hair, thick grey moustache |
| H23 | East Asian man, late 40s, short grey crew cut, scarred knuckle-like brow, hard stare |
| H24 | Mixed-race man, mid-20s, cornrows, thin chin-strap beard |
| HF1-HF6 | Female heads: pending Robert's decision on female Hellions (same style block; vary ethnicity, age 20s-40s, hair: buzz, undercut, braids, long, mohawk) |

Tips: keep the expression neutral-to-tough with the mouth closed (open mouths and smiles generate badly and look wrong on idle animations). Ask again if Gemini adds a hat, hood or glasses. Ethnicity is in the face shape and hair; the final skin colour comes from the SkinTone parameter, so you can also reuse a head with several tones.

## Garment-on-base-body (experimental, shelved with the clothing-piece route)

Garments generated alone come out at their own size and pose and have to be fitted afterwards (fitting is the weak
spot, worst for jackets). The more reliable route: generate the garment **already worn by our base body**, in the
same A-pose, so its size, sleeves and collar match the body from the start. Then Tripo-export it, split the garment
off with `bl_split_by_texture.py` (or Tripo's part export) and it drops onto the base body with almost no fitting.

**Attach two images:** the style reference (`full hellion1.jpg`) and the base body render
(`model-upgrade-samples/gemini_refs/base_body_front.png`: the bare BaseHellion in grey underwear, A-pose).

**Template (paste, then fill in the garment):**

> Use the first attached image as the style reference and the second as the exact body and pose. Show this SAME man,
> same body shape, same proportions, same MetaHuman A-pose (upper arms about 52 degrees below horizontal, palms
> facing the thighs, legs slightly apart), same camera and framing, plain flat mid-grey background, soft even studio
> lighting, now wearing ONLY this one garment over his plain grey underwear: [GARMENT]. Nothing else changes: no
> other clothing, no shoes unless the garment is footwear, no hat, no mask, no jewellery, bare hands, bald head,
> neutral face. The garment must fit his body naturally (sleeves following his arms, collar at his neck, hem at
> the natural length), photoreal Unreal Engine 5 quality, front view, full body head to feet.

**Follow-ups (same chat):** "Now the exact same image from behind (back view)." / "...from his left side."

**Garment lines (Hellions):**
- open black leather biker jacket with orange flame decals on the sleeves and a red goat-head patch on the back
- long dark brown leather trench coat to the knees with scorched hem and flame decals, worn open
- black zip hoodie, hood down, red pentagram on the chest, sleeves to the wrists
- open ochre leather biker vest with studs
- white sleeveless undershirt with a red goat-head print
- olive cargo pants with knee pockets, belted
- black ripped jeans with camo patches
- black lace-up combat boots
- fingerless black leather gloves with metal studs

Save as `garments/<group>_<garment>_onbody_front.png` (+ `_back`, `_left`). Name the Tripo download the same; drop it in
`Tripo Exports\<Group>\<garment>_onbody\`.
