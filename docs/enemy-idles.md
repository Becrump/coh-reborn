# Enemy idles and poses

Enemies standing around should not all play one looping idle. The original
game already solved this, and the data for it is in i24, so this pipeline
reuses it instead of inventing new animations.

## How City of Heroes did it

- **Spawn defs pick a pose.** Each actor in a spawn def has
  `AI_InActive <<PL_ArmsCrossed>>` or similar: what it does before a hero
  arrives. `PL_ArmsCrossed` names an AnimList in
  `sequencers/animlists/*.al`, which sets state bits
  (`ENCOUNTER COMMAND OBSERVE LOW`).
- **The sequencer turns bits into moves.** `sequencers/player.txt` (and its
  includes, mainly `player/encounters.inc`) holds moves with `Requires`
  bits. The move whose bits are met with the highest `Priority` plays.
- **Moves chain at random.** A move flagged `Cycle` lists `CycleMove`
  entries. Each time its clip ends, `seqStep` in
  `Common/seq/seqsequence.c` picks one at random; a name listed twice is
  twice as likely, and a move listing itself can repeat. With no
  `CycleMove`, the move just loops.
- **Moves blend.** The new move blends in over its `Interpolate` frames
  (default 5 at 30 fps). The old one freezes on its last frame while it
  fades out.
- **The default idle works the same way.** `Ready` -> `Ready2` ->
  `Ready_Look` or `Ready_2Hips` -> hands on hips, a look around, arms
  crossed, back to neutral. Each step plays at its own speed
  (`Scale 0.5` and so on).

## What the Hellions used

From the Atlas Park and Galaxy City spawn defs (`city_01_01`,
`city_01_02`), ranked by use. "Needs" means the pose only reads right with
something else present, so it is left out of the random pool unless it is
set by hand.

| Pose | Uses | Needs | Moves (male) |
|---|---|---|---|
| Ready (default idle) | | | 9 moves: neutral, look, hands on hips, arms crossed |
| ArmsCrossed | 99 | | Cross_Arms, Cross_Arms_look, Arms_On_Hips, Arms_On_Hips_look |
| LedgeSit | 95 | seat | 4 sitting variants with 3 moves each |
| BatObserve | 78 | prop | holding a bat, looking left |
| Dealing_Deal / Dealing_Receive | 60 / 42 | partner | a hand-off between two NPCs |
| PurseTug | 50 | partner | tug of war over a purse |
| SprayPaint | 45 | prop | look around, shake can, spray (4 moves) |
| Lookout | 44 | | suspicious, quick look, look right and left (5 moves) |
| PeerIn | 36 | wall | peering into a window |
| Wall_Lean | 30 | wall | leaning on a wall |
| At_Ease | 24 | | at ease |
| PistolObserve | 18 | prop | pistol held, looking right and left |

Other groups have their own mix. Skulls: ArmsCrossed, Lookout, Talk,
Vandalize. The Lost: Sitting, WarmHands. Circle of Thorns: Meditate, Bowing,
Chanting. Clockwork: Siphon. Run `coh2unreal.idles --group <name>` to list a
group's poses. There is no smoking animation in the data. The closest
"hang out" poses are Talk, Amused and Cheering.

## Pipeline

1. **Extract the graphs.** This needs only i24 text data, no piggs:

   ```
   python -m coh2unreal.idles --data <i24/data> --group Hellions \
       --zone city_01_01 --zone city_01_02 \
       --animlist Talk --animlist Amused --out idles_hellions.json
   ```

   You get one graph per pose and per body type (male, fem, huge). Each
   state lists its move, its `.anim` and frame range, its play rate, its
   blend frames and its weighted next states.

2. **Export the clips with the characters.** This needs the piggs, so run it
   on the PC:

   ```
   python -m coh2unreal.character --data <i24/data> --piggs <piggs> \
       --out <out>/characters --group Hellions --all-costumes \
       --idles idles_hellions.json
   ```

   Each character gets one extra glTF clip per idle state, named after the
   move (`Cross_Arms`, `Ready_2Hips`...), next to idle, run, attack, hit and
   death. The graph is copied to `<out>/characters/idles.json`.

3. **Play them in Unreal.** Add a **CoH Idle** component (`UCoHIdleComponent`)
   to the enemy actor:
   - **Graph Json:** the `idles.json` file.
   - **Seq Type:** `male`, `fem` or `huge`.
   - **Clip Folder:** the folder the clips were imported to. Clips are
     matched by move name.
   - **Pose:** leave it empty for a random pose, weighted by how often the
     original spawns used it (Ready counts as much as the most common one),
     or set one such as `Wall_Lean` where there is a wall.
   - **Pose Pool:** limit the random choice.

   The component swaps the mesh to `UCoHIdleAnimInstance`, a C++ anim
   instance that crossfades two clips. You don't need an Anim Blueprint.
   Every enemy starts at a random point in a random entry move and gets a
   small speed jitter (±8%), so a group never moves in step. `SetPose` and
   `SetIdleActive(false)` let combat AI take over later.

## Not done yet

- The clips have not been exported or tried in Unreal. The PC was busy with
  the overnight head and glove generation. The C++ has not been compiled.
- Props (bat, spray can, pistol) come from the costume's weapon and the
  move's FX. They aren't attached yet, so those poses stay out of the
  random pool.
- Partner poses (dealing, purse tug) need two actors placed facing each
  other. A small "encounter" spawner could pair them, as the spawn defs did.
- Female characters use the male encounter animations, as in the original
  game (`fem` falls back to `male`). Check them for clipping on the fem
  skeleton.
