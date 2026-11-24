#!/usr/bin/env python3
"""Cluster the missing/extra instruction hunks of near-miss functions across units.

  python3 tools/nearmiss_hunks.py [--tsv FILE] [--top 30] [--show 3] [--json OUT]
         [--unit U] [--fn NAME]

Input: a TSV with columns bytes, pct, class, insn_diff, unit, function (as
g2-logs/shared_causes_fns.tsv); without --tsv every game function of class
missing/extra at 90-100 % in build/G4SE01/structural_cache.json. Each unit's
built object is diffed with objdiff-cli (functionRelocDiffs=all, as try.py).

A hunk is a maximal run of rows objdiff could not pair (target-only, ours-only,
replaced). Its instructions are normalised (registers -> r/f, stack offsets ->
SP, symbol names kept), and it is anchored to the nearest call before it on the
target side (the "source line" proxy: debug lines aren't in the objects). Two
clusterings are printed, ranked by the bytes of the functions they touch:

  hunks    identical normalised hunk shapes (- target only / + ours only)
  net      single normalised instructions (and callees) whose count differs
           between target and ours across the whole function: moves cancel,
           so these are the real count drift (e.g. "+bl __ct__TBox2<f>")
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from drift_patterns import CACHE, diff_unit, fn_rows, mn_of

DEFAULT_TSV = None
REG = re.compile(r"\b([rf])(\d+)\b")
SPOFF = re.compile(r"-?0x[0-9a-f]+\(r1\)|-?\d+\(r1\)")
PAIRED = {"DIFF_DELETE", "DIFF_INSERT", "DIFF_REPLACE", "DIFF_OP_MISMATCH"}


def norm(ins):
    s = ins.get("formatted", "")
    s = SPOFF.sub("SP", s)
    s = REG.sub(lambda m: "r" if m.group(1) == "r" and m.group(2) not in ("1", "2", "13") else
                (m.group(0) if m.group(1) == "r" else "f"), s)
    s = re.sub(r"\.\.\.(ro)?data\.\d+|\.\.\.bss\.\d+|(lbl|jumptable|jtbl)_[0-9A-Fa-f]{8}|@\d+", "DATA", s)
    return s


def callee(ins):
    f = ins.get("formatted", "")
    if f.startswith("bl "):
        return f[3:].split("__")[0] if not f[3:].startswith("__") else f[3:].split("__F")[0]
    return None


def hunks(lrows, rrows):
    out, cur, last_call = [], None, "<entry>"
    for a, b in zip(lrows, rrows):
        ka, kb = a.get("diff_kind"), b.get("diff_kind")
        ia, ib = a.get("instruction"), b.get("instruction")
        un = (ka in PAIRED and ia) or (kb in PAIRED and ib)
        if un:
            if cur is None:
                cur = {"anchor": last_call, "minus": [], "plus": [], "at": (ia or ib)["address"]}
            if ia and ka in PAIRED:
                cur["minus"].append(norm(ia))
            if ib and kb in PAIRED:
                cur["plus"].append(norm(ib))
        elif cur is not None:
            out.append(cur)
            cur = None
        if ia and callee(ia):
            last_call = callee(ia)
    if cur:
        out.append(cur)
    return out


def net(lrows, rrows):
    tl = Counter(norm(r["instruction"]) for r in lrows if r.get("instruction"))
    tr = Counter(norm(r["instruction"]) for r in rrows if r.get("instruction"))
    return {k: tr[k] - tl[k] for k in set(tl) | set(tr) if tl[k] != tr[k]}


def targets(tsv, unit=None, fn=None):
    out = []
    if tsv:
        for line in Path(tsv).read_text().splitlines()[1:]:
            b, pct, cls, dl, u, n = line.split("\t")
            out.append((u, n, int(b), float(pct), int(dl)))
    else:
        for u, v in json.loads(CACHE.read_text()).items():
            for n, f in v.get("fns", {}).items():
                if "/game/" in u and f[2].startswith("missing/extra") and 90 <= f[0] < 100:
                    out.append((u, n, f[1], f[0], f[3]))
    return [t for t in out if (not unit or t[0].endswith(unit)) and (not fn or t[1] == fn)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", default=DEFAULT_TSV)
    ap.add_argument("--unit")
    ap.add_argument("--fn")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--min-fns", type=int, default=2)
    ap.add_argument("--json")
    a = ap.parse_args()
    byunit = defaultdict(list)
    for t in targets(a.tsv, a.unit, a.fn):
        byunit[t[0]].append(t)
    H = defaultdict(list)   # hunk shape -> [(unit, fn, bytes, anchor, addr)]
    N = defaultdict(list)   # net key -> [(unit, fn, bytes, delta)]
    dump = []
    for u, ts in sorted(byunit.items()):
        d = diff_unit(u)
        if d is None:
            continue
        for _, n, size, pct, dl in ts:
            rows = fn_rows(d["left"], d["right"], n)
            if rows is None:
                continue
            hs = hunks(*rows)
            nt = net(*rows)
            for h in hs:
                key = (tuple(h["minus"]), tuple(h["plus"]))
                H[key].append((u, n, size, h["anchor"], h["at"]))
            for k, v in nt.items():
                N[k].append((u, n, size, v))
            dump.append({"unit": u, "fn": n, "bytes": size, "pct": pct, "delta": dl,
                         "hunks": hs, "net": nt})

    def rank(D):
        rows = []
        for k, occ in D.items():
            fns = {(o[0], o[1]): o[2] for o in occ}
            if len(fns) >= a.min_fns:
                rows.append((sum(fns.values()), len(fns), len(occ), k, occ))
        return sorted(rows, key=lambda r: (-r[0], -r[1]))

    print(f"{len(dump)} functions")
    print("\n== net count drift (+ ours has more, - target has more), by function bytes")
    for b, nf, no, k, occ in rank(N)[:a.top]:
        tot = sum(o[3] for o in occ)
        print(f"{b:7} {nf:3} fns  sum {tot:+4}  {k}")
        for o in sorted(occ, key=lambda o: -o[2])[:a.show]:
            print(f"          {o[3]:+3} {o[0].split('/')[-1]} {o[1]}")
    print("\n== identical hunks, by function bytes")
    for b, nf, no, k, occ in rank(H)[:a.top]:
        print(f"{b:7} {nf:3} fns {no:3} sites  - {' ; '.join(k[0]) or '()'}   + {' ; '.join(k[1]) or '()'}")
        for o in sorted(occ, key=lambda o: -o[2])[:a.show]:
            print(f"          {o[0].split('/')[-1]} {o[1]} after {o[3]} @{int(o[4]):#x}")
    if a.json:
        Path(a.json).write_text(json.dumps(dump, indent=1))


if __name__ == "__main__":
    main()
