# Finishing the imports (2026-11-15)

`tools/imports/finish_imports.cmd` converts the rest of the original game's content on Robert's PC and imports it into the open Unreal editor, unattended and resumable. Details of each stage are in `tools/imports/finish_imports.py`.

| Stage | What | Result in a cloud test run (i24 + the 72 archives) |
| --- | --- | --- |
| encounters | every zone's original encounters | 37 zones |
| enemies | enemy kit for all villains the 18 city-map zones spawn | 834 villains in 43 groups, 384 models (832 villains have one), 1,487 powers |
| enemy_fx | effects, textures and sounds of those powers | 400 effect models, 656 textures, 683 sounds |
| story | contacts, story arcs, task sets, task forces, NPC defs, clues and souvenirs, encounter dialog, English text | 608 contacts, 273 story arcs, 288 task sets, 1,290 NPC defs, 267 clue files, 166 dialog files, 199,058 text lines |
| items | badges, enhancements and set bonuses, inventions, stores, rewards, inventory, misc | 2,122 badges, 2,606 enhancement files, 29 invention files, 4 store files, 1,053 reward tables |
| characters | the 120 hero presets and every contact/mission NPC model | 997 models |
| ue_fx, ue_enemies, ue_presets, ue_npcs | import into Unreal in batches of 15, saving after each | not run yet |

Fixes found on the way:
- Spawn definitions use `var NAME [volatile] = a, b, <<c>>` lists. The old parser kept only the first word (with its comma), so about 100 villain slots across the zones rolled names that don't exist. `coh_encounters.parse_spawndef` now keeps the whole list (`villain_choices`) and both encounter exporters roll from it. Re-run `tools/zones/encounters.py` for the zones (the `encounters` stage does).
- Villain names are case-blind in CoH (`CircleofThorns_*` vs `CircleOfThorns_*`); the all-zones roster matches them that way.
- `coh2unreal.enemies` and `coh2unreal.player models` skip an NPC with no costume instead of stopping.

Data format (story and items): each file keeps the original order as a tree of `{"k": key, "a": args, "c": children, "t": texts}`. `t` holds the English text wherever an arg is a message id, so dialog reads without a lookup; `strings.json` has every id. Nothing in the game reads story or items yet: the contact and mission systems come next.

Not covered: mission maps (the indoor maps missions take place in), villain-side content (`--villains` adds it), and two villains without a usable model (Arachnos police drones: their skeleton is missing in the data).
