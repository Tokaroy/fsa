#!/usr/bin/env python3
"""Second progress metric: "structurally matched" (docs/RULES_CARD.md, "Big functions: structure first").

A function below 100 % counts as structurally done when tools/try.py's classifier
(imported here, not copied) calls it regalloc-only, scheduling or
scheduling+regalloc, with or without reloc-name: every instruction the same apart
from register numbers and order. A function whose instructions are identical and
only relocation names differ (class reloc-name) counts too, but only when every
differing relocation pair is verified (below); otherwise it is reloc-name-unverified. "Structurally
close" is missing/extra with |instruction difference| <= 4 and >= 85 %, alone or together with
differences that count as done on their own (a verified reloc-name).

Writes build/G4SE01/structural.json:
  honest      {functions, code}   100 % matched, from report_honest.json
  structural  {functions, code}   functions at 100 % plus structurally done
  done        {functions, code}   the structurally done ones alone
  close       {functions, code}   structurally close ones alone
  classes     {class: [functions, code]}  every non-100 % function
  units       {unit: {function: [match %, bytes, class]}}  non-100 % functions
  weighted    {code, percent, partial, functions}  honest code bytes + size * fuzzy % / 100 for
              every structurally done or close function (report_honest.json's fuzzy_match_percent)
  weighted_classes {"done"|"close": bytes}
  weighted_fns {unit: {function: credited bytes}}  (site_data.py groups these per region)

It diffs every unit with source once (objdiff-cli, the same project directory
and relocation setting as report_honest.json: build/G4SE01/honest, where the
weak-duplicate stripping already applies), in parallel, and caches each unit's
result by the mtimes of its objects (build/G4SE01/structural_cache.json).

A reloc-name difference counts only when every differing relocation pair (both
sides have a relocation, of the same type) is verified one of three ways:
  value    ours @NNN+k or @stringBaseN+k against the target's lbl_XXXXXXXX+m or
           jumptable_XXXXXXXX+m: the bytes each reaches are equal (the shorter a
           prefix of the other) outside relocation fields, neither is .bss/.sbss
           (value_pair). A literal is its value. Data with relocations in it (jump
           tables, address tables) needs the same relocations at the same offsets in
           the compared bytes, each R_PPC_ADDR32 (RELA) with the same addend, and every
           relocation target pair verified in turn: by value (recursively), by
           address, or as the same function: objdiff paired the two functions of
           this unit, at offset 0, or at the same offset into the function being
           classified when its class is a done one (instructions line up one to one;
           a jump table into a missing/extra or different function stays unverified).
  address  both resolve to the same final address, with the same addend
           (Addresses): a target symbol its own object defines sits at the unit's
           splits.txt section start + its offset, and symbols.txt must list that
           name at that address; an undefined one (either side) is the linked
           ELF's (build/G4SE01/fsa_game_code.elf) unique global/weak definition of
           that name, which symbols.txt must not contradict.
  private  a .bss/.sbss pair that is each side's private variable of the paired
           function (private_bss), like a function-local static's init$NNNN guard:
           NOBITS (zero-initialised) in the same section with the same size, the
           target's a lbl_, ours local, every relocation to each in its object from
           inside the function and as many on both sides, the pairing one to one
           across the function, and no other unit's object (target or ours) naming
           the target's symbol. Equal initial bytes alone don't prove the same
           variable (mutable data has an identity), so a bss pair passes only when
           nothing but these identical instructions can ever read or write it.
A symbol our object defines has no proven address (its layout is what is being
measured), so it passes only by value (a bss one only as private): a same-offset literal with another value
(5.0f for 10.0f) or ours const data in .rodata against the target's .data stays
unverified. So does a name the link doesn't define (a provisional fn_80xxxxxx
whose mangling differs from symbols.txt's: the address is only the writer's
claim and the object wouldn't link), a missing relocation, and a differing type
or addend. Such a function is class "... reloc-name-unverified" and is left out of
the structural total. The cache holds the per-object part; the address check
runs on every invocation against the current link and config.

Usage: python3 tools/structural.py [-j N] [--no-cache]
Run after `ninja build/G4SE01/report_honest.json` (ninja runs it as
build/G4SE01/structural.json).
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path("build/G4SE01")
HONEST = OUT / "honest"
REPORT = OUT / "report_honest.json"
CACHE = OUT / "structural_cache.json"
DONE = {"regalloc-only", "scheduling", "scheduling+regalloc", "reloc-name"}
CLOSE_INSNS, CLOSE_PCT = 4, 85.0
VERSION = 5  # bump when the classification changes


LOCAL_LIT = re.compile(r"^@(stringBase)?\d+$")
ORIG_LBL = re.compile(r"^(lbl|jumptable)_[0-9A-Fa-f]+$")


def read_symbols(path):
    """{name: [(bytes or None for NOBITS, section name)]} of an ELF32 big-endian object."""
    import struct
    d = Path(path).read_bytes()
    shoff, = struct.unpack_from(">I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x2E)
    secs = [struct.unpack_from(">IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]

    def cstr(off):
        return d[off:d.index(b"\0", off)].decode(errors="replace")

    shstr = secs[shstrndx][4]
    names = [cstr(shstr + sh[0]) for sh in secs]
    out = {}
    for sh in secs:
        if sh[1] != 2:  # SHT_SYMTAB
            continue
        strtab = secs[sh[6]][4]
        for k in range(sh[5] // 16):
            nm, val, size, info, other, shndx = struct.unpack_from(">IIIBBH", d, sh[4] + k * 16)
            if not nm or shndx == 0 or shndx >= 0xFF00 or (info & 0xF) in (3, 4):
                continue
            tgt = secs[shndx]
            data = None if tgt[1] == 8 else d[tgt[4] + val: tgt[4] + val + size]
            out.setdefault(cstr(strtab + nm), []).append((data, names[shndx]))
    return out


def read_elf(path, relocations=True):
    """{name: [Sym]} of an ELF32 big-endian object or executable, every named symbol
    except files and sections. Sym.data is None for NOBITS and undefined symbols;
    Sym.relocs is the sorted offsets (from the symbol's start) of the relocations
    that patch the symbol's bytes, Sym.rels the same relocations as Rel (empty with
    relocations=False). The dict's .refs is {target name: [(patched section, offset)]}
    for every relocation in the object (a section-symbol target under its section's
    name)."""
    import bisect
    import struct
    d = Path(path).read_bytes()
    shoff, = struct.unpack_from(">I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x2E)
    secs = [struct.unpack_from(">IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]

    def cstr(off):
        return d[off:d.index(b"\0", off)].decode(errors="replace")

    shstr = secs[shstrndx][4]
    names = [cstr(shstr + sh[0]) for sh in secs]
    tables = {}  # symtab section index -> [(name, value, size, info, shndx)]
    for i, sh in enumerate(secs):
        if sh[1] == 2:
            strtab = secs[sh[6]][4]
            tables[i] = [(cstr(strtab + nm) if nm else "", val, size, info, shndx)
                         for nm, val, size, info, other, shndx in
                         (struct.unpack_from(">IIIBBH", d, sh[4] + k * 16) for k in range(sh[5] // 16))]
    relocs = {}  # patched section index -> sorted [(offset, type, target name, addend, target kind)]
    refs = ElfSyms()
    for sh in secs if relocations else ():
        if sh[1] in (4, 9):  # SHT_RELA, SHT_REL
            ent = 12 if sh[1] == 4 else 8
            st = tables.get(sh[6], [])
            for k in range(sh[5] // ent):
                off, info = struct.unpack_from(">II", d, sh[4] + k * ent)
                # REL keeps the addend in the patched bytes: None, never compared as equal
                add = struct.unpack_from(">i", d, sh[4] + k * ent + 8)[0] if sh[1] == 4 else None
                tn, tval, tsz, tinfo, tsh = st[info >> 8] if info >> 8 < len(st) else ("", 0, 0, 0, 0)
                kind = tinfo & 0xF
                if kind == 3:  # section symbol: name it by its section
                    tn = names[tsh] if 0 < tsh < 0xFF00 else ""
                relocs.setdefault(sh[7], []).append(Rel(off, info & 0xFF, tn, add, kind))
                refs.refs.setdefault(tn, []).append((names[sh[7]], off))
    for v in relocs.values():
        v.sort()
    out = refs
    for st in tables.values():
        for nm, val, size, info, shndx in st:
            if not nm or (info & 0xF) in (3, 4):
                continue
            sec = names[shndx] if 0 < shndx < 0xFF00 else None
            data = None
            if sec is not None and secs[shndx][1] != 8:
                data = d[secs[shndx][4] + val: secs[shndx][4] + val + size]
            rs = relocs.get(shndx, [])
            lo, hi = bisect.bisect_left(rs, (val,)), bisect.bisect_left(rs, (val + size,))
            rl = [r._replace(off=r.off - val) for r in rs[lo:hi]]
            out.setdefault(nm, []).append(Sym(shndx, sec, val, size, info >> 4, data,
                                              [r.off for r in rl], info & 0xF, rl))
    return out


class ElfSyms(dict):
    def __init__(self):
        super().__init__()
        self.refs = {}


Sym = namedtuple("Sym", "shndx sec value size bind data relocs kind rels")
Rel = namedtuple("Rel", "off type name addend kind")
R_PPC_ADDR32 = 1
STT_FUNC = 2


def defined(ents):
    return [e for e in ents if e.shndx != 0]


def literal_names(t, o):
    """Ours an anonymous compiler symbol (@NNN, @stringBaseN), the target's dtk's name for
    an anonymous original one (lbl_XXXXXXXX, jumptable_XXXXXXXX)."""
    return bool(LOCAL_LIT.match(o) and ORIG_LBL.match(t))


def value_pair(t, ta, o, oa, tsyms, osyms, ctx=None, seen=None):
    """Ours @NNN(+oa) against the target's lbl_XXXXXXXX(+ta): the bytes each reference
    reaches are equal outside relocation fields (the shorter one a prefix of the
    other), and every relocation in them has its twin at the same offset (type
    R_PPC_ADDR32, same addend) whose target pair is verified in turn (target_pair);
    neither in .bss/.sbss nor empty. The verified pairs' address pairs left for
    verify_addresses as a list ([] when none), or None when it fails."""
    if not literal_names(t, o):
        return None
    seen = set() if seen is None else seen
    if (t, ta, o, oa) in seen:  # a cycle: the bytes on it are already being compared
        return []
    seen.add((t, ta, o, oa))
    for a in defined(tsyms.get(t, [])):
        for b in defined(osyms.get(o, [])):
            if a.data is None or b.data is None or "bss" in a.sec or "bss" in b.sec:
                continue
            da, db = bytearray(a.data[ta:]), bytearray(b.data[oa:])
            n = min(len(da), len(db))
            if not n:
                continue
            ra = [r for r in a.rels if ta <= r.off < ta + n]
            rb = [r for r in b.rels if oa <= r.off < oa + n]
            if [r.off - ta for r in ra] != [r.off - oa for r in rb]:
                continue
            pend = []
            for x, y in zip(ra, rb):
                if (x.type != R_PPC_ADDR32 or y.type != R_PPC_ADDR32 or x.addend is None
                        or x.addend != y.addend or x.off - ta + 4 > n):
                    pend = None
                    break
                da[x.off - ta: x.off - ta + 4] = db[y.off - oa: y.off - oa + 4] = bytes(4)
                p = target_pair(x, y, tsyms, osyms, ctx, seen)
                if p is None:
                    pend = None
                    break
                pend += [q for q in p if q not in pend]
            if pend is not None and da[:n] == db[:n]:
                return pend
    return None


def func_at(syms, rel):
    """(function name, offset) a relocation to a function, or to a section symbol at a
    function's bytes, reaches; None otherwise."""
    if rel.kind == STT_FUNC:
        ents = [e for e in defined(syms.get(rel.name, [])) if e.kind == STT_FUNC]
        return (rel.name, rel.addend) if len(ents) == 1 else None
    if rel.kind == 3:
        hits = [(n, rel.addend - e.value) for n, ents in syms.items() for e in ents
                if e.kind == STT_FUNC and e.sec == rel.name and e.value <= rel.addend < e.value + e.size]
        return hits[0] if len(hits) == 1 else None
    return None


