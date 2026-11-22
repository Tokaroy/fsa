# Crack pass

Tricks to revisit at the end; each verified byte-identical with the unit Matching.

Every trick line in the source carries a `FAKEMATCH(crack-pass):` comment. `tools/gate.py`
rejects a Matching unit containing "fakematch", so these units stay NonMatching until the
trick is replaced by an honest fix (or the project decides to accept it).

## JSystem/JAudio/System/JASTrack.cpp (unblocks game/tu_80021840.cpp)

- **Trick:** a dummy function template `JASTrack_orderDummy<T>` at the end of
  `libs/sdk/include/JSystem/JAudio/System/JASTrack.h`, compiled only when
  `JASTRACK_ORDER_DUMMY` is defined (JASTrack.cpp defines it before its first include, so
  no other unit sees it and their `@NNN` labels don't shift), and an unused
  `static void JASTrack_orderDummyUse()` at the end of JASTrack.cpp that calls it. Both are
  unreferenced, so the linker dead-strips them (map: `UNUSED ... JASTrack_orderDummyUse__Fv`,
  `UNUSED ... JASTrack_orderDummy<i>__Fi`).
- **Why:** with `-sym on` MWCC puts weak functions in one `.text` section per defining file,
  ordered by first emission; `__sinit` and implicit dtors join the section of the last thing
  the end-of-TU template pass instantiated. Without the trick that is the memPool_
  definition in JASHeapCtrl.h, so `__sinit` lands after `free`/`__dl` (every `bl` into them
  shifts by 0x18C and the link breaks). A function template from JASTrack.h, instantiated
  after the template statics, moves `__sinit` into JASTrack.h's section right after
  `MoveParam_` ct, which is FSA's order.
- **Honest fix would need:** evidence of how FSA's headers really placed this: e.g. a real
  function template or weak inline in FSA's JASTrack.h that JASTrack.cpp instantiates and an
  earlier-linked unit also emits (searched: no JASTrack.h function exists out of line
  outside JASTrack.o in FSA, no bl from JASTrack to one, nothing in mkdd/TP/SMG JASTrack.h),
  or a different home for the `JASPoolAllocObject_MultiThreaded<T>::memPool_` definition that
  every pool user still sees (see progress/JSystem__JAudio__System__JASTrack.md).
- **Verification (2026-11-03):** JASTrack.cpp Matching: `ninja` + `sha1sum -c
  config/G4SE01/build.sha1` OK (d86b3d9f785566e34264035e140ef3daf3cc19f0). JASTrack.cpp and
  game/tu_80021840.cpp both Matching: OK, same SHA-1; honest report 100 % for both units;
  `tools/gen_game.py --check` clean. Set back to NonMatching with the trick in the source:
  `python3 tools/gate.py --all-units --base origin/matching` prints `gate: ok`.

## game/tu_802684A4.cpp fn_80269574 (`goto` out of unrolled tests)

- **Trick:** `goto` at four places in cls_804A71A8::fn_80269574 and its section inlines, every
  goto line tagged `// FAKEMATCH(crack-pass):` (tools/gate.py lets a goto through only with
  that tag on its line; check_fakematch keeps the unit NonMatching): blockMarked50's
  field_0x50 test (`goto block`), liftOn60's field_0x60 test (`goto lift`), the frames-shut-in
  counter (the `field_0xbc = 3` exits `goto warp`, the reset paths `goto align` past the
  'WARP' search) and the near-'WARP' exit (`goto slowFloor`, past the alignment). Owner
  approval 2026-11-06.
- **Why:** at each site the original's unrolled 8-way test branches from every copy straight
  into a block that the loop's normal exit jumps over with a `b` (`beq X` x8, `b` past X).
  Toy files with the unit's flags reproduce that byte for byte with a goto; every goto-free
  form measured leaves the loop index or a bool (`li n` / `cmpwi n, 8`, `li 1` / `clrlwi.`):
  a post-loop index test, a found flag, a bool or int inline, `i == 7` inside the loop;
  non-canonical loops are not unrolled and a canonical loop whose exit block holds a loop
  or a call stays rolled (docs/PLAYER.md "Structural push (tu_802684A4)"). With the gotos
  fn_80269574 is 98.83 % (was 96.90), missing/extra -4; the rest is in its FIXME.
- **Honest fix would need:** a source form other than goto that MWCC compiles to "every
  unrolled exit jumps into the block, the completion path skips it": e.g. a macro or
  inline idiom from FSA's sources (none in the donors). If a later unit shows the same
  shape with a known source form, apply it here.
- **Verification (2026-11-06):** unit NonMatching; full `ninja` and `sha1sum -c
  config/G4SE01/build.sha1` OK; `tools/gate.py --all-units` and `--base matching` pass.

## Retired 2026-11-05: tu_80222CC4, tu_80221B44 (`defer_codegen`) and act_shadow_link_bow

Game code is now compiled `-inline auto,deferred` project-wide (docs/INLINING.md),
which is what the `#pragma defer_codegen on` + reversed-functions trick reproduced
for these two units. The pragmas and their FAKEMATCH(crack-pass) tags are gone; the
sources keep their (now project-standard) descending order. act_shadow_link_bow's
"second trick" is the evidenced whole-file `#pragma auto_inline off` of pragma rule 2;
its vfunc_0x90 is at 100 %.

## Open questions to revisit once more code is written (2026-11-05)

Not tricks: patterns no honest form explains yet. Revisit after the
surrounding code exists, since finishing the rest of a unit may show the cause.

- **Literals pooled before their first visible use.** PARTLY SOLVED 2026-11-05 (tu_8016A2B4): file-scope static const aggregates, and helpers defined early whose out-of-line copy was dead-stripped (see RULES_CARD "Known game-code shapes"); revisit the other units below with that in mind. tu_8016A2B4 (ten GXColor
  objects then 0.125/1/0.5/0 ahead of drawParallaxModel_8016A7DC's literals), tu_801213EC (8.0f
  before 0.0f, 10430.378f before -24f), tu_803BC6F0 (0, -200, 200 first, used
  only by later functions) and tu_8027E5BC (1.5f, 3.0f). Literals are created per
  function in compile order, and an inline helper's aggregate initializers when
  the inline is first read. Candidates: early inline helpers, dead code the
  optimizer removed, or a deferred/reordered codegen mode. Each unit's
  checkpoint has the pool layout.
- **Inlining of later-defined functions.** ANSWERED 2026-11-05: the original was
  compiled with deferred inlining, now the project mode (docs/INLINING.md). The units
  listed here (tu_803099FC, tu_8043A0E8, tu_80256C74, tu_8016A2B4, tu_802F5040,
  tu_803944C8) can write the callee as a plain function.
- **Weak destructor emitted first.** ANSWERED 2026-11-05 (deferred inlining):
  tu_8045A640 now emits the weak __dt__Q29GameAudio16CustomSoundTableFv first;
  every function, .data and .sdata2 are 100 % (extab 71 %: check the weak-dedup
  trial link before flipping it).
- **Save-data layout.** lbl_8050EC80 (SaveData_804AFB30, game/tu_803B8C74.h) is a 0x20-byte
  header, three 0xC8-byte SaveFile_803B950C at 0x20 and three 0x9C4-byte bodies at 0x280;
  every user reads it through getFile / getCurrentFile. Two functions read and write one field
  of the current file through a pointer the original holds at lbl_8050EC80 + file * 0xC8
  (fields at +0x20): tu_801DE714 __dt__12cls_804A51E4Fv (clamp of 0x2C) and act_fairy init
  (bit 0 of 0x87). Every access through mFiles adds an `addi 0x20` (reference/pointer local,
  pointer accessor, inline SaveFile member, nested table struct: 97.2-98.6 / 95.4-97.4 %) or
  CSEs the field address into an lwzu (direct expressions, 98.36 %).
  - **Trick:** `FAKEMATCH(crack-pass)` SaveFileRow_CrackPass (two fields, row offsets) and
    SaveData_804AFB30::getCurrentRow_CrackPass (`reinterpret_cast<SaveFileRow_CrackPass*>(this)
    [mCurrentFile]`), used only by those two functions: 100 % and 97.86 % (their values
    under the old SaveRow_8050EC80 view).
  - **Honest fix would need:** the original's declaration that gives a 0xC8-stride object
    based at lbl_8050EC80 itself (FSA probably viewed the save data as rows somewhere; no
    donor has this class).
- **Data of dead-stripped functions.** tu_803A3484 (title screen): a 0x34-byte .rodata table and "enemy_both2_sob.bin" sit before
  the title's strings, and 0.5f / 120.0f lead its .sdata2, but no surviving function references them; the table's tail {3,4,5,4}
  matches tu_803536C4's lbl_80472260, also followed by that string. Likely a function the linker dropped (dead code or a weak
  duplicate). Keeps fn_803A5380 and the ctor at 99.78 %. Same family as the leading-literal items above.
