# Original UI and menus: survey and build order

Goal (Robert, 2026-11-10): convert the City of Heroes UI and menu systems into the
Unreal rebuild, as close to the original as possible.

## What the original has

Source: `Game/src/UI/` in Thunderspies/CityOfHeroes, about 180 `.c` files (7 MB).

- **Window system** (`uiWindows.c`, `uiWindows_init.c`). Every HUD panel is a
  window with an anchor (left/center/right, top/middle/bottom), offset, size,
  open/closed default, corner radius (R10 or R22), resize limits and child
  tabs that open other windows. `window_defaults[]` is the full default layout,
  so the original screen arrangement can be copied exactly.
- **Frames** (`uiUtilGame.c`, `drawFrameStyleColor`). Windows are drawn from
  tinted corner/edge textures (`Frame_<n>px_<r>r_ul/ur/ll/lr/join...`) plus a
  translucent black back (`0x00000088`). Hero window colour is `0x3399ff`
  (`DEFAULT_HERO_WINDOW_COLOR`); every window can be recoloured and faded.
- **Art**: 508 distinct `.tga` names referenced by UI code; 480 are found in the
  archives (the rest are names built at runtime or unused). All live under
  `texture_library/gui/` in `stage2*.pigg`, `stage3*.pigg`, `texGui1.pigg`.
- **Fonts** (`sprite_font.c`): Mont Heavy/DemiBold (titles, tabs), Red Circle
  (big numbers), Tahoma and Verdana (body text), Digital (timers), Silkscreen
  (tiny), Courier. All 46 are in `fonts.pigg`.
- **Tutorial screenshots** of the real HUD (`gui/tutorial/*`) are in the archives
  and serve as the visual reference.

### Default layout (from `window_defaults[]`)

| Window | Anchor | Size | Default | Child tabs |
|---|---|---|---|---|
| Status (HP/End/XP) | right-top | 330x65 | open | Chat, Tray, Target, Nav, Menu |
| Target | left-top | 236x66 | open | Action options |
| Power tray | right-bottom | 440 wide | open | Powers, Inspirations, Manage, Salvage, Recipes, + |
| Extra trays 1-8 | left-top | 450x50 | closed | |
| Compass / Nav | center-top | 280x60 | open | Map, Contacts, Missions, Clues, Badges |
| Chat | left-bottom | 360x200 | open | Team, League, Friends, SG, Email, LFG, 4 tab windows |
| Inspirations | right-bottom | 52 tall | open | |
| Team | left-top | 245x34 | closed | Pets |
| Powers list | | 440x227 | closed | Combat numbers, Incarnate |
| Enhancements | | 440x73 | closed | Manage, Convert |
| Map | | 384x384 | closed | resizable |
| Contacts / Clues / Badges / Mission | | 400-440 wide | closed | |
| Contact dialog, Store, Trade, Death, Quit, Help | center | various | on demand | |

## What the Unreal project already has

`CoHPowerUI.cpp` (Slate, built in code, ~900 lines): health/endurance bars,
target window with con colour, one 10-slot tray with recharge, floating combat
numbers, the Power Browser (P), the power customize panel and the animation
bench (F8). `CoHGraphicsMenu` is a small settings panel and `CoHLoadingScreen`
shows a PNG while maps load. Power icons are already exported
(`tools/powers/export_icons.py`). All of it is functional test UI, not the
original look.

## Approach

- **Slate in C++**, like the existing HUD, with the original art loaded at
  runtime from PNGs under `Content/UI/` (same trick as the loading screen). No
  editor import step, so the work does not compete for the shared editor.
- Port the window manager and frame drawing first, then move each panel onto it.
  The existing HUD logic (power component, target, recharge) is reused; only the
  look and layout change. Dev tools (Power Browser, bench) stay behind their keys.
- Window positions, colour and opacity are saved per player like the original.
- Original fonts are used as-is for the private server. Tahoma, Verdana, Arial
  (Microsoft) and Mont, Red Circle (commercial) need free lookalikes before
  public hosting.
- Windows that need server systems that do not exist yet (chat channels, team,
  supergroup, trade, store, email) get the original shell first and are wired
  up as those systems arrive.

## Build order

1. **Window framework**: frame drawing, window manager with the original default
   layout, drag/resize/lock, child tabs, colour/opacity, saved layout, fonts,
   cursors, tooltips, context menu.
2. **Core HUD**: status bars (HP, endurance, XP ring, notify icons), target
   window, power tray with tray tabs and extra trays, inspiration tray, compass
   with nav tabs, reticle and target brackets, buffs, combat numbers.
3. **Character windows**: powers list and power info, level-up power pick,
   enhancement management (slotting), combat attributes.
4. **World windows**: map (zone map art from `texMaps.pigg`), contacts,
   contact dialog, missions, clues, badges, death/hospital, quit, help, options
   (graphics, controls, keybinds) replacing the current settings panel.
5. **Social**: chat window and tabs, team window, friends.
6. **Front end**: login screen, character select (original art, 3D hero on
   the pedestal), character creation flow (archetype, origin, primary and
   secondary sets, power customization; the costume step becomes "choose your
   model"), loading screen with original tips.
7. **Later, with server systems**: supergroup, LFG, email, trade, store,
   auction house, arena.

## Extracted assets

- `/mnt/project-files/ui/coh_ui_art.zip`: 7,282 GUI textures as PNG
  (`gui/...`, original folder layout), 46 fonts, menu text files.
- `/mnt/project-files/ui/reference_original_hud.png`: the archive's tutorial
  screenshots of the original HUD.
- Re-run with `tools/ui/export_gui.py <piggs dir> <out dir>`. Needs
  `stage*.pigg`, `texGui1.pigg`, `fonts.pigg`, `texts.pigg` from
  dists.thunderspy.org. Output is game data and stays out of git.

## Status (2026-11-10): first windows built

`CoHUIArt.{h,cpp}` loads the art and fonts at runtime and has `FCoHPainter`, a
port of the original sprite calls (`display_sprite`, `drawFrame`, `drawBar`,
`drawCapsule`, z ordering). `CoHOriginalHud.{h,cpp}` ports the status window,
target window, power tray and inspiration tray, with the original window
layout, jelly tabs and child buttons, dragging by the jelly and positions saved
in GameUserSettings (`[CoHUI.<window>]`). `SCoHHud` shows it instead of the
plain test panels whenever `Content/UI/ui_art.json` exists.

Setup on the PC: unzip `/mnt/project-files/ui/UI_content.zip` (or run the
exporter) so that `Content/UI/ui_art.json`, `Content/UI/gui/...` and
`Content/UI/fonts/...` exist. Nothing is imported in the editor; packaging
stages the folder (`DirectoriesToAlwaysStageAsUFS`). Remove the folder to get
the plain HUD back.

Preview of the intended look (rendered by a Python copy of the same draw code,
not by Unreal): `/mnt/project-files/ui/hud_preview.png`.

Input: tray slots click to use (Ctrl+click locks auto-attack), inspirations
click to use, child buttons toggle windows ("Powers" opens the Power Browser),
drag a window by its jelly tab. Not yet: compass/nav, chat, menus, tooltips,
right-click menus, extra trays, window colour options.
