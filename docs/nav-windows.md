# Nav, contacts, missions, clues and badges windows

The original's navigation windows (uiCompass.c, uiContact.c, uiMission.c,
uiClue.c, uiBadge.c), in `CoHNavWindows.{h,cpp}`. They are built on each
player's PC from the replicated hero record (story and badges) and the story
and badge data every PC loads, so they need no new server calls.

- **Compass**, top centre, open by default: the headings slide past as the
  camera turns, and the waypoint is a gold mark with its name and distance in
  yards. The waypoint is the one the player set, else the task force's, else
  the first unfinished mission's. A set waypoint clears on arrival (20 yards).
  `/nav` or the status window's Nav tab shows or hides it.
- **Contacts** (`/contacts`): every contact met, with profession, zone,
  relationship (Acquaintance, Friend, Confidant, Complete by contact points),
  and whether a mission is in progress or ready to turn in. Click one for its
  description and Set waypoint.
- **Missions** (`/missions`): the task force line and each task with its
  contact, progress (3 of 10) and the mission text. A finished mission's
  waypoint points back at its contact.
- **Clues** and **Souvenirs** (`/clues`, `/souvenirs`): newest first; click for
  the text.
- **Badges** (`/badges`): earned badges by category (or all of them, dim when
  not earned), click for the badge text.

The old chat lists are now `/badgelist`, `/cluelist` and `/souvenirlist`.
The HUD's Salvage and Recipe tray tabs open the inventions window.

Not yet: the map window (zone map art from texMaps.pigg), badge icons,
calling a contact from the window, the original frame art for these windows.
