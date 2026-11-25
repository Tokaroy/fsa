# Behaviour harness, Dolphin side

Runs the original DOL (A) and a DOL built from the decomp's C (B) in headless
Dolphin with the same per-pad-read input, and writes the sync and state
streams in the port's format (fsaport `docs/HARNESS.md`), so A, B and the
port can be diffed by symbol and field with the port's
`tools/harness_compare.py`.

Pieces:

- Dolphin fork (`../dolphin`, branch `fsa-harness`):
  `Source/Core/Core/HLE/HLE_FsaHarness.cpp`, a fixed HLE hook (`FsaHarnessPad`)
  at the instruction after `bl PADRead` in `JUTGamePad::read`, i.e. PADRead's
  return before PADClamp. It is off unless `FSA_HARNESS=<spec file>` is set.
  At read n it writes the sync points and the state record, then replaces the
  four `PADStatus` (`JUTGamePad::mPadStatus`) with line n of the inputs file
  (or records them when there is no inputs file), then counts n. Every
  address comes from the spec; the format is in the file's header comment.
- `tools/harness_dolphin.py`: resolves the symbols (A: `config/G4SE01/symbols.txt`;
  B: `build/G4SE01/fsa_game_code.elf.MAP`), finds the hook by scanning
  `JUTGamePad::read` for the `bl PADRead`, writes the spec, runs Dolphin under
  `sbg`, collects the streams. Its state tables (`GLOBALS`, `ACTOR_FIELDS`,
  `PLAYER_FIELDS`; the file select screen `lbl_8053ADB0` rows included) mirror the port's `game/src/port/harness_state.cpp` row for
  row, with offsets from `include/game` (big-endian reads from emulated RAM;
  a null pointer on the way gives `null`, as in the port).

## Usage

Scripted (closed-loop) runs, the way to compare with the port:

    python3 tools/harness_dolphin.py run --dol A --script tools/harness_scripts/opening.json --reads 3000 -o runs/a1
    python3 tools/harness_dolphin.py run --dol B --script tools/harness_scripts/opening.json --reads 3000 -o runs/b1
    python3 tools/harness_dolphin.py compare runs/a1 runs/b1 --anchor scene
    python3 tools/harness_dolphin.py compare runs/a1 <fsaport logs/diag/<run>> --anchor scene

The script format and its rules are fsaport `docs/HARNESS.md` "Scripted
input"; `tools/harness_scripts/opening.json` is a copy of the port's. The
hook interprets it at each pad read exactly as the port's `platform/harness.cpp`
does (scene sync point, then the active step: a finished step ends before the
read and the next starts at it, zero-read steps, `step` / `script_end` /
`script_timeout` sync lines, timeouts checked after "finished"), writes its
input to `inputs.jsonl`, puts ticks every 60 reads after the latest anchor
(`scene` or `step`) and a state record at each step start. A script error
(unknown key, button or condition key) stops Dolphin at load with the reason
in `dolphin.log`.

Per-read input files (fixed timings; fine for A vs B, not for the port):

    python3 tools/harness_dolphin.py inputs --script opening --reads 8000 -o in.jsonl
    python3 tools/harness_dolphin.py run --dol A --inputs in.jsonl --reads 8000 -o runs/a1
    python3 tools/harness_dolphin.py build-b --tools ../g2/build     # link B (see below)
    python3 tools/harness_dolphin.py run --dol B --inputs in.jsonl --reads 8000 -o runs/b1
    python3 tools/harness_dolphin.py compare runs/a1 runs/b1          # fsaport tools/harness_compare.py

`run` options: `--reads N` stops after read N-1 (Dolphin exits by itself);
`--tick 1` writes a state record every read instead of every 60th (a full
trace; the port compares at 60); `--shots 900,1300` saves screenshots at
those reads to `OUT/shots/`; without `--inputs` it records Dolphin's own pad
input to `OUT/inputs.jsonl`. `--dol PATH --symbols MAP` runs any other DOL.
A run of 8000 reads takes about 20 s (unlimited speed, single core, JIT).