def target_pair(x, y, tsyms, osyms, ctx, seen):
    """A relocation pair inside data value_pair compares: both reach the same function
    of this unit (objdiff paired the two; an offset into it only into the function
    being classified, whose instructions line up), or the targets pass value_pair or
    the address rule. Pending address pairs, or None."""
    fx, fy = func_at(tsyms, x), func_at(osyms, y)
    if fx or fy:
        if not (fx and fy and ctx and fx[1] == fy[1] and ctx["pairs"].get(fx[0]) == fy[0]):
            return None
        # an offset into a function is the same instruction only when the two line up
        # one to one: the function being classified, with no missing/extra or different
        return [] if fx[1] == 0 or ((fx[0], fy[0]) == ctx["self"] and ctx["aligned"]) else None
    if x.kind == 3 or y.kind == 3:
        return None
    v = value_pair(x.name, x.addend, y.name, y.addend, tsyms, osyms, ctx, seen)
    if v is not None:
        return v
    tk, ok = addr_key("target", x.name, tsyms), addr_key("ours", y.name, osyms)
    return None if tk is None or ok is None else [[tk, x.addend, ok, y.addend]]


def private_bss(pairs, ctx, tsyms, osyms):
    """Pairs of .bss/.sbss objects that are each a private variable of the paired
    functions: the same section and size, zero-initialised (NOBITS), one to one across
    the function's pairs, every relocation in each object to it from inside its
    function and as many on both sides, ours local. The target's dtk symbols are
    global, so verify_addresses still checks that no other object names it. {(t, o)}."""
    tf = defined(tsyms.get(ctx["self"][0], []))
    of = defined(osyms.get(ctx["self"][1], []))
    if len(tf) != 1 or len(of) != 1:
        return set()
    tf, of = tf[0], of[0]
    cand = {(t, o) for t, ta, tt, o, oa, ot in pairs if t and o and ta == 0 and oa == 0}
    out = set()
    for t, o in cand:
        if sum(1 for c in cand if c[0] == t) != 1 or sum(1 for c in cand if c[1] == o) != 1:
            continue
        a, b = defined(tsyms.get(t, [])), defined(osyms.get(o, []))
        if len(a) != 1 or len(b) != 1:
            continue
        a, b = a[0], b[0]
        if not (a.data is None and b.data is None and a.sec == b.sec and a.sec in (".bss", ".sbss")
                and a.size == b.size and a.size > 0 and b.bind == 0 and t.startswith("lbl_")):
            continue
        ra, rb = tsyms.refs.get(t, []), osyms.refs.get(o, [])
        ins = lambda refs, f: all(sec == f.sec and f.value <= off < f.value + f.size for sec, off in refs)
        if ra and len(ra) == len(rb) and ins(ra, tf) and ins(rb, of):
            out.add((t, o))
    return out


