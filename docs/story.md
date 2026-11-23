# Contacts and missions (2026-11-17)

The original game's contacts stand in the city and give their original tasks.

## Data

`tools/imports/finish_imports.cmd convert` runs the `story_game` stage (after `story` and `items`):

| Step | Tool | Output |
| --- | --- | --- |
| Where things are | `tools/story/world_points.py <i24>/data <out>/story` | `world_points.json`: per zone, every PersistentNPC (contacts and other story NPCs), mission door (LairType markers), visit-location marker and player spawn, in Unreal world cm (zone offsets from `docs/zones/zone_offsets.json`) |
| What the game reads | `tools/story/story_game.py <out>/story` | `story_game.json`: contacts placed in the 19 zones with their dialogue and tasks, tasks (mission, defeat-X, deliver, visit), story arcs, reward tables (MissionOwner, StoryArcSL2 ...), doors, visits, other story NPCs |

Cloud test run (i24): 255 contacts placed, 219 of them with tasks; 1,663 tasks (1,058 door missions, 316 defeat-X, 269 deliveries, 20 visits); 113 story arcs; 175 other story NPCs (delivery targets). Task variables take their first value; `{HeroName}` and `{Level}` are filled in by the game.

The game loads it from `<out>/story/story_game.json`, next to the rules folder (`RulesDir` in DefaultGame.ini), or from `[/Script/COHREBORN.CoHStory] StoryFile`.

## In the game (`CoHStory.h`)

- **ACoHStoryDirector** (host, added by the first hero): stands each contact and story NPC in the world when a player comes within 120 m (`StandDistance`), removes it past 200 m. It drops them to the ground and onto the nav mesh. Models: `/Game/CoH/Player/Presets/<body>/<model>` or `/Game/CoH/NPCs/<model>`, playing their `idle` clip; a grey post stands in for a model that is not imported.
- **E** talks to the contact in front of the hero (5 m), or uses a mission door or objective.
- **Contact window**: hello / first-visit lines, up to three tasks on offer (the next story-arc episode first), the task's intro, accept and send-off, "still busy" while a task of theirs is in hand, turn-in with the return text and rewards, abandon. At most three tasks at a time, as in the original. Contact points add up; the friend and confidant lines show when reached.
- **Mission list** (top right): each task's active line, progress (defeat-X), and distance and direction to its waypoint.
- **Task kinds**
  - Defeat X: villains of the group (and zone, if the task names one) that the hero gets credit for.
  - Deliver: talk to the target contact or NPC, then go back.
  - Visit: walk within 15 m of the marker.
  - Door mission: a gold beam marks the door (a door of the task's zone whose lair type matches its door type, else any door there). Inside is an original indoor map (docs/missions.md); with no map imported, the mission plays out around the door: its boss (with the original display name), patrols and filler groups of the mission's villain group at the hero's level, and its objectives as green posts to click. Its CanCompleteWith rules decide when it is done.
  - Compound tasks move to their next part at once; story arc episodes are offered one after another.
- **Rewards**: the task's completion table (MissionOwner) and return table (StoryArcSL2 ...) give their XP and influence for the hero's level. Their enhancement drops are logged until enhancements exist.
- **Saving**: the hero file gets a `story` object (contacts met with points, tasks in hand, tasks done). Door missions in hand get their doors back after loading.

Host test command: `coh.Story.Talk [name]` talks to a contact from anywhere (no name: lists contacts within 300 m).

## Not yet

Team-shared missions, enhancement rewards and contact stores, newspaper/police-band missions, villain side, clues window, contact introductions (any contact talks to a hero in its level range).

## Villain chatter (2026-11-23)

Street villains talk as they did in the original. `tools/story/chatter.py <i24>/data <out>` (the
`chatter` stage of `finish_imports.cmd convert`) reads the dialog files
(`scripts.loc/spawndefs/dialog/*.dialog2`: 142 files, about 33,000 lines) and the message ids spawn
definitions name directly, and writes `<out>/story/chatter.json`.

- Zone encounters keep each actor's `dialog_inactive` / `dialog_alerted` and the encounter's `dialog`
  file (`tools/zones/encounters.py`). `UCoHGameRules::ChatterLine` picks a random line of that var.
- A villain says its idle line once when a hero first comes within 20 m, and its alert line when it
  spots a hero. The line floats over its head and goes to local chat for heroes within 100 feet.
- Mission spawns carry their actors' lines in `story_game.json` (`say`: idle, alert), with the task's
  vars and the hero's name filled in: boss taunts, captors' threats.

Not yet: Dialog_Completion and Dialog_ThankHero (rescued civilians thanking the hero; civilians are
not in the game yet), and the original's boss health lines (BOSS_75HEALTH_DIALOG and the like).

## Task forces (2026-11-23)

The original's task forces: a team takes on a contact's story arc together, one episode at a time.
27 task force contacts stand in our zones (Synapse, Citadel, Manticore, Numina, Ms. Liberty, Katie
Hannon, Moonfire, Ernesto Hess, Karsis, Admiral Sutter, Penelope Yin, Dr. Kahn, the trial contacts and
the signature story arc contacts, which the original also ran as task forces).

- **Data**: `story_game.py` gives a task force contact `task_force`: the names it gives the team
  (one is picked: "Task Force Velocity"), `min_size` (MinTaskForceSize) and its lines (invite, level
  too low or high, need a bigger team, send your leader, gather your team, a teammate's level is
  wrong). Tasks keep `force_level` (ForceTaskLevel: their villains' level), and `secondary` /
  `return_secondary` (SecondaryReward: tables for the whole team, e.g. MissionHelper; a name that is
  no reward table is a badge token, e.g. `TaskForceReward, SynapseTF`). `badges_game.py` keeps the
  badges the story gives as tokens (the original's `Requires 0` task force badges).
- **Starting**: the team leader talks to the contact. The level band (every member), team size and
  everyone being near the contact are checked, with the contact's own refusal lines. The original
  asks for 4 to 8 heroes; the game asks for at most `MaxTaskForceTeam` (default 2, `[/Script/COHREBORN.CoHStoryDirector]`
  in Game.ini; 0: the original's number). A hero alone can start one when the size allows.
- **Playing**: the team gets its name; no one can join until it is over (`/invite` refuses). The
  leader holds each episode as a normal task (doors, maps, objectives); teammates enter the door,
  their defeats count for defeat-X tasks, any of them can make a delivery or reach a visit spot, and
  any of them can talk to the contact to accept or turn in. Everyone gets the rewards and clues. The
  mission list shows a TASK FORCE line. Other contacts don't give tasks during a task force.
  `{TaskForceName}` in texts is the team's name.
- **Leaving**: leaving or being kicked from the team leaves the task force. When the holder leaves
  (or disconnects), the task moves to the new leader (an open mission closes and its door opens
  again). The task force goes on with even one hero left, and ends when no one is left.
- **Finishing**: the last turn-in ends it: "Task force complete!", the final rewards and the badge.
- **Tests**: `coh.Story.TaskForceAnyLevel 1` skips the level band; `coh.Story.Talk synapse` talks to
  Synapse from anywhere.

Not yet: merits and the weekly task force bonus (storyarc.merits), task force challenges
(TFChallenge), the original's auto-exemplar to the task force's level, and saving a task force
across a host restart (it ends; the heroes keep what they earned).