`inputs --script` takes `KEY@n[:reads]` items (default 6 reads held): keys
`a b x y z l r start up down left right` and `sl sr su sd` (stick full left
/ right / up / down). `opening` is a preset: title, main menu, Hyrulean
Adventure, "create a file?" Yes, then A every 120 reads; it reaches the
adventure's opening narration (mode 7, stage 8, level 3) at read 1920.

Environment: `FSA_DOLPHIN` (default `../dolphin/build/Binaries/dolphin-emu-nogui`
next to the worktrees), `FSA_DISC` (the .rvz), `FSA_DISC_DIR` (default
`harness-disc/` in the project dir, outside every repo), `FSA_DTK`,
`FSA_PORT` (the fsaport checkout, for `compare`).

## Scripted opening (2026-11-24, `opening.json`)

Dolphin A: title at read 350, main menu 509, file select 656, the
create-a-file prompt (step 4) 703, card write done (step 7) 812, player count
1071, stage 8/3 chosen 1204, mode 7/8/3 at 1315, `script_end` 2215. The port
(run `20261124-225612-g807y207` in an fsaport agent worktree's `logs/diag`):
122, 269, 419, 466, 520, 760, 912, 938, 1838.

| Comparison (`--anchor scene`) | anchors | sync | state |
|---|---|---|---|
| A vs A (two runs, also per read; `inputs.jsonl` identical) | 20/20 | 63/63 | 59/59 |
| A vs B | 20/20, every anchor one read earlier in B from the title on | 60/60 | 57/59: `mRandom.seed` at the main menu and player-count scene entries |
| A vs port | 20/20 | 67/67 | 6/66 |

A vs the port: identical through the title; from the main menu on the RNG
seed differs in every record (the seed advances per frame and the menus take
different numbers of reads: e.g. the card write is 69 reads in Dolphin, 14 in
the port). The other differences are at +120 into steps 2 and 9, where one
side has already moved on (requested mode, fade state, stage/level), i.e.
segment length, not behaviour. Through the 900 reads of the opening
narration (step 11) actors, players, camera box, stage view, fade and demo
timer are identical at every offset; only the seed differs.

## How a run is set up (and why)

- **Boot.** Both DOLs boot as an extracted disc tree (`harness-disc/A`, made
  once with `dtk vfs cp`; `harness-disc/B` is `sys/` with B's `main.dol` plus
  a link to A's `files/`). Booting a bare DOL with the disc as
  `Core.DefaultISO` hangs before the first pad read.
- **Fresh user dir per run** (`OUT/user`, removed afterwards unless
  `--keep-user`): an empty memory card, the same SRAM, single-core CPU, DSP
  HLE, no audio output, custom RTC 2026-01-01 00:00:00 (the port's virtual
  epoch), unlimited speed, OpenGL through EGL on the NVIDIA GPU.
- **Port 0 "Always Connected".** The emulated controller has no input device;
  without that option Dolphin reports port 0 unplugged and the game never
  leaves the title screen, whatever is injected into `PADStatus` (the game
  checks the SI side too). Ports 1-3 are empty, as the port's replay assumes.
- **Script mode input**: pad 0 connected, ports 1-3 unplugged, as the port.
- **PADRead's return value** (`sRumbleSupported`) is left as Dolphin's PADRead
  computed it; only the four `PADStatus` are replaced (analogA/B 0, as the port).
- The `start` sync line carries `"emu":"dolphin"`; compare ignores it.
- **Fast disc speed by default** (`--disc-timing` turns Dolphin's disc timing
  model back on). The disc tree puts the files after `main.dol`, so a DOL of
  another size moves every file; with emulated seek times B's loads then took
  a frame or two more or less than A's, and since the RNG
  (`gGameRoot_8053AAF8->mRandom`) advances once per loading frame, every
  enemy spawned on stage entry got different random directions (the Octoroks'
  `mDir_0x98` in stage 1) and everything after diverged. With fast disc speed
  A and B reach every scene at the same read (and the title at read 124, the
  port's is 122) and stage 1 is identical for 25,000 reads.
  `--overclock F` (emulated CPU clock) exists too but did not remove the
  difference: the loads were disc-bound, not CPU-bound.

## Beyond the opening: gameplay scripts (A vs B)

- `castle.json`: `opening.json`, then START through the narration, A through
  the opening cutscene until its demo timer (`fn_8011921C()->field_0x8`)
  stops at 1551 (Link controllable below the Four Sword), then walking in
  four directions, sword swings, a spin attack, walking up to the sword and
  A / grab-and-pull on it, then A every 30 reads (the sword does not come
  out this way; the script ends in `script_timeout` by design). 30,000 reads.
- `stage_S_L.json` (S = 1..6, L = 0): the menus of `opening.json`, then a
  **`set` step** writes GameState's stage and level (`mStage_0x118`,
  `mLevel_0x11c` and the saved copies `field_0x128` / `field_0x12c`, as
  fsaport's `?stage=` does at mode-7 creation) right after the player count
  screen chose stage 8/3, so the loader builds stage S level L instead; then
  30 rounds of a play pattern (walk the four directions and two diagonals,
  B swings, a spin attack, A for lifting / throwing / talking / messages),
  about 25,000 reads (7 minutes of game time). Other stages or lengths:
  `python3 tools/harness_scripts/gen_stage.py S L ROUNDS`.
- `set` (`{"set": {NAME: number, ...}}`, zero reads) follows fsaport
  docs/HARNESS.md "set": GameState's `lbl_80529DEC.mStage_0x118` (alias
  `stage`), `.mLevel_0x11c` (`level`), `.field_0x128`, `.field_0x12c`,
  `gGameRoot_8053AAF8->mRandom.seed` (alias `seed`, written at once) and
  `seed_on_stage` (u32): kept and written to the seed by a second HLE hook
  at the entry of `GameRoot_8049EF20::createModeScreen_80135020` (spec
  `stagehook`, 0x80135020 in A, from the map in B) when r4 (the mode) is 7,
  i.e. before `GameRootSub04_801F856C`'s constructor spawns the stage's
  actors, then disarmed (dolphin.log: `[fsa-harness] seed ... applied`). The
  Dolphin side also accepts any other state global by name. The stage
  scripts set `seed_on_stage` 12345 in the step that sets the stage, so the
  stage starts from the same RNG state however long the menus took (the
  port's menus are shorter than Dolphin's).
- **Localising a divergence**: `run --tick 1` (a state record every read),
  `run --watch GROUP` (extra fields under `"watch"` in the state records,
  e.g. `root` for GameRoot's mode-switch archive loads, `gameover` for
  GameOverScreen_804B17A0; add groups to `WATCH` in the driver), and
  `run --log-reads` (a `[fsa-harness] read N` line per read in dolphin.log).
  The Dolphin fork prints every invalid memory access (what Dolphin reports
  as "the game would have crashed on real hardware") with LR and the stack's
  back chain; `run` writes them symbolised, by read, to `OUT/invalid.txt` and
  names the first one in its summary line. A null pointer B dereferences and
  A doesn't is the fastest lead to a bug.
- `first-diff A B`: the first state record where two runs differ, aligned by
  the scene/step anchors, with the ActorId of each differing actor. Use runs
  made with `--tick 1` for read precision.

### Results (2026-11-24, B = 386 of 387 NonMatching game units from C)

| Script | reads | A vs B (`--anchor scene`) |
|---|---|---|
| opening.json | 3,000 | 20/20 anchors, state 59/59 identical |
| castle.json | 30,000 | 43/43 anchors, state 519/519 identical |
| stage_1_0 / 3_0 / 4_0 / 5_0 / 6_0 | 25,000 each | 716 anchors each, state 809/809 identical |
| stage_1_1 / 5_1 | 25,000 each | state 809/809 identical |
| stage_2_0, stage_3_1, stage_7_0 | 25,000 each | identical until Link's game over leads to the map select (reads 18541 / 11453 / 3480), then B stays in mode 12: the same bug (below) |

Stage 2: Link dies (life 0) at read ~17430: game over (mode 11, then 12);
the script's A presses choose the option that requests mode 6 (map select);
A switches to mode 6 at read 18542, B never does. At read 18541 B makes 25
invalid reads under `MapYaguraWindow_804B1B60::MapYaguraWindow_804B1B60`
(game/map_yagura_window_80443B0C.cpp, structural 92.27 % missing/extra):
`mScreen->search('Nda01')` returns NULL and `PaneCtrl_804AF86C::setPane_80402F04`
/ `moveFromCentre_80402E08` dereference it. The original searches
`'Ndata01'` (`lis r4,0x4e; addi r5,r4,0x6461` / `lis r5,0x7461; addi r6,r5,0x3031`
at 0x80444C00). Call chain: `fn_80137300` < `applyRequestedMode_80135494` <
`createModeScreen_80135020(6)` < `cls_804AF480` ctor < `MapScreen_804B1288` ctor.

## B: linking the decomp's C

`configure.py --non-matching` links only `Equivalent` units, and there are
none, so it gives the original DOL back. `build-b` instead runs configure.py
with `NonMatching` objects linked under `--non-matching` (a patched copy in
`build/harness_configure.py`; configure.py itself is untouched) and links.
A unit whose object breaks the link goes back to asm and the link is retried:
the owner (from a matching build's map, `--owner-map`) of an undefined symbol
the C does not define, a unit with a multiply-defined symbol, and the
referencing unit of an undefined name nobody owns (a C++-mangled call to an
asm function). The excluded units go to `build/harness_b_excluded.txt`.

`build.ninja` regenerates itself with the plain configure.py whenever dtk's
`config.json` (or configure.py) is newer, which silently links the original
objects again (B then equals A byte for byte). `build-b` brings `config.json`
up to date first, checks that the link step lists every included unit's
`build/G4SE01/src/game/*.o`, and refuses a B identical to the original DOL.
After a `git merge` run `build-b` again before any B run.

2026-11-24 (later, after the grind2 merge): 386 of 387 link from C; only
act_fire_rod_fire goes back to asm (`lbl_8046CB88` undefined).

2026-11-24 (first run): 349 of 387 NonMatching game units link from C (plus every
NonMatching JSystem unit); 38 go back to asm after 6 iterations. The first
blockers, by symbol: `gGameRoot_8053AAF8`, `gGameRoot2_8053AB10`
(game_root_sub_04_80139BE8), `gPlayerManager_8053AC90`, `lbl_8053ACA8`
(tu_8022AD64), `gAudioMgr_8053AF80` (audio_mgr_80457DFC), `lbl_8053AAF0`
(act_navi_after_crystal_cutscene_8013394C), `lbl_8046CB88`
(act_fire_rod_fire): data the unit owns in splits.txt but its C does not
define; `lbl_8053ADD0` defined both by game_mode_803DAC3C's C and the
`auto_10_8053ADA0_sbss` split; `fn_801A6160(ActorBase_804A5770*)` called with
C++ linkage from actor_manager_801F6058 but defined as a C symbol.

## Results (2026-11-24, `opening` preset, 8000 reads)

| Comparison | sync | state |
|---|---|---|
| A vs A (two runs) | 141/141 identical | 139/139 identical |
| B vs B (two runs) | 141/141 identical | 139/139 identical |
| A vs B | 137 identical, scene changes at 349/638/1017 in B vs 350/639/1016 in A | 16 identical, 119 differ: only `mRandom.seed` |

A vs B with `--tick 1` (every read, 0..2399): B creates GameRoot (title,
mode 1) at read 349, one read before A; with that one-read shift everything
matches up to read 461, then the RNG seed differs at some reads (its
advance lands one read apart). In the game (from read 1590) the only fields
that differ besides the seed are `field_0x58` at read 1613 (4 vs 0, the fade
state, one read apart). Actors, players, the camera box and the stage view
match at every read. Where B's boot loader saves a frame is the first
lead (the loader's disc-read wait or a unit's timing, not yet traced).
