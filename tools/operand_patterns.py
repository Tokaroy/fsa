#!/usr/bin/env python3
"""Bucket the differing rows of the near-miss functions that the structural metric
gives no credit (try.py classes `different`, `operands`, `same-text`, with or
without a reloc suffix), so that the mechanical part of the gap can be fixed
in bulk and the rest handed on with a reason.

For every such function (from build/G4SE01/structural_cache.json, or the units
named on the command line) it diffs the unit with objdiff-cli under the honest
setting (build/G4SE01/honest, as tools/structural.py does), walks the aligned
rows objdiff marks, and puts each in one bucket:

  opcode <a>/<b>     different mnemonics (lha/lhz: signedness of a field,
                     lbz/lwz: its width, extsb/clrlwi: a char's sign, ...)
  field-offset +k    same opcode, the d(rA) displacement differs by k
  sizeof +k          `li r3, N` before `bl __nw...`: an operator new size
  immediate          li/addi/cmpwi/rlwinm/... value differs
  register           only register numbers differ in that row
  callee             bl/b to a differently named function
  data-reloc         a data relocation to a differently named symbol or addend
  data-value         same symbol name, but its bytes differ between the objects
  base-offset        base-register access into .bss/.sdata (R_PPC_NONE) paired
                     at a different offset: section layout / object order
  marked-same        objdiff marks the row, text and targets are identical

Usage:
  python3 tools/operand_patterns.py [unit ...] [--json out.json] [--fn NAME] [-v]
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("build/G4SE01")
HONEST = OUT / "honest"
CACHE = OUT / "structural_cache.json"
WANT = ("different", "operands", "same-text")
REG = re.compile(r"^(r|f|cr|qr)\d+$")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = load("fsa_try", "try.py")
S = load("fsa_structural", "structural.py")


def parse(side, row, start):
    """(mnemonic, [args], disp index or None, reloc index or None, target name, addend, reloc type)."""
    ins = row.get("instruction") or {}
    mn, args, disp, rel = "", [], None, None
    parts = ins.get("parts", [])
    for k, p in enumerate(parts):
        if "opcode" in p:
            mn = p["opcode"].get("mnemonic", "")
        elif "arg" in p:
            a = p["arg"]
            nxt = parts[k + 1] if k + 1 < len(parts) else {}
            if nxt.get("basic") == "(":
                disp = len(args)
            if "opaque" in a:
                args.append(a["opaque"])
            elif "branch_dest" in a:
                args.append(f"@{int(a['branch_dest']) - start:x}")
            elif "reloc" in a:
                rel = len(args)
                args.append("RELOC")
            else:
                args.append(str(next(iter(a.values()))))
    r = ins.get("relocation")
    tgt = add = rtype = None
    if r is not None:
        t = r.get("target_symbol")
        syms = side["symbols"]
        tgt = syms[t]["name"] if t is not None and t < len(syms) else "?"
        add = int(r.get("addend") or 0)
        rtype = r.get("type_name")
    return mn, args, disp, rel, tgt, add, rtype, ins.get("formatted", "").strip()


def num(x):
    try:
        return int(x, 0)
    except (TypeError, ValueError):
        return None


def bucket(a, b, prev_t, nxt_t, tsyms, osyms):
    """One bucket name (and a detail) for a marked row pair (target a, ours b)."""
    ma, aa, da, ra, ta, xa, rta, fa = a
    mb, ab, db, rb, tb, xb, rtb, fb = b
    if ma != mb:
        return f"opcode {ma}/{mb}", ""
    for k, (x, y) in enumerate(zip(aa, ab)):
        if x == y:
            continue
        if REG.match(x) and REG.match(y):
            continue
        if k == da and num(x) is not None and num(y) is not None:
            if rta == "R_PPC_NONE" or rtb == "R_PPC_NONE":
                return "base-offset", f"{ta}+{xa} vs {tb}+{xb}"
            base = aa[da + 1] if da + 1 < len(aa) else ""
            if base == "r1":
                return f"stack-offset {num(y) - num(x):+#x}", f"{ma} {x} vs {y}"
            return f"field-offset {num(y) - num(x):+#x}", f"{ma} {x} vs {y}"
        if num(x) is not None and num(y) is not None:
            if ma == "li" and aa[0] == "r3" and nxt_t and nxt_t.startswith("__nw"):
                return f"sizeof {num(y) - num(x):+#x}", f"new {x} vs {y}"
            if rta == "R_PPC_NONE" or rtb == "R_PPC_NONE":
                return "base-offset", f"{ta}+{xa} vs {tb}+{xb}"
            return "immediate", f"{ma} {x} vs {y}"
        return "immediate", f"{ma} {x} vs {y}"
    if any(x != y for x, y in zip(aa, ab)):
        return "register", ""
    if (ta, xa) != (tb, xb):
        if ma in ("bl", "b"):
            return "callee", f"{ta} vs {tb}"
        if rta == "R_PPC_NONE" or rtb == "R_PPC_NONE":
            return "base-offset", f"{ta}+{xa} vs {tb}+{xb}"
        return "data-reloc", f"{ta}+{xa} vs {tb}+{xb}"
    if ta is not None and ma not in ("bl", "b"):
        if not S.same_value(tsyms().get(ta, []), osyms().get(tb, [])):
            return "data-value", f"{ta}"
    return "marked-same", fa


def analyse_unit(u, only=None):
    cmd = [T.OBJDIFF, "diff", "-p", str(HONEST), "-u", u["name"], "-o", "-", "-c", T.CONFIG]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        return u["name"], {"error": out.stderr[-300:]}
    d = json.loads(out.stdout)
    L, R = d["left"], d["right"]
    cache = {}

    def tsyms():
        if "t" not in cache:
            cache["t"] = S.read_symbols(u["target_path"])
        return cache["t"]

    def osyms():
        if "o" not in cache:
            cache["o"] = S.read_symbols(u["base_path"])
        return cache["o"]

    res = {}
    for s in L["symbols"]:
        if s.get("kind") != "SYMBOL_FUNCTION" or s.get("match_percent") == 100:
            continue
        if only and s["name"] not in only:
            continue
        ri = s.get("target_symbol")
        if ri is None:
            continue
        r = R["symbols"][ri]
        t, o = T.insn_list(L, s), T.insn_list(R, r)
        cls, _ = T.classify(t, o, T.reloc_pairs(s, r, L, R))
        if cls.split(" ")[0] not in WANT:
            continue
        sa, sb = int(s.get("address", 0)), int(r.get("address", 0))
        rows = list(zip(s.get("instructions", []), r.get("instructions", [])))
        pa = [parse(L, x, sa) for x, _ in rows]
        pb = [parse(R, y, sb) for _, y in rows]
        bk = []
        for k, (x, y) in enumerate(rows):
            if not (x.get("diff_kind") or y.get("diff_kind")):
                continue
            if not (x.get("instruction") and y.get("instruction")):
                bk.append(("insert/delete", ""))
                continue
            nxt = pa[k + 1][4] if k + 1 < len(pa) else None
            name, det = bucket(pa[k], pb[k], None, nxt, tsyms, osyms)
            bk.append((name, det, k, pa[k][7], pb[k][7]))
        res[s["name"]] = {"pct": float(s.get("match_percent") or 0), "size": int(s.get("size", 0)),
                          "class": cls, "rows": bk}
    return u["name"], res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("--fn", action="append")
    ap.add_argument("-v", action="store_true")
    ap.add_argument("-j", type=int, default=16)
    args = ap.parse_args()
    cfg = json.loads((HONEST / "objdiff.json").read_text())
    byname = {u["name"]: u for u in cfg["units"] if u.get("base_path") and Path(u["base_path"]).exists()}
    if args.units:
        names = [n for n in byname if any(n == a or n.endswith("/" + a) for a in args.units)]
    else:
        c = json.loads(CACHE.read_text())
        names = [n for n, v in c.items() if n in byname and
                 any(x[2].split(" ")[0] in WANT for x in v["fns"].values())]
    with ThreadPoolExecutor(args.j) as ex:
        results = dict(ex.map(lambda n: analyse_unit(byname[n], args.fn), names))
    fn_cnt, row_cnt, fn_bytes = Counter(), Counter(), Counter()
    pure = Counter()  # functions whose every marked row falls in one bucket family
    for unit, fns in sorted(results.items()):
        for fn, v in fns.items():
            if fn == "error":
                print(unit, v, file=sys.stderr)
                continue
            fam = Counter(r[0].split(" ")[0] for r in v["rows"] if r[0] != "register")
            for b in fam:
                fn_cnt[b] += 1
                fn_bytes[b] += v["size"]
            for r in v["rows"]:
                row_cnt[r[0].split(" ")[0]] += 1
            if len(fam) == 1:
                pure[next(iter(fam))] += 1
            if args.v:
                print(f"{unit.split('/')[-1]} {fn} {v['pct']:.2f} {v['class']}")
                for r in v["rows"]:
                    if r[0] != "register":
                        print("   ", r[0], "|", r[1], "|", *r[3:] if len(r) > 3 else "")
    print(f"{'bucket':16} {'rows':>6} {'fns':>5} {'bytes':>8} {'only-bucket fns':>15}")
    for b, n in row_cnt.most_common():
        print(f"{b:16} {n:6} {fn_cnt[b]:5} {fn_bytes[b]:8} {pure[b]:15}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- mechanical fix: split placeholders

LBL = re.compile(r"^lbl_([0-9A-F]{8})$")
SYMLINE = re.compile(r"^(\S+) = (\.\w+):0x([0-9A-Fa-f]+); // (.*)$")


def elf_syms(path):
    """[(name, section, offset, size, bind, type)] of the defined symbols of an ELF32 BE object."""
    import struct
    d = Path(path).read_bytes()
    shoff, = struct.unpack_from(">I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x2E)
    secs = [struct.unpack_from(">IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]

    def cstr(off):
        return d[off:d.index(b"\0", off)].decode(errors="replace")
    names = [cstr(secs[shstrndx][4] + sh[0]) for sh in secs]
    out = []
    for sh in secs:
        if sh[1] != 2:
            continue
        strtab = secs[sh[6]][4]
        for k in range(sh[5] // 16):
            nm, val, size, info, other, shndx = struct.unpack_from(">IIIBBH", d, sh[4] + k * 16)
            if not nm or shndx == 0 or shndx >= 0xFF00:
                continue
            out.append((cstr(strtab + nm), names[shndx], val, size, info >> 4, info & 0xF))
    return out


def plan_splits(unit, fns, osyms, tsyms, symlines, known, sec_bytes=None):
    """{placeholder: [new symbols.txt lines]} for target placeholders that our object
    shows to be several objects: every marked row pairs `lbl_X+k` (target) with one
    of our symbols at the same section offset, and our symbols inside the
    placeholder's extent tile it without overlap. Our names are kept only for
    compiler-local `@NNN` objects; weak copies (memPool_) and anything else become
    unnamed `lbl_<addr>` placeholders (docs/COORDINATOR.md, weak memPool_ copies)."""
    tby = {s[0]: s for s in tsyms if s[5] == 1}
    oby = {}
    for s in osyms:
        oby.setdefault(s[0], s)
    refs = defaultdict(set)
    for v in fns.values():
        for r in v["rows"]:
            if r[0] not in ("base-offset", "data-reloc"):
                continue
            a, b = r[1].split(" vs ")
            ta, xa = a.rsplit("+", 1)
            tb, xb = b.rsplit("+", 1)
            if LBL.match(ta) and ta in tby and tb in oby:
                refs[ta].add((int(xa), tb, int(xb)))
    plans = {}
    for ph, rs in refs.items():
        _, sec, toff, tsize, _, _ = tby[ph]
        if ph not in symlines:
            continue
        deltas = {oby[tb][2] + xb - (toff + xa) for xa, tb, xb in rs if oby[tb][1] == sec}
        if len(deltas) != 1 or any(oby[tb][1] != sec for _, tb, _ in rs):
            continue
        delta = deltas.pop()
        if delta:  # our section is laid out differently from the target's: not a naming question
            continue
        inside = sorted({s for s in osyms if s[1] == sec and s[5] in (0, 1) and s[3] > 0
                         and toff + delta <= s[2] < toff + delta + tsize}, key=lambda s: s[2])
        if len(inside) < 2:
            continue
        ok, end = True, toff + delta
        for s in inside:
            if s[2] < end or s[2] + s[3] > toff + delta + tsize:
                ok = False
            end = s[2] + s[3]
        if not ok:
            continue
        if sec_bytes is not None and "bss" not in sec:
            ob, tb_ = sec_bytes(True, sec), sec_bytes(False, sec)
            lo, hi = inside[0][2], inside[-1][2] + inside[-1][3]
            if ob[lo:hi] != tb_[lo - delta:hi - delta]:
                print(f"  {unit}: {ph}: bytes differ, not split", file=sys.stderr)
                continue
        lineno, secname, addr, attrs = symlines[ph]
        lines = []
        first = inside[0][2] - toff - delta
        if first:  # leading bytes our object has no symbol for: the placeholder keeps them
            lines.append(f"{ph} = {secname}:0x{addr:08X}; // type:object size:0x{first:X}")
        for s in inside:
            a = addr + s[2] - toff - delta
            if s[0].startswith("@") and s[4] == 0:
                name, scope = s[0], " scope:local"
            elif s[4] == 2 or s[0].startswith("lbl_"):  # weak copies, placeholders: no name claim
                name, scope = f"lbl_{a:08X}", ""
            else:  # a static or global our source names
                name, scope = s[0], " scope:local" if s[4] == 0 else ""
                if name in known:
                    ok = False
            lines.append(f"{name} = {secname}:0x{a:08X}; // type:object size:0x{s[3]:X}{scope}")
        if ok:
            plans[ph] = (lineno, lines)
    return plans


def read_symlines(path):
    out, known = {}, set()
    for k, l in enumerate(Path(path).read_text().splitlines()):
        m = SYMLINE.match(l)
        if m:
            known.add(m.group(1))
            out[m.group(1)] = (k, m.group(2), int(m.group(3), 16), m.group(4))
    return out, known


def apply_plans(path, plans):
    lines = Path(path).read_text().splitlines()
    for ph, (k, new) in sorted(plans.items(), key=lambda x: -x[1][0]):
        assert lines[k].startswith(ph + " ")
        lines[k:k + 1] = new
    Path(path).write_text("\n".join(lines) + "\n")


def section_bytes(path):
    """{section name: bytes} of an ELF32 BE object."""
    import struct
    d = Path(path).read_bytes()
    shoff, = struct.unpack_from(">I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x2E)
    secs = [struct.unpack_from(">IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]
    str0 = secs[shstrndx][4]
    out = {}
    for sh in secs:
        nm = d[str0 + sh[0]:d.index(b"\0", str0 + sh[0])].decode()
        if sh[1] != 8:
            out[nm] = d[sh[4]:sh[4] + sh[5]]
    return out


# ---------------------------------------------------------------- trial harness

def unit_scores(unit_name):
    """{symbol or 'SECTION name': match %} of one unit (compiled object vs target,
    honest relocation setting, root project as try.py)."""
    cmd = [T.OBJDIFF, "diff", "-p", ".", "-u", unit_name, "-o", "-", "-c", T.CONFIG]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        return None
    d = json.loads(out.stdout)
    res = {}
    for s in d["left"]["symbols"]:
        if s.get("kind") == "SYMBOL_FUNCTION":
            res[s["name"]] = float(s.get("match_percent") or 0) if s.get("target_symbol") is not None else 0.0
    for s in d["left"]["sections"]:
        res["SECTION " + s["name"]] = float(s.get("match_percent") or 0)
    return res


def compile_unit(obj):
    r = subprocess.run(["timeout", "600", "ninja", obj], capture_output=True, text=True)
    return r.returncode == 0


def verdict(before, after, eps=1e-4):
    """(kept?, gains, losses): kept only when something improved and nothing got worse."""
    if after is None:
        return False, [], ["compile/diff failed"]
    gains = [(k, before.get(k), v) for k, v in after.items() if v > before.get(k, 0) + eps]
    losses = [(k, v, after.get(k)) for k, v in before.items() if after.get(k, -1) < v - eps]
    return bool(gains) and not losses, gains, losses