- **Overflow trap on the player life word (tu_8026FC20 fn_80270DDC).** The original
  does `old = x; x++; if (x == old) for (;;); x = old;` on Player 0xBFC (stw, reload,
  `b .` self-branch, restore) before healing. It is written literally with a comment; no
  assert macro, busy-wait or donor idiom (grep of src/ and donors) yields it. Not a
  FAKEMATCH (nothing is steered), but the source form is unknown; revisit if another
  function shows the same increment-compare-spin shape. It now appears a second time:
  tu_8023FBF0 addCounter_8024ED4C (fn_8024ED4C, Player 0xC04), preceded there by an
  `if (c > 9999) for (;;)` check that fn_8024ECCC also has; the same unexplained assert-like
  halts, fields differ, so no shared inline is written.
- **The 11 units still out of address order** (tools/order_check.py; 12 before the
  deferred switch, act_vaati_demo fixed by it): reordering changed inlining or the
  .sdata2 pool in each under `-inline auto`; revisit each with deferred inlining
  and the auto_inline rule (docs/INLINING.md).

## game/act_hyrule_castle_barrier.cpp: getMidPos / getEndPos1 / getEndPos2

- **Trick:** the three position helpers return the address of a `JGeometry::TVec3f`
  temporary (`return &TVec3f(...)` / `p = &TVec3f(...)`), a dangling pointer in C++.
  Every such line carries `FAKEMATCH(crack-pass)`. The helpers are plain functions at the
  bottom of the file (their out-of-line copies are dead-stripped) and fn_8011EEEC inlines
  them, so MWCC places each temporary in a slot of fn_8011EEEC's own frame and the pointer
  passed to spawnEmitter_8013CC50 is valid at the call.
