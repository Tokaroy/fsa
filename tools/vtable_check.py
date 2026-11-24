#!/usr/bin/env python3
"""Compare every vtable in our compiled objects with dtk's split of the original, slot by slot.

For each unit with source (objdiff.json's base_path, against its target_path),
every `__vt__*` object in the original's split is matched by name to our vtable (looked up
in every compiled object, as the vtable may be emitted by another unit) and each 4-byte
slot's relocation target is compared. Names are resolved to addresses through
config/G4SE01/symbols.txt, so a pure renaming (same address) is not reported. Reported:
  SLOT     ours points at a different function than the original (typically the base
           class's default where the class overrides it: a missing `virtual`)
  MISSING  the original's vtable is not emitted by any of our objects
  SIZE     one vtable has slots past the other's end (padding dtk counts is ignored)
Usage: python3 tools/vtable_check.py [unit-substring...]   Exit 1 if anything is reported.
"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "build/G4SE01"


def read_elf(path):
    """Return {vtable name: (size, {slot offset: (symbol, addend)})}."""
    d = path.read_bytes()
    shoff, = struct.unpack('>I', d[0x20:0x24])
    shnum, shstrndx = struct.unpack('>HH', d[0x30:0x34])
    sh = [struct.unpack('>IIIIIIIIII', d[shoff + i * 40:shoff + i * 40 + 40]) for i in range(shnum)]

    def cstr(off):
        return d[off:d.index(b'\0', off)].decode('latin1')

    symtab = next((s for s in sh if s[1] == 2), None)
    if symtab is None:
        return {}
    strtab = sh[symtab[6]][4]
    syms = []
    for o in range(symtab[4], symtab[4] + symtab[5], 16):
        nm, val, sz, info, _, shn = struct.unpack('>IIIBBH', d[o:o + 16])
        syms.append((cstr(strtab + nm), val, sz, shn))
    vts = {}
    for name, val, sz, shn in syms:
        if name.startswith('__vt__') and 0 < shn < 0xff00:
            vts[name] = (shn, val, sz)
    if not vts:
        return {}
    relocs = {}  # section -> {offset: (sym, addend)}
    for r in sh:
        if r[1] != 4:
            continue
        m = relocs.setdefault(r[7], {})
        for o in range(r[4], r[4] + r[5], 12):
            off, info, add = struct.unpack('>IIi', d[o:o + 12])
            m[off] = (syms[info >> 8][0], add)
    out = {}
    for name, (shn, val, sz) in vts.items():
        rel = relocs.get(shn, {})
        out[name] = (sz, {o - val: rel[o] for o in rel if val <= o < val + sz})
    return out


def load_symbols():
    addr = {}
    for l in (ROOT / "config/G4SE01/symbols.txt").read_text().splitlines():
        m = re.match(r'(\S+) = \.\w+:0x([0-9A-Fa-f]+);', l)
        if m:
            addr[m.group(1)] = int(m.group(2), 16)
    return addr


def main():
    flt = sys.argv[1:]
    addr = load_symbols()
    units = [(ROOT / u['base_path'], ROOT / u['target_path'])
             for u in json.loads((ROOT / "objdiff.json").read_text())['units']
             if u.get('base_path') and u.get('target_path')]
    units = [(p, tp) for p, tp in units if p.exists() and tp.exists()]
    ours = {}
    for p, _ in units:
        for name, vt in read_elf(p).items():
            ours.setdefault(name, (p, vt))
    n_vt = n_bad = 0
    for p, tp in units:
        rel = p.relative_to(B / "src")
        if flt and not any(f in str(rel) for f in flt):
            continue
        for name, (tsz, tslots) in sorted(read_elf(tp).items()):
            n_vt += 1
            if name not in ours:
                n_bad += 1
                print(f"{rel.with_suffix('')}: MISSING {name} ({addr.get(name, 0):08X}, 0x{tsz:X})")
                continue
            op, (osz, oslots) = ours[name]
            where = '' if op == p else f" (emitted by {op.relative_to(B / 'src').with_suffix('')})"
            # dtk's size can include alignment padding: a size difference counts
            # only when the longer table has slots (relocations) past the shorter.
            if osz != tsz and any(o >= min(osz, tsz) for o in (tslots if tsz > osz else oslots)):
                n_bad += 1
                print(f"{rel.with_suffix('')}: SIZE {name}: ours 0x{osz:X}, original 0x{tsz:X}{where}")
            for off in sorted(set(tslots) | set(oslots)):
                t, o = tslots.get(off), oslots.get(off)
                if t == o:
                    continue
                if t and o and t[1] == o[1] and t[0] in addr and addr.get(t[0]) == addr.get(o[0]):
                    continue
                n_bad += 1

                def fmt(x):
                    if not x:
                        return 'null'
                    a = addr.get(x[0])
                    return f"{x[0]}{'+%d' % x[1] if x[1] else ''} ({'%08X' % a if a else '?'})"
                print(f"{rel.with_suffix('')}: SLOT {name} +0x{off:X}{where}\n"
                      f"    ours     {fmt(o)}\n    original {fmt(t)}")
    print(f"{n_vt} vtables checked, {n_bad} problems", file=sys.stderr)
    sys.exit(1 if n_bad else 0)


if __name__ == '__main__':
    main()
