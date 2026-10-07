# CoH character export: format brief

Derived from a read of the Thunderspies/CityOfHeroes source (paths relative to that repo). Goal: a Python exporter that turns an NPC (for example a Hellion) into a rigged, animated glTF. Written from the source only, not yet checked against real data. The notes marked "unverified" are the places to test first. On-disk structs use 32-bit pointers stored as file-relative offsets.

## 1. Villain to costume to geometry

- Villains: `defs/villains/*.villain` (`VillainDef "Name" {...}`), parsed by `ParseVillainDef` (Common/gameComm/VillainDef.c:165). Each `Level N { Costumes "a","b" }` block (VillainDef.c:123) lists costume names. One is picked at random (VillainDef.c:1785) and looked up with `npcFindByName`.
- NPC defs: `defs/**/*.nd` (NPC.c:290). Format `NPC "Name" { DisplayName.., Costume {...} }`. Only `costumes[0]` is used (VillainDef.c:1811).
- `Costume` keywords (`ParseCostume`, Common/entity/costume.c:1769): EntTypeFile, CostumeFilePrefix, Scale, BoneScale, Head/Shoulder/Chest/Waist/Hip/Leg/ArmScale, HeadScales/BrowScales/... (Vec3), SkinColor, NumParts, BodyType, `CostumePart`.
- `CostumePart` keywords (costume.c:1734): `"Name"` (body part name), Fx/FxName, Geometry, Texture1, Texture2, DisplayName, RegionName, BodySetName, Color1..Color4 (RGB).
- Body parts: `defs/UI/*.bp` (Common/gameData/BodyPart.c:91), keys Name, GeoName, TexName, BaseName, BoneCount (1 or 2). Two-bone parts use `GeoName+"R"` and `GeoName+"L"`, otherwise `GeoName`, resolved with `bone_IdFromName` (BodyPart.c:45). NPCs pick the body part with `bpGetIndexFromName(part.Name)` (Game/src/entity/costume_client.c:685).
- Geometry resolution (`doChangeGeo`, costume_client.c:238):
  - `"NONE"` means no mesh on that bone.
  - A Geometry containing `.geo/` (for example `enemies/x.geo/GEO_Chest_y`) becomes `file.model`, with `*` replaced by R or L.
  - Otherwise the name is `"<prefix>_<BaseName>.GEO_<GeoName>[R]_<Geometry>"`, plus an `L` variant for two-bone parts. `prefix` is `costumePrefixName()` (costume.c:2024): CostumeFilePrefix, or the body type's ent type.
  - Collar, Capeharness, Broach, Back and Cape first try chest-linked variants from `defs/chestGeoLink.def`.
  - `changeGeo` (Game/src/entity/entclient.c:3280) splits on `.` into file `player_library/<file>.geo` plus model name.
  - A bone with no costume geometry falls back to model `GEO_<BONENAME>[_LODn]` in the ent type's `Graphics` geo (Common/seq/seqskeleton.c:457-524).
- Textures (`determineTextureNames`, costume_client.c:374): the name is `TexName_<tex>`. A leading `!` means use the name exactly, and `none` means white. If tex1 ends in `a` it is dual-pass. If it ends in `x` it is a single texture and tex2 is none. `gender_prefix_fixup` tries `<SM|SF|SH|prefix>_name` first.
- Body types (`g_BodyTypeInfos`, costume.c:1984): 0 male "male" SM, 1 fem "fem" SF, 4 huge "huge" SH, 5/6 enemy "enemy" EY. The ent type comes from `EntTypeFile`, otherwise from that table (costume.c:2006).

## 2. .geo format with skinning

Loader `geoLoadStubs` (Common/seq/anim.c:1594), writer Utilities/GetVrml/src/output.c:1030. The existing `coh2unreal/geo.py` already reads the container, positions, normals and UVs. This section lists what it still needs for skinning.

- Model record (v>=3, `readModel`, anim.c:1264): after the fields geo.py already reads, the eight PackData entries are tris, verts, norms, sts, sts3, weights, matidxs, grid. v4 skips two PackData. v>=7 adds reductions and `f32 autolod[3]`. Then comes `i16 id`, the BoneId the model is attached to. Advance by `size`.
- Skinning data:
  - weights are `u8[vert_count]`, giving w0 = b/255 and w1 = 1 - w0.
  - matidxs are `u8[2*vert_count]`, stored multiplied by 3 (divide by 3 to get the slot; model_cache.c:464-472, rt_bonedmodel.c:57, GetVrml vrml.c:191).
  - The slot indexes into `BoneInfo` at `data + boneinfo_off`: `i32 numbones; i32 bone_ID[15]; ptr weights; ptr matidxs` (anim.h:76-82).
  - Bone IDs are the `BoneId` enum (Common/seq/bones.h): HIPS=0, WAIST, CHEST, NECK, HEAD, COL_R, COL_L, UARMR, ... with BONEID_COUNT <= 100. Names are the enum names without the `BONEID_` prefix, looked up case-insensitively (bones.c).
