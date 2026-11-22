# Pool helpers: dropped plain functions placed by `.sdata2` order

Decided 2026-11-22 (R2 + tags, see the end). Measured on branch `an-pool` (9c16afc25), 2026-11-22.
Scratch work is in `build/scratch/poolexp/` and is not committed.

## Question

The practice: write a plain (not `inline`) function. The caller inlines it,
the original link dropped its own copy, and it sits in the source where the
original's `.sdata2` order says code was generated. The review accepted some
of these helpers and rejected others. This note lists every such helper,
checks the compiler facts, and proposes rules the owner can choose from.

## 1. Compiler and linker facts (GC/2.6, the game flags)

The game cflags were used unchanged (`-O4,p -inline auto,deferred
-fp_contract on ...`). The pools were read with `tools/pool.py`'s `Obj`.

| # | source | result |
|---|---|---|
| e1 | `A` calls `h`, `B`; `h` plain, defined **below** `A` | `.text` h, B, A (bottom up). Pool `1.0 2.0` (h), `5.0` (B), `3.0` (A). A inlines h (no `bl`) and reuses h's literals. **`h__Ff` is still emitted (`T`).** |
| e2 | the same, `h` defined **above** `A` | `.text` B, A, h. Pool `5.0`, `3.0 1.0 2.0`: A, inlining h, creates h's literals itself. h is emitted. |
| e3 | `static` h below A | the same as e1. **`t h__Ff` is emitted.** |
| e6 | `static` h and an **unreferenced** `static` k | both are emitted (`t k__Ff`, `t h__Ff`). |
| e4/e5 | `inline` h (defined first, or declared and then defined later) | no copy. Its literals land in A's block, in A's place. |
| e7/e8 | file-scope or local `static const f32 k = 8.0f` | folded into an ordinary literal, created where it is first used. It cannot account for a run of literals. |
| e9 | `x*2; x+3; x-9` / `(x+4)*6` | statements are pooled in source order. Inside one expression the outer operand comes first (`6.0`, then `4.0`). |
| link | `mwldeppc -mapunused` on the e-style object plus a separate `__start` caller | `UNUSED h__Ff` and `UNUSED s__Ff` (plain and static, both inlined and never called). The functions that are called stay. |

What follows from these results:

- Under deferred inlining, a plain function creates its literals **at its own
  source position**, but only when it is generated before its callers, which
  means it is defined below them. If it is defined above every caller, the
  first caller to inline it creates the literals instead, and the helper adds
  nothing to the pool.
- MWCC **always** emits the out-of-line copy, whether the function is plain
  or `static`, and even when nothing calls it. A `static` function never
  vanishes at compile time. MWLD's dead-stripping removes it at link time.
- So "ours only" in `try.py` is unavoidable for **every** helper of this kind,
  the original's included: its `.o` had the copy too, and the DOL lost it at
  link. "Ours only" is no evidence against a helper, and a rule like "allowed
  only when ours drops it too" rejects every one of them.
