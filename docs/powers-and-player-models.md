# Original power animations and player models

Step 1 and 2 of the game systems build order (2026-10-20). Robert asked for this. He wants the original player models as stand-ins until our own MetaHuman hero creation exists. Every power should play its original animation.

The converters below run anywhere the game data is present: the cloud workspace or Robert's PC. Their output is game data, so it stays out of git.

## 1. Power to animation map: `coh2unreal.powanim`

```
python tools/rules/coh_rules.py <i24>/data/defs testhero <out>/rules
python -m coh2unreal.powanim --data <i24>/data --out <out>/powers --powers-json <out>/rules/hero_all_sets.json
```

- **Where a power's animation comes from:**
  - Each power def includes a `.pfx` file (`menu/powers/animfx/...`).
  - That file holds the sequencer bits (`AttackBits`, `ActivationBits`, `HitBits`, `InitialAttackBits`, `WindupBits`, `BlockBits`, `DeathBits`, plus `ModeBits`).
  - It also holds the timing (`FramesBeforeHit`, `AttackFrames`, `ProjectileSpeed`, `DelayedHit`) and the effect files (`ActivationFX`, `AttackFX`, `HitFX`, `ContinuingFX` ...).
  - `CustomFX` blocks are the alternate themes (palettes and alternate animations).
- **How the move is picked:** the converter follows the game's own rule from `seqSearchInterrupts` in `Common/seq/seqsequence.c`, starting from `CombatReady` (or `Ready` when nothing interrupts combat ready).
  - The candidates are the moves whose `Interrupts` name a `Member` group of the current move.
  - Of those, only moves whose `Requires` bits are all set count.
  - The highest `Priority` wins. Equal priorities rotate, and the others are listed as `alternates`.
- **The move chain:** the chosen move then runs through its `NextMove` chain back to a cycling ready.
- **Per body type:** the chain is resolved for male, fem and huge. A body type without its own `Anim` falls back to `ParentType`, so fem and huge often play a male anim.
- **Output:**
  - `power_anims.json`: power -> fields above plus `moves[body][bitField].segments = [[move, anim, firstFrame, lastFrame], ...]`. A `lastFrame` of 0 means the end of the track. The data runs at 30 fps.
  - `anim_list.json`: the anims every player power and core move needs, per body. That's 372 male, 385 fem and 388 huge.
- **Checked results:** all 3,105 player powers resolve.
  - Only 168 of about 12,000 bit sets have no move. These are edge cases: `GETUP HIT`, dual pistol `RELOAD`, `HOVER`, staff forms and shapeshifts.
  - Spot checks that match the data:
    - Flares: `Rapid_Quick`, `male/energy_rapid` 1-31, hit at frame 25.
    - Brawl: `Brawl_R` `male/brawl_high2`.
    - Fire Ball: `Cast` `male/palmcast`.
    - Haymaker: `SmashCast` `male/2hsmash`.
    - Storm Kick: `MA_Roundhouse` `male/kick_highspin`.

## 2. Player models and the animation library: `coh2unreal.player`

```
python -m coh2unreal.player --data <i24>/data --piggs <piggs> --out <out>/player presets
python -m coh2unreal.player ... models --all-presets            # or --npc Model_Positron, --costume my_hero.json
python -m coh2unreal.player ... anims --list <out>/powers/anim_list.json
python -m coh2unreal.player ... presets --show Model_MsLiberty  # a preset as an editable costume file
```

- **Presets:** 120 hero NPCs on player bodies make ready stand-ins.
  - Sources: signature heroes, Freedom Corps, Hero Corps, Atlas Park contacts and others.
  - Bodies: 59 male, 52 fem and 9 huge.
  - Each exports as rigged glTF on the real player skeleton: `male/skel_ready2` (68 bones), `fem/skel_ready2` (63 bones) or `huge/skel_ready` (60 bones).
  - Costume parts are kept as separate meshes.
  - Clips: idle, combat_idle, run, attack (Brawl), hit and death.
  - Four pieces were not found in the archives: two capes and one glove pair. Everything else exported.
- **Costume file:** `--costume` takes the NPC `Costume` block as JSON, so a friend can pick any part the costume creator offers. The format is in the module docstring.
- **Animation library:** `anims/<body>/<body>_anims_NN.gltf` (218 MB in total).
  - Each file holds the body's skeleton, a one-triangle `AnimCarrier` mesh skinned to the hips, and 40 clips.
  - Each clip is the whole `.anim` track, named after it: `male/energy_rapid` becomes `male__energy_rapid`.
  - `anims.json` lists each clip with its file, frame count and seconds.
  - Male anims played on the fem and huge skeletons use the game's own rule for that: the pose takes the anim's position minus the anim's base position plus the body's base position (`animDelta`).
- **Verified:** previews were rendered with three.js. Positron, Ms Liberty and Back Alley Brawler play Flares, Brawl, Haymaker and Storm Kick at their hit frames, with correct poses on all three skeletons.

## 3. Unreal side (PC session)

1. **Import.**
   - Import one preset per body as a skeletal mesh. This gives you `SK_CoH_Male`, `SK_CoH_Fem` and `SK_CoH_Huge` with their skeletons.
   - Import every `<body>_anims_NN.gltf` onto that body's skeleton as animations only. Use the Interchange glTF pipeline, set the target skeleton, and skip meshes.
   - Then import the other presets onto the same skeletons. Every preset of a body shares the skeleton, because the joint names are identical.
2. **Emit sockets.**
   - Add sockets on the CoH skeletons (Hips, Chest, Head, `HandR`/`HandL`, feet), the same names as on the mannequin.
   - The original attach bones in the `.fx` files are `WepR`, `WepL`, `HandR`, `HandL`, `Chest`, `Head` and `Hips`, so those can be used directly.
3. **Rules subsystem.**
   - Load `power_anims.json` next to the other rules JSON.
   - For a power, take `moves[body].AttackBits.segments`, or `ActivationBits` for toggles and self powers.
   - Build a dynamic montage from the segments in order: section = clip `anim.replace('/', '__')`, start = `first/30` s, end = `last/30` s or the clip's end.
   - The hit, projectile launch and damage happen at `FramesBeforeHit/30` s after the start. With `DelayedHit`, the hit lands after travel at `ProjectileSpeed` ft/s.
   - The cast time stays `TimeToActivate` from the power, which is the server-side rule, unchanged.
   - Victims play `HitBits`, which is usually `C_HitQuick`.
4. **Hero pawn.**
   - Add a "CoH body" mode to `ACoHHeroCharacter` that uses a preset mesh and the CoH locomotion clips: `idle`/`combat_idle`/`run` from the preset, plus `JumpUp`, `Fall`, `Land` and `FlyCycle` from the library.
   - Keep the mannequin as the option for testing other animation packs.
5. **Pick a preset per player.** Until hero creation exists, a player's hero file names a preset or a costume file.

## Next in the build order

Hero build (archetype, primary and secondary sets, powers at their original levels, then pools), then leveling (XP, level-ups, inspirations), then power effects (`.fx`/`.part` to Niagara, starting with Fire Blast), then enemy setup (Atlas Park levels, villains on their own attack animations).
