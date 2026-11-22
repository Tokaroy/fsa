# Unit flips: units with every function at 100 % but not Matching (2026-11-22)

Found from `build/G4SE01/report_honest.json` on 9c16afc25 (branch an-flips):
26 units whose functions were all at 100 % but which were not
`Object(Matching, ...)` in configure.py. Each was trial-linked with
`python3 tools/link_check.py --unit <unit>`. Every flip was verified with
`python3 configure.py && ninja` (SHA-1 OK) and `python3 tools/gate.py
--all-units` (`gate: ok`).

## Flipped (15)

| Unit | Blocker | Fix | Commit |
|---|---|---|---|
| JSystem/JUtility/JUTDbPrint | 100 % and trial link OK, but mkdd's "likely fakematch" comment on the `enter_` helper fails check_fakematch | JUTReport written the plain way (TWW form), helper removed. Both JUTReport overloads are dead-stripped in FSA, so no counted byte changes | ee7f859fd |
| game/act_random_toggle_switch_8011E96C, act_leever_80182914, act_geldman_80183544, tu_801E5FC8, act_enemy_count_wipe_out_check, act_item_pedestal, act_panel_rewrite_npc_2, act_pot_2_generator, act_princess_zelda_ending, act_link_ending, act_four_person_pull_switch_pswk | extab/extabindex short by the 9 weak `JASMemPool<T>` dtor entries; no weak-dedup evidence recorded yet | Ran `link_check.py --unit` (SHA-1 OK), report then 100 %. Removed a stale `FIXME: 98.39 %` comment in tu_801E5FC8 (draw is 100 %) | 3131000ee |
| game/mg_shooting_screen_80447FAC | .data 96.7 %, .sdata2 66.7 %: dtk sized `__vt__25MgShootingScreen_804B1C58` 0x10 and `lbl_80543DA0` 0x8 (padding swallowed), so the map layout check failed and the weak `__vt__17PaneCtrl_804AF86C` copy (kept in tu_803A60E4.o) and the extab entries weren't stripped | symbols.txt: sizes 0xC and 0x4 (placeholders) | b3cd4ee09 |
| game/save_data_803B8C74 | .rodata 0 % (`lbl_80476548` only declared extern), then the trial DOL was 0x20 short in .bss: card_mgr_803B9940's split .bss had dtk's 8-alignment where its object (thread stack) is 32-aligned | Defined `lbl_80476548` (8 x 10000); splits.txt `align:32` on card_mgr_803B9940's .bss | 19ad72434 |
| game/act_unknown_bgbl_801D7AFC | .sdata2 93.5 %, trial link failed (`lbl_8053F1C8` undefined): dtk put tu_801D8400's first .sdata2 object (a u8, 4) in this unit and started tu_801D8400 at the unaligned 0x8053F1CC | splits.txt boundary moved to 0x8053F1C8; tu_801D8400.cpp defines `lbl_8053F1C8` (its matched code went from 30.3 % to 43.3 %) | 4e5a9975c |

## Not flipped (11)

| Unit | Blocker | Why not fixed |
|---|---|---|
| JSystem/JAudio/System/JASTrack | Links SHA-1 OK, but its `__sinit` placement relies on the FAKEMATCH(crack-pass) order dummy (docs/CRACK_PASS.md) | Needs an honest fix for the weak-section order, not a flip |
| game/tu_80021840 | Trial link differs alone; with JASTrack Matching it links (CRACK_PASS.md) | Waits for JASTrack |
| JSystem/J3DGraphLoader/J3DBinaryFormat, J3DModelSaver | Link SHA-1 OK, 100 %, but configure.py FIXME: pikmin2 emits the weak `J3DShapeMtx::getType` / `getUseMtxIndex` through a fabricated function | Fabricated function, needs a real source construct |
| JSystem/J3DGraphAnimator/J3DAnimation | Trial link differs: FSA emits weak `~J3DAnmBase` before the J3DAnmTransform ctor, ours after (source FIXME) | Weak function order |
| JSystem/JAudio/Utility/JAUAudioMgr | Trial link differs; .sdata2 has an extra 32.0f (`@904`) used only by the weak template `JAUAudience_<...>::mixChannelOut` | Link layout first; the constant then falls in the "data of a weak duplicate" class below |
| JSystem/J3DGraphLoader/J3DAnmLoader | Links SHA-1 OK; .sdata2 66.7 %: `@866` (1.0f) is used only by its weak copy of `J3DAnmCluster::getWeight`, which the map lists as `UNREFERENCED DUPLICATE` (kept in J3DAnimation.o); the map lists `@866` UNUSED | honest_report's dead-data rule requires every referencer to be UNUSED; a discarded weak duplicate isn't. Needs a reviewed rule extension |
| game/act_ice_melted_by_four_players | Links SHA-1 OK; extab/extabindex: an entry for `spawnMeltEmitter`, a non-weak function the original dead-stripped (map: UNUSED) | Rule: non-weak functions' extab entries are never removed |
| game/act_hyrule_castle_barrier | Links SHA-1 OK; same as above for the dead getters getEndPos1/2, getMidPos (+ their .data), and 4 FAKEMATCH(crack-pass) lines | FAKEMATCH, plus the non-weak dead extab rule |
| game/tu_800F39EC, tu_802BA334 | Dead-stripped units: MWLD drops the compiled object (COORDINATOR.md "Dead-stripped units") | Decision on record: stay NonMatching |

## Recurring blocker classes (tool candidates)

1. **No trial evidence recorded** (11 of 15 flips). Units sitting at 100 %
   code with only weak extab short. A sweep that runs `link_check.py --unit`
   for every NonMatching unit whose functions are all 100 %, then lists the
   ones that reach 100 % everywhere, would find these automatically.
2. **dtk split/symbol boundaries off by alignment padding** (mg_shooting_screen_80447FAC,
   save_data_803B8C74, act_unknown_bgbl_801D7AFC): symbol sizes that swallow padding, split
   section alignment below the object's, and boundaries one object off.
   A checker comparing each compiled object's section alignment and symbol
   sizes against splits.txt/symbols.txt would catch them.
3. **Extab/data of dead or discarded functions**: dead-stripped non-weak
   functions' extab (act_ice_melted, act_hyrule_castle_barrier) and
   constants used only by weak duplicates (J3DAnmLoader, JAUAudioMgr).
   Both need a rule decision in honest_report.py/gate.py before any unit
   can flip.
