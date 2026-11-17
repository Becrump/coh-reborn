# Badges

The original's badges that a hero can earn in the core game (CoHBadges.h, `UCoHBadges`).

- `python tools/badges/badges_game.py <i24>/data <out>` (the `badges_game` stage of
  `finish_imports.py`, after `story_game`) compiles 288 badges: 145 exploration
  (tourism), 12 history, 96 defeat, 20 accomplishment, 15 achievement, plus 551
  badge markers ("namedvolume" tourism markers and history plaques, which
  `tools/story/world_points.py` now also extracts) -> `<out>/badges/badges_game.json`.
  Villain-side, event, veteran, PvP, invention, architect, day job and incarnate
  badges are left out, and so are exploration badges whose marker isn't in our zones.
- Requirements are the original's postfix expressions (`kills.Hellions 100 >=`,
  `visits.AtlasPark1`, `level char> 20 >=`, `X owned? Y owned? &&`), evaluated on
  the host from the hero's stats.
- Stats are saved with the hero (`badges` in the hero file):
  - each defeat counts `kills.<group>`, `kills.<group>.<rank>` and `kills.<villain>`;
  - walking within 15 m of a marker counts `visits.<marker>`.
- Earned badges show as a gold combat text and a chat line. `/badges` lists them.
- Atlas Park was rebuilt, so its markers sit at the original layout's spots.
- Defeat badges count by our enemy faction names; any badge whose group name
  differs from the original's won't count until the names are mapped.