- Sub-meshes are consecutive triangle ranges, one per texidx entry.

## 3. Skeleton and .anim

- Path `player_library/animations/<NAME>.anim`, uppercase (animtrack.c:291). The file is a raw memory image of `SkeletonAnimTrack` (animtrack.h:79), loaded by `animReadTrackFile` (animtrack.c:63). Offsets are relative to the file start.
  - `i32 headerSize`, `name[256]`, `baseAnimName[256]`, `f32 max_hip`, `f32 length` (frames), `i32 bone_tracks_off`, `i32 bone_track_count`, `i32 rotComp`, `i32 posComp`, `i32 skelHeir_off`, then runtime fields. 584 bytes in all.
- `BoneAnimTrack` (20 bytes): `i32 rot_off, i32 pos_off, u16 rot_fullkeycount, u16 pos_fullkeycount, u16 rot_count, u16 pos_count, i8 boneId, u8 flags, u16 pad`.
- `SkeletonHeirarchy`: `i32 root; {i32 child, i32 next, i32 id}[100]`, with -1 meaning none. Walk `child` and `next` (`animBuildSkeleton`, seqskeleton.c:312). Only the skeleton file has a hierarchy. Other anims load `baseAnimName` for the hierarchy and for missing bones (animtrack.c:250).
- Flags (animtrack.h:39):
  - ROT_UNCOMP=1: 4 x f32.
  - ROT_5BYTE=2: `unPack5ByteQuat` / `animExpand5ByteQuat` (animtrackanimate.c:1518, 334). The high nibble of byte 0 is the index of the missing component, and the low nibble is the top 4 bits of idx0. The next little-endian u32 holds idx0 low 8 bits (bits 24-31), idx1 (bits 12-23) and idx2 (bits 0-11). Value = `2*0.70710678*(i/4096) - 0.70710678`, and the missing component is `sqrt(1 - sum of squares)`.
  - ROT_8BYTE=4: 4 x s16 times 1e-4.
  - NONLINEAR=0x80: same packing, but value = `i*(pi/2)/4096 - pi/4`, clamped (`unpackQuatElemQuarterPi`, libs/UtilitiesLib/src/network/netcomp.c:51).
  - POS_UNCOMP=8: 3 x f32. POS_6BYTE=0x10: 3 x s16 / 32000.
  - Key k is frame k. Interpolation is lerp for positions and slerp for rotations. `rot_count == 1` means constant (animtrackanimate.c:480-598). Quaternions are (x, y, z, w).
  - `quatToMat` with row-vector `mulVecMat3` yields the transpose, so the exporter probably needs to conjugate for glTF. This is unverified.
- Bind pose: key 0 of each bone in the base skeleton. The base has no rotations, only offsets from the parent (seqskeleton.c:996-1013). `btt[bone] = btt[parent] + localPos`, with `btt[HIPS] = 0` (seqskeleton.c:39).
- Retargeting between anim and skeleton: animated pos = animPos - (animBasePos - basePos) (`animDelta`, seqskeleton.c:1016; seqanimate.c:198).
- Skinning math (renderbonedmodel.c:140-157, rendertree.c:2649-2657): `bpt[b] = World_b * Scale_b * T(-btt[b])`, and `boneMat_j = bpt[bone_ID[j]] * T(btt[model.id])`. So mesh vertices are relative to the attach bone's bind position. Add `btt[model.id]` to get skeleton space. The glTF inverse bind matrix for bone b is `T(-btt[b])`.
- Frame rate 30 fps (`TIMESTEP` = frame_time_30; seqsequence.c:1177).

## 4. Sequencers

- Ent types: `ent_types/<type>.txt` (seqtype.c:411,458; keys at seqtype.c:157-250). Relevant keys: Sequencer, SequencerType, Graphics (default geo), GeomScale / GeomScaleMax, BoneScaleFat / BoneScaleSkinny (geo files), Shoulder / Hip / Neck / LegScale vectors, HeadScaleMin / Max.
- Sequencer files: `sequencers/<name>` (seqload.c:197-205).
  - `TypeDef <name> { BaseSkeleton male/skel_ready; ParentType x }`
  - `Move NAME { Type <typename> { Anim male/run 0 0 ; Scale; MoveRate } TEnd ... Requires / Member / Interrupts / NextMove / CycleMove / Flags } MEnd`
