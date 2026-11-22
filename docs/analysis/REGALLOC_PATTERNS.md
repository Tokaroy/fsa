# Register- and order-only differences: patterns and recipes (2026-11-22)

Scope: the 535 functions that `build/G4SE01/structural.json` (2026-11-20) classes `regalloc-only`,
`scheduling` or `scheduling+regalloc` (with or without `reloc-name`): 295 regalloc-only, 45
scheduling, 195 scheduling+regalloc; 27 are JSystem, the rest game code.

## Method

`python3 tools/regalloc_patterns.py [--build] [--json out] [--show TAG]` diffs every unit that has
such a function (objdiff-cli with `functionRelocDiffs=all`, the instruction lists of tools/try.py),
re-classifies each function and tags it mechanically (the tag list is in the script's docstring):

- registers (regalloc-only): the map target register -> our register over aligned rows; which
  register classes differ (callee-saved / volatile GPR, FPR, CR), and for callee-saved GPRs the
  shape of the permutation (one swap, one rotation, several cycles, an open chain, one target
  register split over several of ours), plus whether the saved-register count differs;
- order (scheduling*): difflib over the rows with registers erased; moved rows are paired, tagged
  by what moved (load, store, const, mr, cmp, float, arith), how far, and whether a move crosses a
  `bl`, or touches only the prologue/epilogue;
- source (regex over our body of the function): a FIXME, a call of an `inline` function of the file
  or of include/game, a loop, a PPC intrinsic called directly (`__fabsf` ...).

About 40 functions were read by hand (fdiff/diag) to pick the tags. A full run takes ~20 s.

## Tags (2026-11-22, after the commits below; 530 still differ)

| tag | n | bytes | examples | likely cause (docs/REGALLOC.md) | honest fix? |
|---|---|---|---|---|---|
| ra:split-saved | 87 | 133916 | act_ending_map_skipper update, act_stop_npc fn_802ED140, bg_rewrite_8029D898 fn_8029DF80 | live ranges of several values coloured in another order: creation order (inline nesting, decl order) | yes, case by case (permute --callees) |
| ra:volatile-only | 70 | 43956 | J3DMatBlock setTevOrder x15, actor_manager_801F6058 fn_801F7AB8 | J3D: struct `operator=` form; game: unclear (decl order tested, no effect) | J3D: no (word-copy cast is banned, docs/COORDINATOR.md); game: open |
| ra:float-only-volatile | 67 | 48728 | act_zol_small_slime_8020C0A8 vfunc_0x88, act_rope vfunc_0x94, actor_manager_801F6058 fn_801F7664 | operand objects of a header inline (abs, square ...) vs a bare intrinsic/expression | yes: **recipe fabs-inline** |
| ra:mixed-int-float | 29 | 39456 | act_vaati_boss fn_801D63D0, act_push_switch update | mixed; often fabs/inline as above plus saved swaps | partly |
| ra:float-only-saved | 25 | 28464 | pane_ctrl_804023D0 scaleKeepCentre_80402CE0, act_zora_lotus fn_8033FC4C | float locals' declaration order / inline copies | likely (decl order) |
| ra:rotate-saved | 16 | 15080 | act_zol_small_slime_8020C0A8 isBlocked_0x4C, vaati_emitters_8021775C fn_80217ED4 | a group coloured in another order: declaration order or one value from a nested inline | yes (REGALLOC rules 2, 4) |
| ra:swap2-saved | 9 | 3592 | tu_801D6CEC __dt__12cls_801D7730, escort_base_801213EC fn_80121ABC | two compiler temporaries of an inlined helper; the same helper matches in another caller | yes, but needs the helper's shape |
| ra:multi-saved / other | 4 | 2512 | act_eyeball_switch vfunc_0x10 | as rotate | yes |
| ra:with-order (sched+regalloc) | 193 | 242440 | | order differences first; registers usually follow | - |
| sc:near-swap | 94 | 97012 | tu_8013AAD4 fn_8013AC54, actor_sound_obj_80455CA4 stopOK | statement order / which operand is named first | yes when the asm shows the order |
| sc:far | 106 | 134364 | tu_801E2540 fn_801E2EE4, J2DTevStage ctors | a load or address computed earlier: value read once in an inline or a named local | usually |
| sc:across-call | 23 | 39216 | act_thwomp_switch update (`&mPos` formed before the distance math, reused at the later call), wander_turn_timer_80217374 | an address/value CSE'd from an inline helper that takes a pointer | yes if the helper is found |
| sc:prologue/epilogue | 14 | 4908 | act_view_mode init, act_shadow_link_2_801C71BC fn_801C8B50, act_tingle_time_up_manager init | `lwz r0,lr` vs `lwz r31` order in the epilogue after identical code, both directions | unexplained (compiler-side) |
| sc:moved-* | | | load 159, store 100, arith 80, const 57, float 39, mr 35, cmp 5, branch 4 | what moved (overlaps the rows above) | |
| reloc-name | 54 | 77636 | act_blizzard_battle init, act_navi vfunc_0x9C | literal pool order on top of the shape (tools/pool.py) | yes |
| src:inline-call | 291 | | | the difference sits in or next to an inlined copy | |
| src:fixme | 371 | | | | |

Cross-tab: of the 530, 291 call a file/header inline and 239 do not; regalloc-only without any
inline call and without a FIXME: 33 functions (the cleanest targets for declaration-order work).

## Recipes

### fabs-inline (tried, committed)

`__fabsf(x)` written bare gives the abs operand the register of a plain temporary; through the
JMath header inline `JMAAbs(x)` (`return __fabsf(input);`) the argument becomes the inline's
parameter object and is coloured in another place: the float registers then match. Evidence:
tu_801D8400 already wrote the same statement as act_frostare_tail with `JMAAbs`, and that function
matched; JMAAbs is used across game code. A natural form (a header inline instead of the
intrinsic), not a trick. Swept every game file that calls `__fabsf` (36), each call kept only if
its function rises and nothing in the unit drops:

| unit | function(s) | before -> after |
|---|---|---|
| act_frostare_tail | vfunc_0x88 | 97.86 -> **100** |
| act_beamos | vfunc_0x90 | 99.05 -> 99.41 |
| act_shadow_link_2_801C5B08 | fn_801C6260, fn_801C5B08, fn_801C5EBC | 99.14 -> 99.45, 97.19 -> 97.41, 98.80 -> 99.23 |
| act_shadow_link_2_801C71BC | fn_801C9234 | 83.81 -> 85.24 |
| tu_801D8400 | vfunc_0x90, fn_801D95F4, fn_801D9960 | 99.70 -> 99.80, 99.09 -> 99.41, 99.45 -> 99.82 |
| tu_801D11FC | fn_801D11FC | 96.15 -> 98.08 |
| tu_801CB270 | fn_801CBB98, fn_801CB85C | 91.06 -> 95.56, 96.55 -> 96.89 |
| act_stone_arrghus_800F7FCC | fn_800F9170 | 84.23 -> 84.60 |
| act_boulder_800F46C0, actor_base_801EE24C, act_other_characters_ending_80362634, act_seesaw_lift | one function each | +0.05 to +0.10 |

13 commits, one per unit, 1 new 100 % function, 17 functions up, none down. Files where a call
stayed `__fabsf` lost something with JMAAbs there (another wrapper, e.g. the `FABS` macro or
`JGeometry::TUtil<f32>::abs`, may be the original's; untested).

### J3D struct copy (trick-only)

The 15 J3DMatBlock setters (`lwz r5,0(r5); addi r0,r4,off; stwx r5,r3,r0`) match only with tp's
`*(u32*)this = *(u32*)&other` operator= (verified again: 412 -> 422 of 431). Rejected by the owner
on 2026-11-02 (docs/COORDINATOR.md "Evaluated and rejected"); not committed.

### Declaration order / inline creation order (honest, untested here)

rotate-saved, swap2-saved, float-only-saved and split-saved: follow docs/REGALLOC.md, start with the
33 inline-free regalloc-only functions (`--show ra:rotate-saved` etc. minus `src:inline-call`), then
`permute.py --callees` for those whose difference sits in an inlined copy. One volatile case
(actor_manager_801F6058 fn_801F7AB8, `count`/`end`) did not move with either declaration order, and dropping
the `end` local made it worse: volatile colouring is not covered by the rules yet.

### Open

- Epilogue `lwz r0` / `lwz r31` order after identical code (14 functions, both directions): the
  cause is in MWCC's scheduler, not visible in the function's source; read `Scheduler.c` in the
  mweppc donor before trying source changes.
- across-call address hoists (act_thwomp_switch): look for the inline helper that takes the
  pointer (a distance-in-XY helper); none exists in include/game yet.