- **Why:** the original fn_8011EEEC (frame 0xF0) builds a separate stack TVec3f per switch
  arm (0x74, 0x80, 0x8C, 0x98, ...) and passes its address. Returning by value with a
  caller local gave 43.8 %; void helpers with an out-parameter gave 89.8 % (frame 0xB0,
  shared slots). With this form init, fn_8011EEEC and fn_8011F314 are 100 %.
- **Honest fix would need:** a source form that gives one caller-frame temporary per call
  site without a dangling return, e.g. the call sites constructing `TVec3f` arguments
  inline in a shape MWCC lays out identically (not found yet), or evidence of the original
  helper signature (a reference-returning inline that MWCC treats the same way).
- **Verification:** unit NonMatching; full link SHA-1 OK; reviewed 2026-11-07
  (pool-owners round 2). The pattern came in with the Argon act_hyrule_castle_barrier
  merge (e8647783) and was tagged when it was moved to the bottom of the file.

## Pool helpers that fail rule R2 (owner decision 2026-11-22)

- **Trick:** 99 plain helper functions, each inlined at one call site and longer
  than one statement, written where the original's `.sdata2` order says code was
  generated (docs/analysis/POOL_POLICY.md). The pool proves a dropped function
  existed there; it does not fix where that function's body starts and ends, so
  these bodies are code split out where the pool needs it. Each definition carries
  `// FAKEMATCH(crack-pass): pool helper failing R2 ...` (docs/RULES_CARD.md
  "Pool helpers (R2)").
- **Why:** turning one into `inline` moves its literals into its caller's block and
  shifts the pool; the functions in the table's last column (measured alone, on
  an-pool 9c16afc25, `functionRelocDiffs=all`) leave 100 %. All of them together
  hold about 171 functions (POOL_POLICY section 3; the per-helper figures overlap).
- **Honest fix would need:** evidence that fixes the body's extent: a second inlined
  copy of the same code in the asm, a one-statement body that creates the run by
  itself, or the identical body in another unit. Failing that, the helper becomes
  `inline` (or is folded into its caller) and the functions listed drop until the
  pool order has another explanation.
- **Pending owner: Matching units.** None: all 99 sit in NonMatching units
  (configure.py, 2026-11-22), so all are tagged and no unit had to change status.
- **Verification (2026-11-22):** `python3 configure.py && ninja` SHA-1 OK;
  `tools/names_compare.py` against the report before the tags: no drops (10,346 at
  100 %); `tools/gate.py --all-units` ok.

