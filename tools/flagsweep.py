#!/usr/bin/env python3
"""Does a unit (or one of its functions) match better under other compiler settings?

  python3 tools/flagsweep.py <unit> [<unit> ...] [--json FILE] [-v]
  python3 tools/flagsweep.py --game [--only-open] [--json FILE]      # every game unit

Compiles each unit as it stands under every variant below (one option or pragma changed at a time)
and scores every function natively (tools/fnscore.cpp, via tools/scratch.py's farm). For each
variant it prints how many functions newly match and how many stop matching, and which.

Reading the result:
  * a variant that makes MANY functions of one unit match and breaks none is evidence that the
    whole file was built with that setting (a per-file option, or a pragma at the top of the file);
  * a variant that fixes ONE function and breaks nothing else in a run of neighbours points at a
    `#pragma` region in the original source. That is a lead, not a licence: docs/RULES_CARD.md
    allows a pragma only with evidence, and one function matching is not evidence by itself;
  * variants that only break things are noise (the expected outcome for most units).

Nothing is written to the source or to configure.py.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scratch  # noqa: E402

# (label, flags to add, flags to drop). The last occurrence of an option wins in mwcc, so most
# variants only add; -inline is dropped first because its settings accumulate.
VARIANTS = [
    ("-O4,s", ["-O4,s"], []),
    ("-O3,p", ["-O3,p"], []),
    ("-O2,p", ["-O2,p"], []),
    ("-inline auto (not deferred)", ["-inline auto"], ["-inline auto,deferred"]),
    ("-inline noauto,deferred", ["-inline noauto,deferred"], ["-inline auto,deferred"]),
    ("-inline off", ["-inline off"], ["-inline auto,deferred"]),
    ("-inline all,deferred", ["-inline all,deferred"], ["-inline auto,deferred"]),
    ("-fp_contract off", ["-fp_contract off"], []),
    ("-use_lmw_stmw off", ["-use_lmw_stmw off"], []),
    ("-Cpp_exceptions off", ["-Cpp_exceptions off"], []),
    ("-char unsigned", ["-char unsigned"], []),
    ("-enum min", ["-enum min"], []),
    ("-RTTI on", ["-RTTI on"], []),
    ("-str noreuse", ["-str noreuse"], []),
    ("-sdata 0 -sdata2 0", ["-sdata 0", "-sdata2 0"], []),
    ("-opt nopeephole", ["-opt nopeephole"], []),
    ("-opt noschedule", ["-opt noschedule"], []),
    ("-opt nostrength", ["-opt nostrength"], []),
    ("-opt noloop", ["-opt noloop"], []),
    ("-opt nopropagation", ["-opt nopropagation"], []),
    ("-opt nocse", ["-opt nocse"], []),
    ("-opt nodeadcode", ["-opt nodeadcode"], []),
    ("-opt nolifetimes", ["-opt nolifetimes"], []),
    ("pragma opt_unroll_loops off", ['-pragma "opt_unroll_loops off"'], []),
    ("pragma inline_bottom_up on", ['-pragma "inline_bottom_up on"'], []),
    ("pragma inline_bottom_up off", ['-pragma "inline_bottom_up off"'], []),
    ("pragma inline_depth(1)", ['-pragma "inline_depth(1)"'], []),
    ("pragma inline_depth(2)", ['-pragma "inline_depth(2)"'], []),
    ("pragma inline_depth(4)", ['-pragma "inline_depth(4)"'], []),
    ("pragma inline_depth(8)", ['-pragma "inline_depth(8)"'], []),
    ("pragma inline_max_auto_size(5)", ['-pragma "inline_max_auto_size(5)"'], []),
    ("pragma inline_max_auto_size(50)", ['-pragma "inline_max_auto_size(50)"'], []),
    ("pragma inline_max_size(100)", ['-pragma "inline_max_size(100)"'], []),
    ("pragma scheduling 603", ['-pragma "scheduling 603"'], []),
    ("pragma scheduling 604", ['-pragma "scheduling 604"'], []),
    ("pragma scheduling off", ['-pragma "scheduling off"'], []),
    ("pragma global_optimizer off", ['-pragma "global_optimizer off"'], []),
    ("pragma optimize_for_size on", ['-pragma "optimize_for_size on"'], []),
    ("pragma no_register_coloring on", ['-pragma "no_register_coloring on"'], []),
    ("pragma opt_strength_reduction_strict on", ['-pragma "opt_strength_reduction_strict on"'], []),
    ("pragma fp_contract off", ['-pragma "fp_contract off"'], []),
    ("pragma ppc_unroll_speculative off", ['-pragma "ppc_unroll_speculative off"'], []),
    ("pragma ppc_opt_bclr off", ['-pragma "ppc_opt_bclr off"'], []),
    ("pragma readonly_strings off", ['-pragma "readonly_strings off"'], []),
]


def sweep(unit_name, verbose=False):
    u = scratch.Unit(unit_name)
    src = u.source()
    try:
        names, res = scratch.farm(u, [src], None, jobs=1)
    except scratch.CompileError as e:
        return {"unit": u.name, "error": str(e)[:200]}
    if isinstance(res[0], Exception):
        return {"unit": u.name, "error": f"does not compile: {res[0]}"}
    base = dict(zip(names, res[0]))
    open_fns = {n for n, s in base.items() if s > 0}

    def one(v):
        label, flags, drop = v
        try:
            _, r = scratch.farm(u, [src], None, flags=flags, drop=drop, jobs=1)
        except scratch.CompileError as e:
            return label, str(e)[:120]
        if isinstance(r[0], Exception):
            return label, str(r[0])[:120]
        return label, dict(zip(names, r[0]))
    out = {"unit": u.name, "functions": len(base), "open": len(open_fns), "variants": []}
    for label, r in scratch.pmap(one, VARIANTS):
        if not isinstance(r, dict):
            if verbose:
                out["variants"].append({"variant": label, "error": r})
            continue
        fixed = sorted(n for n in open_fns if r.get(n) == 0)
        broke = sorted(n for n, s in base.items() if s == 0 and r.get(n, -1) != 0)
        closer = sorted(n for n in open_fns if 0 < r.get(n, -1) < base[n])
        total = sum(s for s in r.values() if s > 0)
        if fixed or (verbose and closer):
            out["variants"].append({"variant": label, "fixed": fixed, "broke": len(broke), "closer": len(closer),
                                    "score": total, "base_score": sum(s for s in base.values() if s > 0)})
    u.clean()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("units", nargs="*")
    ap.add_argument("--game", action="store_true", help="every game/*.cpp unit")
    ap.add_argument("--only-open", action="store_true", help="skip units whose functions all match")
    ap.add_argument("--json")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    units = list(a.units)
    if a.game:
        allu = json.loads(Path("objdiff.json").read_text())["units"]
        units += [u["name"] for u in allu if "/game/" in u["name"] and "base_path" in u
                  and (u.get("metadata") or {}).get("source_path")]
    if not units:
        print(__doc__)
        return 0
    results = []
    for k, name in enumerate(units, 1):
        try:
            r = sweep(name, a.verbose)
        except Exception as e:  # noqa: BLE001
            r = {"unit": name, "error": f"{type(e).__name__}: {e}"[:200]}
        results.append(r)
        if "error" in r:
            if a.verbose or not a.game:
                print(f"[{k}/{len(units)}] {r['unit']}: {r['error']}", flush=True)
            continue
        if a.only_open and not r["open"]:
            continue
        hits = [v for v in r["variants"] if v.get("fixed")]
        if hits or not a.game:
            print(f"[{k}/{len(units)}] {r['unit'].split('/', 1)[-1]}: {r['open']} of {r['functions']} functions open", flush=True)
        for v in sorted(hits, key=lambda v: (v["broke"], -len(v["fixed"]))):
            print(f"    {v['variant']:36} fixes {len(v['fixed']):3}, breaks {v['broke']:3}, {v['closer']:3} closer: "
                  + ", ".join(n.split("__")[0] for n in v["fixed"][:4]) + (" ..." if len(v["fixed"]) > 4 else ""), flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
