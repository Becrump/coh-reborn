# HQ lobby: the game's front end

Status 2026-11-12: written, **not yet compiled or tested** (the editor was busy
with the zone import). Clickable look-and-feel mockup: the "HQ Lobby mockup"
artifact in the project.

The game now starts in the HQ lobby instead of dropping straight into Atlas
Park. Everyone settles how the game runs there: host a server, or join a
friend's.

## What the player sees

A "mission control" screen over the city at night: searchlights, a holo grid,
a scanner sweep, a spinning holo table showing how many heroes are online,
and a Paragon News ticker. Four tabs:

- **Join Friends**: the saved servers, each with a live status light
  (online, offline, checking), the zone, the heroes on it with pips
  (3 / 7), ping bars, and a PASSWORD tag when it needs one. Join, Edit
  (rename, change address, remove), Add Server, Direct Connect (also saved),
  Refresh. **Found on your network** lists servers on the home network that
  aren't saved yet (Save or Join).
- **Host a Server**: server name, optional password (Show/Hide), max heroes
  2 to 7, start zone (Atlas Park now; other zones show "After zone import"),
  "Show on local network", "Remember these settings". **Tell your friends**
  lists the internet address (public IP, router ports opened by UPnP)
  and the home network address, with Copy buttons. Launch Server.
- **Hero Roster**: the hero files in `Saved/Heroes` as cards (name, level,
  origin, archetype, sets), plus "Starter hero" and **New Hero** (name +
  archetype, copied from the archetype starters).
- **Settings**: opens the F10 graphics and city life panel.

Joining a locked server asks for the password (with "Remember for this
server"). While connecting, a spinner shows "Heading to ...". A wrong
password, a full server, an unreachable host, a dropped connection or a
different build lands back in the HQ with a red message.

In game, **Esc** opens "Leave the city?": Return to HQ (the host's version
says it closes the server), Keep playing, Quit game. In Play-In-Editor Esc
stops play first, so test this in Standalone or a build.

## How it works

| Piece | File |
| --- | --- |
| Lobby data and actions, Esc menu, failure messages | `CoHFrontend.h/.cpp` (`UCoHFrontend`, a GameInstance subsystem) |
| Frontend game mode (no hero, no villains) | `ACoHFrontendGameMode` in `CoHFrontend.h` |
| Server status beacon | `CoHLobbyNet.h/.cpp` |
| The HQ screen (Slate) | `SCoHLobby.h/.cpp` |
| Password check, server name | `ACoHGameMode::InitGame/PreLogin` in `CoHHeroCharacter.cpp` |
| Hero choice | `ACoHHeroCharacter::SendLocalHero` uses the lobby's pick first, then `-Hero=` |

- **Startup**: `GameDefaultMap` is the empty engine map `/Engine/Maps/Entry`.
  `GameModeMapPrefixes` gives it `CoHFrontendGameMode`, and the subsystem
  shows the HQ whenever that map is loaded. A map on the command line still
  skips the lobby (`COHREBORN.exe AtlasPark_DressingStudy_Nanite?listen`).
  Play-In-Editor is unchanged: it plays the open level.
- **Host**: `OpenLevel(<zone>, "listen?MaxPlayers=N?ServerName=...?Password=...")`.
  Values are %-encoded so spaces and symbols survive the URL. The name and
  password are kept in the subsystem so they survive monorail travel.
- **Join**: `OpenLevel("<ip>:<port>", "Password=...")`. The host's
  `PreLogin` refuses a wrong password with `WRONG_PASSWORD`, and
  `MaxPlayers` turns away the 8th player ("Server full").
- **Status**: the host answers UDP on **game port + 1 (7778)**:
  `COHR? <nonce> <direct|lan>` gets `COHR! <nonce> {json}` with name,
  zone, players, max, heroes, password yes/no, net version and game port.
  The lobby asks every saved server every 4 s (`StatusInterval`), measures
  the ping, and broadcasts once per round for "Found on your network". No
  reply for 2.5 s means offline. PC names (Tailscale MagicDNS like
  `robert-pc`) are looked up off the game thread.
- **Player names**: the host sets each player's name to their hero's name
  when the hero file arrives, so the server list shows who is on.
- **Version check**: `CoHLobby::NetVersion` (now 1). Bump it when old and
  new builds can no longer play together; the lobby then shows "OTHER
  VERSION" and greys out Join.

## Files on each PC

- `Saved/CoHLobby.json`: saved servers (password only when "remember" is
  ticked; security isn't a concern for this friends server), last seen time,
  the chosen hero, the last host settings.
- `Saved/Heroes/<name>.json`: heroes (unchanged, see multiplayer.md).
- `Content/Frontend/HQ_Backdrop.png`: the backdrop (a crop of the key art),
  read at runtime and staged with the build. Swap the file to change it.

## Config (DefaultGame.ini `[/Script/COHREBORN.CoHFrontend]`)

- `Zones`: the host's zone choices. Galaxy City and Kings Row are listed with
  `bReady=False` until their levels have player starts.
- `NewsLines`: the ticker.
- `FrontendMap` must match `GameDefaultMap`. A playable HQ zone later only
  needs a new map here; the screen draws over whatever map that is.

## Networking notes for friends (no Tailscale needed)

- Opening the Host tab looks up the host's public IP (api.ipify.org) and asks
  the router over UPnP to forward **UDP 7777 and 7778** to this PC
  (`CoHPortMapper`, Windows UPnP NAT service, removed again when the game
  quits). "Tell your friends" shows the internet address with Copy, and says
  whether the ports opened.
- If the router has UPnP off, the line says to forward UDP 7777-7778 to the
  PC's home address once in the router.
- If the router's own internet address is private (CGNAT from the provider),
  no port forward can work; the line says so. Tailscale (or a relay later)
  is the way around that.
- Same home network: nothing needed, servers show under "Found on your network".
- Tailscale still works if someone has it: its 100.x address is listed too.
- Windows asks to allow the game through the firewall the first time it
  hosts: allow private networks (and public if Tailscale shows as public).

## Test plan (when the editor is free)

1. Build. Run Standalone (or a packaged build): the HQ appears, the
   backdrop moves, the ticker scrolls.
2. Host tab: launch with a password. In a second instance (same PC, or a
   friend), Add Server `127.0.0.1` (or the Tailscale IP): it shows ONLINE,
   1/7, the host's hero name, PASSWORD, a ping.
3. Join with the wrong password: back to HQ with "Wrong password". Join
   with the right one and "remember": in game.
4. Host presses Esc > Close server: the client returns to HQ with "Lost the
   connection". The server shows OFFLINE, "last seen just now".
5. Hero Roster: New Hero (needs the starters in the rules HeroesDir), pick
   it, host or join: the hero arrives with that name.
