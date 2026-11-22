# Naming fields in rounds

How to continue the field pass (docs/names/METHOD.md "Fields") in rounds that
cheaper agents can run in parallel. Each round owns a **disjoint list of
classes**; rows of one class never go in two rounds.

## Done (round 1, 2026-11-22)

ActorBase_804A5770 (24), Player_804A6F38 (8), GameView_804A9950 (4),
GameRoot_8049EF20 (5): `grep -P '\tfield\t' docs/names/names.tsv`.
EnemyBase_804A4808's own fields were already named (mFlags, mState, ...).

## Picking a round

1. Take classes from the top of the use count that nobody holds (count the
   `field_0x` decls per class body, as in round 1, then the uses in the
   units that define its methods). Next up: the rest of Player_804A6F38
   (~435 left; the 0x3F8-0x404 bytes, 0x1240, 0xD60-0xD70, 0xCE4-0xCF4 are
   the most used), MapScreen_804B1288, ResultScreen_804AF9A0,
   ConnectScreen_804B0F10, GameRootSub24_8016A3AC, GameState_804B0FE0,
   TileMap_804AA858, Camera_804AA9E4, ActorManager_804A5800, then the
   act_* classes.
2. Give a round's classes whole, one class per agent at most, and list them
   in the brief; a class and its base are fine in different rounds (a row
   names the declaring class only).
3. Branch per round off the current tree; the coordinator merges and re-runs
   `python3 tools/rename.py --apply` (rows already applied are "done").

## Doing a round

- Read the class's header and the units that write and read each field.
  Name only what the uses prove (METHOD.md grades); cite `file fn: use`.
  Keep `_0x<off>` as in the old name; m + CamelCase.
- Add rows `addr<TAB>field<TAB>field_0x..<TAB>mName_0x..<TAB>med|low<TAB>yes<TAB>evidence`
  (addr = the class's vtable from symbols.txt).
- `python3 tools/rename.py --kind field` (dry run), then
  `python3 tools/rename.py --kind field --apply` (~10-30 s; prints each
  compile). A failure restores the files and names the error.
- Verify: `python3 configure.py && ninja` (DOL SHA-1 equal to
  config/G4SE01/build.sha1), `python3 tools/names_compare.py BEFORE AFTER`
  (report saved before the rename; no drop), `python3 tools/gate.py
  --all-units`, `python3 tools/gen_game.py --check`, `python3
  tools/names_low.py` if low rows were added.
- Commit manifest + rename together, one commit per batch.

## Rakes

- A field read only as "stored by fn_X" gets no name; neither does a padding
  array (`u8 field_0x2b5[...]`).
- Don't rename by hand: a hand edit is lost to `--revert` and the next
  `--apply`. If the tool fails on a construct, fix the tool.
- Header comments elsewhere that mention another class's placeholder are
  left; docs (`.md`) keep placeholders.
