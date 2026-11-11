# Rivals (Nemesis system) data

Research-stage tools for the opt-in Nemesis/rival system. Design: `research/nemesis-system.md` in the project's shared folder.

- `rival_data.json`: for 10 street gangs (Hellions, Skulls, Outcasts, Clockwork, Vahzilok, Trolls, Tsoo, Family, Freakshow, Lost): 20-30 street handles each, nickname prefixes/suffixes, Gang Legend and Supervillain title templates, traits, and Breakout origins (CoH origins) with candidate power sets. Plus the six stages (Marked, Rising, Crew Boss, Gang Legend, Breakout, Supervillain) with rank, trait count and crew size.
- `gen_rivals.py`: rolls rivals and grows them through the stages. `--selftest`, `--path <Faction>`, `--json`, and `--catalog <catalog.json>` to check the power set names against the real catalog from `tools/rules/coh_rules.py <defs> catalog <out>` (needs game data, run on the PC).

Power set names are written from memory of the original game and are not yet checked against the catalog. Handles are hand-written, not taken from game data, so this folder is safe to keep in git.
