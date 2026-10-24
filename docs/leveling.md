# Leveling: XP, influence, defeat debt, inspiration drops

This is step 4 of the game systems build order (2026-10-20). It follows the original server code (`TeamReward.c`, `Reward.c` and `character_level.c` in Thunderspies/CityOfHeroes) and reads every number from the original data.

The tool is `tools/rules/coh_rewards.py`.

```
python tools/rules/coh_rewards.py <i24>/data/defs export <rules_dir>   # rewards.json
python tools/rules/coh_rewards.py <i24>/data/defs defeat --villain-level 3 --rank Lieutenant --hero-level 2 [--team 3]
python tools/rules/coh_rewards.py <i24>/data/defs curve                # XP to next level and defeats needed
python tools/rules/coh_rewards.py <i24>/data/defs selftest
```

## Rules

| Rule | Source | Value |
| --- | --- | --- |
| Reward table | `defs/reward/<rank>.reward`, row = villain level | Minion, Lieutenant, Boss, Elite, ArchVillain, Small, Sniper, Pet. `Chance 100 Always` rows give XP and influence. |
| Level difference | `level_bonus.def` | Villain above the hero: x1.2, 1.4, 1.65, 1.9, then 2.0. Villain below: x0.8, 0.6, 0.4, 0.2, then 0 at 5 below. |
| Team | `team_xp_boost.def` | The team's total is x1.0 solo, x1.25 for 2 ... x2.2 for 7, x2.5 for 8, split evenly. A team gets the share of the reward that matches its share of the damage. |
| XP cap | `TeamReward.c` | At most 1.9 x the table XP of a villain 4 levels above the hero, and at most half the XP to the next level |
| Items | `TeamReward.c` | One member of the top-damage team gets the drop, taking turns. No drops when the hero is 3+ levels above the villain's con level (lieutenant +1, boss +2, elite boss +3, archvillain +4). |
| Inspiration drops | `defs/reward/*.itemset` | A level 1 minion has a 35% chance of a small inspiration. The weighted pick is Luck 5, Insight 10, Catch a Breath 10, Respite 10, Enrage 10, Sturdy 5, Awaken 1. |
| Defeat debt | `experience.def` `DefeatPenalty` | None below level 10. 160 at 10, rising with level. Halved in missions, capped at 5 penalties. While in debt, half of each XP award pays it off. |
| Level up | `experience.def` | 106 XP for level 2, 39,149,119 for level 50. XP sets the XP level; the hero trains to it ("level up"), which grants the level's power pick or auto powers (see [hero-build.md](hero-build.md)). At 50, XP pays debt, then turns into influence. |
| Inspiration tray | `schedules.def` | 3 x 1 at level 1, growing to 5 x 4 at 50 |
| Kill credit | constants | 200 ft for kill credit, nothing past 300 ft without damage |

Solo, a hero needs about 11 even-level minions for level 2, 180 at level 10, about 470 at level 20 and about 1,900 in the late 30s (`curve`). That is the original pace, before missions and bonuses.

## Checked

`selftest`, 15 checks, all pass:

- Level 1 minion gives 10 XP and 7 influence; a level 1 lieutenant gives 33.
- A minion 2 levels up pays x1.4. A minion 5 levels below pays nothing and drops nothing.
- Items stop 3 levels above a minion, and a boss at that gap still drops.
- A team of 3 gets 5 XP each for a minion (x1.5 split 3). The team bonus is 2.2 for 7 and 2.5 for 8.
- Debt: a defeat at 10 adds 160, debt caps at 800, half of 100 XP pays debt, and there's no debt below 10.
- The tray is 3 x 1 at 1 and 5 x 4 at 50. The small inspiration set and its 35% drop chance match the data.

## Files

`rewards.json` (rules dir, about 2.8 MB) has:

- `xp_for_level`, `defeat_penalty`, `level_bonus_above`, `level_bonus_below`, `team_bonus`, `con_adjust`, `constants`, `inspiration_tray`.
- `tables`: per rank, per villain level, the sets (chance, always, XP, influence, item set).
- `itemsets`: weighted items. These include salvage and enhancements, which come later; for now the game only needs inspirations.

The hero file (format 2) already has `xp`. The Unreal side should add `debt`, `influence` and an `inspirations` grid to it.

## Unreal side (PC session)

1. **Rewards subsystem:** load `rewards.json`. Port `defeat()` and `give_xp()` (about 100 lines in Python).
2. **Damage tracker** on each enemy: record damage per player and team. On defeat, split the reward by damage share, skip players past the kill-credit range, and roll the drops for the top-damage team.
3. **Hero component:**
   - Add XP, influence and debt, with the debt split.
   - When XP passes the next level, show "Level up" (the original trainer step). Training raises the level, refreshes auto powers, and opens the power picker from step 3.
   - On defeat by villains, add the debt.
4. **Inspirations:** a tray of the size for the level, filled by drops, with click to use. The inspiration powers are already in the powers data (`Inspirations.*`).
5. **UI:** XP bar with debt shown in purple, as in the original; influence counter; level-up button; inspiration tray.

## Next

Step 5 is power FX (`.fx` to Niagara, Fire Blast first). Step 6 is enemy setup.
