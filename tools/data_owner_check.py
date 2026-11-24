#!/usr/bin/env python3
"""Data a unit owns but its C does not define.

For every unit with source, the global data symbols that config/G4SE01/symbols.txt places
inside the unit's data sections in splits.txt (.data, .rodata, .bss, .sbss, .sdata, .sdata2)
must be defined by the unit's compiled object; a Matching unit gets them from its own C,
but a NonMatching one links the original asm, so a missing definition goes unnoticed until
the unit is linked from C (tools/harness_dolphin.py build-b). Also lists names the object
defines that another unit owns (defined twice once both are linked from C).

Only names some other object references (undefined there) are reported missing: an
unreferenced lbl_ is usually our own local under another name.
Locals (scope:local, @NNN literals, name$NNN statics) are skipped: they have no fixed name.

Usage: python3 tools/data_owner_check.py [unit ...]   (default: every unit with source)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import importlib.util

spec = importlib.util.spec_from_file_location("st", ROOT / "tools/structural.py")
ST = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ST)

DATA = (".data", ".rodata", ".bss", ".sbss", ".sdata", ".sdata2")
SYM = re.compile(r"^(\S+) = (\.\w+):0x([0-9A-Fa-f]+);(.*)$")


def read_splits():
    units, cur = {}, None
    for line in (ROOT / "config/G4SE01/splits.txt").read_text().splitlines():
        if line and not line[0].isspace() and line.endswith(":"):
            cur = line[:-1]
            units[cur] = []
        elif cur and line.strip():
            p = line.split()
            if p[0] in DATA and "start:" in line:
                kv = dict(x.split(":") for x in p[1:] if ":" in x)
                units[cur].append((p[0], int(kv["start"], 16), int(kv["end"], 16)))
    return units


def main():
    splits = read_splits()
    syms = []
    for line in (ROOT / "config/G4SE01/symbols.txt").read_text().splitlines():
        m = SYM.match(line)
        if m and "type:function" not in m[4] and "scope:local" not in m[4]:
            name = m[1]
            if name.startswith("@") or "$" in name or name.startswith("..."):
                continue
            syms.append((m[2], int(m[3], 16), name))
    cfg = json.loads((ROOT / "objdiff.json").read_text())["units"]
    want = set(sys.argv[1:])
    owner_of = {}
    for path, ranges in splits.items():
        for sec, a, b in ranges:
            for s, addr, name in syms:
                if s == sec and a <= addr < b:
                    owner_of[name] = path
    # names another object references: only those can break a link from C
    needed = set()
    for u in cfg:
        base = u.get("base_path")
        if base and Path(base).exists():
            needed |= {n for n, v in ST.read_elf(base, relocations=False).items() if all(x.shndx == 0 for x in v)}
    total = 0
    for u in cfg:
        base = u.get("base_path")
        if not base or not Path(base).exists():
            continue
        src = (u.get("metadata") or {}).get("source_path", "")
        path = src.split("src/", 1)[-1] if src else ""
        short = u["name"].split("/", 1)[-1]
        if want and short not in want and short.rsplit("/", 1)[-1] not in want:
            continue
        if path not in splits:
            continue
        elf = ST.read_elf(base, relocations=False)
        defined = {n for n, v in elf.items() if any(x.shndx != 0 for x in v)}  # SHN_UNDEF = 0
        owned = sorted(n for n, p in owner_of.items() if p == path)
        missing = [n for n in owned if n not in defined and n in needed]
        stolen = sorted(n for n in defined if n in owner_of and owner_of[n] != path
                        and any(x.bind == 1 for x in elf[n]))  # global definitions only
        if missing or stolen:
            total += len(missing) + len(stolen)
            print(f"{short}:")
            for n in missing:
                print(f"  missing  {n}")
            for n in stolen:
                print(f"  defines  {n} (owned by {owner_of[n]})")
    print(f"{total} problems")


if __name__ == "__main__":
    main()
