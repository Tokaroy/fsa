#!/usr/bin/env python3
"""Bucket the instruction-count drift of near-miss functions into patterns.

Usage:
  python3 tools/drift_patterns.py [--min 85] [--max 100] [--json out.json]
         [--unit <unit>] [--fn <name>] [--show N]

Reads build/G4SE01/structural_cache.json ({unit: {"fns": {name: [pct, size,
class, ninsn_delta]}}}), takes the game functions of class missing/extra at
--min..--max %, diffs each unit's built object with objdiff-cli
(functionRelocDiffs=all, as try.py) and looks at the rows objdiff could not
pair: instructions only the target has (missing) and only ours has (extra),
plus paired rows whose opcode differs (replace / op mismatch). Each such
instruction is mapped to a pattern:

  ext        extsh/extsb/clrlwi/rlwinm used as an extension: an integer
             width or signedness (local, parameter, field, return)
  cmp-sign   cmpwi<->cmplwi, cmpw<->cmplw paired: signed vs unsigned compare
  float      fmr/frsp/fctiwz/lfd/stfd/fcmpu vs fcmpo: float vs double
  cvt-sign   xoris 0x8000: an int converted to float as signed vs unsigned
  const      li: a constant materialised (often with bool)
  bool       cntlzw/neg/or/srwi/extrwi/subfic/xori: a materialised bool
  copy       mr: an extra temporary or value kept in a second register
  mem        lwz/stw/lbz/stb/lhz/sth/lfs/stfs/lwzx... (not r1): a reload or a
             store the other side lacks (aliasing, volatile-like, copies)
  stack      loads/stores off r1 that aren't the prologue: a spill or a
             stack temporary
  prologue   stw/lwz/stmw/lmw of r14-r31 at r1, stwu/mflr/mtlr: saved
             registers (a register more or fewer live)
  branch     b/bc/beq/bne/... : branch layout or order
  call       bl/blr/bctrl/mtctr: an inlined vs out-of-line call
  mul        mulli/mullw/slwi/add pairs: multiply vs shift
  addr       addi/addis/lis: an address computed again
  arith      the rest of the integer ALU
  other

Per function the dominant pattern is the one with the most unpaired
instructions. Prints a table (functions where the pattern appears, functions
where it dominates, unpaired bytes) and with --show N the N largest examples
per dominant pattern.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

OBJDIFF = "build/tools/objdiff-cli"
CONFIG = "functionRelocDiffs=all"
CACHE = Path("build/G4SE01/structural_cache.json")

EXT = {"extsh", "extsb", "extsh.", "extsb.", "clrlwi", "clrlwi.", "rlwinm", "rlwinm.", "extrwi"}
FLOAT = {"fmr", "frsp", "fctiwz", "lfd", "stfd", "lfdx", "stfdx", "fcmpu", "fcmpo", "fneg", "fabs",
         "xoris", "lfdu", "stfdu"}
BOOL = {"cntlzw", "neg", "subfic", "xori", "srwi", "srawi", "or", "subfe", "addze", "adde", "subfze"}
CMP = {"cmpwi", "cmplwi", "cmpw", "cmplw"}
CALL = {"bl", "blr", "bctrl", "mtctr", "bctr", "blrl"}
MUL = {"mulli", "mullw", "slwi", "slw", "mulhw", "mulhwu"}
ADDR = {"addi", "addis", "lis", "subi"}
MEMOPS = re.compile(r"^(l|st)(b|h|w|f[sd]|ha|hz|bz|wz|mw)[zux]*$")
SAVED = re.compile(r"^r(1[4-9]|2\d|3[01])$|^f(1[4-9]|2\d|3[01])$")


def mn_of(ins):
    for p in ins.get("parts", []):
        if "opcode" in p:
            return p["opcode"].get("mnemonic", "")
    return ""


def args_of(ins):
    return [next(iter(p["arg"].values())) for p in ins.get("parts", []) if "arg" in p]


def bucket(ins, cmp_pair=False):
    mn = mn_of(ins)
    a = [str(x) for x in args_of(ins)]
    base = mn.rstrip(".")
    if cmp_pair:
        return "cmp-sign"
    if base in ("stwu", "mflr", "mtlr", "stmw", "lmw", "psq_st", "psq_l") and "r1" in a and base.startswith("psq"):
        return "stack"
    if base in ("stwu", "mflr", "mtlr", "stmw", "lmw"):
        return "prologue"
    if MEMOPS.match(base) or base.startswith("psq"):
        if "r1" in a:
            if a and SAVED.match(a[0]) and base in ("stw", "lwz", "stfd", "lfd"):
                return "prologue"
            return "stack"
        if base in ("lfd", "stfd", "lfdx"):
            return "float"
        return "mem"
    if base in EXT:
        return "ext"
    if base == "xoris":
        return "cvt-sign"
    if base in FLOAT or base.startswith("f"):
        return "float"
    if base == "li":
        return "const"
    if base in BOOL:
        return "bool"
    if base == "mr":
        return "copy"
    if base in CMP:
        return "cmp"
    if base in CALL:
        return "call"
    if base.startswith("b"):
        return "branch"
    if base in MUL:
        return "mul"
    if base in ADDR:
        return "addr"
    if base and base[0] in "asnxomr":
        return "arith"
    return "other"


def fn_rows(dl, dr, name):
    L = {s["name"]: s for s in dl["symbols"]}
    R = {s["name"]: s for s in dr["symbols"]}
    if name not in L or name not in R:
        return None
    return L[name].get("instructions", []), R[name].get("instructions", [])


def analyse(lrows, rrows):
    """Counter of pattern -> unpaired instructions, plus (side, mnemonic) list."""
    c = Counter()
    items = []
    for a, b in zip(lrows, rrows):
        ka, kb = a.get("diff_kind"), b.get("diff_kind")
        ia, ib = a.get("instruction"), b.get("instruction")
        if ka == "DIFF_DELETE" and ia:  # target only
            p = bucket(ia)
            c[p] += 1
            items.append(("-", ia.get("formatted", ""), p))
        elif kb == "DIFF_INSERT" and ib:  # ours only
            p = bucket(ib)
            c[p] += 1
            items.append(("+", ib.get("formatted", ""), p))
        elif ka in ("DIFF_REPLACE", "DIFF_OP_MISMATCH") and ia and ib:
            ma, mb = mn_of(ia).rstrip("."), mn_of(ib).rstrip(".")
            if ma in CMP and mb in CMP and ma != mb:
                p = "cmp-sign"
            elif {ma, mb} <= (MUL | {"add"}):
                p = "mul"
            else:
                pa, pb = bucket(ia), bucket(ib)
                p = pa if pa == pb else f"{pa}/{pb}"
                if "/" in p:
                    # a replaced pair counts in both buckets' families; keep the target's
                    p = pa
            c[p] += 1
            items.append(("~", f"{ia.get('formatted','')} | {ib.get('formatted','')}", p))
    return c, items


def net(lrows, rrows):
    """Pattern -> (missing, extra): the multiset difference of the two
    instruction lists by pattern (moves cancel out; only real count drift stays)."""
    tl = Counter(bucket(r["instruction"]) for r in lrows if r.get("instruction"))
    tr = Counter(bucket(r["instruction"]) for r in rrows if r.get("instruction"))
    return {p: (max(tl[p] - tr[p], 0), max(tr[p] - tl[p], 0)) for p in set(tl) | set(tr) if tl[p] != tr[p]}


def candidates(lo, hi, unit=None, fn=None):
    d = json.loads(CACHE.read_text())
    out = defaultdict(list)
    for u, v in d.items():
        if "/game/" not in u or (unit and not u.endswith(unit.replace(".cpp", ""))):
            continue
        for n, f in v.get("fns", {}).items():
            if fn and n != fn:
                continue
            if f[2].startswith("missing/extra") and lo <= f[0] < hi:
                out[u].append((n, f))
    return out


def diff_unit(u):
    r = subprocess.run([OBJDIFF, "diff", "-p", ".", "-u", u, "-o", "-", "-c", CONFIG],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=85)
    ap.add_argument("--max", type=float, default=100)
    ap.add_argument("--unit")
    ap.add_argument("--fn")
    ap.add_argument("--json")
    ap.add_argument("--show", type=int, default=0)
    args = ap.parse_args()
    cands = candidates(args.min, args.max, args.unit, args.fn)
    present, dominant, insns = Counter(), Counter(), Counter()
    dom_bytes = Counter()
    netm, nete, netf = Counter(), Counter(), Counter()
    examples = defaultdict(list)
    results = []
    nfn = 0
    for u, fns in sorted(cands.items()):
        d = diff_unit(u)
        if d is None:
            print(f"{u}: objdiff failed", file=sys.stderr)
            continue
        for n, f in fns:
            rows = fn_rows(d["left"], d["right"], n)
            if rows is None:
                continue
            c, items = analyse(*rows)
            if not c:
                continue
            nt = net(*rows)
            for p, (mi, ex) in nt.items():
                netm[p] += mi
                nete[p] += ex
                netf[p] += 1
            nfn += 1
            for p, k in c.items():
                present[p] += 1
                insns[p] += k
            dom = c.most_common(1)[0][0]
            dominant[dom] += 1
            dom_bytes[dom] += f[1]
            examples[dom].append((f[1], u, n, f[0], f[3], dict(c)))
            results.append({"unit": u, "fn": n, "pct": f[0], "size": f[1], "delta": f[3],
                            "patterns": dict(c), "net": nt, "dominant": dom, "items": items})
    print(f"{nfn} functions (game, missing/extra, {args.min}-{args.max} %)")
    print(f"{'pattern':10} {'fns':>5} {'dominant':>8} {'fn bytes':>9} {'unpaired':>8} {'bytes':>6}")
    for p, _ in insns.most_common():
        print(f"{p:10} {present[p]:5} {dominant[p]:8} {dom_bytes[p]:9} {insns[p]:8} {4 * insns[p]:6}")
    print("\nnet drift (instruction multiset difference; moves cancel):")
    print(f"{'pattern':10} {'fns':>5} {'missing':>8} {'extra':>6} {'bytes':>6}")
    for p, _ in (netm + nete).most_common():
        print(f"{p:10} {netf[p]:5} {netm[p]:8} {nete[p]:6} {4 * (netm[p] + nete[p]):6}")
    for p, ex in examples.items():
        if args.show:
            print(f"\n== {p}")
            for e in sorted(ex, reverse=True)[:args.show]:
                print("  ", e)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
