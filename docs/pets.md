# Pets, patches and respec

## Pets (the original kEntCreate mods)

A power that calls something has `kEntCreate` attribute mods. Each mod names an
entity def (a villain def such as `Pets_FireImp` or `MastermindPets_Thug`), a
Duration (99999 = stays until dismissed), a Delay, and a level offset in its
name (`LevelMinus` = one below, `Levelminus2` = two below). Mastermind upgrades
come from `Requires combatlevel source> N >`: that henchman only comes once the
caster is above level N.

`UCoHPowerComponent::SummonPets` (CoHPowers.cpp) reads those mods when the power
fires and calls `ACoHCombatEnemy::SpawnPet` (CoHCombat.cpp) for each one:

- **Where:** the spot picked for location powers (Fire Imps, Rain of Fire, Call
  Thugs), the target for powers aimed at a foe, else in front of the caster.
  Several pets stand on a 1.5 m ring.
- **Side:** the pet's power component takes the owner's side (`bPlayerSide`,
  now replicated), so heroes' pets fight villains and villains' pets fight heroes.
- **Credit:** damage a pet does counts as its owner's (`CreditFor`), for XP,
  influence, badges and mission defeats.
- **Model:** the pet's own kit model when it has been imported, else a small
  glowing orb stands in (replicated with `PetLook`).
- **Brain (`PetThink`):** follows the owner (about 2.5 m), catches up by
  teleporting when more than 60 m behind, and fights whoever is hurting it or
  its owner, else the nearest foe in sight within 15 m. It uses the pet's own
  powers (range, recharge, endurance). A taunt draws it too.
- **End:** a timed pet goes when its Duration runs out; lasting pets go when
  the owner is defeated or leaves, when the same power is cast again (the new
  set replaces the old), on `/release`, and on a respec.

### Pseudo-pets (patches)

Rain of Fire, Ice Slick, Caltrops, Voltaic Sentinel and similar powers call an
invisible entity (AI config `Pets_Ignore` / `*Stationary*`, with
`Pets.ResistAll*`). These spawn with no model and no collision, can't be
targeted or hit (`bUntouchable`), don't move, and pulse their auto power at its
`ActivatePeriod`. A villain hurt by a patch blames the caster. Their effect
shows as a burst in the element's colour about once a second until the
original FX for them are hooked up.

### Pet models

`tools/zones/enemy_kit_all.py` now adds every entity def that a hero power
category calls (372 of them; patches left out) to `roster.json` with ally
`Pet`, so the next enemy kit run on the PC exports their models. Leave them
out with `--no-pets`.

## Respec

`/respec` rebuilds the hero: every power pick is chosen again from level 1 up
(same archetype and sets), and slotted enhancements go back to the inventory
so the slots can be placed again. It uses one respec. The original earned
respecs from the respec trials at levels 24, 34 and 44; those trials aren't
imported, so a respec now comes with training to those levels. For tests,
`coh.Hero.RespecFree 1` allows it without one.

Picks now record the level of their slot (the original's rule), so exemplars
keep the right powers after a respec.

## Trainers

Training stays on L anywhere (one level per press, as one trainer visit was).
The original sent heroes to a trainer NPC; that can come back with the
contacts UI if wanted.

## Not done yet

- Recasting a Mastermind summon replaces the whole set instead of topping it up.
- The Mastermind pet window (pet commands: attack, follow, stay) is not in.
- Patch effects use a simple burst, not their original FX.
