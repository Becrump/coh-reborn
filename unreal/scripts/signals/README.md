# Glowing traffic signals

The original CoH traffic lights paint all three lenses on one texture (`traffic_light.tga`) and the walk panel on
another (`traffic_light_pedestrian.tga`), so at night they stay dark. `M_CoH_TrafficSignal`
(`coh2unreal/unreal/coh_materials.py`, `build_signal`) keeps the original texture and lights one lamp at a time:

- Vehicle heads: green, amber (3 s), red on a 40 s cycle. The lit lens glows (`SignalGlow`), the unlit ones are dimmed (`SignalDim`).
- Walk panels: white walker while the traffic beside it is green, flashing hand during amber, steady hand on red.
- Direction: from each face's world normal. Heads facing along world X (traffic moving along X) are group 0, heads
  facing along Y group 1, half a cycle later, so crossing streets alternate. Works on baked Nanite tiles and on
  instanced props, with no placement data.
- Clock: `MPC_CoHSignals.SignalClock` when a `CoHLifeManager` writes it (set its SignalCollection to
  `/Game/CoH/Materials/MPC_CoHSignals`; it uses the server clock, so every player sees the same lamps and its cars
  stop at red with the same timing: `SignalState(Offset 0, Group)`). Otherwise the material's own game time.

Applying it:

- Existing maps and zones: `python unreal/scripts/ue_exec.py - < unreal/scripts/signals/light_signals.py` (once; backs
  up each original to `/Game/SignalUpgrade/OriginalBackup`). `SIGNAL_DRY=1` lists what it would change.
- New zone imports: `apply_tuning.py` routes the two materials automatically, and the zone batch links slots to
  Atlas Park's already-converted material.

Tuning (material parameters): `SignalCycle`, `SignalAmber`, `SignalGlow`, `SignalDim`, lens position `SignalLensU`,
`SignalRedV`, `SignalAmberV`, `SignalGreenV`, `SignalRadius`, `SignalSoft`.

`docs/signals/signal_states_preview.png` is an offline sketch of the shader on the original textures.
