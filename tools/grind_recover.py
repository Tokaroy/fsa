#!/usr/bin/env python3
"""Re-review work whose review never happened (the reviewer had no quota) and integrate what passes.

  python3 tools/grind_recover.py N unit BASE TIP --tier T [--review-tier R]

Takes the unit's commits BASE..TIP (e.g. from the worker's reflog), applies their diff to the
current grind2 in g2-wN, judges it against the unit as it stands now, reviews it as one change
(the reviewer reads every hunk) and integrates it when it survives.
"""
import argparse, json, subprocess, sys, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grind as g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("unit")
    ap.add_argument("base")
    ap.add_argument("tip")
    ap.add_argument("--tier", required=True, choices=g.TIER_NAMES)
    ap.add_argument("--review-tier", choices=g.TIER_NAMES)
    a = ap.parse_args()
    owner, wt, branch = f"g2-w{a.n}", g.WT / f"g2-w{a.n}", f"{g.BRANCH}-w{a.n}"
    diff = g.sh(["git", "diff", a.base, a.tip, "--", "src", "include", "libs", "config"], wt).stdout
    if not g.claim(a.unit, owner, wt):
        sys.exit(f"{a.unit} is claimed")
    try:
        g.reset_to_integration(wt)
        base_head = g.head(wt)
        g.sh(["timeout", "900", "python3", "tools/try.py", a.unit], wt)
        base = g.evaluate(wt, a.unit)
        r = subprocess.run(["git", "apply", "--3way", "--whitespace=nowarn", "-"], cwd=wt, input=diff, capture_output=True, text=True)
        g.sh(["git", "reset", "-q"], wt)
        if r.returncode:
            g.revert(wt)
            sys.exit("does not apply: " + r.stderr.strip()[-300:])
        (wt / "build/grind").mkdir(parents=True, exist_ok=True)
        (wt / "build/grind/task.json").write_text(json.dumps({"unit": a.unit, "fn": None, "addr": None, "base": base}))
        why, ev, notes = g.judge(wt, a.unit, base, None)
        if why:
            g.revert(wt)
            sys.exit("judge: " + why)
        desc = g.describe(base, ev, None)
        g.sh(["git", "add", "-A", "--", "src", "include", "libs", "config/G4SE01/symbols.txt",
              "config/G4SE01/splits.txt", "config/G4SE01/gen_game.tsv"], wt)
        g.sh(["git", "commit", "-qm", f"{a.unit[:-4]}: {desc} (grind, reviewed after the reviewer's quota ran out)\n\n"
              + g.trailer(a.tier)], wt, check=True)
        old, new = g.by_addr(base), g.by_addr(ev)
        fns = [x["name"] for k, x in new.items() if k not in old or abs(x["pct"] - old[k]["pct"]) > g.EPS
               or x["score"] != old[k]["score"]]
        ch = [{"id": "c1", "sha": g.head(wt), "tier": a.tier, "lane": "structure", "fn": "FILE", "fns": fns,
               "size": sum(new[k]["size"] for k in new if new[k]["name"] in fns), "desc": desc}]
        kept = g.run_review(wt, owner, a.unit, base_head, base, ch, types.SimpleNamespace(review_tier=a.review_tier))
        if kept:
            g.stamp_commit(wt, a.unit)
            # credit each function the way a session would, so highlights and stats see it
            g.sh(["timeout", "900", "python3", "tools/try.py", a.unit], wt)
            fin = g.by_addr(g.evaluate(wt, a.unit))
            for k, x in fin.items():
                if k in old and abs(x["pct"] - old[k]["pct"]) > g.EPS:
                    g.log([owner, a.tier, "structure", a.unit, x["name"], x["size"], f"{old[k]['pct']:.2f}", old[k]["score"],
                           f"{x['pct']:.2f}", x["score"], "ACCEPT", f"recovered: {x['name']}: {old[k]['pct']:.2f} % -> {x['pct']:.2f} %"] + [""] * 7)
        result = g.integrate(wt, branch, a.unit) if kept else "rejected in review"
        print(a.unit, desc, "->", result)
    finally:
        g.sh(["python3", "tools/claim.py", "release", a.unit], g.MAIN)


if __name__ == "__main__":
    main()
