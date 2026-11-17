# Talk to target (AI speech) prototype

Test bench for the AI speech system planned in the Claude Doc "AI speech and Nemesis plan". No game code yet: this mirrors what the host will do in Unreal for one conversation turn, so prompts, rules and models can be tuned first.

The rule that makes it safe: **the game decides, the model only words it.** Resolve, reputation, which clue unlocks and whether a heroic speech sways a villain are computed by `talk_sim.py`'s rules (later C++). The model gets a snapshot, the result it must say, and returns `{"say", "emote"}` (plus `"think"` when the hero is a telepath). Replies that are too long, use filtered words, leak a secret the hero hasn't found, or drop the clue they had to give are replaced by a hand-written fallback line.

| File | What it is |
| --- | --- |
| `talk_data.json` | Reputation tiers and the tone NPCs take at each, reputation events, approach menu, temperaments (Resolve and sway numbers), clue thresholds, persona templates per NPC kind, gang voices, secret tables, fallback lines, word filter |
| `mock_world.json` | Mock snapshots: 3 heroes (one telepath, one feared) and 6 NPCs (rival Cinder, a Hellion informant, a rescued citizen, a civilian, a cop, a placeholder contact). This is the shape the game's snapshot builder must fill |
| `mock_script.json` | 10 test scenes |
| `talk_sim.py` | The turn: combat check, filter, approach (keyword guess, then the model picks from the menu), rules, reply, checks, word balloon. Interactive (`--npc cinder --hero blue_comet`) or scripted (`--script`); `--selftest` checks the rules without a model |
| `bench_talk.cmd` / `.ps1` | On the PC: downloads llama.cpp + Qwen3 1.7B and 4B once (~4.5 GB in `.cache`, not in git), times the script with llama-server on N CPU threads, appends to `bench_talk_results.txt`. `-Load 300` keeps it talking so the game can run alongside |

```
python tools/talk/talk_sim.py --selftest
python tools/talk/talk_sim.py --npc thug --hero ironjaw                    # fallback lines only
python tools/talk/talk_sim.py --npc cinder --hero blue_comet --showdown --server http://127.0.0.1:8090
tools\talk\bench_talk.cmd                                                   # PC, editor closed for clean numbers
```

## First cloud results (2026-11-17, 3 cloud CPU threads, slower than a Ryzen 7 3700X)

| Model | Prompt reading | Writing | Reply time | Quality |
| --- | --- | --- | --- | --- |
| Qwen3 1.7B Q8 | ~180 tokens/s | ~17 tokens/s | 4 to 9 s | Usable for civilians and police; invents facts for contacts, sometimes misses the clue (fallback covers it) |
| Qwen3 4B Q4_K_M | ~75 tokens/s | ~6 tokens/s | 9 to 17 s | Clearly better: stays first person, short, in character, gives the clue in its own words |

Both are too slow on cloud CPUs; the PC bench decides. Planned speed-ups: keep each NPC's persona as a cached prompt prefix in llama-server, stream the 💬 balloon word by word as it is written, drop the classify call when the keyword guess is confident, and use 1.7B for street NPCs and 4B for rivals and informants.
