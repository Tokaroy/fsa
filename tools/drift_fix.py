#!/usr/bin/env python3
"""Try mechanical declaration-type fixes on near-miss game functions.

Usage:
  python3 tools/drift_fix.py --drift drift.json [--pattern ext,cmp-sign,...]
         [--unit game/<unit>.cpp] [--fn <name>] [--rounds 3] [--log out.jsonl]

For each function in the drift_patterns.py JSON (filtered by its patterns),
finds its body in the unit's source and enumerates edits of the TYPE of one
local declaration inside it (e.g. `s16 x` -> `s32 x`, `u8 f` -> `s8 f`,
`f64 t` -> `f32 t`). Each edit is compiled (ninja <unit .o>) and diffed
(objdiff-cli, functionRelocDiffs=all). An edit is kept only if the function's
match % rises and NO symbol of the unit (function or data, by objdiff's
target-side match %) drops. Kept edits are greedy (best per round, then
again on the new baseline). Parameters and fields are not touched here
(a parameter changes the mangled name; a field affects other units).

Nothing is committed; the source is left with the kept edits applied and the
log lists them. Every kept edit still needs a review of the asm: the type
must be the one the loads/compares prove, never one picked to force an
extension (docs/RULES_CARD.md "No tricks").
"""

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from drift_patterns import analyse, net  # noqa: E402

OBJDIFF = "build/tools/objdiff-cli"
TRIAL_DIR = Path("build/drift_trials")
JOBS = 16
TYPED = ("ext", "cvt-sign", "float", "cmp-sign")
CONFIG = "functionRelocDiffs=all"

ALT = {
    "s8": ["u8", "s32"], "u8": ["s8", "s32", "u32"],
    "s16": ["u16", "s32"], "u16": ["s16", "s32", "u32"],
    "s32": ["u32", "s16", "u16", "s8", "u8"], "int": ["u32", "s16", "u16", "u8"],
    "u32": ["s32", "u16", "u8"], "bool": ["u8", "s32", "BOOL"], "BOOL": ["bool", "u8"],
    "f32": ["f64"], "f64": ["f32"], "float": ["double"], "double": ["float"],
}
TYPES = "|".join(sorted(ALT, key=len, reverse=True))
# a local declaration: start of statement (or for-init), type, name, then = ; , [
DECL = re.compile(rf"(?:(?<=[;{{}}(])|^)(\s*(?:const\s+)?)\b({TYPES})\b(\s+)(\w+)(\s*(?:=|;|,|\[))", re.M)


def units_by_name():
    return {u["name"]: u for u in json.loads(Path("objdiff.json").read_text())["units"]}


def find_body(text, mangled):
    """(start, end) of the function's body braces, or None."""
    base = mangled.split("__", 1)[0]
    if base.startswith("__"):  # __ct__, __dt__ etc.: skip
        return None
    cls = None
    m = re.match(re.escape(base) + r"__(\d+)", mangled)
    if m:
        n = int(m.group(1))
        cls = mangled[len(base) + 2 + len(m.group(1)):][:n]
    pat = re.compile(r"(?:\b(\w+)::)?\b" + re.escape(base) + r"\s*\(")
    for mm in pat.finditer(text):
        if cls and mm.group(1) and mm.group(1) != cls:
            continue
        # matching close paren
        i, depth = mm.end() - 1, 0
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        rest = text[i + 1:i + 40]
        r = re.match(r"\s*(const\s*)?\{", rest)
        if not r:
            continue
        # a call statement would not be followed by '{'; make sure the head isn't 'if (...)'
        line_start = text.rfind("\n", 0, mm.start()) + 1
        head = text[line_start:mm.start()]
        if re.search(r"\b(if|while|for|switch|return)\b", head):
            continue
        s = i + 1 + r.end() - 1
        depth, j = 0, s
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return s, j + 1
            j += 1
    return None


def compile_cmd(unit):
    """The unit's MWCC command line (from ninja), split at its source and -o."""
    r = subprocess.run(["ninja", "-t", "commands", unit["base_path"]], capture_output=True, text=True)
    line = r.stdout.strip().splitlines()[-1].split(" && ")[0]
    return line