def addr_key(side, name, syms):
    """What fixes the address a relocation to `name` reaches, independent of other units:
    ["def", section, offset] for a symbol the target object defines (dtk's split:
    its section starts at the unit's splits.txt address), ["und", name] for an
    undefined one (the link resolves it by name). None for a symbol our object
    defines: its address depends on our own, unproven layout."""
    ents = syms.get(name, [])
    d = defined(ents)
    if side == "ours":
        return ["und", name] if ents and not d else None
    if len(d) == 1 and d[0].sec is not None:
        return ["def", d[0].sec, d[0].value, name]
    return ["und", name] if ents and not d else None


def rich_pairs(lsym, rsym, left, right):
    """[target name, addend, reloc type, our name, addend, type] (names None without a
    relocation) for each aligned row where objdiff marks the relocation argument as
    different; the same rows as try.py's reloc_pairs."""
    pairs = []
    for a, b in zip(lsym.get("instructions", []), rsym.get("instructions", [])):
        ia, ib = a.get("instruction"), b.get("instruction")
        if not (ia and ib) or not (a.get("diff_kind") or b.get("diff_kind")):
            continue
        marked = False
        for ins, row in ((ia, a), (ib, b)):
            k = next((n for n, p in enumerate(x for x in ins.get("parts", []) if "arg" in x)
                      if "reloc" in p["arg"]), None)
            marked |= k is not None and k < len(row.get("arg_diff", [])) and bool(row["arg_diff"][k])
        if not marked:
            continue
        rec = []
        for ins, side in ((ia, left), (ib, right)):
            r = ins.get("relocation")
            t = r.get("target_symbol") if r else None
            if r is None or t is None or t >= len(side["symbols"]):
                rec += [None, 0, None]
            else:
                rec += [side["symbols"][t]["name"], int(r.get("addend") or 0), r.get("type")]
        if rec not in pairs:
            pairs.append(rec)
    return pairs


