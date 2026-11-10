# Active ragdoll (bodies with muscles)

Bodies used to go fully limp the moment they were knocked, then snapped upright.
They are now **active ragdolls**: the physics asset's rigid bodies and joints,
with Unreal's physical animation drives acting as muscles that pull each joint
toward the pose the animation is playing. Code: `CoHActiveRagdoll.h/.cpp`, used by
`ACoHCombatEnemy` and `ACoHHeroCharacter`.

Gameplay doesn't change. Who gets knocked, how far and when still comes from
the power rules (`CoHPowers.cpp`, knockback/knockup mods). This only changes how
the body moves.

## What happens

| Event | Villains | Heroes |
|---|---|---|
| Any hit (not a defeat) | The upper body (WAIST and up) jolts from the hit's direction. Strong muscles bring it back within 0.5 s, and the legs stay planted. The jolt scales with damage as a share of max health. | Same |
| Knockdown / knockback / knockup | The whole body goes to physics. The muscles brace in the original KnockDown/KnockBack move (0.25 s), then relax to a low tone while it tumbles. The top of the body gets a little more of the launch than the feet, so it tips over its legs. | The capsule is launched as before (the player keeps control and camera). The limbs and spine flail around the hips and settle on landing. |
| Hit while down | The downed body takes a jolt. | n/a |
| Defeat | Muscles fade from half tension to limp over 1.2 s, so the body slumps instead of dropping like a sack. | Unchanged (respawn) |
| Get-up | The host waits until the body rests on a floor, then picks the spot and the facing: on its back it sits up toward its feet, face down toward its head. Every PC captures the lying pose and crossfades it into the original GetUp move over 0.4 s. AI resumes when the move ends. | n/a |

Joints are tuned in code by the original CoH bone names (HIPS, WAIST, CHEST,
NECK, HEAD, UARM/LARM/HAND, ULEG/LLEG/FOOT; UE mannequin names as a fallback):
swing/twist limits a little inside a human's range (knees and elbows barely
twist), masses for an ~80 kg body (costume bones like capes and belts are 0.3 kg
so they never swing the body), and some damping. So every imported model gets the
same body without editing physics assets.

## Multiplayer

The host decides and every PC runs the physics locally:
- `UCoHActiveRagdoll::HitReact` (host, from `UCoHPowerComponent::ApplyDamage`) → `MulticastFlinch` (unreliable, cosmetic).
- `ACoHCombatEnemy::LaunchRagdoll` (host) → `MulticastRagdoll(velocity, bDefeated)`. The defeat flag rides along so a client never waits on the replicated State.
- `RecoverRagdoll` runs on the host only → `MulticastGetUp(spot, yaw)`, so every PC stands the villain up at the same place.
- Heroes: the knock branch in `ApplyMod` → `MulticastTumble`.

The bodies settle slightly differently on each PC. The get-up crossfade hides
that, because everyone stands up at the host's spot.

## Tuning

Everything is a config property, so it can be tuned in `DefaultGame.ini` without
a rebuild, or live on the ActiveRagdoll component in the editor:

```ini
[/Script/COHREBORN.CoHActiveRagdoll]
bEnabled=True            ; False = the old limp ragdoll, no flinches
MuscleStrength=1000      ; muscle stiffness at tension 1
MuscleDamping=80
BraceTension=0.8         ; knocked: tension while bracing...
BraceSeconds=0.25
RelaxSeconds=0.8         ; ...then relaxing to...
TumbleTension=0.3        ; ...this while tumbling and lying
DefeatTension=0.5
DefeatRelaxSeconds=1.2
FlinchSpeed=320          ; cm/s for a hit worth a full health bar
FlinchMin=0.3
FlinchWeight=0.8
FlinchSeconds=0.5
FlinchTension=1.5
TumbleWeight=0.75
GetUpBlendSeconds=0.4
bTuneJoints=True
```

## Test plan (first PC build)

1. Play in Atlas Park and punch a Hellion. Its chest and head should snap back
   from the punch and recover. No sliding, no legs leaving the ground.
2. Use a knockback power (e.g. Energy Blast's Power Push) on a minion. It should
   fly with arms and legs bracing, tip over, tumble with some tone, settle, then
   get up from where it lies without popping.
3. Knock one into a wall at high magnitude. CCD keeps it from passing through.
4. Defeat one with a big hit. It should slump over about a second, then go limp.
5. Get knocked as a hero. The limbs flail in the air and settle on landing, and
   the camera is unaffected.
6. Listen server with 2 players: both screens see the same flinches and knocks,
   and the villain gets up at the same spot on both.

## Known limits / next steps

- The get-up uses the one original GetUp move, which starts on the back. Face-down
  bodies roll over during the 0.4 s crossfade. A separate face-down get-up clip
  would look better.
- Swing limits are symmetric (Unreal constraints), so knees can bend slightly the
  wrong way within the limit. Proper hinge frames need editing the physics assets
  in the editor (rotate the knee/elbow constraint frames, then lock one swing axis).
- Villains without a kit model (catalog/preview enemies) have no knock or get-up
  clips. They keep their current pose as the muscle target and snap at get-up.
- Hero defeat is unchanged (instant respawn, as before).