def measure_trial(unit, cmd, text, k):
    """Compile `text` as a sibling copy of the unit's source into a scratch dir
    (no ninja, so trials can run in parallel) and diff it against the target."""
    src = Path(unit["metadata"]["source_path"])
    trial = src.with_name(f"{src.stem}.drift{k}{src.suffix}")
    out = TRIAL_DIR / str(k)
    out.mkdir(parents=True, exist_ok=True)
    trial.write_text(text)
    try:
        c = cmd.replace(f"-c {src} ", f"-c {trial} ").rsplit(" -o ", 1)[0] + f" -o {out}"
        r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=300)
        if r.returncode:
            return None
        return diff_measure(["-1", unit["target_path"], "-2", str(out / (trial.stem + ".o"))])
    finally:
        trial.unlink()


def measure(unit):
    r = subprocess.run(["timeout", "300", "ninja", unit["base_path"]], capture_output=True, text=True)
    if r.returncode:
        return None
    return diff_measure(["-p", ".", "-u", unit["name"]])


def diff_measure(which):
    r = subprocess.run([OBJDIFF, "diff", *which, "-o", "-", "-c", CONFIG],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    d = json.loads(r.stdout)
    rights = {s["name"]: s for s in d["right"]["symbols"]}
    # data objects only ours has (e.g. a new double literal in .sdata2): a section regression
    # the per-symbol target-side % can't show
    res = {"#extra_data": -sum(1 for s in d["right"]["symbols"]
                               if s.get("kind") == "SYMBOL_OBJECT" and s.get("target_symbol") is None)}
    for s in d["left"]["symbols"]:
        if s.get("match_percent") is not None and s.get("kind") in ("SYMBOL_FUNCTION", "SYMBOL_OBJECT"):
            res[s["name"]] = s["match_percent"]
            if s.get("kind") == "SYMBOL_FUNCTION" and s["name"] in rights:
                c, _ = analyse(s.get("instructions", []), rights[s["name"]].get("instructions", []))
                res["#unpaired:" + s["name"]] = -sum(c.values())  # higher is better
                lr, rr = s.get("instructions", []), rights[s["name"]].get("instructions", [])
                nt = net(lr, rr)
                res["#net:" + s["name"]] = -sum(a + b for a, b in nt.values())
                # the drift a type can explain: extensions, signed/unsigned compares and
                # conversions, float/double ops
                res["#typed:" + s["name"]] = -(sum(sum(nt.get(p, (0, 0))) for p in TYPED)
                                               + c.get("cmp-sign", 0) + c.get("cvt-sign", 0))
    return res


CAST = re.compile(r"\((?:s8|u8|s16|u16|s32|u32|int|f32|f64)\)\s*(?=[\w(])")
FLIT = re.compile(r"(?<![\w.])(\d+\.\d*(?:e[-+]?\d+)?)(f?)(?![\w.])")


def edits_in(text, span):
    """(start, end, old, new, what) edits inside the body: a local's type, a
    redundant integer cast dropped, a float literal's f suffix toggled."""
    s, e = span
    body = text[s:e]
    out = []
    for m in DECL.finditer(body):
        t = m.group(2)
        a = s + m.start(2)
        for alt in ALT[t]:
            out.append((a, a + len(t), t, alt, m.group(4)))
    for m in CAST.finditer(body):
        out.append((s + m.start(), s + m.end(), m.group(0).strip(), "", "(cast dropped)"))
    for m in FLIT.finditer(body):
        a = s + m.start()
        old = m.group(0)
        new = m.group(1) if m.group(2) else m.group(1) + "f"
        out.append((a, a + len(old), old, new, "(literal)"))
    return out


def worse(base, new, eps=1e-6, trial=False):
    # a trial copy's __sinit is named after the copy's file name, so objdiff can't pair it;
    # the ninja confirmation of the real file checks it
    return [k for k, v in base.items() if (not k.startswith("#") or k == "#extra_data")
            and new.get(k, -1e9) < v - eps and not (trial and "__sinit_" in k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drift", required=True)
    ap.add_argument("--pattern", default="")
    ap.add_argument("--unit")
    ap.add_argument("--fn")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    pats = set(p for p in args.pattern.split(",") if p)
    items = json.loads(Path(args.drift).read_text())
    units = units_by_name()
    logf = open(args.log, "a") if args.log else None
    by_unit = {}
    for it in items:
        if args.unit and not it["unit"].endswith(args.unit.replace(".cpp", "")):
            continue
        if args.fn and it["fn"] != args.fn:
            continue
        if pats and not (pats & set(it["patterns"])):
            continue
        by_unit.setdefault(it["unit"], []).append(it)
    for uname, its in sorted(by_unit.items()):
        unit = units.get(uname)
        if not unit or "base_path" not in unit:
            continue
        src = Path((unit.get("metadata") or {}).get("source_path") or "")
        if not src.exists():
            continue
        orig_text = src.read_text()
        cmd = compile_cmd(unit)
        base = measure(unit)
        if base is None:
            print(f"{uname}: baseline build failed", file=sys.stderr)
            continue
        text = orig_text
        for it in sorted(its, key=lambda x: -x["size"]):
            fn = it["fn"]
            if fn not in base:
                continue
            start_pct = base[fn]
            for rnd in range(args.rounds):
                prev_text = text
                span = find_body(text, fn)
                if not span:
                    break
                best = None
                eds = edits_in(text, span)
                trials = [text[:a] + alt + text[b:] for a, b, t, alt, var in eds]
                with ThreadPoolExecutor(JOBS) as ex:
                    ms = list(ex.map(lambda kt: measure_trial(unit, cmd, kt[1], kt[0]),
                                     enumerate(trials)))
                for (a, b, t, alt, var), trial, m in zip(eds, trials, ms):
                    if m is None:
                        continue
                    gain = m.get(fn, 0) - base[fn]
                    # the drift itself must shrink: fewer unpaired instructions, not a register lottery
                    # and the part of it a type explains must shrink, with the whole count drift
                    # not growing: the asm's extensions/compares are what prove the new type
                    fewer = (m.get("#unpaired:" + fn, -1e9) > base.get("#unpaired:" + fn, 0)
                             and m.get("#typed:" + fn, -1e9) > base.get("#typed:" + fn, 0)
                             and m.get("#net:" + fn, -1e9) >= base.get("#net:" + fn, 0))
                    if gain > 1e-6 and fewer and not worse(base, m, trial=True):
                        tot = sum(v for k, v in m.items() if not k.startswith("#")) - sum(v for k, v in base.items() if not k.startswith("#"))
                        if best is None or (gain, tot) > (best[0], best[1]):
                            best = (gain, tot, trial, m, f"{t} {var} -> {alt} {var}")
                if not best:
                    break
                gain, tot, text, _, desc = best
                src.write_text(text)
                m = measure(unit)  # confirm with ninja's own build of the real file
                if m is None or worse(base, m) or m.get(fn, 0) <= base[fn] + 1e-6:
                    print(f"  {fn}: {desc} did not confirm under ninja", flush=True)
                    text = prev_text
                    src.write_text(text)
                    measure(unit)
                    break
                others = {k: (base[k], m[k]) for k in base if not k.startswith("#") and m.get(k, 0) > base[k] + 1e-6 and k != fn}
                rec = {"unit": uname, "fn": fn, "edit": desc, "before": base[fn], "after": m[fn],
                       "unpaired": [-base["#unpaired:" + fn], -m["#unpaired:" + fn]],
                       "net": [-base["#net:" + fn], -m["#net:" + fn]],
                       "typed": [-base["#typed:" + fn], -m["#typed:" + fn]],
                       "others_up": others, "patterns": it["patterns"]}
                print(json.dumps(rec), flush=True)
                if logf:
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                base = m
            if base[fn] > start_pct + 1e-6:
                print(f"  {uname.split('/')[-1]} {fn}: {start_pct:.2f} -> {base[fn]:.2f}", flush=True)
        src.write_text(text)
        measure(unit)  # leave the object matching the source on disk


if __name__ == "__main__":
    main()
