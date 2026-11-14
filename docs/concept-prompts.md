# Concept prompt kit (Gemini) for City of Heroes Reborn enemies

Goal: concept images in the same style as `full hellion1.jpg` / `Headless hellion1.jpg`, which work very well for 3D generation (local Hunyuan3D, Tripo, Meshy). One character = 2 images (full + headless), optionally side and back for multi-view.

## How to use

1. Start a new Gemini chat and attach `full hellion1.jpg` as the style reference.
2. Paste the **style block**, then one **character line** from below.
3. When it looks right, ask for the **headless follow-up** in the same chat (keeps the same character).
4. Optional for better 3D: ask for the **side** and **back** follow-ups.
5. Save as `<group>_<tier>_<n>_full.jpg`, `..._headless.jpg` (`_side`, `_back`) and drop them in `C:\Users\rtcru\charpipe_test\in\<group>_<tier>_<n>\` (rename full to `front.jpg`).

Tips: keep each prompt to one character. If Gemini adds a weapon in the hand, say "empty hands, no props" (weapons and gear are generated separately and attached in the pipeline). If arms come out too close to the body, repeat "arms 30 degrees away from the body, hands not touching anything".

## Style block (paste first, every time)

> Use the attached image as the style reference. Create a NEW character in exactly this style: photoreal modern video game character render (Unreal Engine 5 quality), full body from the top of the head to the soles of the boots, front view facing the camera, neutral relaxed A-pose with both arms held about 30 degrees away from the body, hands open with the fingers slightly spread and not touching the body or clothing, feet shoulder-width apart, plain flat mid-grey background, soft even studio lighting, no shadows on the background, no text, no logo watermark, empty hands with no weapons or props, realistic adult proportions (about 7.5 heads tall). The character:

## Follow-ups (same chat)

- **Headless:** "Now the exact same character, same pose, clothing and lighting, but without the head: show a clean neck stump at the collar, nothing above the neck. Keep everything else identical."
- **Side:** "Now the exact same character from the left side (90 degrees), same pose, clothing and lighting, plain mid-grey background."
- **Back:** "Now the exact same character from behind (back view), same pose, clothing and lighting, plain mid-grey background."
- **Head close-up (for separate head generation):** "Now a head-and-shoulders portrait of the same character, front view, neutral expression, plain mid-grey background, same lighting."

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

- Keep the same grey background and A-pose for every image so the 3D generator and the auto-rig behave the same for all characters.
- The headless image plus a separate head close-up gives the best faces (the pipeline attaches the head at the neck).
- Gear, weapons, hats and masks are best generated separately ("isolated object, plain grey background, product shot") and attached as rigid pieces.