def pending_pairs(pairs, tsyms, osyms, ctx=None):
    """The pairs value_pair can't verify, as [target key, addend, our key, addend] for
    verify_addresses; None when one can't be verified at all (no pairs found, a
    missing relocation, differing relocation types or addends, a symbol our object
    defines). ctx: {"self": (target, our function), "pairs": {target: our function},
    "aligned": its instructions line up one to one (its class is a done one)}."""
    if not pairs:
        return None
    out = []
    bss = private_bss(pairs, ctx, tsyms, osyms) if ctx else set()
    for t, ta, tt, o, oa, ot in pairs:
        if t is None or o is None or tt != ot:
            return None
        if (t, o) in bss:
            key = [["private", t], 0, ["private", o], 0]
            if key not in out:
                out.append(key)
            continue
        v = value_pair(t, ta, o, oa, tsyms, osyms, ctx)
        if v is not None:
            out += [q for q in v if q not in out]
            continue
        tk, ok = addr_key("target", t, tsyms), addr_key("ours", o, osyms)
        if tk is None or ok is None or ta != oa:
            return None
        if [tk, ta, ok, oa] not in out:
            out.append([tk, ta, ok, oa])
    return out


class Addresses:
    """Final addresses: the linked ELF's global and weak symbols (a name defined at two
    addresses resolves to none), symbols.txt (it must agree where it names the symbol),
    and splits.txt's section starts for the target objects' own symbols."""

    def __init__(self, units=()):
        self.units, self.objects = list(units), None
        self.link = {}
        for n, ents in read_elf(OUT / "fsa_game_code.elf", relocations=False).items():
            vals = {e.value for e in ents if e.bind in (1, 2) and e.shndx != 0}
            self.link[n] = vals.pop() if len(vals) == 1 else None
        self.symtxt = {}
        for line in Path("config/G4SE01/symbols.txt").read_text().splitlines():
            m = re.match(r"(\S+) = [^:\s]+:0x([0-9A-Fa-f]+);", line)
            if m:
                self.symtxt.setdefault(m.group(1), set()).add(int(m.group(2), 16))
        self.splits, cur = {}, None
        for line in Path("config/G4SE01/splits.txt").read_text().splitlines():
            if line and not line[0].isspace() and line.endswith(":"):
                cur = self.splits.setdefault(re.sub(r"\.[A-Za-z]+$", "", line[:-1]), {})
            elif cur is not None:
                m = re.match(r"\s+(\S+)\s+start:0x([0-9A-Fa-f]+)\s+end:0x", line)
                if m:
                    cur.setdefault(m.group(1), []).append(int(m.group(2), 16))

    def resolve(self, unit, key):
        if key[0] == "def":
            starts = self.splits.get(unit.split("/", 1)[-1], {}).get(key[1], [])
            a = starts[0] + key[2] if len(starts) == 1 else None
            return a if a is not None and a in self.symtxt.get(key[3], ()) else None
        # a name the link doesn't define (e.g. ours fn_803BBF08 against the target's
        # fn_803BBF08__FP12CARDFileInfoPvPvUlUl) resolves to nothing: the address in a
        # provisional name is only the writer's claim, and the object wouldn't link
        name = key[1]
        a = self.link.get(name)
        if a is not None and name in self.symtxt and a not in self.symtxt[name]:
            return None
        return a

    def private(self, unit, name):
        """No object but the unit's own target object names `name` (dtk exports its
        symbols as global, so another unit could reference it)."""
        if self.objects is None:
            self.objects = [p for u in self.units for p in (u.get("target_path"), u.get("base_path")) if p]
        own = {u.get("target_path") for u in self.units if u["name"] == unit}
        pat = name.encode() + b"\0"
        for p in self.objects:
            if p in own or not Path(p).exists():
                continue
            if pat in Path(p).read_bytes():  # a byte search first; confirm in the symbol table
                if name in read_elf(p, relocations=False):
                    return False
        return True

    def same(self, unit, tkey, okey):
        if tkey[0] == "private":  # private_bss: ours is local, checked in diff_unit
            return okey[0] == "private" and self.private(unit, tkey[1])
        a, b = self.resolve(unit, tkey), self.resolve(unit, okey)
        return a is not None and a == b


