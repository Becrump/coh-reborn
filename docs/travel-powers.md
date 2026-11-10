# Travel powers: Sprint and Climb

Two inherent toggles on every hero's tray (Sprint, Climb), with the cost and period of the original Sprint (0.146 Endurance every 0.5 s).

| | Sprint | Climb |
| --- | --- | --- |
| Where | tray slot, `Inherent.Inherent.Sprint` (original data) | tray slot or **V**, `Inherent.Inherent.Climb` (ours, built from Sprint's row in `UCoHPowerDatabase`) |
| Effect | run speed 600 -> 1100 cm/s (`SprintSpeed`); Shift still sprints while held, free | walking into a wall climbs it (no jump needed); climbing 1.4x faster (`ClimbPowerSpeedScale`) |
| Exclusive | switching it on turns Climb off | switching it on turns Sprint off |

Everyone can cling to a wall: jump or fall into it while pushing forward. Without Climb on that costs `ClimbFastDrain` (4) Endurance per second, and at zero the grip gives out ("Out of Endurance: you lose your grip"). A grab also needs 3 Endurance. C still lets go.

Icon: `tools/make_climb_icon.py` writes `Content/CoH/Data/Icons/inherent_climb.cohicon`. The HUD shows the toggle green like any toggle.

## Climbing animations

The climbing set is the Meshy "Climbing" category, retargeted to the three CoH body skeletons (male, fem, huge) as `/Game/CoH/Player/Anims/<body>/<body>__<clip>`, 16 clips each:

| Made how | Clips |
| --- | --- |
| the old Captain Valor wall clips | `climbing_up_wall`, `climbing_down_wall`, `Climb_Left_with_Both_Limbs`, `Climb_Right_with_Both_Limbs` |
| fetched from Meshy on the Hellion biker's rig, 3 credits each (36 in all) | `Grab_Wall_Midair_Idle`, `Jump_and_Grab_Wall`, `Wall_Support_to_Step_Down`, `Hang_and_Climb_Left`, `Hang_and_Climb_Rght`, `Fast_Ladder_Climb`, `Slow_Ladder_Climb`, `Ladder_Climb_Loop`, `Ladder_Mount_Start`, `Ladder_Climb_Finish`, `Climb_Up_Rope`, `diagonal_wall_run` |

Used by the wall climb now (`UpdateClimbAnim`, `PlayClimbMove` in CoHHeroCharacter.cpp): holding on = `Grab_Wall_Midair_Idle`; up / down / left / right = the four wall clips; grabbing the wall plays `Jump_and_Grab_Wall` once; C (let go) plays `Wall_Support_to_Step_Down`; with Climb on, sideways uses the `Hang_and_Climb` shuffles and the loop plays 1.4x faster. The ladder, rope, diagonal and finish clips are in the project, not wired: ladders, ropes and the vault over a ledge have no code yet.

Pipeline (repeatable): `tools/meshy_anims.py` (the Meshy API; paid) -> `tools/anim/export_climb_clips.py` (Blender: per-clip glTF; the looping climbs lose their hips drift and share one hang height) -> `tools/anim/climb_clips_unreal.py` (the editor: import on the biker's skeleton, IK rigs for the CoH skeletons with chains named like the Meshy rigs, retarget FK only). Not play-tested on a real wall yet.