- No construct other than code generated at that point can put a run of
  literals between two functions' blocks. Neither `inline` nor a scalar
  `static const` can do it. Leading file-scope aggregates and tables are the
  known exception at the head of the pool (RULES_CARD "Literals before their
  first visible use" (1) and (4)). Once the function order is verified
  (`order_check.py`), a mid-pool run therefore **proves that a dropped
  function existed at that position**, and that its inlined body uses those
  literals first. The run does **not** prove where the function's body starts
  and ends, or what it was called. That is the real point of dispute.

## 2. Inventory

Method:

1. Every game unit was built, and `objdiff-cli` was run against the target.
   The inventory takes every non-weak function that exists in ours but not in
   the target. That is 75 units and 168 helpers. Excluded: JGeometry
   template instances (`TVec3<f>` ctor/`set`) and tu_8042E964's
   `StageSelectWindow_804B1600` ctor. 82 of the helpers have a comment citing
   pool/`.sdata2`. The rest are "dead-stripped, X inlines it" helpers.
2. None of the 168 is called out of line in ours (no `R_PPC_REL24` to it).
   Every caller inlines it.
3. A/B test. A copy of the unit was compiled with the helper turned into
   `inline` at the same place. That is the "no helper" alternative: the code
   sits in each caller and creates nothing of its own. Both objects were
   diffed with `functionRelocDiffs=all`.

Table columns:

- **alone**: the functions at 100 % that are lost when only this helper
  becomes inline.
- **unit**: the functions lost when all of the unit's helpers become inline.
  The figures overlap: one misplaced literal shifts the whole pool, so the
  per-helper numbers do not add up.
- **sites**: the call sites in our source. Each one is an inlined copy in the
  original's asm.
- **lines**: the definition's length. 3 means a one-statement body.
- **R1, R2, R3**: the rules in section 3.
- **review**: the known verdicts (accepted examples from RULES_CARD and the
  reviewer, rejected ones from `contested`). The helpers that `contested`
  reverted are still present on `an-pool`.

Figures:

- If all 168 become inline, **321 functions lose 100 %**. The status quo is
  worth 321 functions.
- 39 helpers change nothing on their own. Dropping all 39 still costs 37,
  because some are needed jointly (tu_803A8DFC's three row-alpha setters:
  each 0 alone, 19 together; escort_base_801213EC's life-meter spawners: 12).

| unit | helper | body (start) | lines | sites | alone | unit | evidence beyond pool | R1 | R2 | R3 | review |
|---|---|---|---:|---:|---:|---:|---|:-:|:-:|:-:|---|
| act_block | keepsMoving | `{ JGeometry::TVec3f vel = field_0x3c; if ((field_0x90 & 3) != 0 && thr` | 11 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_bombchu | faceMoveDirection | `{ if (field_0x276 == 1) { if (field_0x234 > 0.0f) { field_0x27c = 0.0f` | 15 | 1 | 4 | 4 | pool only | - | - | - |  |
| act_cannon | readSwingRange | `{ self->field_0x280 = (f32)(self->field_0x90 >> 8 & 0x1F); }` | 3 | 1 | 2 | 3 | one statement | - | y | - |  |
| act_cannon | swing | `{ if (c->field_0x280 <= 0.0f) { return; } f32 speed; f32 rate; switch ` | 38 | 2 | 2 | 3 | 2 call sites | y | y | y |  |
| act_cannon | spawnTakenEffect | `{ spawnEmitter_8013CC50(self->field_0x4, &self->mPos, 0x503, 0, 0, NUL` | 3 | 1 | 2 | 3 | one statement | - | y | - |  |
| act_cannon | findOwner | `{ for (s32 i = 0; i < 4; i++) { u8 bit = 1 << i; if ((gGameRoot_8053AA` | 15 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_cannon | updateRise | `{ self->field_0x284 += 0.05f; { f32 t = 2.0f * (0.5f - self->field_0x2` | 8 | 1 | 2 | 3 | same name in act_force_gem_winged | - | - | y |  |
| act_cannon | updateRecoil | `{ static s32 lbl_8053AA70 = 0; static f32 lbl_8053AA78 = 0.0f; lbl_805` | 37 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_cannon | setBounceHeight | `{ f32 sinv = JMath::sincosTable_.sinDegree(a); self->mPos.y = self->mH` | 4 | 1 | 4 | 3 | pool only | - | - | - |  |
| act_cloud | isAirborne | `{ return getPlayerPos_8023E724(player)->z > 0.0f; }` | 3 | 1 | 3 | 3 | one statement | - | y | - | rejected |
| act_eyeball_switch | open | `{ setScreenFlag_0x30(0xFF, true); gBgRewrite_8053AC98->fn_802A3948(&mPos, 0, f` | 6 | 2 | 0 | 0 | 2 call sites | y | y | y |  |
| act_fairy_invincible | setUniformScaleMtx | `{ m[0][3] = 0.0f; m[1][3] = 0.0f; m[2][3] = 0.0f; m[0][0] = scale; m[0` | 14 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_fish | stopSwim | `{ field_0x25c = 0.0f; field_0x258 = 0.0f; field_0x254 = 0.0f; field_0x` | 6 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_force_gem | stopMoving | `{ field_0x3c.z = 0.0f; field_0x3c.y = 0.0f; field_0x3c.x = 0.0f; }` | 5 | 7 | 5 | 5 | 7 call sites | y | y | y |  |
| act_force_gem_winged | updateRise | `{ if (field_0x286 == 1) { s32 serial = -1; bool found = false; while (` | 32 | 1 | 0 | 0 | same name in act_cannon | - | - | y |  |
| act_force_like | spawnKindEmitter | `{ spawnEmitter_8013CC50(field_0x4, &mPos, lbl_80539E70[field_0x234], 0` | 3 | 2 | 0 | 0 | 2 call sites; one statement | y | y | y |  |
| act_four_person_pull_switch | checkAllPulled | `{ if (((field_0x90 >> 4) & 3) != 0) { return false; } s32 i; for (i = ` | 19 | 1 | 2 | 2 | pool only | - | - | - | accepted |
| act_four_sword_demo | spawnPlayerEffects | `{ JGeometry::TVec3f pos = mPos; for (s32 i = 0; i < 4; i++) { const JG` | 11 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_four_sword_demo | spreadPlayers | `{ bool flag = false; for (s32 i = 0; i < 4; i++) { JGeometry::TVec3f p` | 16 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_four_sword_demo | raisePlayers | `{ bool flag = false; for (s32 i = 0; i < 4; i++) { JGeometry::TVec3f p` | 13 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_four_sword_demo | checkPlayers | `{ for (s32 i = 0; i < 4; i++) { if (!fn_8023561C(i)) { return false; }` | 22 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_four_sword_demo | showMessage | `{ u32 msg = 0x4b2; if (field_0x230 != 0) { msg = 0x4b3; } return fn_80` | 7 | 1 | 3 | 2 | same name in act_force_gem_winged, act_shop_item | - | - | y |  |
| act_gambling_shop | swapTwoChests | `{ s32 roll = (s32)(3.0f * gGameRoot_8053AAF8->mRandom.get_ufloat_1());` | 23 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_great_fairy_spfr | talkTo | `{ JGeometry::TBox2f box = mBox; box.i.x += mPos.x; box.i.y += mPos.y; ` | 21 | 1 | 1 | 3 | same name in act_escorted_woman_arrival_point_80125B58 | - | - | y |  |
| act_great_fairy_spfr | placeAtBarrier | `{ JGeometry::TVec3f pos(0.0f, 0.0f, 0.0f); s32 bari = getActorManager_` | 20 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_great_fairy_spfr | spawnSoldier | `{ JGeometry::TVec3f pos(0.0f, 0.0f, 0.0f); s32 bari = getActorManager_` | 15 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_hyrule_castle_barrier | getMidPos | `{ return &JGeometry::TVec3f(mPos.x, mPos.y + 16.0f * (i - 1), 0.0f); /` | 3 | 1 | 3 | 3 | one statement | - | y | - |  |
| act_hyrule_castle_barrier | getEndPos2 | `{ const JGeometry::TVec3f* p; switch (field_0x234) { case 1: p = &JGeo` | 12 | 3 | 0 | 3 | 3 call sites | y | y | y |  |
| act_hyrule_castle_barrier | getEndPos1 | `{ const JGeometry::TVec3f* p; switch (field_0x234) { case 1: p = &JGeo` | 12 | 3 | 0 | 3 | 3 call sites | y | y | y |  |
| act_ice_melted_by_four_players | spawnMeltEmitter | `{ if (mEmitter230 == NULL) { mEmitter230 = spawnEmitter_8013CC50(field` | 5 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_ice_wall | startMelting | `{ deleteEmitter(&mEmitter100); deleteEmitter(&mEmitter104); s32 layer ` | 15 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_ice_wall | hitByFire | `{ JGeometry::TBox2f box; JGeometry::TVec2f hitPos; box.set(mBox); box.` | 14 | 1 | 0 | 3 | pool only | - | - | - |  |
| act_ice_wall | hitByWeapon | `{ JGeometry::TBox2f box; JGeometry::TVec3f stack40; JGeometry::TVec2f ` | 30 | 1 | 0 | 3 | pool only | - | - | - |  |
| act_icicle | fall | `{ field_0x23c += 0.1f; mPos.y = mSpawnPos.y + 0.5f * (9.8f * square(fi` | 4 | 1 | 5 | 5 | pool only | - | - | - |  |
| act_maiden_demo | moveToGoal | `{ field_0x248 += 0.04f; moveToward_801CD950(&field_0x24c, 2.0f, 0.05f); s16 an` | 15 | 1 | 2 | 4 | pool only | - | - | - |  |
| act_maiden_demo | shrinkCrystal | `{ moveToward_801CD950(&field_0x250, 0.0f, -0.02f); }` | 3 | 1 | 4 | 4 | one statement | - | y | - |  |
| act_old_man | updateFacing | `{ if (field_0x24c != 0) { field_0x24c--; return; } field_0x24c = 20; J` | 25 | 3 | 3 | 3 | 3 call sites; same name in tu_8034AA40, act_special_conversation_npc | y | y | y |  |
| act_princess_zelda | stepSpeed | `{ if (dist >= 32.0f) { moveToward_801CD950(&field_0x334, 1.1f, 0.02f); } else ` | 7 | 1 | 3 | 5 | pool only | - | - | - |  |
| act_princess_zelda | approachPlayerSide | `{ switch (field_0x98) { case 0: ppos.x -= 16.0f; break; case 1: ppos.x` | 19 | 1 | 4 | 5 | pool only | - | - | - |  |
| act_princess_zelda | followPlayerSide | `{ switch (field_0x98) { case 0: ppos.x -= 16.0f; break; case 1: ppos.x` | 25 | 1 | 4 | 5 | pool only | - | - | - |  |
| act_princess_zelda | spawnEffect33A | `{ JGeometry::TVec3f pos = mPos; pos.y += -24.0f; spawnEmitter_8013CC50` | 5 | 2 | 4 | 5 | 2 call sites | y | y | y |  |
| act_princess_zelda | resetAnimFrame | `{ mSpriteAnim.setFrame_801D1F14(0.0f); }` | 3 | 5 | 5 | 5 | 5 call sites; one statement | y | y | y |  |
| act_princess_zelda_demo | faceDir | `{ if (dir >= 0) { field_0x98 = dir; if (dir + 6 != mAnim0.mAnim) { mAn` | 9 | 2 | 0 | 5 | 2 call sites | y | y | y |  |
| act_princess_zelda_demo | flashAtFeet | `{ JGeometry::TVec3f pos = mPos; pos.y += -16.0f; spawnEmitter_8013CC50` | 6 | 2 | 3 | 5 | 2 call sites | y | y | y | rejected |
| act_princess_zelda_demo | setCenter | `{ pos.x = box.f.x + 0.5f * (box.i.x - box.f.x); pos.y = box.f.y + 0.5f` | 5 | 1 | 3 | 5 | same body in act_four_sword_demo, act_blizzard_battle | - | - | y |  |
| act_princess_zelda_demo | standBelow | `{ JGeometry::TVec3f pos = target; pos.y -= 16.0f; mPos.set(pos); }` | 5 | 1 | 3 | 5 | pool only | - | - | - | rejected |
| act_princess_zelda_demo | flyToGoal | `{ field_0x268 += 0.04f; moveToward_801CD950(&field_0x26c, 2.0f, 0.05f); s16 an` | 24 | 1 | 4 | 5 | pool only | - | - | - | rejected |
| act_princess_zelda_demo | shrinkAway | `{ moveToward_801CD950(&field_0x270, 0.0f, -0.02f); }` | 3 | 1 | 4 | 5 | one statement | - | y | - | rejected |
| act_princess_zelda_demo | showSceneMessage | `{ fn_8038BD08(0, lbl_8053C548[field_0x234], field_0x4, JGeometry::TVec` | 3 | 1 | 2 | 5 | one statement | - | y | - | rejected |
| act_princess_zelda_demo | lowerPlayers | `{ f32 dz = 2.0f - 0.2f * (fn_8011921C()->field_0x8 - lbl_80464550[33])` | 13 | 1 | 5 | 5 | pool only | - | - | - | rejected |
| act_princess_zelda_demo | sinkToPlayer | `{ mAnim0.mFrameCtrl.setRate(1.0f); if (moveToward_801CD950(&mPos.y, getPlayerP` | 8 | 1 | 6 | 5 | pool only | - | - | - | rejected |
| act_rainbow_bridge | checkActivate | `{ if (isScreenFlagSet_0x34()) { field_0x238 = 1; // The original stores the stat` | 35 | 2 | 0 | 1 | 2 call sites | y | y | y | accepted |
| act_rainbow_bridge | isPlayerOn | `{ if (player < 0) { return false; } if (field_0x4 != getPlayerLayer_80` | 26 | 1 | 1 | 1 | same name in act_extending_lift | - | - | y | accepted |
| act_room_transfer_lift | isInside | `{ s32 layer = field_0x4; s32 playerLayer = getPlayerLayer_8023DE58(pla` | 14 | 1 | 1 | 1 | pool only | - | - | - | accepted |
| act_rope | walk | `{ field_0x250 = randInt_801CD664(0x29) + 0x3c; mTargetSpeed = 0.4f; if (mSt` | 9 | 3 | 0 | 0 | 3 call sites | y | y | y |  |
| act_score | updateState1 | `{ if (mTimer >= 0x50) { s32 d = 90 - mTimer; field_0x3c.y = -3.0f * (1` | 10 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_score | updateState2 | `{ field_0x3c.x = 0.2f * JMath::sincosTable_.sinShort((mTimer % 60) << ` | 7 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_score | putScoreDigit | `{ Vec v; v.x = x; v.y = self->mPos.y; v.z = self->mPos.z; if (self->fi` | 10 | 8 | 2 | 3 | 8 call sites | y | y | y |  |
| act_seesaw_lift | spawnSandEmitters | `{ spawnEmitter_8013CC50(field_0x4, &mPos, 0x3DE, 0, 0, NULL, NULL, tru` | 6 | 2 | 5 | 6 | 2 call sites | y | y | y |  |
| act_seesaw_lift | isPlayerInside | `{ JGeometry::TVec3f rel = *getPlayerPos_8023E724(player); JGeometry::T` | 9 | 1 | 5 | 6 | pool only | - | - | - |  |
| act_seesaw_lift | fillTiles | `{ JGeometry::TVec3f p; JGeometry::TVec3f base; p = mPos + JGeometry::T` | 15 | 9 | 6 | 6 | 9 call sites; same name in act_trick_floor_2 | y | y | y |  |
| act_shadow_link_demo | spawnFlash | `{ JGeometry::TVec3f pos(mPos); pos.y += -8.0f; spawnEmitter_8013CC50(f` | 5 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_shadow_link_demo | hopDown | `{ s32 t = fn_8011921C()->field_0x8 - lbl_80464AF8[9]; field_0x3c.z = 4` | 8 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_shovel_old_timer | findDigSpot | `{ JGeometry::TBox2f box = field_0x230; box.i.x += 64.0f; box.i.y += 32` | 31 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_small_key | fallOnTile | `{ if (tile == 3) { if (fn_801EE24C() == true) { field_0x240 = 4; retur` | 22 | 3 | 0 | 1 | 3 call sites | y | y | y |  |
| act_small_key | dropAtPlayer | `{ if (!field_0x2b0) { return true; } mPos.z = 400.0f; if (!isPlayerActive_8023F264` | 37 | 1 | 0 | 1 | pool only | - | - | - |  |
| act_small_key | bounceOffTile | `{ JGeometry::TVec3f checkPos; checkPos.x = mPos.x + 6.0f; checkPos.y =` | 19 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_snow_wall | shrink | `{ mDrawEnabled = false; bool done; if (field_0x238 >= 0.5f && fn_801CD` | 16 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_snow_wall | melt | `{ if (field_0x234 == 0) { JGeometry::TVec3f pos = mPos; pos.y += 16.0f` | 19 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_snowball | chase | `{ u16 angle = 0; s32 dir = 0; s32 player = 0; f32 dist = 0.0f; fn_801E` | 26 | 1 | 2 | 3 | pool only | - | - | - |  |
| act_snowball | followRail | `{ u16 angle = 0; JGeometry::TVec3f outStep(0.0f, 0.0f, 0.0f); s32 laye` | 13 | 1 | 0 | 3 | pool only | - | - | - |  |
| act_snowball | grow | `{ field_0x260 += (0.002f * field_0x264) / 1.6f; if (field_0x260 >= 2.0` | 19 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_snowball | fallStep | `{ moveToward_801CD950(&field_0x3c.z, -10.0f, -0.15f); mPos += field_0x3c; bool` | 13 | 3 | 3 | 3 | 3 call sites; same name in player_8028FBA0 | y | y | y |  |
| act_snowball | dropRupee | `{ s32 kind = 0; if (field_0x270 >= 2.0f) { kind = 2; } else if (field_` | 15 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_snowball | spawnBurst | `{ JGeometry::TVec3f pos = mPos; pos.y -= 16.0f * field_0x260; spawnEmi` | 7 | 1 | 3 | 3 | same name in act_unknown_lnbm_801BEDBC | - | - | y |  |
| act_snowball | updateTrailEmitter | `{ if (field_0x4 == 0) { if (field_0x374 == NULL) { field_0x374 = spawn` | 16 | 3 | 2 | 3 | 3 call sites | y | y | y |  |
| act_snowball | advance | `{ field_0x3c.x = field_0x264 * JMath::sincosTable_.sinShort(field_0x23` | 6 | 2 | 3 | 3 | 2 call sites | y | y | y |  |
| act_somaria_block | holdPlayers | `{ for (s32 i = 0; i < 4; i++) { if (field_0x246[i] == 1) { if (!fn_802` | 11 | 2 | 2 | 2 | 2 call sites | y | y | y |  |
| act_somaria_block | checkGround | `{ JGeometry::TBox2f box = field_0x80; box.addPos(mPos.x, mPos.y); JGeo` | 17 | 3 | 2 | 2 | 3 call sites | y | y | y |  |
| act_strange_block | blockedAtFullReach | `{ JGeometry::TVec3f saved = field_0x3c; if (field_0x260 == 2 && reach ` | 10 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_thwomp_launch_npc | launch | `{ field_0x3c = JGeometry::TVec3f((field_0x278.x - mPos.x) / 40.0f, (fi` | 5 | 2 | 1 | 1 | 2 call sites; same name in act_thwomp_launch_npc_2 | y | y | y |  |
| act_thwomp_launch_npc_2 | launch | `{ field_0x3c = JGeometry::TVec3f( (field_0x278.x - mPos.x) / 40.0f, (f` | 8 | 2 | 0 | 1 | 2 call sites; same name in act_thwomp_launch_npc | y | y | y |  |
| act_thwomp_launch_npc_2 | addRandomDelay | `{ field_0x234 += (s32)(3.0f * gGameRoot_8053AAF8->mRandom.get_ufloat_1` | 3 | 1 | 1 | 1 | one statement | - | y | - |  |
| act_tingle_first | selectNearestPlayer | `{ s32 count = gGameRoot_8053AAF8->getPlayerCount_80138A30(); s32 bestPlayer = 0; f` | 23 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_vaati_demo | updateBobbing | `{ static s16 lbl_8053AA88 = 0; mPos.z = 4.0f * JMath::sincosTable_.sin` | 11 | 2 | 1 | 1 | 2 call sites | y | y | y |  |
| act_vaati_demo | updateDescent | `{ if (mSpawnPos.y - mPos.y <= 24.0f) { moveToward_801CD950(&field_0x3c.y, 0.4f` | 10 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_vaati_time_up | steer | `{ if (field_0x2c4 <= 0 \|\| (field_0x2c0 <= 0 && mPos.x >= field_0x290` | 12 | 1 | 1 | 1 | same name in tu_80334318 | - | - | y |  |
| act_vaati_time_up | pickTarget | `{ if (field_0x2c0 <= 0) { field_0x290 = mViewBox.i.x - 192.0f; field_0` | 10 | 1 | 1 | 1 | same name in act_vaati_boss | - | - | y |  |
| act_warp | updateSandHole | `{ for (s32 i = 0; i < 4; i++) { if (fn_802373EC(i) == 1 && fn_8023A51C` | 18 | 1 | 1 | 1 | pool only | - | - | - |  |
| act_warp_cannon | findPlayer | `{ JGeometry::TBox2f probe = mBox; f32 dy = mPos.y - mPos.z; probe.i.x ` | 15 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | allPlayersIn | `{ for (s32 p = 0; p < 4; p++) { if (!fn_80230188(p)) { return false; }` | 8 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | movePlayers | `{ moveToward_801CD950(&field_0x27c, -10.0f, -0.2f); for (s32 p = 0; p < 4; p++` | 8 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | flyPlayers | `{ moveToward_801CD950(&field_0x27c, -10.0f, -0.002f); for (s32 p = 0; p < 4; p` | 8 | 2 | 0 | 2 | 2 call sites | y | y | y |  |
| act_warp_cannon | resetIfAllPlayersReady | `{ for (s32 i = 0; i < 4; i++) { if (!fn_80230360(i)) { return; } } fie` | 8 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | liftPlayers | `{ for (s32 i = 0; i < 4; i++) { JGeometry::TVec3f pos = *getPlayerPos_` | 7 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | landPlayers | `{ bool all = false; moveToward_801CD950(&field_0x27c, -10.0f, -0.2f); for (s32` | 12 | 1 | 0 | 2 | pool only | - | - | - |  |
| act_warp_cannon | recoil | `{ field_0x280 += 0.05f; JGeometry::TVec3f step(0.0f, 2.0f * (0.5f - fi` | 13 | 1 | 1 | 2 | pool only | - | - | - |  |
| act_warp_cannon | fireRecoil | `{ static s32 counter = 0; static f32 phase = 0.0f; phase += 0.1f; if (` | 26 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_zora_escort | hasNearbyBari | `{ if (getEscortActorList_80131F0C()->mCount <= 1) { return false; } f32 distSq = 300.0` | 21 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_zora_escort | findNearbyPlayer | `{ if (field_0x33c != 0) { return -1; } u16 angle = 0; s32 dir = 0; s32` | 17 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_zora_escort | stepToPlayer | `{ JGeometry::TVec3f targetPos = *getPlayerPos_8023E724(field_0x3cc); t` | 24 | 1 | 0 | 0 | pool only | - | - | - |  |
| act_zora_escort_goal | startTalk | `{ JGeometry::TBox2f box(mBox); box.i.x += mPos.x; box.i.y += mPos.y; b` | 21 | 2 | 2 | 4 | 2 call sites; same name in act_princess_zelda_demo | y | y | y |  |
| act_zora_escort_goal | walkRail | `{ bool flag; if (field_0x238 <= 0) { flag = true; } else { JGeometry::` | 25 | 1 | 2 | 4 | pool only | - | - | - |  |
| act_zora_escort_goal | hover | `{ JGeometry::TVec3f pos(0.0f, 0.0f, 0.0f); field_0x248 += 600; if (fie` | 15 | 2 | 2 | 4 | 2 call sites | y | y | y |  |
| act_zora_escort_goal | spawnEmitters | `{ JGeometry::TVec3f pos(mPos); pos.x += 8.0f; field_0x37c = spawnEmitt` | 6 | 1 | 4 | 4 | same name in act_tower_appearance_demo_8012A5EC, act_link_ending | - | - | y |  |
| act_stone_arrghus_800F7FCC | randomSlotTime | `{ return 400.0f + (f32)(s32)(100.0f * gGameRoot_8053AAF8->mRandom.get_` | 3 | 2 | 2 | 9 | 2 call sites; one statement | y | y | y |  |
| act_stone_arrghus_800F7FCC | headingOf | `{ return (s32)(JMath::atanTable_.atan2_(x, y) * 10430.378f); }` | 3 | 3 | 9 | 9 | 3 call sites; one statement | y | y | y |  |
| act_whack_a_mole_shop_8010089C | showTimer | `{ s32 timer = field_0x23c; lbl_8053AF18->field_0x30 = timer / 60; lbl_` | 10 | 1 | 2 | 4 | pool only | - | - | - | rejected |
| act_whack_a_mole_shop_8010089C | spawnSmoke | `{ spawnEmitter_8013CC50(field_0x4, &mPos, 0x1DA, 0, 1, NULL, NULL, tru` | 3 | 3 | 3 | 4 | 3 call sites; one statement | y | y | y | rejected |
| act_crystal_cutscene_80113788 | spawnEmitters | `{ JGeometry::TVec3f pos[5] = { mPos, JGeometry::TVec3f(mSpawnPos.x - 8` | 12 | 1 | 2 | 2 | same name in act_zora_escort_goal, act_tower_appearance_demo_8012A5EC | - | - | y |  |
| act_crystal_cutscene_80113788 | spawnSealEmitters | `{ for (s32 i = 0; i < 7; i++) { field_0x2a8[i] = spawnEmitter_8013CC50` | 7 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_crystal_cutscene_80113788 | spawnBurstEmitters | `{ spawnEmitter_8013CC50(field_0x4, &mPos, 0x20, 0, 0, NULL, NULL, true` | 4 | 1 | 1 | 2 | pool only | - | - | - |  |
| act_crystal_cutscene_80113788 | positionPlayers | `{ JGeometry::TVec3f pos = mSpawnPos; pos.y += 48.0f; pos.x -= 36.0f; f` | 12 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_crystal_cutscene_80113788 | updateCameraFocus | `{ switch (field_0x23c) { case 0: case 1: case 10: case 17: break; case` | 44 | 1 | 2 | 2 | pool only | - | - | - |  |
| act_crystal_cutscene_80113788 | spawnCrystal | `{ JGeometry::TVec3f spawnPos = mSpawnPos; spawnPos.z = 20.0f; getActor` | 5 | 2 | 2 | 2 | 2 call sites | y | y | y |  |
| tu_80118384 | spawnFadeEmitters | `{ JGeometry::TVec3f pos(0.0f, 0.0f, 0.0f); spawnEmitter_8013CC50(0, &p` | 7 | 1 | 3 | 3 | pool only | - | - | - |  |
| act_after_goal_opening_8011CEC8 | setOverlayRect | `{ Camera_804AA9E4* cam = gGameRoot2_8053AB10->field_0x24; Vec out; Vec` | 21 | 1 | 1 | 2 | pool only | - | - | - |  |
| act_after_goal_opening_8011CEC8 | startScroll | `{ field_0x23c = 0.0f; field_0x238 = 0.0f; field_0x230 = 0; s32 dir[2];` | 9 | 1 | 2 | 2 | pool only | - | - | - |  |
| escort_base_801213EC | angleOf | `{ return (s32)(JMath::atanTable_.atan2_(x, y) * (32768.0f / JMath::TAn` | 3 | 3 | 8 | 20 | 3 call sites; one statement; same name in act_big_poe_2_8018A8D8 | y | y | y |  |
| escort_base_801213EC | spawnLifeMeters | `{ s32 serial; if (field_0x332) { JGeometry::TVec3f pos(mPos); pos.x -=` | 19 | 2 | 0 | 20 | 2 call sites | y | y | y |  |
| escort_base_801213EC | respawnLifeMeters | `{ if (field_0x332) { for (s32 i = 0; i < field_0x360; i++) { if (field` | 9 | 1 | 0 | 20 | pool only | - | - | - |  |
| escort_base_801213EC | spawnLifeMeter | `{ if (field_0x332 && index < field_0x360 && index >= 0) { JGeometry::T` | 14 | 1 | 0 | 20 | pool only | - | - | - |  |
| escort_base_801213EC | lifeMeterSpacing | `{ return 8.0f; }` | 3 | 1 | 19 | 20 | one statement | - | y | - | accepted |
| act_escorted_woman_arrival_point_80125B58 | talkTo | `{ JGeometry::TVec3f pos(mPos); pos.y -= 64.0f; return openMessage_8038AD24(play` | 5 | 1 | 2 | 4 | same name in act_great_fairy_spfr | - | - | y |  |
| act_escorted_woman_arrival_point_80125B58 | startSignAnim | `{ switch (field_0x238) { case 1: mAnim27c.startAnim_801D22DC(0, 0, fal` | 12 | 1 | 4 | 4 | pool only | - | - | - |  |
| act_navi_after_crystal_cutscene_8013394C | spawnEmitters | `{ if (mEmitters[0] == NULL) { mEmitters[0] = spawnEmitter_8013CC50(fie` | 8 | 1 | 1 | 1 | same name in act_zora_escort_goal, act_tower_appearance_demo_8012A5EC | - | - | y |  |
| effect_system_8013C5C8 | addTrackedEmitter | `{ static cls_8049F15C callback; JPABaseEmitter*& emitter = mEmitters[m` | 10 | 25 | 1 | 6 | 25 call sites | y | y | y |  |
| effect_system_8013C5C8 | set2DDrawInfo | `{ JPADrawInfo unused; PSMTXCopy(gGameRoot2_8053AB10->field_0x10->mPosM` | 7 | 3 | 5 | 6 | 3 call sites | y | y | y |  |
| tu_8015F454 | drawLetterbox | `{ J2DFillBox(0.0f, 0.0f, (f32)(s32)JUTVideo::sManager->getFbWidth(), b` | 5 | 1 | 2 | 2 | pool only | - | - | - | rejected |
| game_root_sub_24_8016A2B4 | getMapTexView | `{ Camera_804AA9E4* camera = gGameRoot2_8053AB10->field_0x24; TileMap_8` | 14 | 12 | 19 | 19 | 12 call sites | y | y | y | accepted |
| act_big_poe_2_8018A8D8 | angleOf | `{ return JMath::atanTable_.atan2_(x, y) * 10430.378f; }` | 3 | 1 | 1 | 1 | one statement; same name in escort_base_801213EC | - | y | y |  |
| act_big_moldorm_tail_8018EB94 | setHeading | `{ s16 angle = (s32)(4000.0f * (f32)field_0x98); field_0x27c.x = field_` | 13 | 1 | 0 | 0 | pool only | - | - | - |  |
| tu_801CB270 | tileCenter | `{ return 8.0f + (u32)((s32)v & ~0xF); }` | 3 | 4 | 5 | 5 | 4 call sites; one statement; same name in player_80285E58 | y | y | y |  |
| player_8027E5BC | followStep | `{ if (fn_802486A0() == 5 && field_0xbf0->field_0xb4) { moveByStick_802808E8(1.5` | 26 | 1 | 18 | 18 | pool only | - | - | - |  |
| tu_802E9428 | updateCamera | `{ JGeometry::TVec2f pos(field_0x250.x, field_0x250.y); JGeometry::TVec` | 20 | 4 | 0 | 1 | 4 call sites | y | y | y |  |
| tu_802E9428 | stepZoom | `{ if (field_0x270 != field_0x274) { field_0x270 += field_0x278; if (fi` | 12 | 1 | 1 | 1 | pool only | - | - | - |  |
| tu_8030C058 | setScreenRectViewport | `{ u32 w = field_0x144.f.x - field_0x144.i.x; u32 h = field_0x144.f.y -` | 7 | 1 | 5 | 5 | pool only | - | - | - |  |
| tu_8034AA40 | updateFacing | `{ JGeometry::TVec3f dir; f32 dist; getNearestPlayerDir_801EE558(&dir, &dist, 0); if (di` | 22 | 2 | 1 | 3 | 2 call sites; same name in act_special_conversation_npc, act_tingle_tower | y | y | y |  |
| tu_8034AA40 | markRandomCucco | `{ f32 roll = gGameRoot_8053AAF8->mRandom.get_ufloat_1(); Cucco_804AB8C` | 8 | 1 | 3 | 3 | pool only | - | - | - |  |
| tu_80362634 | faceOwl | `{ if (PSVECDistance(&mPos, &owl->mPos) >= 80.0f) { field_0x23c = 0; } ` | 17 | 2 | 5 | 12 | 2 call sites | y | y | y |  |
| tu_80362634 | chaseOwl | `{ if (PSVECDistance(&mPos, &actor->mPos) < 100.0f) { field_0x24c = i; ` | 25 | 2 | 7 | 12 | 2 call sites | y | y | y |  |
| tu_80362634 | isBlocked | `{ if (mPos.x < 2600.0f \|\| mPos.x > 3016.0f) { return true; } if (mPo` | 23 | 2 | 10 | 12 | 2 call sites | y | y | y |  |
| tu_80362634 | spawnRoomEmitters | `{ // the centre of the room (512 x 384) the actor is in JGeometry::TVe` | 8 | 1 | 12 | 12 | pool only | - | - | - |  |
| tu_8036FB60 | guidePlayer_80370764 | `{ JGeometry::TVec3f d = JGeometry::TVec3f(2232.0f, 1624.0f, 0.0f) - *g` | 6 | 1 | 6 | 7 | pool only | - | - | - |  |
| tu_8036FB60 | tickPlayer_80371284 | `{ for (s32 i = 0; i < 4; i++) { if (field_0x374[i] != 0) { field_0x374` | 25 | 2 | 7 | 7 | 2 call sites | y | y | y |  |
| tu_80376FA0 | rewriteTiles | `{ f32 x = mPos.x; x -= 24.0f; f32 y = mPos.y; f32 z = mPos.z; // The i` | 22 | 1 | 1 | 1 | pool only | - | - | - |  |
| tu_80376FA0 | touchesPlayer | `{ s32 layer = field_0x4; s32 playerLayer = getPlayerLayer_8023DE58(pla` | 23 | 1 | 1 | 1 | pool only | - | - | - |  |
| tu_80376FA0 | setBoxes | `{ mBox.i.x = -31.5f; mBox.i.y = -31.5f; mBox.f.x = 31.5f; mBox.f.y = 3` | 10 | 1 | 1 | 1 | pool only | - | - | - |  |
| tu_80376FA0 | spawnBreakEmitters | `{ if (mEmitter230 == NULL) { mEmitter230 = spawnEmitter_8013CC50(field` | 22 | 1 | 1 | 1 | pool only | - | - | - |  |
| tu_803944C8 | drawTextPicture | `{ self->field_0x30[self->field_0x68[i]->field_0x8]->draw(px, py, 29.0f` | 3 | 1 | 7 | 7 | one statement | - | y | - | accepted |
| tu_803A60E4 | moveCursorToRow | `{ for (s32 i = 0; i < 6; i++) { field_0xc[i]->moveFromCentre_80402E08(` | 9 | 2 | 2 | 2 | 2 call sites | y | y | y |  |
| tu_803A8DFC | setHeaderAlpha | `{ if (field_0x450 < 2) { for (int i = 0; i < 13; i++) { field_0x10[fie` | 7 | 3 | 0 | 19 | 3 call sites | y | y | y |  |
| tu_803A8DFC | setScoreRowAlpha | `{ if (field_0x450 < 2) { for (int j = 0; j < 3; j++) { field_0x10[fiel` | 7 | 3 | 0 | 19 | 3 call sites | y | y | y |  |
| tu_803A8DFC | setRankRowAlpha | `{ if (field_0x450 < 2) { for (int j = 0; j < 2; j++) { field_0x10[fiel` | 7 | 5 | 0 | 19 | 5 call sites | y | y | y |  |
| tu_803B7DCC | setFrameBufferOrtho | `{ JGeometry::TBox2f box(0.0f, 0.0f, (s32)JUTVideo::getManager()->getFb` | 5 | 1 | 2 | 2 | pool only | - | - | - |  |
| tu_803BC6F0 | getProgressMsg | `{ int cleared = 0; for (int stage = 0; stage < 8; stage++) { if (fn_80` | 11 | 3 | 0 | 24 | 3 call sites | y | y | y |  |
| tu_803BC6F0 | setFadeStep | `{ f32 t = (f32)(self->field_0xde * self->field_0xde) / (f32)(frames * ` | 5 | 2 | 24 | 24 | 2 call sites | y | y | y |  |
| tu_803E1668 | drawFade | `{ if (field_0x26e != 0) { switch (field_0x26e) { case 1: if (field_0x2` | 30 | 1 | 11 | 11 | same name in tu_803F0A54 | - | - | y |  |
| tu_803E1668 | enterState15 | `{ field_0x1d8 = field_0x1d4; field_0x1d4 = 15; if (field_0x1bc == 2 &&` | 21 | 2 | 11 | 11 | 2 call sites | y | y | y |  |
| tu_803F0A54 | drawFade | `{ if (field_0x25e != 0) { switch (field_0x25e) { case 1: if (field_0x2` | 26 | 1 | 11 | 11 | same name in tu_803E1668 | - | - | y |  |
| tu_803F0A54 | enterState13 | `{ field_0x1c8 = field_0x1c4; field_0x1c4 = 13; field_0x350 = 6; lbl_80` | 13 | 4 | 11 | 11 | 4 call sites | y | y | y |  |
| tu_80403D84 | hideSubStagePanes | `{ if (field_0x65e == 1) { field_0x120[0]->field_0x22 = 0; field_0x120[` | 8 | 13 | 0 | 20 | 13 call sites | y | y | y |  |
| tu_80403D84 | hideStagePanes | `{ switch (stage) { case 1: field_0xc->search('P21')->hide(); field_0xc` | 34 | 4 | 0 | 20 | 4 call sites | y | y | y |  |
| tu_80403D84 | slidePane | `{ f32 t = (f32)(frame * frame) / (f32)(frames * frames); field_0x2b4->` | 5 | 2 | 20 | 20 | 2 call sites | y | y | y |  |
| tu_8042165C | updateGaugeBar | `{ if (val >= 0x60) { field_0x4->search(lbl_8048E300[player][bar])->res` | 9 | 1 | 1 | 2 | pool only | - | - | - |  |
| tu_8042165C | calcHudPos | `{ f32 px = sx * (screen.x / JFWDisplay::getManager()->getEfbWidth()); ` | 6 | 2 | 2 | 2 | 2 call sites | y | y | y |  |
| tu_8042E964 | scaleFrames | `{ f32 sx0 = (w + (field_0x24[0]->field_0x18 - field_0x24[4]->field_0x1` | 21 | 1 | 2 | 2 | pool only | - | - | - |  |
| tu_80443B0C | resetCursorTimer | `{ field_0x48 = (s32)(11.0f * gGameRoot_8053AAF8->mRandom.get_ufloat_1(` | 3 | 3 | 5 | 5 | 3 call sites; one statement | y | y | y |  |

## 3. Candidate rules

Each rule applies on top of the conditions every helper must already meet:

- the unit's function order is verified;
- `pool.py` shows an "order only" run at that position;
- every caller inlines the helper (no new `bl`);
- the helper carries the "dropped" comment.

Net effect was measured by compiling each unit with the failing helpers made
`inline` and counting the functions that leave 100 % (no function gained in
any variant).

| rule | test | helpers kept / dropped | net functions |
|---|---|---|---:|
| R0 status quo | the pool needs it | 168 / 0 | 0 |
| R1 repeated body | inlined at **2 or more call sites** (the same code appears 2+ times in the original asm, so the copies fix its boundaries) | 57 / 111 | **-199** |
| R2 bounded body | R1, **or** a one-statement body (the run's literals sit in one statement, so the body is the smallest possible and there is no boundary left to choose) | 68 / 100 | **-171** |
| R3 repeat or cross-unit | R1, or the same helper name exists in another unit (mostly as an `inline` there; only `setCenter` has an identical body, in 3 other units) | 73 / 95 | -171 |
| (reference) only helpers that pay | individual A/B > 0 | 129 / 39 | -37 |
| (reference) none | every helper inline | 0 / 168 | -321 |

Agreement with the past verdicts (7 accepted, 11 rejected, 18 in all):

- R1 agrees on 11 of 18. It rejects the accepted lifeMeterSpacing,
  drawTextPicture, isPlayerOn, isInside and checkAllPulled. It allows the
  rejected flashAtFeet and spawnSmoke (3 sites).
- R2 agrees on 10 of 18.
- No size, site or shape rule reproduces the review. Examples:
  - lifeMeterSpacing (`return 8.0f;`, 1 site) was accepted, while
    duckedBgmVolume (`return 0.7f;`) and isAirborne (one comparison, 1 site)
    were rejected.
  - spawnSmoke, with 3 identical inlined copies, was rejected as having "no
    trace in the asm".

  The verdicts came from case-by-case taste, which is the inconsistency a
  rule should remove.

## Recommendation

Adopt **R2 (bounded body)**, with a naming rule:

- **Existence** counts as proven by the pool (section 1). Callers inlining
  the helper and "ours only" are expected, not objections.
- **Body**: it must be pinned. Either it is inlined at 2 or more sites (the
  copies fix its extent), or it is the single statement holding the run's
  literals. A single-site helper with more than one statement is code split
  where the pool needs it. It is not allowed, or it goes in as
  `FAKEMATCH(crack-pass)` in docs/CRACK_PASS.md if the owner wants to keep
  the function count.
- **Name**: it must be provisional unless some evidence beyond the pool
  supports it. The helper has no address, so name it after its first
  `.sdata2` literal (e.g. `pool_8053C2C0`) or after its caller and a counter.
  A descriptive name needs the usual name evidence.

Net effect: 68 helpers stay and 100 are reverted (or tagged as crack-pass).
**-171 functions at 100 %** against the status quo; tagging them keeps the
count but marks them. R1 is stricter (-199) and drops the clean
one-statement cases that the pool fully determines. R3's cross-unit leg rests
on names agents invented, so it is not evidence. Its one solid case is
`setCenter` (act_princess_zelda_demo), whose body is identical in 3 other
units. That is worth adding to R2 as a third leg: "the same body exists in
another unit".

## Decision 2026-11-22: R2 + tags

The owner chose **R2** with the third leg added: a helper stays when it is inlined at
2+ call sites, has a one-statement body, or has a body identical to one in another
unit (only `setCenter`). Helpers that fail R2 stay in the source as tricks:
`// FAKEMATCH(crack-pass):` on the definition and a row in docs/CRACK_PASS.md
("Pool helpers that fail rule R2"), which keeps their units NonMatching. The rule is
in docs/RULES_CARD.md "Pool helpers (R2)".

Applied on branch pool-r2 (from grind2 524d2fd3f):

- **69 pass** and are renamed `pool_<address of the first literal they create>`
  (the target `.sdata2` symbol at that pool index, checked equal in value and in the
  pool prefix up to it). Ten create no literal of their own (their bodies are pinned by
  their call sites, and they reuse literals other code creates): `inl_<address of an
  inlining caller>`, `_1`/`_2` when two share a caller. None had name evidence beyond
  the agents' descriptions, so none kept a descriptive name; each comment names the R2
  clause and the old name.
- **99 fail** and are tagged. All sit in NonMatching units, so the "pending owner:
  Matching units" list is empty and no unit changed status.
- Net: no function changes (renames and comments only); `ninja` SHA-1 OK,
  `names_compare.py` 10,346 -> 10,346 at 100 %, `gate.py --all-units` ok.

### Kept (R2 passes)

| unit | old name | new name | R2 clause |
|---|---|---|---|
| act_cannon | spawnTakenEffect | `pool_8053C2F4` | one statement |
| act_cannon | swing | `pool_8053C2F8` | 2 sites |
| act_cannon | readSwingRange | `pool_8053C300` | one statement |
| act_cloud | isAirborne | `pool_8053C228` | one statement |
| act_eyeball_switch | open | `pool_80542F20` | 2 sites |
| act_force_gem | stopMoving | `pool_80541D88` | 7 sites |
| act_force_like | spawnKindEmitter | `pool_8053BF30` | 2 sites; one statement |
| act_hyrule_castle_barrier | getEndPos2 | `inl_8011EEEC` | 3 sites |
| act_hyrule_castle_barrier | getEndPos1 | `pool_8053C8F8` | 3 sites |
| act_hyrule_castle_barrier | getMidPos | `pool_8053C8FC` | one statement |
| act_maiden_demo | shrinkCrystal | `pool_8053C628` | one statement |
| act_old_man | updateFacing | `pool_80543048` | 3 sites |
| act_princess_zelda | resetAnimFrame | `pool_8053C3E0` | 5 sites; one statement |
| act_princess_zelda | spawnEffect33A | `pool_8053C3E4` | 2 sites |
| act_princess_zelda_demo | faceDir | `inl_8011093C` | 2 sites |
| act_princess_zelda_demo | showSceneMessage | `pool_8053C570` | one statement |
| act_princess_zelda_demo | shrinkAway | `pool_8053C574` | one statement |
| act_princess_zelda_demo | setCenter | `pool_8053C58C` | same body in act_four_sword_demo, act_blizzard_battle, act_wind_environment |
| act_princess_zelda_demo | flashAtFeet | `pool_8053C590` | 2 sites |
| act_rainbow_bridge | checkActivate | `pool_8053CB48` | 2 sites |
| act_rope | walk | `pool_8053EAF4` | 3 sites |
| act_score | putScoreDigit | `pool_80543188` | 8 sites |
| act_seesaw_lift | fillTiles | `pool_8054286C` | 9 sites |
| act_seesaw_lift | spawnSandEmitters | `pool_80542878` | 2 sites |
| act_small_key | fallOnTile | `inl_802C2C30` | 3 sites |
| act_snowball | advance | `pool_8053C490` | 2 sites |
| act_snowball | updateTrailEmitter | `pool_8053C494` | 3 sites |
| act_snowball | fallStep | `pool_8053C4AC` | 3 sites |
| act_somaria_block | checkGround | `pool_80541738` | 3 sites |
| act_somaria_block | holdPlayers | `pool_80541740` | 2 sites |
| act_thwomp_launch_npc | launch | `pool_80542068` | 2 sites |
| act_thwomp_launch_npc_2 | addRandomDelay | `pool_805427E0` | one statement |
| act_thwomp_launch_npc_2 | launch | `pool_805427F0` | 2 sites |
| act_vaati_demo | updateBobbing | `pool_8053C724` | 2 sites |
| act_warp_cannon | flyPlayers | `pool_8053CCD0` | 2 sites |
| act_zora_escort_goal | hover | `pool_8053CAA8` | 2 sites |
| act_zora_escort_goal | startTalk | `pool_8053CAB4` | 2 sites |
| act_stone_arrghus_800F7FCC | headingOf | `pool_8053C050` | 3 sites; one statement |
| act_stone_arrghus_800F7FCC | randomSlotTime | `pool_8053C094` | 2 sites; one statement |
| act_whack_a_mole_shop_8010089C | spawnSmoke | `pool_8053C140` | 3 sites; one statement |
| act_crystal_cutscene_80113788 | spawnCrystal | `pool_8053C678` | 2 sites |
| escort_base_801213EC | spawnLifeMeters | `inl_80121ABC` | 2 sites |
| escort_base_801213EC | lifeMeterSpacing | `pool_8053C9B0` | one statement |
| escort_base_801213EC | angleOf | `pool_8053C9F0` | 3 sites; one statement |
| effect_system_8013C5C8 | addTrackedEmitter | `inl_8013DDEC` | 25 sites |
| effect_system_8013C5C8 | set2DDrawInfo | `pool_8053CE10` | 3 sites |
| game_root_sub_24_8016A2B4 | getMapTexView | `pool_8053D938` | 12 sites |
| act_big_poe_2_8018A8D8 | angleOf | `pool_8053E1B0` | one statement |
| tu_801CB270 | tileCenter | `pool_8053EF98` | 4 sites; one statement |
| tu_802E9428 | updateCamera | `pool_805412F8` | 4 sites |
| tu_8034AA40 | updateFacing | `pool_80542558` | 2 sites |
| tu_80362634 | isBlocked | `pool_80542B20` | 2 sites |
| tu_80362634 | chaseOwl | `pool_80542B4C` | 2 sites |
| tu_80362634 | faceOwl | `pool_80542B58` | 2 sites |
| tu_8036FB60 | tickPlayer_80371284 | `pool_80542DD8` | 2 sites |
| tu_803944C8 | drawTextPicture | `pool_805431D8` | one statement |
| tu_803A60E4 | moveCursorToRow | `pool_80543370` | 2 sites |
| tu_803A8DFC | setHeaderAlpha | `inl_803AA8F8_1` | 3 sites |
| tu_803A8DFC | setScoreRowAlpha | `inl_803AA8F8_2` | 3 sites |
| tu_803A8DFC | setRankRowAlpha | `pool_805433B8` | 5 sites |
| tu_803BC6F0 | getProgressMsg | `inl_803CE4CC` | 3 sites |
| tu_803BC6F0 | setFadeStep | `pool_80543458` | 2 sites |
| tu_803E1668 | enterState15 | `pool_80543680` | 2 sites |
| tu_803F0A54 | enterState13 | `pool_80543748` | 4 sites |
| tu_80403D84 | hideStagePanes | `inl_80404D70` | 4 sites |
| tu_80403D84 | hideSubStagePanes | `inl_80405B10` | 13 sites |
| tu_80403D84 | slidePane | `pool_80543898` | 2 sites |
| tu_8042165C | calcHudPos | `pool_80543A58` | 2 sites |
| tu_80443B0C | resetCursorTimer | `pool_80543D70` | 3 sites; one statement |

### Tagged (R2 fails)

99 helpers in 54 units (count in brackets when more than one); the per-helper list
with the functions each holds is in docs/CRACK_PASS.md: act_block, act_bombchu, act_cannon (4), act_fairy_invincible, act_fish, act_force_gem_winged, act_four_person_pull_switch, act_four_sword_demo (5), act_gambling_shop, act_great_fairy_spfr (3), act_ice_melted_by_four_players, act_ice_wall (3), act_icicle, act_maiden_demo, act_princess_zelda (3), act_princess_zelda_demo (4), act_rainbow_bridge, act_room_transfer_lift, act_score (2), act_seesaw_lift, act_shadow_link_demo (2), act_shovel_old_timer, act_small_key (2), act_snow_wall (2), act_snowball (5), act_strange_block, act_tingle_first, act_vaati_demo, act_vaati_time_up (2), act_warp, act_warp_cannon (8), act_zora_escort (3), act_zora_escort_goal (2), act_whack_a_mole_shop_8010089C, act_crystal_cutscene_80113788 (5), tu_80118384, act_after_goal_opening_8011CEC8 (2), escort_base_801213EC (2), act_escorted_woman_arrival_point_80125B58 (2), act_navi_after_crystal_cutscene_8013394C, tu_8015F454, act_big_moldorm_tail_8018EB94, player_8027E5BC, tu_802E9428, tu_8030C058, tu_8034AA40, tu_80362634, tu_8036FB60, tu_80376FA0 (4), tu_803B7DCC, tu_803E1668, tu_803F0A54, tu_8042165C, tu_8042E964.
