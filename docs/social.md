# Chat and teams

The original game's chat channels and teams, for a small group of friends
(CoHSocial.h / .cpp, a `UCoHSocial` on each hero; the host routes chat and owns teams).

## Chat

**Enter** opens the chat line (bottom left); the HUD's Chat button shows or hides it.
Plain text goes to the current channel (Local to start).

| Command | |
|---|---|
| `/l text` | Local: heroes within 100 ft (as the original) |
| `/b text`, `/y` | Broadcast: everyone in the city |
| `/t text`, `/tm`, `/g` | Team |
| `/tell name, text` (`/p`) | A private tell (names match from the start) |
| `/who` | Who is online |

A channel command with no text switches the default channel.

## Teams

- `/invite name` (`/i`), then the other hero types `/accept` or `/decline`.
  Only the leader invites (the inviter becomes leader of a new team). Up to 8.
- `/leave`, `/kick name` (leader), `/team` lists the team. When the leader
  leaves the next member leads; a team of one disbands.
- The team window above the chat shows each teammate's health; the leader has a `*`.
- **Rewards**: each teammate within kill-credit range gets the whole team's
  share of a defeat (XP, influence), instead of only the damage they did.
  Item drops (inspirations, enhancements) still go to the hero who did the most damage.
- **Missions**: teammates see each other's mission doors and can go in once the
  mission's owner has entered; they can click objectives and use the exit. When
  the mission's map closes, teammates still inside come out at the door. The task
  completes for its owner.

# Defeat, hospital and resurrection

As the original: a defeated hero goes limp where it fell (debt is taken at the
defeat, from level 10). **H** wakes it in the nearest hospital, healed (the
"gurney" spawn points of the converted zones; Atlas Park was rebuilt, so heroes
there wake at the start point until it has a hospital). A teammate's resurrect
power (any power with a `kDead...` target, such as Empathy's Resurrect) or an
Awaken / Bounce Back / Restoration inspiration (25 / 50 / 100%) brings the hero
back up where it lies; so does Rise of the Phoenix.
