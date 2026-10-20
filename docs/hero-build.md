# Hero build: archetypes, power picks, pools, inherents

This is step 3 of the game systems build order (2026-10-20). A hero is built the way the original game builds one, from the original data. There is no costume step yet: a hero wears a player-body preset or a costume file (see [powers-and-player-models.md](powers-and-player-models.md)).

The tool is `tools/rules/coh_build.py`. It reuses the loaders in `coh_rules.py`. Loading the defs takes about 30 seconds.

```
python tools/rules/coh_build.py <i24>/data/defs export <rules_dir>      # hero_rules.json
python tools/rules/coh_build.py <i24>/data/defs starters <heroes_dir>   # one level-1 hero per archetype
python tools/rules/coh_build.py <i24>/data/defs new my_hero.json --class Blaster --primary Fire_Blast \
       --secondary Fire_Manipulation --first Flares --name "Ember" --origin Science --preset Model_Positron
python tools/rules/coh_build.py <i24>/data/defs level my_hero.json 6
python tools/rules/coh_build.py <i24>/data/defs options my_hero.json    # what the next pick may take
python tools/rules/coh_build.py <i24>/data/defs pick my_hero.json Fire_Ball
python tools/rules/coh_build.py <i24>/data/defs validate my_hero.json
python tools/rules/coh_build.py <i24>/data/defs selftest
```

## Rules (all from the data)

| Rule | Source | Value |
| --- | --- | --- |
| Power picks | `schedules.def` `Power` | 24 picks: two at level 1, then 2, 4, 6 ... 32, 35, 38, 41, 44, 47, 49 |
| Level 1 | powersets `Available 0` | One of the primary's level 1 powers, plus the secondary's level 1 power |
| Power levels | powersets `Available` (0-based) | For example, Fire Ball at 2 and Fly at 4 |
| Pool sets | `PoolPowerSet` | A new pool set is allowed at 4, 6, 8 and 10. That's 4 at most. |
| Origin pools | powerset `SetBuyRequires` | Sorcery, Gadgetry, Experimentation, Force of Will and Utility Belt exclude each other |
| Power requirements | power `BuyRequires` (postfix) | Owned powers, `$archetype`, level, `&&` / `||` / `!` |
| Epic sets | `EpicPowerSet`, category `Epic` | One epic set from 35. Each epic power names the archetypes allowed. |
| Inherents | `Inherent.Inherent`, `Inherent.Fitness` | Free and automatic: Brawl, Sprint, the archetype inherent (Defiance, Gauntlet, Critical Hit ...) at 1. Rest, Walk and Fitness (Swift, Hurdle, Health, Stamina) at 2. |
| XP | `experience.def` | XP needed per level, 106 at level 2 up to 39,149,119 at level 50 |
| Enhancement slots, inspiration tray | `AssignableBoost`, `InspirationCol/Row` | Exported for the leveling step |

- **Archetypes:** 14 playable ones.
  - 5 hero archetypes: Blaster, Controller, Defender, Scrapper and Tanker.
  - 5 villain archetypes: Brute, Corruptor, Dominator, Mastermind and Stalker.
  - 2 Kheldians: Peacebringer and Warshade.
  - 2 Arachnos archetypes: Soldier and Widow.
  - In the game, Kheldians and Arachnos were unlocked by a level 20 character. `hero_rules.json` marks them `epic: true` so the server can apply that rule or skip it.
- **Store, promotion and veteran powers** (prestige sprints, pets, event costumes) are left out. Their `BuyRequires` need store or account tokens.
- **Store-sold power sets** are open to everyone, because their gate is `SetAccountRequires`, which isn't checked. On the store-only pools, the gate is `ProductOwned?`.

## Files

- **`hero_rules.json`** (rules dir, next to the other rules JSON). It contains:
  - The schedule, with levels shown 1-based.
  - The XP table.
  - The origins.
  - Each archetype's primary and secondary sets, origins, and side.
  - The pool and epic sets.
  - For every player set, each power's level, `requires` (the raw postfix expression), `free`, `auto` and `promo`.
- **Hero file, format 2.** Format 1 was `hero_all_sets.json`, and the old loader still works because the `sets` field is kept:

```json
{"format": 2, "name": "Ember", "class": "Class_Blaster", "origin": "Science", "level": 6, "xp": 3062,
 "model": {"preset": "Model_Positron"},
 "primary": "Blaster_Ranged.Fire_Blast", "secondary": "Blaster_Support.Fire_Manipulation",
 "picks": [{"level": 1, "power": "Blaster_Ranged.Fire_Blast.Flares"}, ...],
 "auto_powers": ["Inherent.Inherent.Brawl", ...],
 "sets": [{"set": "Blaster_Ranged.Fire_Blast", "powers": [...]}, ...],
 "next_pick_level": 8}
```

`picks` are the bought powers in order. `auto_powers`, `sets` and `next_pick_level` are derived from the picks and the level.

## Checked

`selftest`, 26 checks, all pass:

- **Schedule:** 24 picks, the last at level 49.
- **Inherents:** Brawl, Sprint and Defiance are granted at level 1. Rest and Fitness come at 2.
- **Illegal picks are refused:**
  - Fire Ball at level 1.
  - Fly at level 2.
  - A fifth pool set.
  - Sorcery together with Gadgetry.
  - Afterburner before level 14.
- **Full builds:** every one of the 14 archetypes builds a valid level 1 to 50 hero with 24 picks. Each build was chosen through `options()` alone.

`starters` writes one valid level 1 hero per archetype, with classic sets and a preset:

- Blaster: Fire / Fire, as Positron.
- Controller: Mind / Empathy, as Sister Psyche.
- Defender: Empathy / Energy, as Ms Liberty.
- Scrapper: Martial Arts / Super Reflexes, as Synapse.
- Tanker: Invulnerability / Super Strength, as Back Alley Brawler.
- The villain archetypes get classic sets with no preset yet.

## Unreal side (PC session)

1. **Rules subsystem:** load `hero_rules.json`. Port `Rules.requires` (a small postfix stack evaluator), `can_pick`, `options` and `auto_powers` to C++. They are about 150 lines in Python and need no other data.
2. **Hero component:**
   - Load a format 2 hero file (`model.preset` picks the player-body mesh).
   - Grant `picks` plus the auto powers for the level.
   - Recompute the auto powers when the level changes.
   - The server is authoritative: a pick request from a client goes through `can_pick` on the server.
3. **UI:**
   - A "new hero" screen: archetype, origin, primary, secondary, first power and preset.
   - A level-up power picker that lists `options()` (the P picker already lists sets and can filter to these).
   - The all-sets test hero stays as a debug toggle.
4. **Storage:** hero files go in the server's hero folder for now. The shared database comes later.

## Next

Step 4, leveling, is in [leveling.md](leveling.md).
