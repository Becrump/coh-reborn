# Running on lower-spec PCs

Short answer: yes for most gaming PCs from about 2017 on, once each PC uses the preset
that fits it. The city as built is tuned for looks (Lumen lighting, hardware ray tracing,
Virtual Shadow Maps, 3,000+ street lamp lights). Those features are what overran Robert's
8 GB card, and they are exactly what the Low and Medium presets switch off.

The spec numbers below are estimates from what Unreal 5 needs for these features and from
the editor measurements so far. They become real numbers once `tools/build/bench_lowend.cmd`
has run on Robert's PC (and, ideally, on one weaker friend PC).

## Estimated specs

| | Minimum (Low) | Recommended (High) | Epic |
|---|---|---|---|
| Target | 1080p at 50-67% render scale, 30+ FPS | 1080p, 60 FPS | 1440p, 60 FPS |
| Graphics card | DirectX 12 card with 4 GB: GTX 1650, GTX 1060 6 GB, RX 570/580, Arc A380 | 8 GB: RTX 3060, RTX 4060, RX 6600 XT | 12 GB+: RTX 4070, RX 7800 XT |
| Processor | 4 cores / 8 threads: i5-8400, Ryzen 5 1600 | 6 cores: Ryzen 5 5600, i5-12400 | 8 cores |
| Memory | 16 GB | 16 GB (32 GB for the PC that hosts) | 32 GB |
| Drive | SSD (the one-world map streams from disk while you move) | SSD | NVMe SSD |
| System | Windows 10/11 64-bit | | |

Will not run: cards without DirectX 12 Shader Model 6 (GTX 700 series and older), PCs with
8 GB of RAM, hard drives (streaming stalls). Built-in laptop graphics (Iris Xe, Radeon 680M)
may manage Low at 720p; this is untested.

The host does the most work: with World Partition the host keeps loaded the area around
every player, so seven friends in seven zones means seven zones in the host's memory. The
host's PC should be the strongest one, with 32 GB of RAM.

## What each preset does

Presets are Unreal's scalability levels, tuned in `unreal/project/Config/DefaultScalability.ini`,
plus three city settings in code (`CoHPerformance.cpp`).

| | Low | Medium | High | Epic |
|---|---|---|---|---|
| Lighting | sky light only, no Lumen | no Lumen, distance field shadows | Lumen (software) | Lumen (software) |
| Reflections | none | screen space | Lumen | Lumen |
| Shadows | classic shadow maps, 1 cascade | classic, 2 cascades | Virtual Shadow Maps | Virtual Shadow Maps |
| Ray tracing scene | off | off | off | off (Cinematic only) |
| Nanite detail | 4 px per edge | 2 px | 1 px | 1 px |
| Texture pool | 600 MB | 1 GB | 1.5 GB | 2 GB |
| Street lamp lights | 40 m, no shadows | 40 m, no shadows | 100 m, shadows | all |
| Trees and props | 100 m | 200 m | 400 m | as placed |
| Civilians / traffic | 35% / 40% | 65% / 70% | 100% | 100% |

Nanite stays on everywhere: it needs the same DirectX 12 cards as the rest and is cheap;
turning it off would need fallback meshes for every building. Hardware ray tracing is now
Cinematic only, so the High and Epic presets no longer keep the ray tracing scene in video
memory (the main reason Epic overran 8 GB).

## In the game

- **First start:** the game runs Unreal's hardware benchmark once, then caps the result by
  video memory: under 3 GB (laptop graphics) is Low at 67% render scale, under 6 GB is at
  most Medium with no Lumen, under 10 GB is at most High. Friends get a sensible preset
  without touching anything.
- **F10 screen:** shows the graphics card and how much of its memory the game uses right
  now, the preset buttons (Low, Medium, High, Epic, Auto), street lamp lights (Glow, Near,
  Far, All), tree and prop distance (100 m, 200 m, 400 m, Max), render scale, comic look,
  civilian and traffic density, window mode, resolution, FPS cap and VSync. It scrolls on a
  720p screen.
- **Console:** `coh.preset 0-3`, `coh.lamps 0-3`, `coh.trees 0-3` (not saved), and
  `coh.bench 60` to measure.

Lamp and tree limits are re-applied whenever World Partition streams a cell in, so they
hold across the one-world map.

## Measuring

`tools/build/bench_lowend.cmd` runs one copy of the game, nothing else, per preset:

```
bench_lowend.cmd              Low, Medium, High, Epic on Atlas Park at 1920x1080
bench_lowend.cmd all city     the same on L_ParagonCity
bench_lowend.cmd lowend       Low at 1280x720 and 67% render scale
```

Each run waits 20 s for streaming, turns the camera a full circle for 60 s, appends one line
to `bench_results.txt` (average FPS, 1% low, GPU ms, video memory now and peak, RAM) and
quits. `memreport -full` writes the detail to `Saved/Profiling/MemReports`. The script
refuses to run while the editor or another game copy is open, because they share video
memory (the two-copy playtest ran out of it with the editor open), and it puts the player's
own settings back afterwards.

Robert's PC can show what Low saves, but it cannot imitate a smaller card's memory limit.
The real low-end check is a friend's weaker PC, which needs the packaged build (item 2
below); the packaged game takes the same `-cohquality=0 -cohbench=60` options.

## Still to do

1. Run the benchmark on Robert's PC with the editor closed (Atlas Park, then L_ParagonCity)
   and replace the estimates above with measured numbers.
2. Package a cooked build for friends. Today the game runs through `UnrealEditor.exe -game`,
   which loads editor modules and uncooked assets (several GB more RAM, shader compiles on
   first start). A packaged Shipping build is the single biggest saving for weaker PCs.
3. World Partition loading range for L_ParagonCity: smaller grid loading ranges plus HLODs
   for the far city cut host memory. Set per grid in World Settings once the map is final.
4. Street lamps: 3,302 spot lights is a lot even with distance limits. Baking the lamp glow
   into the street material and keeping real lights only near players would save more.
