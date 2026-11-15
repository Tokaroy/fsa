#!/usr/bin/env python3
"""The float-literal pool of a unit (.sdata2), the original's against ours, and what its order says.

  python3 tools/pool.py <unit>             # both pools side by side, who creates each literal, the verdict
  python3 tools/pool.py --all [--json F]   # every unit: same / order only / other values, functions waiting on it
  python3 tools/pool.py <unit> --fix       # search: which statements were a plain function, and where it stood

MWCC writes a float or double literal into .sdata2 the moment it first meets it (TOC.c
createfloatconstant): while it generates a function, for the literals in that function's statements
in order (inlined copies included), then for the constants instruction selection adds (the bias of
an int -> float conversion). A unit's pool is therefore the list of its literals in the order its
functions were GENERATED: with -inline deferred from the bottom of the source file up, which is the
ascending address order of .text.

A function whose instructions are right but whose literal loads read `lbl_8053C2C0` in the original
and `@845` in ours (class `reloc-name`) is waiting for that order: the literal sits at another
offset of our pool. Three causes, and this tool tells them apart:

  order only   Same literals, another order. A run of the original's pool that comes BEFORE the
               literals of the function that uses it was created by another function, generated
               earlier: a plain (non-inline) function that the original inlined into its callers
               and whose own copy the linker dropped. Ours has that code written into the caller,
               or as an `inline` helper, which creates nothing at its own place. Write it as a
               plain function where the pool puts it (below every function generated after it:
               for a leading run, the bottom of the file). --fix searches for the statements.
  other values Ours has a literal the original lacks, or the other way round: a function computes
               with another constant (x * 0.5f for x / 2.0f, a signed for an unsigned conversion),
               or is not written yet. The listing names the first function that uses it.
  functions    The unit's functions are not in descending address order (tools/order_check.py).

A helper found by --fix is proven by two things at once: the pool reaches the original's order, and
every caller still inlines it (no new `bl`, no function that matched breaks). It is saved as a
`.hand.diff`: give it a real name, make it a member where it reads private fields, and keep the
comment that says the linker dropped its own copy.
"""

import argparse
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------- objects

