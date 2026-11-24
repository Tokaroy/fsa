#!/usr/bin/env python3
"""Join the port's runtime diagnostics (fsaport tools/diag, docs/DIAGNOSTICS.md) with
build/G4SE01/structural.json: which functions below 100 % the port actually runs, by class.

Coverage records are keyed by "sym", the mangled name verbatim from config/G4SE01/symbols.txt
("" when the port could not map it; those are skipped). Records are cumulative, so the
merged coverage_by_sym.jsonl (one line per symbol) is the input.

Usage: python3 tools/port_diag.py [--coverage FILE] [--top N] [--tsv OUT]
Default coverage: /bigdata/agent-tom/projects/fsaport/logs/diag/coverage/merged/coverage_by_sym.jsonl
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COV = Path("/bigdata/agent-tom/projects/fsaport/logs/diag/coverage/merged/coverage_by_sym.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", type=Path, default=DEFAULT_COV)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--tsv", type=Path, help="write every live function below 100 %% here")
    args = ap.parse_args()

    st = json.loads((ROOT / "build/G4SE01/structural.json").read_text())
    sfns = st.get("struct_fns", {})
    calls, scene = {}, {}
    for line in args.coverage.read_text().splitlines():
        r = json.loads(line)
        if r.get("sym"):
            calls[r["sym"]] = calls.get(r["sym"], 0) + int(r.get("calls_sum") or r.get("calls") or 0)
            scene.setdefault(r["sym"], r.get("first_scene") or {})

    by = defaultdict(lambda: [0, 0, 0, 0])  # status -> [fns, bytes, live fns, live bytes]
    live = []
    for unit, fns in st["units"].items():
        for fn, (pct, size, cls) in fns.items():
            status = sfns.get(unit, {}).get(fn, "open")
            b = by[status]
            b[0] += 1
            b[1] += size
            n = calls.get(fn, 0)
            if n:
                b[2] += 1
                b[3] += size
                live.append((status, size, pct, cls, n, unit.split("/", 1)[-1], fn, scene.get(fn, {})))

    print(f"coverage: {len(calls)} symbols with calls ({args.coverage})")
    print(f"{'status':8}{'fns':>7}{'bytes':>10}{'live fns':>10}{'live bytes':>12}")
    for k in ("done", "close", "open"):
        f, b, lf, lb = by[k]
        print(f"{k:8}{f:7}{b:10}{lf:10}{lb:12}  ({100 * lb / max(1, b):.0f} % of bytes run)")
    live.sort(key=lambda r: (r[0] != "open", -r[1]))
    print(f"\nlargest live functions that are neither done nor close (top {args.top}):")
    for status, size, pct, cls, n, unit, fn, sc in [r for r in live if r[0] == "open"][:args.top]:
        print(f"  {size:6} {pct:6.2f} %  {cls[:34]:34} calls {n:<9} {unit}  {fn[:60]}")
    if args.tsv:
        with args.tsv.open("w") as f:
            f.write("status\tbytes\tpct\tclass\tcalls\tunit\tfunction\tfirst_scene\n")
            for status, size, pct, cls, n, unit, fn, sc in live:
                f.write(f"{status}\t{size}\t{pct:.2f}\t{cls}\t{n}\t{unit}\t{fn}\t"
                        f"{sc.get('mode', '')}/{sc.get('stage', '')}/{sc.get('level', '')}\n")


if __name__ == "__main__":
    main()