def load_try():
    spec = importlib.util.spec_from_file_location("fsa_try", Path(__file__).resolve().parent / "try.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def is_done(cls):
    parts = cls.split(" + ")
    return all(p in DONE for p in parts)


def is_close(cls):
    """missing/extra, alone or with differences that count as done on their own (a verified
    @NNN/lbl_ literal name): a "+ reloc-name" must not cost a near function its credit."""
    parts = cls.split(" + ")
    return parts[0] == "missing/extra" and all(p in DONE for p in parts[1:])


def mtime(p):
    try:
        return os.stat(p).st_mtime_ns
    except OSError:
        return 0


_HERE = Path(__file__).resolve().parent
TOOLS_STAMP = [mtime(_HERE / "try.py"), mtime(_HERE / "structural.py")]


def unit_stamp(u):
    return [mtime(u.get("base_path", "")), mtime(u.get("target_path", "")), VERSION, *TOOLS_STAMP]


def diff_unit(T, u):
    """{function: [pct, bytes, class, detail-count]} for the unit's non-100 % functions."""
    cmd = [T.OBJDIFF, "diff", "-p", str(HONEST), "-u", u["name"], "-o", "-", "-c", T.CONFIG]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{u['name']}: {out.stderr.strip()[-300:]}")
    d = json.loads(out.stdout)
    left, right = d["left"], d["right"]
    tsyms = osyms = None
    fpairs = {s["name"]: right["symbols"][s["target_symbol"]]["name"] for s in left["symbols"]
              if s.get("kind") == "SYMBOL_FUNCTION" and s.get("target_symbol") is not None}
    res = {}
    for s in left["symbols"]:
        if s.get("kind") != "SYMBOL_FUNCTION" or s.get("match_percent") == 100:
            continue
        r = s.get("target_symbol")
        r = right["symbols"][r] if r is not None else None
        size = int(s.get("size", 0))
        if r is None:
            res[s["name"]] = [0.0, size, "missing", 0, []]
            continue
        t, o = T.insn_list(left, s), T.insn_list(right, r)
        rp = T.reloc_pairs(s, r, left, right)
        if rp and tsyms is None:
            tsyms, osyms = read_elf(u["target_path"]), read_elf(u["base_path"])
        cls, _ = T.classify(t, o, rp)
        pending = []
        if "reloc-name" in cls:
            pending = pending_pairs(rich_pairs(s, r, left, right), tsyms, osyms,
                                    {"self": (s["name"], r["name"]), "pairs": fpairs, "aligned": is_done(cls)})
            if pending != []:  # main() may still verify these by address
                cls = cls.replace("reloc-name", "reloc-name-unverified")
        res[s["name"]] = [float(s.get("match_percent") or 0), size, cls, len(o) - len(t), pending or []]
    return res


def verify_addresses(results, units=()):
    """Turn "reloc-name-unverified" into "reloc-name" where every remaining pair
    resolves to the same final address on both sides (Addresses)."""
    addrs = None
    for unit, fns in results.items():
        for v in fns.values():
            if v[4] and "reloc-name-unverified" in v[2]:
                addrs = addrs or Addresses(units)
                if all(addrs.same(unit, tk, ok) for tk, ta, ok, oa in v[4]):
                    v[2] = v[2].replace("reloc-name-unverified", "reloc-name")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=min(16, os.cpu_count() or 4))
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    T = load_try()
    cfg = json.loads((HONEST / "objdiff.json").read_text())
    units = [u for u in cfg["units"] if u.get("base_path") and Path(u["base_path"]).exists()]
    try:
        cache = {} if args.no_cache else json.loads(CACHE.read_text())
    except (OSError, ValueError):
        cache = {}

    todo, results = [], {}
    for u in units:
        c = cache.get(u["name"])
        if c and c["stamp"] == unit_stamp(u):
            results[u["name"]] = c["fns"]
        else:
            todo.append(u)
    with ThreadPoolExecutor(args.j) as ex:
        for u, fns in zip(todo, ex.map(lambda u: diff_unit(T, u), todo)):
            results[u["name"]] = fns
            cache[u["name"]] = {"stamp": unit_stamp(u), "fns": fns}
    live = {u["name"] for u in units}
    CACHE.write_text(json.dumps({k: v for k, v in cache.items() if k in live}, separators=(",", ":")))
    # the cache keeps the per-object result; addresses come from the current link and config
    results = {name: {f: list(v) for f, v in fns.items()} for name, fns in results.items()}
    verify_addresses(results, cfg["units"])

    m = json.loads(REPORT.read_text())["measures"]
    honest = {"functions": m.get("matched_functions", 0), "code": int(m.get("matched_code", 0))}
    fuzzy = {(u["name"], f["name"]): f.get("fuzzy_match_percent", 0.0)
             for u in json.loads(REPORT.read_text())["units"] for f in u.get("functions", [])}
    done, close, classes, out_units = [0, 0], [0, 0], {}, {}
    wfns, wcls = {}, {"done": 0.0, "close": 0.0}

    def credit(unit, fn, size, kind):
        w = size * fuzzy.get((unit, fn), 0.0) / 100
        wfns.setdefault(unit, {})[fn] = round(w, 3)
        wcls[kind] += w
    for name, fns in sorted(results.items()):
        if fns:
            out_units[name] = {f: v[:3] for f, v in fns.items()}
        for fn, (pct, size, cls, ninsn, _) in fns.items():
            c = classes.setdefault(cls, [0, 0])
            c[0] += 1
            c[1] += size
            if is_done(cls):
                done[0] += 1
                done[1] += size
                credit(name, fn, size, "done")
            elif is_close(cls) and abs(ninsn) <= CLOSE_INSNS and pct >= CLOSE_PCT:
                close[0] += 1
                close[1] += size
                credit(name, fn, size, "close")
    partial = wcls["done"] + wcls["close"]
    wcode = honest["code"] + partial
    total_code = int(m["total_code"])
    weighted = {"code": round(wcode, 1), "percent": round(100 * wcode / total_code, 4) if total_code else 0.0,
                "partial": round(partial, 1), "functions": done[0] + close[0]}
    doc = {
        "total_functions": m["total_functions"], "total_code": int(m["total_code"]),
        "honest": honest,
        "structural": {"functions": honest["functions"] + done[0], "code": honest["code"] + done[1]},
        "done": {"functions": done[0], "code": done[1]},
        "close": {"functions": close[0], "code": close[1]},
        "weighted": weighted, "weighted_classes": {k: round(v, 1) for k, v in wcls.items()},
        "weighted_fns": wfns,
        "classes": classes, "units": out_units,
    }
    (OUT / "structural.json").write_text(json.dumps(doc, separators=(",", ":")))
    print(f"structural: {doc['structural']['functions']} / {doc['total_functions']} functions "
          f"(honest {honest['functions']} + {done[0]} structurally done), "
          f"+{close[0]} close; weighted {weighted['percent']:.2f} % of code; {len(todo)}/{len(units)} units diffed")


if __name__ == "__main__":
    main()
