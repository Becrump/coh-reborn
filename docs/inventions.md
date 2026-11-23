# Inventions: salvage, recipes and invention enhancements

`tools/items/inventions_game.py <out>` compiles the converted invention and
reward defs into `<out>/items/inventions_game.json` (convert stage
`inventions_game` in `tools/imports/finish_imports.py`). The game loads it
next to `items_game.json` (`UCoHItems::LoadInventions`).

## What drops

The original's per-rank salvage tables (`defs/reward/<rank>_salvage.reward`):
every defeat rolls each line of the villain rank's table for its level. Lines
name villain groups (magic groups drop arcane salvage, tech groups tech
salvage) or are the default; a line that rolls gives one item of its item set.
Recipe sets read further tables at the villain's level (common, uncommon and
rare recipes), and set recipes drop at the villain's level within the set's
range. As with inspirations, drops go to the hero who did the most damage,
and none when the villain is too far below the hero.

- 108 invention salvage pieces (common, uncommon, rare; arcane and tech).
- About 15,000 recipes: common invention enhancements (Invention: Damage 10 to
  50) and the invention set pieces (Annoyance, Bonesnap...).
- Not yet: temporary power recipes, costume recipes, merits, Hamidon,
  incarnate and base salvage.

Room for salvage and recipes grows with level (`defs/inventory_sizes.def`).

## Crafting

`/inventions` (or the Inventions button in the Enhancements window) lists the
recipes, the salvage each needs (have / need) and the influence it costs.
Craft uses up the salvage, the recipe and the influence, and puts the
enhancement in the enhancement tray. Salvage and recipes can be sold from the
same page. The original crafted at an invention table in a university; here
it works anywhere for now.

## Invention enhancements

- Strength comes from the class table the enhancement names
  (`Melee_Boosts_33`) at the enhancement's own level: a level 50 damage IO
  gives 42.4%. It doesn't weaken or strengthen with the hero's level, but it
  can't be slotted more than 3 levels above the hero.
- Set pieces enhance several things at once (Accuracy/Damage). Each attribute
  gets its own share of the table value.
- Unique pieces can only be slotted once per hero.
- A piece fits any power that takes one of the kinds it enhances.

## Not done yet

- Set bonuses (2 to 6 pieces of a set in one power).
- The power's set categories (the original only let a set go in powers of its
  kind, such as Melee Damage).
- The university invention tables, the auction house and merit vendors.
- Temporary power recipes (there are no temporary powers in the game yet).
