# Inline leads: header and file inlines our source writes out by hand

2026-11-22, branch `an-inlines`. Question: which inline functions did the original source
use that our source writes out at each site? A missing inline changes the creation order of
values and so register colouring, stack slots and scheduling (docs/REGALLOC.md rules 1-4).
The model case is 2290324a7: 14 copies of
`getActorManager_801F856C()->findActorBySerial_801F666C(field_0xd68)` became one
`Player_804A6F38::heldActor()` and fixed fn_80273518 without changing anything else.

## Method

`python3 tools/inline_leads.py [--asm] [--kind chain,shape,stmt,pair] [--top N] [--grep RE] [--json F]`

- **Source side** (default, ~5 s). Cuts every function body out of `src/game/*.cpp` and
  collects, once per function: call chains with two or more calls (`a()->b(x)`) or a call as
  an argument; the same chains with arguments elided (`a(…)->b(…)`, kind `shape`); every
  statement with a call; every pair of consecutive statements.
- **Asm side** (`--asm`, ~10 s with clones.py's cached index). The shared instruction blocks
  of the original (tools/clones.py), per function.
- **Ranking**: by the number of functions that contain the lead and are not at 100 % in
  `build/G4SE01/report_honest.json` (report of 2026-11-20), then by their bytes.
- **Testing** (scratch harness, not committed): introduce the inline at every site of a
  unit, build all affected objects in one ninja call, diff each with objdiff-cli under the
  report's setting, compare every function and section to the baseline, revert. A unit
  keeps an inline only if it gains and loses nothing at 100 %, and only if it has more than
  one site (single-use inlines are rejected by review).

## Results of the tests

| Lead | Form tested | Units | Result |
|---|---|---:|---|
| `getActorManager_801F856C()->findActorBySerial_801F666C(x)` | one header inline `actorBySerial(serial)` at all 380 sites; once `return ...;`, once with a named local | 171 | +3 / -7 for both forms (losses: tu_8020B354 x3, tu_80209C14, tu_801E2540, act_sword_soldier dtor, act_ice_melted_by_four_players). **Not a game-wide header inline.** |
| same, per file | file-local `static inline actorBySerial` at every site of the unit | 3 units gain | **kept**: tu_8020D58C (2 sites, fn_8020D6AC 97.67 -> 100 %), tu_801DE714 (36 sites, cls_804A51E4::calcVelocity_0x88 97.22 -> 100 %). act_life_meter gains too (update 99.32 -> 100 %) but has one site: not kept. |
| `getGameView_802D6A9C()->isInTransition_802DCD0C()` | file-local inline at every site | 31 | no change at all |
| `getActorManager_801F856C()->fn_801F68E0()` | same | 25 | no change (one function +0.02) |
| `getActorManager_801F856C()->fn_801F6884();` | same | 24 | no change |
| `fn_8011921C()->fn_80118454();` / `->fn_801183BC();` | same | 9 / 8 | no change |
| `box.i.x += mPos.x; ... box.f.y += mPos.y;` (4 lines, 67 units) | `box.addPos(mPos.x, mPos.y)` (JGeometry inline) | 67 | **-52 at 100 %, 0 gained**: the hand-written form is right; the original did not use addPos there. |

What this says: a wrapper around calls whose result is used at once creates nothing that
changes colouring, so the void and test-at-once chains (GameView, fn_8011921C, fn_801F6884)
are dead leads. Only lookups whose result lives on (an actor pointer kept across calls) move
registers, and for those the original used per-file or per-class helpers, not one header
inline: the same class cls_804A51E4 gains in tu_801DE714 and loses in tu_801E2540.

## Best remaining leads

1. **Per-field / per-class lookups** like heldActor: group the findActorBySerial sites by
   (class, member argument), e.g. `mTargetSerial` (12 functions, 4 non-100), `field_0x250`,
   and test a member inline per group. The 171-unit run shows the per-file signal is small but real.
2. `getActorManager_801F856C()->spawnActor_801F9484(…)` (222 functions, 139 not at 100 %):
   the result (the new actor) is kept; untested.
3. The actor-list loop `s32 end = getActorManager_801F856C()->mActorEnd; for (s32 i = 0; ...`
   (22 functions, 20 not at 100 %), and `ActorBase_804A5770* actor = getActorManager_801F856C()->mActors[i];`
   (32 / 29): probably an iteration inline in the original (REGALLOC.md: a loop counter in the wrong
   register next to a compiler pointer = the loop belongs in an inline). Untested.
4. `GameView_804A9950* view = getGameView_802D6A9C();` paired with `s32 layer = field_0x4;`
   (25 functions, 16 not at 100 %).
5. Asm side: the top blocks are already-known inlines (JMath random's LCG `mullw` /
   `addis 0x3c6f` / `oris 0x3f80`, the TVec add sequences); the lead list is most useful
   with `--grep` for a call name.

## Round 2 (2026-11-22, branch `inlines-2`)

Same method, per class or file scope: each helper at every site of its scope, all affected
units compiled, every function compared before/after. Counts are functions reaching or
leaving 100 %.

| Lead | Form tested | Units | Result |
|---|---|---:|---|
| member lookups `findActorBySerial_801F666C(<member>)`, grouped by (class, member), 2+ sites | inline taking the object, named local and `return expr;`; also as a real member (BirdFormation_804A5E98::targetActor) | 18 (22 groups) | **-3, 0 gained** (tu_8020B354 x2, tu_80209C14 checkHitByPlayer_0x5C); everything else unchanged. Member and free-function forms give identical code. |
| same with an index (`mSerials[i]`, `field_0x240[i]`, `mSlots[i].mSerial`, ...) | inline (self, s32 i) | 14 (17 groups) | 0 / 0 (two units slightly worse) |
| `getActorManager_801F856C()->spawnActor_801F9484(...)` | file-local inline with the same six parameters, named local / `return expr;` | 145 | named local +1 / -0, `return` form **+3 / -0**: the arguments are evaluated before getActorManager_801F856C is called. **Kept** (cc24e25cf) in tu_8013C5C8 (9 sites, cls_8049F140::execute) and tu_802684A4 (3 sites, fn_8026EC88); tu_801CDC8C gains too but has one site. |
| `getActorManager_801F856C()->mActors[i]` | `getActor(i)` (existing accessor), file inline named local, file inline `return` | 37 | 0 / 0 for all three |
| `s32 end = getActorManager_801F856C()->mActorEnd;` | `ActorManager_804A5800::getActorEnd() { return mActorEnd; }`; the same with a named local, and a free inline (named local or `return`) give identical code | 37 | **+9 / -1** game-wide (loss: act_battle_royale_end_check fn_803D6BDC 100 -> 99.59; moving its loop into an inline makes it worse, 96.03). **Kept** (5a2cbe993) in the 26 units where no function gets worse: +11 (gambling_shop, kaepora_gaebora_ending, knight_of_hyrule, navi_maiden_crystal, small_key, stop_npc, warp_entrance_wall, tu_802D39B8 x2; act_stop_npc and act_warp_entrance_wall reach 100 % .text). 11 units keep the direct read. |
| `GameView_804A9950* view = getGameView_802D6A9C();` | file inline, named local | 62 | 0 / 0 |
| `layer < 8 ? &view->mVisibleBox : &view->field_0xdc` (49 sites) | GameView member `screenBox(layer)` as `?:` and as if/return | 32 | 0 / 0 (one function -0.17) |

What this adds: an inline call changes registers even when it only returns a member, if the
object is a call result (`getActorManager_801F856C()->getActorEnd()` makes that result the
inline's `this`). The accessor's pattern (gains in 8 units, no change in most, worse in 11)
says the original had such an accessor and some files, or some programmers, read the field
directly. A wrapper also changes the order of calls (arguments before the manager lookup),
which is what the spawn helper fixes. Lookups of a member serial through a member inline
gain nothing outside Player: heldActor's gains come from Player's deep inline chains.

Next: for the 11 units left on the direct mActorEnd read, the loop or its owner is probably
in an inline (fn_803D6BDC needs the bound in r30 and the offset in r29); `getActor(i)`
combined with `getActorEnd()` per file was not tested.

## Ranked candidates

Counts from report_honest.json of 2026-11-20 (before the two commits above).

### Call-chain shapes (arguments elided), top 30

| # | non-100 fns | their bytes | fns | units | lead |
|---:|---:|---:|---:|---:|---|
| 1 | 175 | 387804 | 371 | 171 | `getActorManager_801F856C(…)->findActorBySerial_801F666C(…)` |
| 2 | 139 | 364460 | 222 | 145 | `getActorManager_801F856C(…)->spawnActor_801F9484(…)` |
| 3 | 28 | 77124 | 54 | 43 | `getGameView_802D6A9C(…)->fn_802D8050(…)` |
| 4 | 28 | 72844 | 36 | 32 | `getActorManager_801F856C(…)->spawnActorSimple_801F8544(…)` |
| 5 | 27 | 68020 | 44 | 32 | `getGameView_802D6A9C(…)->fn_802D79E8(…)` |
| 6 | 26 | 84292 | 41 | 30 | `fn_80230498(…)` |
| 7 | 24 | 82500 | 35 | 31 | `getGameView_802D6A9C(…)->isInTransition_802DCD0C(…)` |
| 8 | 23 | 53612 | 56 | 44 | `getGameView_802D6A9C(…)->isScreenFlagSet_802D800C(…)` |
| 9 | 21 | 95888 | 25 | 25 | `getActorManager_801F856C(…)->fn_801F68E0(…)` |
| 10 | 20 | 81416 | 25 | 24 | `getActorManager_801F856C(…)->fn_801F6884(…)` |
| 11 | 17 | 40844 | 23 | 18 | `pos(…)` |
| 12 | 16 | 63952 | 22 | 18 | `fn_80119DD0(…)->fn_80119998(…)` |
| 13 | 16 | 25544 | 29 | 24 | `getActorManager_801F856C(…)->fn_801F78F4(…)` |
| 14 | 14 | 62416 | 26 | 21 | `spawnEmitter_8013CC50(…)` |
| 15 | 14 | 18712 | 34 | 23 | `getGameView_802D6A9C(…)->fn_802D7440(…)` |
| 16 | 12 | 51728 | 29 | 14 | `getMessageText_803832BC(…)` |
| 17 | 12 | 41000 | 14 | 13 | `getActorManager_801F856C(…)->fn_801F7818(…)` |
| 18 | 12 | 26844 | 16 | 16 | `fn_8020D58C(…)->addBox(…)` |
| 19 | 11 | 40860 | 24 | 14 | `getPlayerPos_8023E724(…)` |
| 20 | 11 | 26512 | 16 | 9 | `fn_8011921C(…)->fn_80118454(…)` |
| 21 | 11 | 25248 | 18 | 18 | `getGameView_802D6A9C(…)->fn_802D9FF4(…)` |
| 22 | 10 | 54608 | 11 | 10 | `fn_8022FE80(…)` |
| 23 | 10 | 13376 | 15 | 10 | `__fabsf(…)` |
| 24 | 10 | 13232 | 10 | 10 | `setRotScaleMtx(…)` |
| 25 | 9 | 18700 | 16 | 8 | `fn_8011921C(…)->fn_801183BC(…)` |
| 26 | 9 | 15912 | 22 | 18 | `getActorManager_801F856C(…)->findSerialByActorId_801F7A08(…)` |
| 27 | 9 | 14028 | 10 | 10 | `fn_8011921C(…)->fn_801186B0(…)` |
| 28 | 9 | 10124 | 11 | 4 | `fn_800FE294(…)` |
| 29 | 8 | 34168 | 9 | 9 | `addCalc2_801F71A4(…)` |
| 30 | 8 | 25888 | 9 | 8 | `sqrt(…)` |

### Call chains as written, top 15

| # | non-100 fns | their bytes | fns | units | lead |
|---:|---:|---:|---:|---:|---|
| 1 | 121 | 270912 | 241 | 130 | `getActorManager_801F856C()->findActorBySerial_801F666C(serial)` |
| 2 | 24 | 82500 | 35 | 31 | `getGameView_802D6A9C()->isInTransition_802DCD0C()` |
| 3 | 21 | 95888 | 25 | 25 | `getActorManager_801F856C()->fn_801F68E0()` |
| 4 | 20 | 81416 | 25 | 24 | `getActorManager_801F856C()->fn_801F6884()` |
| 5 | 12 | 24588 | 16 | 14 | `getGameView_802D6A9C()->fn_802D79E8(field_0x4, 4.0f, 0.0f, false)` |
| 6 | 11 | 26608 | 15 | 15 | `fn_8020D58C()->addBox(mSerial)` |
| 7 | 11 | 26512 | 16 | 9 | `fn_8011921C()->fn_80118454()` |
| 8 | 9 | 21552 | 17 | 15 | `getGameView_802D6A9C()->fn_802D8050(bit, true, 0xFF)` |
| 9 | 9 | 18700 | 16 | 8 | `fn_8011921C()->fn_801183BC()` |
| 10 | 6 | 19664 | 8 | 3 | `getActorManager_801F856C()->fn_801F6204(0)` |
| 11 | 6 | 12772 | 7 | 6 | `sqrt(square(dx)+ square(dy))` |
| 12 | 6 | 6200 | 15 | 15 | `getGameView_802D6A9C()->fn_802D7440(false)` |
| 13 | 6 | 6176 | 9 | 8 | `getGameView_802D6A9C()->fn_802D7440(0)` |
| 14 | 5 | 12232 | 6 | 1 | `getActorManager_801F856C()->fn_801F7E88()` |
| 15 | 5 | 11572 | 5 | 1 | `getActorManager_801F856C()->fn_801F7B18()` |

### Statements, top 10

| # | non-100 fns | their bytes | fns | units | lead |
|---:|---:|---:|---:|---:|---|
| 1 | 51 | 125844 | 87 | 71 | `fn_801F3668();` |
| 2 | 48 | 102652 | 117 | 64 | `ActorBase_804A5770* actor = getActorManager_801F856C()->findActorBySerial_801F666C(serial);` |
| 3 | 44 | 94284 | 77 | 69 | `JGeometry::TBox2f box(mBox);` |
| 4 | 43 | 114256 | 72 | 64 | `fn_80239914(&box, field_0x4, mSerial);` |
| 5 | 40 | 88536 | 65 | 51 | `field_0x3c.set(0.0f, 0.0f, 0.0f);` |
| 6 | 39 | 85284 | 88 | 61 | `GameView_804A9950* view = getGameView_802D6A9C();` |
| 7 | 34 | 100792 | 51 | 30 | `mPos.add(field_0x3c);` |
| 8 | 34 | 94724 | 65 | 59 | `setScreenFlag_0x30(0xFF, true);` |
| 9 | 33 | 133964 | 55 | 40 | `die_0x24();` |
| 10 | 29 | 107504 | 34 | 32 | `fn_801F2618(NULL, false);` |

### Statement pairs, top 10

| # | non-100 fns | their bytes | fns | units | lead |
|---:|---:|---:|---:|---:|---|
| 1 | 20 | 32684 | 22 | 18 | `s32 end = getActorManager_801F856C()->mActorEnd; for(s32 i = 0;` |
| 2 | 18 | 59456 | 19 | 17 | `fn_801F2618(NULL, false); return;` |
| 3 | 16 | 27812 | 25 | 21 | `s32 layer = field_0x4; GameView_804A9950* view = getGameView_802D6A9C();` |
| 4 | 15 | 29764 | 29 | 23 | `JGeometry::TBox2f box(mBox); box.i.x += mPos.x;` |
| 5 | 14 | 40544 | 30 | 23 | `box.f.y += mPos.y; fn_80239914(&box, field_0x4, mSerial);` |
| 6 | 12 | 18716 | 16 | 16 | `fn_801F3668(); break;` |
| 7 | 11 | 41768 | 13 | 13 | `spawnEmitter_8013CC50(field_0x4, &mPos, 0x117, 0, 1, NULL, NULL, true, 1.0f); spawnEmitter_8013CC50(field_0x4, &mPos, 0x118, 0, 1, NULL, ...` |
| 8 | 10 | 37200 | 16 | 15 | `fn_801F3668(); return;` |
| 9 | 9 | 23188 | 9 | 9 | `s32 count = getActorManager_801F856C()->mActorEnd; for(s32 i = 0;` |
| 10 | 9 | 15724 | 11 | 11 | `JGeometry::TBox2f box(mBox); box.addPos(mPos.x, mPos.y);` |

### Asm blocks of the original (clones.py index), top 10

| # | non-100 fns | their bytes | fns | units | lead |
|---:|---:|---:|---:|---:|---|
| 1 | 71 | 169704 | 101 | 74 | `[10 insns] mullw r3, r3, r0 ; addis r3, r3, 0x3c6f ; subi r0, r3, 0xca1 ...` |
| 2 | 67 | 174900 | 104 | 72 | `[10 insns] stw r0, 0xb4(r4) ; lwz r0, 0xb4(r4) ; srwi r0, r0, 9 ...` |
| 3 | 51 | 142592 | 69 | 52 | `[10 insns] lwz r0, 0xb4(r4) ; srwi r0, r0, 9 ; oris r0, r0, 0x3f80 ...` |
| 4 | 50 | 137796 | 68 | 51 | `[11 insns] stw r0, 0xb4(r4) ; lwz r0, 0xb4(r4) ; srwi r0, r0, 9 ...` |
| 5 | 49 | 77096 | 68 | 47 | `[10 insns] cror eq, lt, eq ; bne .L_800FE0D8 ; b .L_800FE0FC ...` |
| 6 | 43 | 85876 | 84 | 53 | `[10 insns] lfs f0, 0xc(r31) ; fadds f1, f1, f0 ; fadds f0, f2, f0 ...` |
| 7 | 42 | 114300 | 68 | 49 | `[11 insns] subi r0, r3, 0xca1 ; stw r0, 0xb4(r4) ; lwz r0, 0xb4(r4) ...` |
| 8 | 42 | 114300 | 66 | 49 | `[12 insns] addis r3, r3, 0x3c6f ; subi r0, r3, 0xca1 ; stw r0, 0xb4(r4) ...` |
| 9 | 41 | 84328 | 82 | 51 | `[11 insns] stfs f3, 0x98(r1) ; lfs f0, 0xc(r31) ; fadds f1, f1, f0 ...` |
| 10 | 41 | 68836 | 59 | 42 | `[11 insns] fcmpo cr0, f4, f0 ; cror eq, lt, eq ; bne .L_800FE0D8 ...` |
