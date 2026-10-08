# Character upgrade pipeline

These scripts upgrade the exported City of Heroes characters (`coh2unreal.character` output). They upscale the textures and smooth the meshes, swap in new AI-generated heads and hands, run automatic checks, and place the result in the open Unreal editor. The exports and the generated files stay outside git.

## Running a batch

```
python tools/upgrade/run_upgrade.py tools/upgrade/jobs/<batch>.json
```

Then read `<work_dir>/summary.json`. The command prints which characters `need review`. For each of those:

- Open the renders in `<work_dir>/<costume>/checks/`: rest, idle and attack shots of the face and both hands.
- Read `report.json` in the same folder for the check that failed.

Do not mark a batch done while any character needs review. Report it with the failing check names instead.

Useful options:

- `--only Thug_Hellion_Boss_01`: run one character.
- `--stages upscale smooth`: run only some stages.

Each stage skips work it has already done. To redo a stage, delete its output folder: `upscaled/`, `smooth/`, `fitted/`, or `_parts/<name>.*`.

## Stages

| Stage | Script | Runs in | Time (RTX 3070) |
| --- | --- | --- | --- |
| upscale | `upscale_textures.py`: Real-ESRGAN x4, plus normal and roughness maps | ComfyUI's embedded Python | ~15 s |
| smooth | `smooth_mesh.py`: one subdivision with skin weights kept and sharp edges creased | Blender | ~6 s |
| parts | `gen_parts.py`: Z-Image concept, Trellis2 mesh, `fill_bg.py` | system Python, starts ComfyUI itself | ~15 min per part, once per batch |
| fit | `fit_parts.py`: fits the head and hands, skins them, checks them, renders check images | Blender | ~20 s |
| unreal | `ue_import.py`: Interchange import as one skeletal mesh, then place and save | inside Unreal via `unreal/scripts/ue_exec.py` | ~10 s |

Generated parts (`"parts"` in the batch) are shared. Make one head and one glove per enemy group, and list them on every costume that should wear them.

## Automatic checks (fit stage)

- `head_on_neck`: the new head's base sits within 3 cm of the old head's base.
- `fingers_point_outward_R/L`: the fingertips are more than 8 cm out from the wrist, along the arm.
- `thumb_in_front_R/L`: the thumb is on the front side, so the hand is a correct left or right hand.
- `cuff_meets_forearm_R/L`: the glove cuff is within 1.5 cm of the forearm, so there is no visible gap.
- `fist_curls_fingers_R/L`: the punch animation moves the fingertips more than 2 cm relative to the hand, so the fingers are rigged.

The checks cannot judge style. Someone still looks at the check renders for colour, faces and anything odd.

## Setup

1. Copy `config.example.json` to `config.json` and fix the paths: Blender, ComfyUI, the upscaler model, and `ue_exec`.
2. For the `unreal` stage, Unreal must be open with Python Remote Execution enabled.
3. ComfyUI must not be running a big job while Unreal is open: an 8 GB GPU runs out of video memory. `gen_parts.py` stops the ComfyUI it started.

## Known limits

- Hand and head colours are projected from a single front or back concept image, so the sides and palms are approximate.
- CoH animates all four fingers as one chain (`RING`, `F2`, `F1`), so individual fingers can't move separately. `finger_follow` (default 0.65) damps the curl, because the generated fingers are already part-curled at rest.
- `is_right_hand` must match the concept image. The `thumb_in_front` check catches a mismatch.
- Trellis2's own texture output is ignored, because it often comes out as noise on 8 GB GPUs.
