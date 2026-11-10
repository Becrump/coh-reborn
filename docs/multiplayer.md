# Multiplayer: hosting and hero saves

Status 2026-11-10: written, not yet compiled or tested. Review and test plan:
the Claude Doc "Multiplayer hosting and saves review" in the project.

## Hosting (friends group)

A listen server: one player hosts and plays, the others join.

- Host: `COHREBORN.exe AtlasPark_DressingStudy_Nanite?listen`
- Join: `COHREBORN.exe <host IP>` (or console `open <host IP>`)
- Over the internet: everyone on the same Tailscale network (no port
  forwarding), or the host forwards UDP 7777.
- `MaxPlayers=7` in DefaultGame.ini.

## Hero saves live on each player's PC

Robert's decision (2026-11-10): local saves, no anti-cheat.

1. The owning PC picks its hero name: `-Hero=<name>` on the command line,
   else the starter `HeroFile` name (Play-In-Editor players after the first
   get `_P1`, `_P2`...).
2. It reads `Saved/Heroes/<name>.json` and sends the text to the host
   (`ACoHHeroCharacter::ServerSubmitHero`). First run: the old host-side
   `<HeroFile>_save.json` in HeroesDir if it exists (keeps Robert's progress),
   else the starter `HeroFile`, else the test hero.
3. The host runs the rules as before. Every save (`UCoHHeroProgress::Save`)
   goes back to the owning PC (`ClientSaveHero`) and a backup goes to the
   host's `Saved/HeroBackups/<player>/<hero>.json`.
4. Power looks: the customize panel sends them to the host
   (`ServerSetLooks`); other players get them with the replicated record
   (`OnRep_Hero`).

The file format is the hero file (format 2, docs/hero-build.md), so moving
saves to a server later (public hosting) only changes where the file lives.

## What else replicates

- Villains: the host's chosen model, clips and kit (`FCoHEnemyLook`
  `NetLook`), their state (each PC plays the clip) and ragdolls
  (`MulticastRagdoll`).
- Travel powers and climbing (`FCoHTravelState NetTravel`): the owner sets it,
  the host follows (`ServerSetTravel`), others see it.

## Known gaps

- Encounter idle moves and civilian-harass poses play only on the host.
- Civilians and traffic (`ACoHLifeManager`) are simulated per PC.
- The old Brawl punch path (`LandPunch`) still deals damage locally.
- `RulesDir` in DefaultGame.ini points at Robert's folder; a friend's
  packaged copy needs the rules JSON shipped with it.
- One big map: set `wp.Runtime.EnableServerStreaming=1` so the host loads
  only the cells near players.

## Quick test (editor)

Play settings: Net Mode "Play As Listen Server", 3 players, "Run Under One
Process" ON (the PIE instance number picks each window's hero file). Then
the checklist in the review doc.