| unit | helper | lines | functions it holds at 100 % alone |
|---|---|---:|---|
| act_block | `Block_804A7A10::keepsMoving` | 11 | `fn_8028D4DC` |
| act_bombchu | `Bombchu_804AB464::faceMoveDirection` | 15 | `fn_8032506C__16Bombchu_804AB464Fv`, `draw__16Bombchu_804AB464Fv`, `vfunc_0x54__16Bombchu_804AB464Fv`, `init__16Bombchu_804AB464Fv` |
| act_cannon | `findOwner` | 15 | `init__15Cannon_8049CCF0Fv`, `fn_801080B8__15Cannon_8049CCF0CFv` |
| act_cannon | `setBounceHeight` | 4 | `draw__15Cannon_8049CCF0Fv`, `init__15Cannon_8049CCF0Fv`, `fn_801080B8__15Cannon_8049CCF0CFv`, `__ct__15Cannon_8049CCF0Fv` |
| act_cannon | `updateRecoil` | 37 | `draw__15Cannon_8049CCF0Fv`, `init__15Cannon_8049CCF0Fv`, `fn_801080B8__15Cannon_8049CCF0CFv` |
| act_cannon | `updateRise` | 8 | `init__15Cannon_8049CCF0Fv`, `fn_801080B8__15Cannon_8049CCF0CFv` |
| act_fairy_invincible | `setUniformScaleMtx` | 14 | (none alone; needed jointly with the unit's other helpers) |
| act_fish | `Fish_804AC658::stopSwim` | 6 | (none alone; needed jointly with the unit's other helpers) |
| act_force_gem_winged | `WingedForceGem_804AB098::updateRise` | 32 | (none alone; needed jointly with the unit's other helpers) |
| act_four_person_pull_switch | `FourPersonPullSwitch_804AE230::checkAllPulled` | 19 | `draw__29FourPersonPullSwitch_804AE230Fv`, `update__29FourPersonPullSwitch_804AE230Fv` |
| act_four_sword_demo | `FourSwordCutscene_8049DA0C::checkPlayers` | 22 | (none alone; needed jointly with the unit's other helpers) |
| act_four_sword_demo | `FourSwordCutscene_8049DA0C::raisePlayers` | 13 | `fn_80117074__26FourSwordCutscene_8049DA0CFl`, `draw__26FourSwordCutscene_8049DA0CFv` |
| act_four_sword_demo | `FourSwordCutscene_8049DA0C::showMessage` | 7 | `fn_80117074__26FourSwordCutscene_8049DA0CFl`, `draw__26FourSwordCutscene_8049DA0CFv`, `__ct__26FourSwordCutscene_8049DA0CFv` |
| act_four_sword_demo | `FourSwordCutscene_8049DA0C::spawnPlayerEffects` | 11 | `fn_80117074__26FourSwordCutscene_8049DA0CFl`, `draw__26FourSwordCutscene_8049DA0CFv` |
| act_four_sword_demo | `FourSwordCutscene_8049DA0C::spreadPlayers` | 16 | `fn_80117074__26FourSwordCutscene_8049DA0CFl`, `draw__26FourSwordCutscene_8049DA0CFv` |
| act_gambling_shop | `GamblingShop_804AAA70::swapTwoChests` | 23 | (none alone; needed jointly with the unit's other helpers) |
| act_great_fairy_spfr | `GreatFairy_8049EB8C::placeAtBarrier` | 20 | `fn_801321E4__19GreatFairy_8049EB8CFv`, `init__19GreatFairy_8049EB8CFv` |
| act_great_fairy_spfr | `GreatFairy_8049EB8C::spawnSoldier` | 15 | `fn_801321E4__19GreatFairy_8049EB8CFv`, `draw__19GreatFairy_8049EB8CFv`, `init__19GreatFairy_8049EB8CFv` |
| act_great_fairy_spfr | `GreatFairy_8049EB8C::talkTo` | 21 | `fn_801321E4__19GreatFairy_8049EB8CFv` |
| act_ice_melted_by_four_players | `IceMeltedByFourPlayers_804AE888::spawnMeltEmitter` | 5 | `fn_80378680__31IceMeltedByFourPlayers_804AE888Fv`, `update__31IceMeltedByFourPlayers_804AE888Fv`, `init__31IceMeltedByFourPlayers_804AE888Fv` |
| act_ice_wall | `IceWall_8049DE18::hitByFire` | 14 | (none alone; needed jointly with the unit's other helpers) |
| act_ice_wall | `IceWall_8049DE18::hitByWeapon` | 30 | (none alone; needed jointly with the unit's other helpers) |
| act_ice_wall | `IceWall_8049DE18::startMelting` | 15 | `draw__16IceWall_8049DE18Fv`, `init__16IceWall_8049DE18Fv`, `__ct__16IceWall_8049DE18Fv` |
| act_icicle | `Icicle_8049CFC8::fall` | 4 | `fn_8010B284__15Icicle_8049CFC8Fv`, `fn_8010B40C__15Icicle_8049CFC8Fl`, `draw__15Icicle_8049CFC8Fv`, `init__15Icicle_8049CFC8Fv`, `__ct__15Icicle_8049CFC8Fv` |
| act_maiden_demo | `MaidenCutscene_8049D740::moveToGoal` | 15 | `fn_80112654__23MaidenCutscene_8049D740Fl`, `draw__23MaidenCutscene_8049D740Fv` |
| act_princess_zelda | `PrincessZelda_8049CEE0::approachPlayerSide` | 19 | `fn_80109534__22PrincessZelda_8049CEE0Fv`, `fn_80109AE0__22PrincessZelda_8049CEE0FPQ29JGeometry8TVec3<f>`, `draw__22PrincessZelda_8049CEE0Fv`, `init__22PrincessZelda_8049CEE0Fv` |
| act_princess_zelda | `PrincessZelda_8049CEE0::followPlayerSide` | 25 | `fn_80109534__22PrincessZelda_8049CEE0Fv`, `fn_80109AE0__22PrincessZelda_8049CEE0FPQ29JGeometry8TVec3<f>`, `draw__22PrincessZelda_8049CEE0Fv`, `init__22PrincessZelda_8049CEE0Fv` |
| act_princess_zelda | `PrincessZelda_8049CEE0::stepSpeed` | 7 | `fn_80109AE0__22PrincessZelda_8049CEE0FPQ29JGeometry8TVec3<f>`, `draw__22PrincessZelda_8049CEE0Fv`, `init__22PrincessZelda_8049CEE0Fv` |
| act_princess_zelda_demo | `PrincessZeldaDemo_8049D208::flyToGoal` | 24 | `fn_8010E2D4__26PrincessZeldaDemo_8049D208Fl`, `fn_8010F4DC__26PrincessZeldaDemo_8049D208Fv`, `fn_80110454__26PrincessZeldaDemo_8049D208Fv`, `__ct__26PrincessZeldaDemo_8049D208Fv` |
| act_princess_zelda_demo | `PrincessZeldaDemo_8049D208::lowerPlayers` | 13 | `fn_8010E2D4__26PrincessZeldaDemo_8049D208Fl`, `fn_8010F4DC__26PrincessZeldaDemo_8049D208Fv`, `fn_8010F7EC__26PrincessZeldaDemo_8049D208Fl`, `fn_80110454__26PrincessZeldaDemo_8049D208Fv`, `__ct__26PrincessZeldaDemo_8049D208Fv` |
| act_princess_zelda_demo | `PrincessZeldaDemo_8049D208::sinkToPlayer` | 8 | `fn_8010E2D4__26PrincessZeldaDemo_8049D208Fl`, `fn_8010F4DC__26PrincessZeldaDemo_8049D208Fv`, `fn_8010F7EC__26PrincessZeldaDemo_8049D208Fl`, `fn_80110454__26PrincessZeldaDemo_8049D208Fv`, `init__26PrincessZeldaDemo_8049D208Fv`, `__ct__26PrincessZeldaDemo_8049D208Fv` |
| act_princess_zelda_demo | `PrincessZeldaDemo_8049D208::standBelow` | 5 | `fn_8010E2D4__26PrincessZeldaDemo_8049D208Fl`, `fn_80110454__26PrincessZeldaDemo_8049D208Fv`, `__ct__26PrincessZeldaDemo_8049D208Fv` |
| act_rainbow_bridge | `RainbowBridge_8049E610::isPlayerOn` | 26 | `init__22RainbowBridge_8049E610Fv` |
| act_room_transfer_lift | `RoomTransferLift_8049CC40::isInside` | 14 | `update__25RoomTransferLift_8049CC40Fv` |
| act_score | `Score_804AF4C0::updateState1` | 10 | `fn_80393228__14Score_804AF4C0Fv`, `update__14Score_804AF4C0Fv` |
| act_score | `Score_804AF4C0::updateState2` | 7 | `fn_80393228__14Score_804AF4C0Fv`, `update__14Score_804AF4C0Fv` |
| act_seesaw_lift | `SeesawLift_804AD348::isPlayerInside` | 9 | `fn_80358F98__19SeesawLift_804AD348Fv`, `fn_803597EC__19SeesawLift_804AD348Fv`, `fn_8035A210__19SeesawLift_804AD348Fv`, `fn_8035AC84__19SeesawLift_804AD348Fl`, `fn_8035AE9C__19SeesawLift_804AD348Fl` |
| act_shadow_link_demo | `ShadowLinkCutscene_8049DB90::hopDown` | 8 | `fn_8011B878__27ShadowLinkCutscene_8049DB90Fl` |
| act_shadow_link_demo | `ShadowLinkCutscene_8049DB90::spawnFlash` | 5 | `fn_8011B878__27ShadowLinkCutscene_8049DB90Fl` |
| act_shovel_old_timer | `ShovelOldTimer_804AAB40::findDigSpot` | 31 | `draw__23ShovelOldTimer_804AAB40Fv`, `init__23ShovelOldTimer_804AAB40Fv` |
| act_small_key | `SmallKey_804A8CD8::bounceOffTile` | 19 | `fn_802C24A8__17SmallKey_804A8CD8Fv` |
| act_small_key | `SmallKey_804A8CD8::dropAtPlayer` | 37 | (none alone; needed jointly with the unit's other helpers) |
| act_snow_wall | `SnowWall_8049E8A0::melt` | 19 | `update__17SnowWall_8049E8A0Fv`, `init__17SnowWall_8049E8A0Fv`, `__ct__17SnowWall_8049E8A0Fv` |
| act_snow_wall | `SnowWall_8049E8A0::shrink` | 16 | `update__17SnowWall_8049E8A0Fv`, `init__17SnowWall_8049E8A0Fv` |
| act_snowball | `Snowball_8049D020::chase` | 26 | `update__17Snowball_8049D020Fv`, `__ct__17Snowball_8049D020Fv` |
| act_snowball | `Snowball_8049D020::dropRupee` | 15 | `update__17Snowball_8049D020Fv`, `init__17Snowball_8049D020Fv`, `__ct__17Snowball_8049D020Fv` |
| act_snowball | `Snowball_8049D020::followRail` | 13 | (none alone; needed jointly with the unit's other helpers) |
| act_snowball | `Snowball_8049D020::grow` | 19 | `update__17Snowball_8049D020Fv`, `init__17Snowball_8049D020Fv`, `__ct__17Snowball_8049D020Fv` |
| act_snowball | `Snowball_8049D020::spawnBurst` | 7 | `update__17Snowball_8049D020Fv`, `init__17Snowball_8049D020Fv`, `__ct__17Snowball_8049D020Fv` |
| act_strange_block | `StrangeBlock_804AC2D8::blockedAtFullReach` | 10 | `fn_8033D4AC`, `init__21StrangeBlock_804AC2D8Fv` |
| act_tingle_first | `TingleFirstAppearance_804AADD8::selectNearestPlayer` | 23 | `draw__30TingleFirstAppearance_804AADD8Fv` |
| act_vaati_demo | `VaatiCutscene_8049D940::updateDescent` | 10 | `update__22VaatiCutscene_8049D940Fv` |
| act_vaati_time_up | `VaatiTimeUp_804ACCC0::pickTarget` | 10 | `draw__20VaatiTimeUp_804ACCC0Fv` |
| act_vaati_time_up | `VaatiTimeUp_804ACCC0::steer` | 12 | `draw__20VaatiTimeUp_804ACCC0Fv` |
| act_warp | `updateSandHole` | 18 | `draw__13Warp_804A6DC8Fv` |
| act_warp_cannon | `WarpCannon_8049EAE0::allPlayersIn` | 8 | (none alone; needed jointly with the unit's other helpers) |
| act_warp_cannon | `WarpCannon_8049EAE0::findPlayer` | 15 | (none alone; needed jointly with the unit's other helpers) |
| act_warp_cannon | `WarpCannon_8049EAE0::fireRecoil` | 26 | `draw__19WarpCannon_8049EAE0Fv`, `__ct__19WarpCannon_8049EAE0Fv` |
| act_warp_cannon | `WarpCannon_8049EAE0::landPlayers` | 12 | (none alone; needed jointly with the unit's other helpers) |
| act_warp_cannon | `WarpCannon_8049EAE0::liftPlayers` | 7 | (none alone; needed jointly with the unit's other helpers) |
| act_warp_cannon | `WarpCannon_8049EAE0::movePlayers` | 8 | (none alone; needed jointly with the unit's other helpers) |
| act_warp_cannon | `WarpCannon_8049EAE0::recoil` | 13 | `draw__19WarpCannon_8049EAE0Fv` |
| act_warp_cannon | `WarpCannon_8049EAE0::resetIfAllPlayersReady` | 8 | (none alone; needed jointly with the unit's other helpers) |
| act_zora_escort | `ZoraEscort_8049DF78::findNearbyPlayer` | 17 | (none alone; needed jointly with the unit's other helpers) |
| act_zora_escort | `ZoraEscort_8049DF78::hasNearbyBari` | 21 | (none alone; needed jointly with the unit's other helpers) |
| act_zora_escort | `ZoraEscort_8049DF78::stepToPlayer` | 24 | (none alone; needed jointly with the unit's other helpers) |
| act_zora_escort_goal | `ZoraEscortGoal_8049E424::spawnEmitters` | 6 | `fn_80126A4C__23ZoraEscortGoal_8049E424Fl`, `draw__23ZoraEscortGoal_8049E424Fv`, `init__23ZoraEscortGoal_8049E424Fv`, `__ct__23ZoraEscortGoal_8049E424Fv` |
| act_zora_escort_goal | `ZoraEscortGoal_8049E424::walkRail` | 25 | `fn_80126A4C__23ZoraEscortGoal_8049E424Fl`, `init__23ZoraEscortGoal_8049E424Fv` |
| tu_8010089C | `WhackAMoleShop_8049C8EC::showTimer` | 10 | `draw__23WhackAMoleShop_8049C8ECFv`, `init__23WhackAMoleShop_8049C8ECFv` |
| tu_80113788 | `CrystalCutscene_8049D83C::positionPlayers` | 12 | `fn_80113790__24CrystalCutscene_8049D83CFv`, `__ct__24CrystalCutscene_8049D83CFv` |
| tu_80113788 | `CrystalCutscene_8049D83C::spawnBurstEmitters` | 4 | `fn_80113790__24CrystalCutscene_8049D83CFv` |
| tu_80113788 | `CrystalCutscene_8049D83C::spawnEmitters` | 12 | `fn_80113790__24CrystalCutscene_8049D83CFv`, `__ct__24CrystalCutscene_8049D83CFv` |
| tu_80113788 | `CrystalCutscene_8049D83C::spawnSealEmitters` | 7 | `fn_80113790__24CrystalCutscene_8049D83CFv`, `__ct__24CrystalCutscene_8049D83CFv` |
| tu_80113788 | `CrystalCutscene_8049D83C::updateCameraFocus` | 44 | `fn_80113790__24CrystalCutscene_8049D83CFv`, `__ct__24CrystalCutscene_8049D83CFv` |
| tu_80118384 | `spawnFadeEmitters` | 7 | `fn_801194C4__12cls_80119E5CFv`, `fn_80119628__12cls_80119E5CFv`, `startFade_80119998__12cls_80119E5CFlllllll` |
| tu_8011CEC8 | `AfterGoalOpening_8049DD68::setOverlayRect` | 21 | `update__25AfterGoalOpening_8049DD68Fv` |
| tu_8011CEC8 | `AfterGoalOpening_8049DD68::startScroll` | 9 | `update__25AfterGoalOpening_8049DD68Fv`, `init__25AfterGoalOpening_8049DD68Fv` |
| tu_801213EC | `EscortBase_8049E0C8::respawnLifeMeters` | 9 | (none alone; needed jointly with the unit's other helpers) |
| tu_801213EC | `EscortBase_8049E0C8::spawnLifeMeter` | 14 | (none alone; needed jointly with the unit's other helpers) |
| tu_80125B58 | `EscortedWomanArrivalPoint_8049E350::startSignAnim` | 12 | `fn_80125BF4__34EscortedWomanArrivalPoint_8049E350Fv`, `fn_80125C58__34EscortedWomanArrivalPoint_8049E350Fb`, `draw__34EscortedWomanArrivalPoint_8049E350Fv`, `init__34EscortedWomanArrivalPoint_8049E350Fv` |
| tu_80125B58 | `EscortedWomanArrivalPoint_8049E350::talkTo` | 5 | `fn_80125BF4__34EscortedWomanArrivalPoint_8049E350Fv`, `draw__34EscortedWomanArrivalPoint_8049E350Fv` |
| tu_8013394C | `NaviAfterCrystalCutscene_8049ED30::spawnEmitters` | 8 | `init__33NaviAfterCrystalCutscene_8049ED30Fv` |
| tu_8015F454 | `drawLetterbox` | 5 | `fn_8015F454__FP10JUTTexturePCfPCf8_GXColorPC11_GXColorS10P10JUTTextureUcUc`, `fn_8016005C__12cls_804A03A8Fv` |
| tu_8018EB94 | `BigMoldormTail_804A1FA0::setHeading` | 13 | (none alone; needed jointly with the unit's other helpers) |
| tu_8027E5BC | `Player_804A6F38::followStep` | 26 | `fn_8027FA08__15Player_804A6F38FPQ29JGeometry8TVec3<f>`, `fn_80280074__15Player_804A6F38Fv`, `fn_802804E0__15Player_804A6F38Fv`, `moveByStick_802808E8__15Player_804A6F38Ff`, `fn_80280B30__15Player_804A6F38Fv`, `fn_8028126C__15Player_804A6F38Fv`, `fn_80281E98__15Player_804A6F38Fv`, `fn_80282094__15Player_804A6F38Fv`, `fn_80282ACC__15Player_804A6F38Fv`, `fn_80283D2C__15Player_804A6F38Fv`, `fn_80283E70__15Player_804A6F38Fv`, `fn_80284294__15Player_804A6F38Fv`, `fn_8028434C__15Player_804A6F38Fv`, `fn_80284430__15Player_804A6F38Fv`, `fn_802844F8__15Player_804A6F38Fv`, `fn_80285098__15Player_804A6F38Fv`, `fn_8028538C__15Player_804A6F38Fv`, `fn_80285690__15Player_804A6F38Fv` |
| tu_802E9428 | `UnknownENDM_804AA0FC::stepZoom` | 12 | `init__20UnknownENDM_804AA0FCFv` |
| tu_8030C058 | `Camera_804AA9E4::setScreenRectViewport` | 7 | `fn_8030C380__15Camera_804AA9E4FPQ29JGeometry8TVec3<f>`, `fn_8030C4A0__15Camera_804AA9E4FPCQ29JGeometry8TVec2<f>bPQ29JGeometry8TVec3<f>`, `fn_8030C5F0__15Camera_804AA9E4FPC3VecbbP3Vec`, `fn_8030C7C4__15Camera_804AA9E4FPCQ29JGeometry8TVec2<f>f`, `fn_8030DFE8__15Camera_804AA9E4Fb` |
| tu_8034AA40 | `markRandomCucco` | 8 | `fn_8034AAA0__24CuccoHerdingNPC_804AC8C0Fv`, `vfunc_0x10__24CuccoHerdingNPC_804AC8C0Fv`, `init__24CuccoHerdingNPC_804AC8C0Fv` |
| tu_80362634 | `OtherCharactersEnding_804ADF28::spawnRoomEmitters` | 8 | `fn_80362680__30OtherCharactersEnding_804ADF28Fv`, `fn_803628D4__30OtherCharactersEnding_804ADF28Fv`, `fn_80362B74__30OtherCharactersEnding_804ADF28Fv`, `fn_80363360__30OtherCharactersEnding_804ADF28Fv`, `fn_80363664__30OtherCharactersEnding_804ADF28Fv`, `fn_80364340__30OtherCharactersEnding_804ADF28Fv`, `fn_80364900__30OtherCharactersEnding_804ADF28Fv`, `fn_80364F60__30OtherCharactersEnding_804ADF28Fv`, `fn_8036509C__30OtherCharactersEnding_804ADF28Fv`, `fn_80365220__30OtherCharactersEnding_804ADF28Fv`, `fn_80365274__30OtherCharactersEnding_804ADF28Fv`, `fn_803653EC__30OtherCharactersEnding_804ADF28Fv` |
| tu_8036FB60 | `FourGirlsControl_804AE4B0::guidePlayer_80370764` | 6 | `fn_803703C8__25FourGirlsControl_804AE4B0Fv`, `fn_80370508__25FourGirlsControl_804AE4B0Fv`, `fn_80370764__25FourGirlsControl_804AE4B0Fv`, `fn_80370A7C__25FourGirlsControl_804AE4B0Fv`, `fn_8037100C__25FourGirlsControl_804AE4B0Fv`, `fn_80371284__25FourGirlsControl_804AE4B0Fv` |
| tu_80376FA0 | `RockDroppedIntoTheRiver11_804AE7D8::rewriteTiles` | 22 | `init__34RockDroppedIntoTheRiver11_804AE7D8Fv` |
| tu_80376FA0 | `RockDroppedIntoTheRiver11_804AE7D8::setBoxes` | 10 | `init__34RockDroppedIntoTheRiver11_804AE7D8Fv` |
| tu_80376FA0 | `RockDroppedIntoTheRiver11_804AE7D8::spawnBreakEmitters` | 22 | `init__34RockDroppedIntoTheRiver11_804AE7D8Fv` |
| tu_80376FA0 | `RockDroppedIntoTheRiver11_804AE7D8::touchesPlayer` | 23 | `init__34RockDroppedIntoTheRiver11_804AE7D8Fv` |
| tu_803B7DCC | `setFrameBufferOrtho` | 5 | `fn_803B7DCC__12cls_804AFAB0Fv`, `fn_803B7E64__12cls_804AFAB0Fv` |
| tu_803E1668 | `AdvEntryScreen_804B0B00::drawFade` | 30 | `fn_803E2A20__23AdvEntryScreen_804B0B00Fv`, `fn_803E3564__23AdvEntryScreen_804B0B00Fv`, `fn_803E3CB0__23AdvEntryScreen_804B0B00Fv`, `fn_803E4344__23AdvEntryScreen_804B0B00Fv`, `fn_803E4650__23AdvEntryScreen_804B0B00Fv`, `fn_803E4940__23AdvEntryScreen_804B0B00Fv`, `fn_803E8210__23AdvEntryScreen_804B0B00Fv`, `fn_803E9A20__23AdvEntryScreen_804B0B00Fv`, `fn_803E9EE8__23AdvEntryScreen_804B0B00Fv`, `fn_803EDA2C__23AdvEntryScreen_804B0B00Fv`, `fn_803EDBF0__23AdvEntryScreen_804B0B00FUc` |
| tu_803F0A54 | `ConnectScreen_804B0F10::drawFade` | 26 | `fn_803F1C70__22ConnectScreen_804B0F10Fv`, `fn_803F267C__22ConnectScreen_804B0F10Fv`, `fn_803F2B78__22ConnectScreen_804B0F10Fv`, `fn_803F3324__22ConnectScreen_804B0F10Fv`, `fn_803F35B0__22ConnectScreen_804B0F10Fv`, `fn_803F38A4__22ConnectScreen_804B0F10Fv`, `fn_803F715C__22ConnectScreen_804B0F10Fv`, `fn_803F8AE4__22ConnectScreen_804B0F10Fv`, `fn_803F8FBC__22ConnectScreen_804B0F10Fv`, `fn_803FC46C__22ConnectScreen_804B0F10Fv`, `fn_803FC5E4__22ConnectScreen_804B0F10FUc` |
| tu_8042165C | `BattleHud_804B146C::updateGaugeBar` | 9 | `fn_80424148__18BattleHud_804B146CFlb` |
| tu_8042E964 | `WarningWindow_804B1634::scaleFrames` | 21 | `fn_80431174__22WarningWindow_804B1634FUc`, `fn_804317AC__22WarningWindow_804B1634Fv` |