class Obj:
    """What the pool needs from a relocatable PowerPC ELF: .sdata2 objects in order, functions in
    .text order, and for each function the pool objects it loads, in code order."""

    def __init__(self, path, section=".sdata2"):
        b = Path(path).read_bytes()
        if b[:4] != b"\x7fELF":
            raise ValueError(f"{path}: not an ELF object")
        shoff, = struct.unpack_from(">I", b, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from(">HHH", b, 0x2E)
        secs = []
        for i in range(shnum):
            name, typ, _, _, off, size, link, info, _, _ = struct.unpack_from(">IIIIIIIIII", b, shoff + i * shentsize)
            secs.append({"name": name, "type": typ, "off": off, "size": size, "link": link, "info": info})

        def cstr(tab, o):
            e = b.index(b"\0", tab["off"] + o)
            return b[tab["off"] + o:e].decode("latin1")
        for x in secs:
            x["n"] = cstr(secs[shstrndx], x["name"])
        symtab = next((x for x in secs if x["type"] == 2), None)
        self.pool, self.funcs = [], []            # pool: [(offset, size, name, bytes)]
        if symtab is None:
            return
        strtab = secs[symtab["link"]]
        syms = []
        for i in range(symtab["size"] // 16):
            nm, val, size, info, _, shndx = struct.unpack_from(">IIIBBH", b, symtab["off"] + i * 16)
            syms.append((cstr(strtab, nm), val, size, info, shndx))
        pool = []
        for name, val, size, info, shndx in syms:
            if 0 < shndx < len(secs) and secs[shndx]["n"] == section and (info & 0xF) in (0, 1) and size:
                sec = secs[shndx]
                pool.append((val, size, name, b[sec["off"] + val:sec["off"] + val + size]))
        pool.sort()
        byname = {p[2]: k for k, p in enumerate(pool)}
        funcs = sorted((val, size, name, shndx) for name, val, size, info, shndx in syms
                       if (info & 0xF) == 2 and 0 < shndx < len(secs) and secs[shndx]["n"].startswith(".text") and size)
        refs, single = {}, set()
        for r in secs:
            if r["type"] != 4 or not secs[r["info"]]["n"].startswith(".text"):
                continue
            text = secs[r["info"]]
            for i in range(r["size"] // 12):
                off, info, add = struct.unpack_from(">IIi", b, r["off"] + i * 12)
                name, val, size, sinfo, shndx = syms[info >> 8]
                if not (0 < shndx < len(secs)) or secs[shndx]["n"] != section:
                    continue
                k = byname.get(name) if (sinfo & 0xF) != 3 else None
                if k is None:  # through the section symbol: the object that holds the address
                    at = val + add
                    k = next((j for j, p in enumerate(pool) if p[0] <= at < p[0] + p[1]), None)
                if k is not None:
                    refs.setdefault(r["info"], []).append((off, k))
                    word, = struct.unpack_from(">I", b, text["off"] + (off & ~3))
                    if word >> 26 == 48:  # lfs: a float, whatever size the symbol was given
                        single.add(k)
        # a float followed by padding (the last literal of a unit, or one before a double) is an 8-byte
        # symbol in dtk's split: it is the 4-byte float the code loads with lfs
        self.pool = pool = [(o, 4, n, d[:4]) if k in single and sz == 8 and d[4:] == b"\0\0\0\0" else (o, sz, n, d)
                            for k, (o, sz, n, d) in enumerate(pool)]
        for val, size, name, shndx in funcs:  # .text order = the order the functions were generated
            seq = []
            for off, k in sorted(refs.get(shndx, [])):
                if val <= off < val + size and k not in seq:
                    seq.append(k)
            self.funcs.append((name, seq))

    def values(self):
        return [(p[1], p[3]) for p in self.pool]

    def creator(self):
        """pool index -> (name of the first function, in .text order, that loads it; its place in that function)"""
        out = {}
        for fi, (name, seq) in enumerate(self.funcs):
            for pos, k in enumerate(seq):
                out.setdefault(k, (name, fi, pos))
        return out


def show(size, data):
    if size == 4:
        return "%gf" % struct.unpack(">f", data)[0]
    if size == 8:
        if data[:2] == b"\x43\x30":
            return "int->float bias (%s)" % ("signed" if data[4] == 0x80 else "unsigned")
        return "%g (double)" % struct.unpack(">d", data)[0]
    return data[:8].hex() + (".." if size > 8 else "") + f" ({size} B)"


def lcp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def verdict(P, Q):
    """'same' | 'order' | 'values', plus what ours has too much / lacks."""
    if P == Q:
        return "same", [], []
    from collections import Counter
    cp, cq = Counter(P), Counter(Q)
    extra = list((cq - cp).elements())
    missing = list((cp - cq).elements())
    return ("order" if not extra and not missing else "values"), extra, missing


def unit_paths(name):
    for u in json.loads(Path("objdiff.json").read_text())["units"]:
        if u["name"].endswith(name) or u["name"].split("/")[-1] == name.split("/")[-1].replace(".cpp", ""):
            if "base_path" in u and "target_path" in u:
                return u
    raise KeyError(f"no unit {name!r} in objdiff.json")


def short(name, n=40):
    return name if len(name) <= n else name[:n - 2] + ".."


# ---------------------------------------------------------------- the listing

def runs(obj):
    """The pool as runs of literals first loaded by one function: [(function index, name, [pool index])].
    A literal that an earlier function also loads does not end the run of a function that loads it too."""
    cr = obj.creator()
    loads = [set(seq) for _, seq in obj.funcs]
    out = []
    for k in range(len(obj.pool)):
        name, fi, _ = cr.get(k, ("(nothing loads it)", -1, 0))
        if out and (out[-1][0] == fi or (out[-1][0] >= 0 and k in loads[out[-1][0]] and fi < out[-1][0])):
            out[-1][2].append(k)
        else:
            out.append((fi, name, [k]))
    return out


def early_runs(obj):
    """Runs that stand before the literals of a function generated EARLIER than their own user: created by
    a function the linker dropped. [(pool indices, user, the surviving function they come before)]"""
    rs = [r for r in runs(obj) if r[0] >= 0]
    out = []
    for i, (fi, name, ks) in enumerate(rs):
        later = [r for r in rs[i + 1:] if r[0] < fi]
        if later:
            first = min(later, key=lambda r: r[0])
            out.append((ks, name, first[1]))
    return out


def report(name, tgt, ours, verbose=True):
    P, Q = tgt.values(), ours.values()
    kind, extra, missing = verdict(P, Q)
    k = lcp(P, Q)
    print(f"{name}: .sdata2 original {len(P)} literals, ours {len(Q)}; "
          + {"same": "the same pool", "order": f"same literals, another order (equal up to #{k})",
             "values": f"other literals (equal up to #{k})"}[kind])
    if kind == "same":
        return kind
    if extra:
        print("  ours only: " + ", ".join(show(*x) for x in extra[:12]))
    if missing:
        print("  original only: " + ", ".join(show(*x) for x in missing[:12]))
    ct, co = tgt.creator(), ours.creator()
    if verbose:
        print("  original pool (first loaded by, in .text order)          | ours")
        for i in range(max(len(P), len(Q))):
            a = f"+{tgt.pool[i][0]:<3X} {show(*P[i]):26} {short(ct.get(i, ('-',))[0], 28)}" if i < len(P) else ""
            b = f"+{ours.pool[i][0]:<3X} {show(*Q[i]):26} {short(co.get(i, ('-',))[0], 28)}" if i < len(Q) else ""
            print(f"  {'=' if i < len(P) and i < len(Q) and P[i] == Q[i] else '>'} {a:62} | {b}")
    er = early_runs(tgt)
    for ks, user, before in er:
        vals = ", ".join(show(*P[i]) for i in ks[:8]) + (" .." if len(ks) > 8 else "")
        print(f"  early run #{ks[0]}..#{ks[-1]} ({vals}): loaded by {short(user)}, but created before the literals of "
              f"{short(before)}: that code was a plain function generated before it (below it in the source)")
    if kind == "order" and not er:
        print("  the original's order is its functions' .text order: check ours with tools/order_check.py, then the order "
              "of the statements inside the first function that differs")
    return kind


def survey(a):
    units = json.loads(Path("objdiff.json").read_text())["units"]
    st = {}
    try:
        st = json.loads(Path("build/G4SE01/structural.json").read_text())["units"]
    except OSError:
        pass
    rows = []
    for u in units:
        if "base_path" not in u or "target_path" not in u or "/game/" not in u["name"]:
            continue
        try:
            tgt, ours = Obj(u["target_path"]), Obj(u["base_path"])
        except (OSError, ValueError):
            continue
        P, Q = tgt.values(), ours.values()
        kind, extra, missing = verdict(P, Q)
        if kind == "same":
            continue
        fns = st.get(u["name"], {})
        wait = [(f, v[1]) for f, v in fns.items() if v[0] < 100 and v[2] in ("reloc-name", "reloc-name-unverified")]
        part = [(f, v[1]) for f, v in fns.items() if v[0] < 100 and "reloc-name" in v[2] and v[2] not in ("reloc-name", "reloc-name-unverified")]
        rows.append({"unit": u["name"], "kind": kind, "lcp": lcp(P, Q), "original": len(P), "ours": len(Q), "extra": len(extra),
                     "missing": len(missing), "early_runs": len(early_runs(tgt)), "waiting": len(wait),
                     "waiting_bytes": sum(s for _, s in wait), "partly": len(part)})
    rows.sort(key=lambda r: (-r["waiting"], r["unit"]))
    for kind in ("order", "values"):
        sel = [r for r in rows if r["kind"] == kind]
        print(f"{kind}: {len(sel)} units, {sum(r['waiting'] for r in sel)} functions wait on the pool alone "
              f"({sum(r['waiting_bytes'] for r in sel)} B), {sum(r['partly'] for r in sel)} more have it among other differences")
        for r in sel[:a.top]:
            print(f"  {r['unit'].split('/')[-1]:28} original {r['original']:3} ours {r['ours']:3} equal up to #{r['lcp']:<3} "
                  f"ours only {r['extra']:2} original only {r['missing']:2} early runs {r['early_runs']} waiting {r['waiting']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1) + "\n")
    return 0


def main():
    if "--all" not in sys.argv:
        import grind_broker
        grind_broker.maybe_delegate("pool", sys.argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("unit", nargs="?")
    ap.add_argument("--all", action="store_true", help="survey every game unit (objects of the last ninja build)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json")
    ap.add_argument("--fix", action="store_true", help="search for the plain functions the pool order asks for")
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--save", default="build/permute/pool")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.all:
        return survey(a)
    if not a.unit:
        print(__doc__)
        return 0
    import scratch
    unit = scratch.Unit(a.unit)
    try:
        if a.fix:
            import pool_fix
            return pool_fix.run(unit, a)
        obj = unit.compile()
        kind = report(a.unit, Obj(unit.root / unit.target), Obj(obj))
    finally:
        unit.clean()
    return 0 if kind == "same" else 1


if __name__ == "__main__":
    sys.exit(main())
