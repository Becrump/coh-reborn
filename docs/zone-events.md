# Zone events

The original's scripted zone events and city-wide invasions, run by the host.

## Data

`tools/zones/zone_events.py <i24>/data <out>/zone_encounters` (stage `zone_events` of
`tools/imports/finish_imports.py`) reads the zones' `Marker_Script` groups
(`Name`, `RunEvery` hours, `RunEveryRange` minutes, `ScriptLocation`) and their
scriptdefs, and writes `<out>/zone_encounters/zone_events.json`: each event's
marker position (local and one-world cm), its variables, its messages (P-strings
looked up in texts/english) and the villains it can spawn (from its spawndefs).
Seasonal, PvP and beta scripts are left out.

Found in the city zones:

| Zone | Event | What happens |
| --- | --- | --- |
| King's Row (city_02_01) | HellionsFire x6 | Hellions set a building on fire, then the Arson boss |
| Skyway City (city_02_02) | TrollsRave x3 | Trolls gather at the rave spots, then the Supa Troll |
| Croatoa (city_03_03) | CroatoaBattle | the Red Cap and Fir Bolg giants come out |
| city-wide | RiktiInvasion, ZombieApocalypse | waves around every hero, after a warning |

`enemy_kit_all.py` adds the event villains (32) to the enemy kit, so the
`enemies` and `ue_enemies` stages must run after `zone_events` for their models.

## Game

`ACoHZoneEvents` (CoHZoneEvents.h/.cpp) is spawned by the game mode on every
non-lobby map. The original scripts were C code in the server, so these are our
versions:

- A zone event comes due every RunEvery hours (give or take RunEveryRange) and
  starts when a hero is in its zone (one of a kind per zone at a time; the
  Croatoa giants only ChanceOfGiants % of the time). Zone events need the
  one-world map (ParagonCity); invasions run on any map.
- Fires and raves: the zone-wide alert, then waves near the marker up to the
  event's total (scaled down for a small server: 20 per hero nearby), then the
  boss. Fire bursts play around a burning building. Ravers head for the rave spots.
- Invasions: every 4 to 8 hours (setting `InvasionHours`), a warning, then
  groups around every hero at the hero's level, 25 per hero.
- An event ends when its villains are beaten (win: XP and influence for the
  heroes within RewardRadius), when no hero has been near for 3 minutes, or
  after 15 minutes (20 for invasions).

Settings (`[/Script/COHREBORN.CoHZoneEvents]` in Game.ini): `bZoneEvents`,
`TimeScale` (0.1 = ten times as often), `InvasionHours` (0 turns invasions off).

The host can type `/zoneevent list`, `/zoneevent stop`, `/zoneevent HellionsFire`
(nearest marker), `/zoneevent HellionFire_3` (a marker) or `/zoneevent RiktiInvasion`.

## Not yet

- KeepPopulated (Faultline) is left to the zone's own spawns.
- The Croatoa battle spawns the giants only, not the fighting armies.
- Rewards are our guess (level x 60 XP, level x 40 influence); the original's
  event reward tables are not read.
- Burnt buildings, the rave music and lights are not shown.
