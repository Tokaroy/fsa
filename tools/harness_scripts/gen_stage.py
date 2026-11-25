#!/usr/bin/env python3
"""Writes tools/harness_scripts/stage_S_L.json (docs/HARNESS_DOLPHIN.md). Run from the repo root:
    python3 tools/harness_scripts/gen_stage.py S L ROUNDS"""
import json, sys
# Writes tools/harness_scripts/stage_S_L.json: opening.json's menus, then a `set` of the stage
# (Dolphin-side extension), then a fixed play pattern repeated.
S, L, reps = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
d = json.load(open('tools/harness_scripts/opening.json'))
steps = d['steps'][:10]
steps += [
 {"comment": f"10: `set` step (fsaport docs/HARNESS.md): enter stage {S} level {L} instead of the opening, as fsaport's ?stage= does (mStage/mLevel and GameState 0x128/0x12C), and start it from RNG seed 12345 (seed_on_stage: applied when createModeScreen_80135020(7) builds the stage, before its actors spawn), so runs whose menus took different numbers of frames start the stage alike",
  "set": {"lbl_80529DEC.mStage_0x118": S, "lbl_80529DEC.field_0x128": S, "lbl_80529DEC.mLevel_0x11c": L, "lbl_80529DEC.field_0x12c": L,
         "seed_on_stage": 12345}},
 {"comment": "11: the stage loads", "wait": {"mode": 7, "stage": S, "level": L}, "timeout": 3000},
 {"comment": "12: A through the stage's opening messages", "press": ["A"], "every": 30, "until": {"mode": 99}, "timeout": 600},
]
# script_timeout of step 12 would end the script: use wait_reads + taps instead
steps[-1] = {"comment": "12: settle", "wait_reads": 300}
def walk(x, y, n, b=None):
    s = {"stick": [x, y], "reads": n}
    if b: s["buttons"] = b
    return s
def tap(b, n=4): return {"hold": [b], "reads": n}
def gap(n): return {"wait_reads": n}
pattern = [
 walk(127, 0, 90), tap("B"), gap(20), tap("A"), gap(30),
 walk(0, -127, 60), tap("B"), gap(20),
 walk(-127, 0, 120), tap("A"), gap(30), tap("A"), gap(30),
 walk(0, 127, 60), tap("B"), gap(20),
 {"hold": ["B"], "reads": 90}, gap(60),
 walk(90, 90, 60), tap("B"), gap(20), walk(-90, -90, 60), tap("A"), gap(40),
 tap("A"), gap(40),
]
for r in range(reps):
    block = [dict(s) for s in pattern]
    block[0]["comment"] = f"play pattern {r}: walk the four directions and diagonals, B swings, a spin attack, A (lift / throw / talk / messages)"
    steps += block
steps.append({"end": True})
out = f'tools/harness_scripts/stage_{S}_{L}.json'
json.dump({"version": 1, "comment": f"Stage {S} level {L} play (A vs B in Dolphin; uses the Dolphin-side set step). Menus as opening.json. docs/HARNESS_DOLPHIN.md", "steps": steps}, open(out, 'w'), indent=1)
print(out, len(steps))
