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

2026-11-24: 349 of 387 NonMatching game units link from C (plus every
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