- Animation choice: `seqGetTypeGfx` (seqload.c:959) matches `Type` against SequencerType and falls back to ParentType. If lastFrame is 0 it is set to the track length (seqload.c:643). Move names (READY, RUN, DEATH, ...) are data-defined.

## 5. Scaling and colours

- Height: `scaleHero`, scale = Scale/100 + 1, multiplied by type GeomScale (costume_client.c:545, entclient.c:3472). GeomScaleMax adds a random spread (seq.c:921).
- Per-bone scale: `changeBoneScaleEx` (seqskeleton.c:150). Per axis, `s = 1 + (fatOrSkinnyModel.scale - 1) * |v|`, with the fat or skinny geo chosen by sign and the matching model found by `model.id == bone`. `v` is BoneScale for most bones, WaistScale for WAIST, ChestScale for CHEST (male/huge) or BOSOM (female), and f3DScales for BROW..NOSE. It is applied as a node matrix scale (rendertree.c:2651). Unverified: whether the scale propagates to children.
- Translation offsets: COL_R/L get shoulderScaleFat/Skinny times ShoulderScale (x mirrored for L). NECK/HEAD get -y neckScale. ULEG gets hipScale times HipScale (seqanimate.c:165-193).
- Colours: `get_color` (costume_client.c:39) gives c1 = Color1 and c2 = Color2. If tex1 contains "SKIN", c1 = SkinColor and c2 = Color1. Shader COLORBLEND_DUAL, with unit0 = Texture1 (base) and unit1 = Texture2 (generic). Per channel: `C = T2*c1 + (1 - T2)*c2`, `B = 4*light*T1`, `out = T1.a*B + (1 - T1.a)*B*(4*light*C)`, `alpha = c1.a*T2.a`. The mapping from the ATI constants to Color1/Color2 is inferred. For an unlit export use roughly `T1 * lerp(2C, 1, T1.a)`.

## Unverified

- Bone scale propagation to children.
- UV v-flip and handedness (the Atlas Park converter already negates Z, swaps winding and flips V, so reuse that).
- Quaternion conjugation for glTF.

## Checked against the real data (2026-10-07)

- **Model id:** for v7 .geo files the `i16 id` at the end of the model record is -2 on disk. The attach bone comes from the model name (`GEO_Hips_...` → HIPS) with `bone_IdFromText`.
- **Model name suffixes:** names may end in trick suffixes such as `__dblsided`, `__alpha` or `__Collar2x`. Strip everything from `__` on before matching.
- **BoneInfo:** it sits at `data_offset + boneinfo` (the same base as the PackData offsets). The weights and matidxs packs are raw bytes (`vert_count` and `2*vert_count`), and matidx/3 is the slot. Confirmed.
- **Quaternions:** stored as (x, y, z, w). `quatToMat` + `mulVecMat3` applies the conjugate. With the Z mirror, the glTF quaternion is (x, y, -z, w). Verified visually on run, attack, hit and death, with no flipped limbs.
- **Non-linear packing:** it is `sin()` of the clamped angle (`unpackQuatElemQuarterPi` returns `sinf`).
- **Skinning:**
  - Vertices are relative to the attach bone's btt, with HIPS = 0.
  - The exporter writes them in skeleton space: v + btt[attach] + the hips rest position.
  - The inverse bind matrix is T(-world rest position), so the rest pose and the inverse bind matrices agree.
- **Facing:** after the Z mirror the character faces -Z. The root node gets a 180° Y rotation so it faces +Z, the glTF forward axis.
- **Body parts file:** `bodyparts.bp` uses `BodyPart ... End` blocks, not braces.
- **Composite textures:** names such as `X_Hips_CoThorns_01` are `Texture` blocks in `tricks/**/*.txt`. Their `Base1` names the real texture file.
- **Tint:**
  - In costume textures the T1 alpha is mostly 0–40 (gloss), not a tint mask, so in practice the whole texture is tinted.
  - A gain of 2 (`T1*2C`) washes pale colours to white. The default gain is 1, and `--tint-gain` changes it.
  - Texture2's alpha cuts out emblems (alpha = c1.a * T2.a).
- **Not checked yet:** whether bone scale propagates to children (body scaling is not implemented).
