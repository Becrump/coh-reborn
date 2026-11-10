# Glass rollout runbook (all old buildings)

Rules: editor must be idle (no PIE, no other session's import/build); never export textures; never re-send a
call that may have run (`uex.sh` enforces this); save explicit packages only; after stopping any job, check
`Win32_Process` command lines for `uex.sh` / `ue_exec.py` leftovers and kill the whole chain.

1. `import_masks.py` - imports `masks/T_GlassMask_*.png` to `/Game/GlassUpgrade/Masks` (8 small textures).
2. `build_glass_material.py` - the ONE master rebuild (adds PaneMaskRecess: mask texture option, fake recess
   reveal + sill shadow, PanesPerTileY, opacity mask for masked originals). Locks the editor a few minutes.
3. Perf BEFORE at the tower reference spot and a low-rise street (stat unit / stat rhi).
4. `apply_test_overrides.py` with `GLASS_OPTION=Interior GLASS_SCOPE=all` (creates missing per-texture
   children once; skyscraper children are reused), perf AFTER, then the same with `GLASS_SAVE=1` to save
   only the touched tile actor packages.
5. PIE night shots (19:00, 02:00), day wide, low-rise close-up next to a City Sample building; Lumen
   `r.EyeAdaptation.CachedLightingPreExposure` fix.
