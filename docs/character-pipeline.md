# Character pipeline (charpipe): local image-to-3D to a rigged, CoH-animatable character

`tools/charpipe/` turns reference images of a character into a textured, rigged model that plays the original City of Heroes clips. It runs locally and unattended on Robert's PC (RTX 3070 8 GB), uses no paid services, and can be rerun to resume.

```
reference images ─► Hunyuan3D-2 shape ─► Hunyuan3D-Paint texture ─► auto-rig (shared 24-bone skeleton)
   (1-4 views)       (2mini / 2mv)          (CPU offload)            + heat weights
                                                                          │
   preview PNGs ◄─ CoH idle/run/Brawl retarget ◄─ FBX + GLB (+ part slots) ◄─ rig cleanup
```

## Install (once)

```
bash tools/charpipe/install/install_hy3d.sh 2>&1 | tee C:/Users/rtcru/hy3d/install.log
```

It installs into `C:\Users\rtcru\hy3d\` (outside the repo):
- Python 3.12 venv (uv), torch 2.6.0+cu126, Tencent-Hunyuan/Hunyuan3D-2 (commit in `hy3d_commit.txt`), transformers 4.46.3 / diffusers 0.31.0. Newer transformers renamed the DINOv2 weights, so the checkpoints fail to load.
- `setup_cuda.sh`: a portable CUDA 12.6.3 toolkit assembled from NVIDIA's official redistributable zips (`cuda126\`, SHA-256 checked, no admin, no system changes).
- `build_rasterizer.cmd`: compiles Hunyuan3D's `custom_rasterizer` for **sm_86** with VS 2022 Build Tools (v14.29 toolset). The prebuilt wheels that ship with ComfyUI wrappers are sm_89 (RTX 40-series) only and fail on a 3070 with `no kernel image is available`.
- `mesh_processor` (CPU) comes prebuilt from 3D Gen Studio's ComfyUI-Hunyuan3DWrapper.
- Model weights download on first use into `~/.cache/huggingface` (2mini 7 GB, 2mv 9 GB, paint + delight 18 GB). All of them are ungated.

Requires Blender 5.2 and VS 2022 Build Tools with the C++ workload.

## Use

```
tools\charpipe\charpipe.cmd <in_dir> <out_dir> [--only NAME] [--parts] [--wait] [--redo STEP] [--height 1.8]
```

- `<in_dir>/<character>/front.png` is required. Add `left.png`, `back.png` and `right.png` for multi-view (better proportions). Any single image works as the front. An optional `height.txt` sets the height in metres.
- Make the inputs from an original CoH model: `blender -b --factory-startup -P tools/charpipe/bl_refviews.py -- <character.gltf> <in_dir>/<name>`, which renders the 4 orthographic T-pose views + `height.txt`. Concept art, Meshy renders or photos also work, best with a T-pose and plain background.
- Copy `config.example.json` to `config.json` to change paths, VRAM thresholds or the face budget.

Per character, in `<out_dir>/<character>/`:

| Step | Output | Runs on | Time (3070) |
|---|---|---|---|
| shape | `shape.glb` (≤40k faces) | GPU, Hunyuan3D-2mini (1 view) / 2mv (2+ views) | ~3-4 min incl. model load |
| texture | `textured.glb` | GPU, Hunyuan3D-Paint v2.0 turbo, CPU offload | see test run below |
| rig | `rigged_raw.glb`, `autorig.json` | Blender (CPU) | ~15 s |
| clean | `<name>.glb`, `cleanup.json` | Blender (CPU) | ~6 s |
| export | `<name>.fbx` (+ `parts/<name>_<slot>.glb` with `--parts`) | Blender (CPU) | ~10 s |
| preview | `preview/preview_{idle,run,brawl,head}.png` | Blender EEVEE (light GPU) | ~20 s |

Each step is skipped when its output exists, so a rerun resumes. `--redo STEP` reruns from that step on. Logs: `<out_dir>/charpipe_log.txt` has one line per character and step (`OK` / `FAIL` / `SKIP` / `WAIT` with time and details), and `<character>/logs/<step>.log` holds the full output.

### GPU guard

Before every GPU step the pipeline checks for `UnrealEditor*.exe` (editor, `-Cmd`, or a `-game` copy) and for free VRAM in `nvidia-smi` (shape/texture need 6000 MB, preview 1500 MB). If either check fails:
- without `--wait` it logs `WAIT <reason>` and exits with code 3;
- with `--wait` it checks again every 3 minutes and starts as soon as the GPU is free.

It **never closes or touches the Unreal editor**. Hunyuan3D cannot share 8 GB with an open editor.

## The rig

`bl_autorig.py` fits the 24-bone skeleton that Meshy uses (`Hips, Spine02, Spine01, Spine, neck, Head, Left/Right Shoulder/Arm/ForeArm/Hand/UpLeg/Leg/Foot/ToeBase`, plus `head_end`, `headfront`) to the mesh:
- torso joints at fixed height fractions, centred on the body cross-section;
- hands at the farthest arm point (works for T-pose and arms-down);
- knees and ankles at the leg cross-section centres; toes at the most forward foot point.

Weights come from Blender's automatic (heat) weighting, with envelope weights as the fallback.

`rig_cleanup.py` then bakes scale, faces the model down -Y, grounds it, and fixes the weights: stray hand weights, plus limb isolation by surface distance, so hands never pull thigh or pocket skin and the left arm never moves the right. Because the bone names are Meshy's, the same files also clean Meshy rigs.

`retarget2.py` plays CoH clips (family `coh`, male/skel_ready2) on it (family `meshy`). It has one shared bone map per body family, with elbow/knee hinge alignment, forearm twist from the thumb direction, hips scaled by leg length, and a ground pass that keeps run airtime. The same code drives the samples in `model-upgrade-samples` (Meshy Hellions on CoH clips, style packs).

## Known limits

- **No finger bones.** The skeleton has none, so hands keep the pose the generator made. Use references with closed fists for brawlers. CoH's finger curl (RING/F2/F1) is lost.
- **Facing:** generated meshes come out facing -Y. If one comes out backwards, pass `--face-plus-y` to `bl_autorig.py`.
- **Fused geometry:** arms-down references can fuse hands to thighs. The cleanup keeps the hands with the arms, but the fused faces still stretch. Use T-pose references.
- **Joint fitting is heuristic.** Very wide costumes (capes, huge shoulder pads, long coats) can misplace shoulders or hips. Check `preview_brawl.png`; `autorig.json` lists every joint.
- **Texture** uses the front image only: backs and sides are inferred. Multi-view reference images improve the shape, not yet the texture.
- **Part slots** (`--parts`) are cut by dominant bone. Seams between parts of different characters need collars/cuffs or a common base body (see the seam log in `model-upgrade-samples/README.md`); in Unreal this maps to Mutable object groups.
- **Weights** stay in the user cache, not the repo. Outputs are not committed.

## Files

| File | Runs in | Purpose |
|---|---|---|
| `charpipe.py` / `charpipe.cmd` | system Python | orchestration, resume, GPU guard, log |
| `hy3d_gen.py` | hy3d venv | Hunyuan3D shape / texture |
| `bl_refviews.py` | Blender | reference views from an original CoH model |
| `bl_autorig.py` | Blender | skeleton fit + weights |
| `rig_cleanup.py` | Blender | scale / facing / ground / weight fixes (also for Meshy rigs) |
| `bl_export.py` | Blender | FBX for Unreal + part slots |
| `bl_preview.py`, `common.py`, `retarget2.py` | Blender | CoH clip retarget + preview renders |
| `install/install_hy3d.sh`, `install/setup_cuda.sh`, `install/build_rasterizer.cmd` | bash / cmd | one-time install |
