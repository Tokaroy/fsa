#!/usr/bin/env python3
"""Do the target and our function compute the same values? (dataflow check behind the
structural metric; the port's proposal: a "structurally done" function should do the same
thing, not only use the same instructions.)

For a function whose instructions line up one to one (structural class regalloc-only), each
side is run symbolically, one basic block at a time: every register holds an expression
(constants, the instruction that computed it, memory loads by address expression, call
results), with the operands of commutative operations sorted. Registers at a block's start
are entry symbols; the two sides' entry symbols are paired as the comparison needs them,
one to one per block. What must agree at the same row on both sides:
  stores      address and value
  calls       the argument registers the callee reads (from its mangled signature; all of
              r3-r10 / f1-f8 when it has none) and the callee
  branches    the compared values of a conditional branch
  returns     r3 / f1 at blr
Relocation targets are paired one to one the same way (their names differ between the
objects; tools/structural.py verifies the values they reach). A mismatch means the two programs put different values somewhere: a swap of fields,
operands or arguments that register renaming alone would hide.

Reports; changes nothing. Usage: python3 tools/value_check.py [--unit U] [--all-classes]
(--all-classes also checks scheduling classes positionally, which flags reorderings too.)
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("st", ROOT / "tools/structural.py")
ST = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ST)
T = ST.load_try()

REG = re.compile(r"^(r|f|cr)\d+$")
COMM = {"fmuls", "fadds", "fmul", "fadd", "add", "mullw", "and", "or", "xor", "nand", "nor",
        "ps_mul", "ps_add"}
FMA = {"fmadds", "fmsubs", "fnmadds", "fnmsubs", "fmadd", "fmsub", "fnmadd", "fnmsub"}  # d, a, c, b: a*c+b
ARGS = ["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]
VOLATILE = ["r0"] + [f"r{k}" for k in range(3, 13)] + [f"f{k}" for k in range(0, 14)] + ["cr0", "cr1", "cr5", "cr6", "cr7"]
STORE = re.compile(r"^(stb|sth|stw|stfs|stfd|psq_st|stmw|stwbrx|sthbrx)")
LOAD = re.compile(r"^(lbz|lhz|lha|lwz|lfs|lfd|psq_l|lmw|lwbrx|lhbrx)")


def parse_type(s,i):
    """(kind, next index) of one CW-mangled parameter type: i(nt/pointer), f(loat), v(oid), e(llipsis), s(truct)."""
    while i<len(s) and s[i] in "CVU S": 
        if s[i]=="S": pass
        i+=1
    c=s[i]
    if c in "PR":
        _,j=parse_type(s,i+1); return "i",j
    if c in "fd": return "f",i+1
    if c in "lisbcxw": return "i",i+1
    if c=="v": return "v",i+1
    if c=="e": return "e",i+1
    if c.isdigit():
        m=re.match(r"\d+",s[i:]); n=int(m.group()); j=i+len(m.group())+n
        return "s",j  # struct by value (pointer in reg)
    if c=="Q":
        n=int(s[i+1]); j=i+2
        for _ in range(n):
            m=re.match(r"\d+",s[j:]); j+=len(m.group())+int(m.group())
        return "s",j
    if c=="F":  # function type
        raise ValueError
    if c=="M": raise ValueError
    raise ValueError(c)

def skipname(s,j):
    if s[j]=="Q":
        n=int(s[j+1]); j+=2
        for _ in range(n):
            m=re.match(r"\d+",s[j:]); j+=len(m.group())+int(m.group())
        return j
    m=re.match(r"\d+",s[j:]); return j+len(m.group())+int(m.group())

def _argregs(name):
    if name is None: return None
    name=name.split("+")[0]
    for j0 in [k for k in range(len(name)-1) if name[k:k+2]=="__"]:
        j=j0+2
        if j>=len(name): continue
        member=False
        try:
            if name[j].isdigit() or name[j]=="Q":
                j=skipname(name,j); member=True
                if name[j]=="C": j+=1
            if name[j]!="F": continue
            ps=name[j+1:]
        except Exception:
            continue
        ints=1 if member else 0; flts=0; i=0
        try:
            while i<len(ps):
                if ps[i]=="_": break
                k,i=parse_type(ps,i)
                if k=="v": break
                if k=="e": return None
                if k=="f": flts+=1
                else: ints+=1
        except Exception:
            return None
        return {f"r{3+k}" for k in range(min(ints,8))} | {f"f{1+k}" for k in range(min(flts,8))}
    return None


def argregs(name):
    """The argument registers a callee reads, from its CW-mangled name (member functions add
    r3 for this); None when the name carries no signature (C functions, bctrl)."""
    return _argregs(name)


def sort_key(e):
    """Order for commutative operands that doesn't depend on register names (entry symbols
    are paired between the sides, so their names must not decide the order)."""
    return re.sub(r"\('entry', \d+, '[to]', '[rf]\d+'\)", "E", repr(e))


class Side:
    def __init__(self, tag):
        self.tag = tag
        self.reg = {}

    def val(self, r, block):
        if r not in self.reg:
            self.reg[r] = ("entry", block, self.tag, r)
        return self.reg[r]


def parse(i):
    mn, args, rel = i[0], list(i[1]), (("rel", i[2]) if i[2] else None)
    regs = [a for a in args if REG.match(a)]
    imms = [a for a in args if not REG.match(a) and not a.startswith("@")]
    return mn, args, regs, imms, rel


def mem_addr(side, args, regs, rel, block):
    # d(rA) forms: args like [rS, disp, rA]; indexed forms: [rS, rA, rB]
    base = [side.val(r, block) for r in regs[1:]]
    disp = [a for a in args[1:] if not REG.match(a)]
    return ("addr", tuple(base), tuple(disp), rel)


def run_row(side, i, block, mem):
    """Executes one row; returns the comparison key for this row (or None)."""
    mn, args, regs, imms, rel = parse(i)
    key = None
    if STORE.match(mn):
        v = side.val(regs[0], block) if regs else None
        a = mem_addr(side, args, regs, rel, block)
        mem[a] = v
        key = ("store", mn, a, v)
        if mn.endswith("u") and len(regs) > 1:
            side.reg[regs[-1]] = ("upd", a)
        return key
    if LOAD.match(mn):
        a = mem_addr(side, args, regs, rel, block)
        v = mem.get(a, ("load", mn, a))
        if regs:
            side.reg[regs[0]] = v
        if mn.endswith("u") and len(regs) > 1:
            side.reg[regs[-1]] = ("upd", a)
        return None
    if mn in ("bl", "bctrl", "blrl"):
        used = argregs(i[2]) if mn == "bl" else None
        argv = tuple(side.reg.get(r) if used is None or r in used else None for r in ARGS)
        key = ("call", rel, argv)
        res = ("call", rel, argv)
        for r in VOLATILE:
            side.reg.pop(r, None)
        side.reg["r3"] = ("ret_r3", res)
        side.reg["f1"] = ("ret_f1", res)
        return key
    if mn.startswith(("cmp", "fcmp")):
        ops = [side.val(r, block) for r in regs if not r.startswith("cr")]
        crd = regs[0] if regs and regs[0].startswith("cr") else "cr0"
        side.reg[crd] = ("cmp", mn, tuple(ops), tuple(imms))
        return None
    if mn.startswith("b"):
        if mn in ("blr",):
            return ("ret", side.reg.get("r3"), side.reg.get("f1"))
        crs = [r for r in regs if r.startswith("cr")] or (["cr0"] if mn not in ("b", "bctr") else [])
        conds = []
        for c in crs:
            v = side.val(c, block)
            if mn in ("beq", "bne") and isinstance(v, tuple) and v and v[0] == "cmp":
                v = ("cmp", v[1], tuple(sorted(v[2], key=sort_key)), v[3])  # a == b is b == a
            conds.append(v)
        return ("branch", mn, tuple(conds))
    if not regs:
        return None
    dst, srcs = regs[0], regs[1:]
    if mn in ("rlwimi",):
        srcs = regs
    vals = [side.val(r, block) for r in srcs]
    if mn in COMM and len(vals) >= 2:
        vals = sorted(vals[:2], key=sort_key) + vals[2:]
    elif mn in FMA and len(vals) == 3:  # fmadds d, a, c, b = a*c + b: a and c commute
        a, c, b = vals
        x, y = sorted([a, c], key=sort_key)
        vals = [x, y, b]
    if mn == "mr" or mn == "fmr":
        side.reg[dst] = vals[0]
    else:
        side.reg[dst] = (mn, tuple(vals), tuple(imms), rel)
    if mn.endswith(".") and dst:
        side.reg["cr0"] = ("rc", side.reg[dst])
    return None


def blocks(t):
    starts = {0}
    for k, i in enumerate(t):
        if i[0].startswith("b") and i[0] not in ("bl",):
            starts.add(k + 1)
            for a in i[1]:
                if a.startswith("@"):
                    starts.add(int(a[1:], 16) // 4)
    return sorted(s for s in starts if s < len(t))


def same(a, b, pairs, block):
    """Structural equality with entry symbols paired one to one per block."""
    if isinstance(a, tuple) and isinstance(b, tuple):
        if len(a) == 2 and a[0] == "rel" and len(b) == 2 and b[0] == "rel":
            if str(a[1]).startswith("...") or str(b[1]).startswith("..."):
                return True  # a section symbol (...bss.0) for a base address: its offset is checked by structural.py
            fa, fb = pairs.setdefault("rt", {}), pairs.setdefault("ro", {})
            if fa.get(a[1], b[1]) != b[1] or fb.get(b[1], a[1]) != a[1]:
                return False
            fa[a[1]], fb[b[1]] = b[1], a[1]
            return True
        if a and a[0] == "entry" and b and b[0] == "entry":
            ka, kb = (a[1], a[3]), (b[1], b[3])
            fa, fb = pairs.setdefault("t", {}), pairs.setdefault("o", {})
            if fa.get(ka, kb) != kb or fb.get(kb, ka) != ka:
                return False
            fa[ka], fb[kb] = kb, ka
            return True
        if len(a) != len(b):
            return False
        return all(same(x, y, pairs, block) for x, y in zip(a, b))
    return a == b


def check_fn(t, o):
    if len(t) != len(o) or any(x[0] != y[0] for x, y in zip(t, o)):
        return None
    bad = []
    bs = blocks(t)
    ends = bs[1:] + [len(t)]
    pairs = {}
    for b0, b1 in zip(bs, ends):
        st, so = Side("t"), Side("o")
        mt, mo = {}, {}
        for k in range(b0, b1):
            kt = run_row(st, t[k], b0, mt)
            ko = run_row(so, o[k], b0, mo)
            if kt is None and ko is None:
                continue
            if kt is None or ko is None or not same(kt, ko, pairs, b0):
                bad.append((k, t[k][0], " ".join(t[k][1]), " ".join(o[k][1])))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit")
    ap.add_argument("--all-classes", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()
    d = json.loads((ROOT / "build/G4SE01/structural.json").read_text())
    classes = ("regalloc-only",) + (("scheduling", "scheduling+regalloc") if args.all_classes else ())
    want = {}
    for unit, fns in d["units"].items():
        if args.unit and not unit.endswith(args.unit):
            continue
        for f, v in fns.items():
            if v[2].split(" + ")[0] in classes:
                want.setdefault(unit, []).append(f)
    tot, flagged, out = 0, 0, []
    for unit, fns in want.items():
        res = subprocess.run([T.OBJDIFF, "diff", "-p", str(ST.HONEST), "-u", unit, "-o", "-", "-c", T.CONFIG],
                             capture_output=True, text=True, cwd=ROOT)
        dd = json.loads(res.stdout)
        L, R = dd["left"], dd["right"]
        for s in L["symbols"]:
            if s["name"] not in fns or s.get("target_symbol") is None:
                continue
            r = R["symbols"][s["target_symbol"]]
            bad = check_fn(T.insn_list(L, s), T.insn_list(R, r))
            if bad is None:
                continue
            tot += 1
            if bad:
                flagged += 1
                out.append((len(bad), int(s.get("size", 0)), unit.split("/")[-1], s["name"], bad[:2]))
    out.sort(key=lambda x: (-x[1]))
    print(f"checked {tot} functions ({', '.join(classes)}); values differ in {flagged}")
    for n, size, u, f, b in out[:args.top]:
        print(f"  {size:6} {n:4} rows  {u[:36]:36} {f[:56]}")
        for row in b:
            print(f"         row {row[0]}: {row[1]} {row[2]}  |  {row[3]}")


if __name__ == "__main__":
    main()
