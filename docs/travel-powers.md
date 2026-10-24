# Travel powers: Sprint and Climb

Two inherent toggles on every hero's tray (Sprint, Climb), with the cost and period of the original Sprint (0.146 Endurance every 0.5 s).

| | Sprint | Climb |
| --- | --- | --- |
| Where | tray slot, `Inherent.Inherent.Sprint` (original data) | tray slot or **V**, `Inherent.Inherent.Climb` (ours, built from Sprint's row in `UCoHPowerDatabase`) |
| Effect | run speed 600 -> 1100 cm/s (`SprintSpeed`); Shift still sprints while held, free | walking into a wall climbs it (no jump needed); climbing 1.4x faster (`ClimbPowerSpeedScale`) |
| Exclusive | switching it on turns Climb off | switching it on turns Sprint off |

Everyone can cling to a wall: jump or fall into it while pushing forward. Without Climb on that costs `ClimbFastDrain` (4) Endurance per second, and at zero the grip gives out ("Out of Endurance: you lose your grip"). A grab also needs 3 Endurance. C still lets go.

Icon: `tools/make_climb_icon.py` writes `Content/CoH/Data/Icons/inherent_climb.cohicon`. The HUD shows the toggle green like any toggle.

Not done: climb animations on the CoH bodies. The four wall clips (`ClimbAnims`) are Meshy clips on the old hero's skeleton; they have to be retargeted to the male / fem / huge CoH skeletons first.
