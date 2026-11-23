# Enhancements, slots and stores

The original game's enhancement system for the core game: Training (TO), Dual
Origin (DO) and Single Origin (SO) enhancements, slots, stores and drops.
Inventions (salvage, recipes, invention enhancements): see inventions.md. Set bonuses, Hamidon origins and attuned enhancements come later.

## Data

`python tools/items/items_game.py <out>` (also the `items_game` stage of
`tools/imports/finish_imports.py`) reads the converted item defs
(`<out>/items/enhancements.json`, `stores.json`) and `<out>/story/story_game.json`,
and writes `<out>/items/items_game.json`:

- `boosts`: 313 enhancements (33 TO, 140 DO, 140 SO) with type (`kDamage_Boost`...),
  strength (`scale`: TO 8.3%, DO 16.7%, SO 33.3%, lower for schedule B), the
  attributes they strengthen and their origins.
- `stores`: what each store used by a contact or store NPC sells (enhancement,
  level, price), from `stores.def` departments and `items.def`.
- `slots`: the player levels a new slot comes at (schedules.def AssignableBoost).
- `effect_above` / `effect_below`: strength of an enhancement above / below the
  hero's level (more than 3 below: no effect, as the original's red enhancements).

The game reads it with `UCoHItems` (CoHItems.h); default path is next to the
rules folder (`<out>/items/items_game.json`), or `ItemsFile` in the config.

## In game

- **N** or the tray's **Enhancements** button opens the window: each power with
  its slots, the enhancement tray (10), "+ slot" while slots are left to place
  (max 6 per power). Pick an enhancement, then a slot. A slotted enhancement
  replaces what was in the slot, as the original.
- A power takes an enhancement when its type is in the power's `BoostsAllowed`,
  and DO/SO ones must match the hero's origin.
- Slotted enhancements change the hero's powers on the host
  (`UCoHPowerComponent::SetBoosts` / `Def`): damage and effect scales, accuracy,
  recharge, endurance cost, range, and mez durations. The total per attribute
  goes through the original's diminishing returns (schedule A from 70%,
  schedule B from 40%). Mods with `AllowStrength kFalse` are left alone.
- **Stores**: store NPCs ("Store" button on their page) and contacts that sell
  (their tier improves at friend and confidant contact points: `_CL1` / `_CL2` /
  `_CL3`). The window lists the store's enhancements for the hero's origin
  around the hero's level, with Buy; in a store the tray gets Sell (40% of price).
- **Drops**: a defeated villain that gives items has a 7% chance to drop an
  enhancement (TO under level 12, DO under 22, then SO, of the hero's origin);
  mission rewards' power-up lists (`PL.Single5Magic`, `PL.Dual5...`,
  `PL.GenericPowerFive`) give one too.
- Slots and the tray save with the hero (`enhancements` in the hero file).
