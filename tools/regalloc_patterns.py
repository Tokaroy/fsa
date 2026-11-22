#!/usr/bin/env python3
"""Tag every register/order-only function by the shape of its difference.

  python3 tools/regalloc_patterns.py [--build] [--json out.json] [--show TAG] [--fn NAME]

Reads build/G4SE01/structural.json `units` and keeps the functions whose class (tools/try.py) is
regalloc-only, scheduling or scheduling+regalloc (with or without reloc-name). For each unit it
diffs the compiled object with objdiff-cli (functionRelocDiffs=all, as try.py) and tags the
function mechanically:

  registers (aligned rows; target register -> ours):
    ra:swap2-saved        one 2-cycle among callee-saved GPRs (two values exchanged)
    ra:rotate-saved       one cycle of 3+ callee-saved GPRs (a group coloured in another order)
    ra:multi-saved        several cycles among callee-saved GPRs
    ra:shift-saved        an open chain (ours uses a register the target doesn't): one value more/less
    ra:count-saved        the number of saved GPRs differs (stmw/lmw start or stw/lwz count)
    ra:split-saved        one target register maps to several of ours (live ranges merged/split)
    ra:volatile-only      only r0/r3-r12 differ
    ra:float-only         only FPRs differ (sub: -saved / -volatile)
    ra:cr-only            only condition-register fields differ
    ra:mixed-int-float    both GPRs and FPRs differ
  order (difflib over normalised rows, registers erased):
    sc:prologue/epilogue  only frame setup/teardown rows moved
    sc:across-call        a moved row sits on the other side of a `bl` than in the target
    sc:near-swap          every moved row moved <= 3 rows, no call crossed
    sc:far                a moved row moved > 3 rows without crossing a call
    sc:moved-<kind>       what moved: load, store, const (li/lis), mr, cmp, branch, arith, float
  source (regex over the function's body in our source, best effort):
    src:fixme             a FIXME comment in the body
    src:inline-call       the body calls a function this file or include/game declares inline
    src:loop              the body has a for/while loop
    src:no-body           the body could not be found
    src:__fabsf (etc.)    the body calls a PPC intrinsic directly rather than through a header inline
"""

import difflib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("try_tool", str(Path(__file__).resolve().parent / "try.py"))
_try = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_try)
load_units, run_diff, insn_list, reloc_pairs, classify = (_try.load_units, _try.run_diff, _try.insn_list,
                                                           _try.reloc_pairs, _try.classify)
noreg, noreloc, nobranch = _try.noreg, _try.noreloc, _try.nobranch

REG = re.compile(r"^(r|f|cr|qr)(\d+)$")
WANT = ("regalloc-only", "scheduling", "scheduling+regalloc")


def regclass(r):
    m = REG.match(r)
    k, n = m.group(1), int(m.group(2))
    if k == "r":
        return "gpr-saved" if n >= 14 else ("sp" if n in (1, 2, 13) else "gpr-vol")
    if k == "f":
        return "fpr-saved" if n >= 14 else "fpr-vol"
    return k


def reg_tags(t, o):
    mp = defaultdict(Counter)
    for a, b in zip(t, o):
        for x, y in zip(a[1], b[1]):
            if REG.match(x) and REG.match(y):
                mp[x][y] += 1
    diff = {x: c for x, c in mp.items() if any(y != x for y in c)}
    tags = []
    classes = {regclass(x) for x in diff} | {regclass(y) for c in diff.values() for y in c}
    gpr = {"gpr-saved", "gpr-vol"} & classes
    fpr = {"fpr-saved", "fpr-vol"} & classes
    if gpr and fpr:
        tags.append("ra:mixed-int-float")
    elif fpr:
        tags.append("ra:float-only-" + ("saved" if "fpr-saved" in fpr else "volatile"))
    elif classes == {"cr"}:
        tags.append("ra:cr-only")
    elif gpr == {"gpr-vol"}:
        tags.append("ra:volatile-only")
    # saved GPRs
    def saved_count(seq):
        for i in seq:
            if i[0] == "stmw":
                return 32 - int(REG.match(i[1][0]).group(2))
        return sum(1 for i in seq[:12] if i[0] == "stw" and i[1] and REG.match(i[1][0])
                   and regclass(i[1][0]) == "gpr-saved")
    if saved_count(t) != saved_count(o):
        tags.append("ra:count-saved")
    sv = {x: c for x, c in diff.items() if regclass(x) == "gpr-saved"}
    if sv:
        split = any(len([y for y in c if regclass(y) == "gpr-saved"]) > 1 for c in sv.values())
        if split:
            tags.append("ra:split-saved")
        else:
            p = {x: c.most_common(1)[0][0] for x, c in sv.items()}
            seen, cycles, chains = set(), 0, 0
            lens = []
            for x in p:
                if x in seen:
                    continue
                path, y = [x], p[x]
                while y in p and y not in path:
                    path.append(y)
                    y = p[y]
                seen.update(path)
                if y == x:
                    cycles += 1
                    lens.append(len(path))
                else:
                    chains += 1
            # an open chain fragment can be found from its middle; count unique by roots
            if chains:
                tags.append("ra:shift-saved")
            elif cycles == 1:
                tags.append("ra:swap2-saved" if lens[0] == 2 else "ra:rotate-saved")
            elif cycles > 1:
                tags.append("ra:multi-saved")
    if not tags and diff:
        tags.append("ra:other")
    pairs = Counter()
    for x, c in diff.items():
        for y, n in c.items():
            if y != x:
                pairs[f"{x}->{y}"] += n
    return tags, ", ".join(p for p, _ in pairs.most_common(5))


def kind_of(mn):
    if mn.startswith(("lwz", "lhz", "lha", "lbz", "lfs", "lfd", "lmw", "psq_l")):
        return "load"
    if mn.startswith(("stw", "sth", "stb", "stf", "stmw", "psq_st")):
        return "store"
    if mn in ("li", "lis"):
        return "const"
    if mn in ("mr", "fmr"):
        return "mr"
    if mn.startswith(("cmp", "fcmp")):
        return "cmp"
    if mn.startswith("b"):
        return "branch"
    if mn.startswith("f") or mn.startswith("ps_"):
        return "float"
    return "arith"


def sched_tags(t, o, regs_too):
    key = (lambda i: nobranch(noreg(i))) if regs_too else nobranch
    T, O = [key(i) for i in t], [key(i) for i in o]
    sm = difflib.SequenceMatcher(None, T, O, autojunk=False)
    dels, ins = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            dels += range(i1, i2)
        if op in ("insert", "replace"):
            ins += range(j1, j2)
    # pair moved rows by key
    pool = defaultdict(list)
    for j in ins:
        pool[O[j]].append(j)
    moves = []
    for i in dels:
        if pool[T[i]]:
            moves.append((i, pool[T[i]].pop(0)))
    calls_t = [k for k, i in enumerate(t) if i[0] == "bl" or i[0] == "bctrl"]
    calls_o = [k for k, i in enumerate(o) if i[0] == "bl" or i[0] == "bctrl"]
    tags = set()
    n = len(t)
    frame = ("mflr", "mtlr", "stwu", "stmw", "lmw", "blr", "addi")
    pe = all(t[i][0] in frame or (t[i][1] and "r1" in " ".join(t[i][1])) or i < 6 or i > n - 7 for i, _ in moves)
    if moves and pe and all(i < 8 or i > n - 9 for i, _ in moves):
        tags.add("sc:prologue/epilogue")
    across = any(sum(1 for c in calls_t if c < i) != sum(1 for c in calls_o if c < j) for i, j in moves)
    if across:
        tags.add("sc:across-call")
    dist = max((abs(i - j) for i, j in moves), default=0)
    if not across and "sc:prologue/epilogue" not in tags:
        tags.add("sc:near-swap" if dist <= 3 else "sc:far")
    for k in sorted({kind_of(t[i][0]) for i, _ in moves}):
        tags.add("sc:moved-" + k)
    return sorted(tags), f"{len(moves)} moved, max dist {dist}"


# ---------------------------------------------------------------- source features

INLINE_DEF = re.compile(r"\binline\b[^;{]*?\b(\w+)\s*\(")


def inline_names(text):
    return {m.group(1) for m in INLINE_DEF.finditer(text)}


_hdr_inlines = None


def header_inlines():
    global _hdr_inlines
    if _hdr_inlines is None:
        s = set()
        for p in Path("include/game").rglob("*.h"):
            try:
                s |= inline_names(p.read_text(errors="replace"))
            except OSError:
                pass
        # in-class member definitions in headers are implicitly inline: `name(...) {` inside a class
        _hdr_inlines = s
    return _hdr_inlines


def func_body(text, name, demangled):
    m = re.match(r"fn_([0-9A-F]{8})", name)
    pats = []
    if m:
        pats.append(re.escape(name) + r"\s*\(")
    base = (demangled or "").split("(")[0]
    if base:
        pats.append(re.escape(base) + r"\s*\(")
        pats.append(re.escape(base.split("::")[-1]) + r"\s*\(")
    for p in pats:
        for mm in re.finditer(p, text):
            # a definition: ')' ... '{' before the next ';'
            k = text.find(")", mm.end())
            semi, brace = text.find(";", mm.end()), text.find("{", mm.end())
            if brace < 0 or (0 <= semi < brace):
                continue
            line_start = text.rfind("\n", 0, mm.start()) + 1
            if text[line_start:mm.start()].strip().startswith(("//", "return", "=")):
                continue
            depth, i = 0, brace
            while i < len(text):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[max(0, line_start - 200):i + 1]
                i += 1
    return None


def src_tags(src_path, name, demangled):
    try:
        text = Path(src_path).read_text(errors="replace")
    except OSError:
        return ["src:no-body"]
    body = func_body(text, name, demangled)
    if body is None:
        return ["src:no-body"]
    tags = []
    if "FIXME" in body:
        tags.append("src:fixme")
    inl = inline_names(text) | header_inlines()
    calls = set(re.findall(r"\b(\w+)\s*\(", body.split("{", 1)[-1]))
    if calls & inl:
        tags.append("src:inline-call")
    if re.search(r"\b(for|while)\s*\(", body):
        tags.append("src:loop")
    for intr in ("__fabsf", "__frsqrte", "__fres", "__fnmsubs", "__fmadds"):
        if intr + "(" in body:
            tags.append("src:" + intr)
    return tags


# ---------------------------------------------------------------- main

def main():
    argv = sys.argv[1:]
    st = json.loads(Path("build/G4SE01/structural.json").read_text())["units"]
    sel = {u: {f: v for f, v in fs.items() if v[2].split(" + ")[0] in WANT} for u, fs in st.items()}
    sel = {u: fs for u, fs in sel.items() if fs}
    units = {u["name"]: u for u in load_units()}
    if "--build" in argv:
        objs = [units[u]["base_path"] for u in sel if u in units and "base_path" in units[u]]
        subprocess.run(["ninja", "-k", "0", *objs], capture_output=True)
    rows = []
    for un, fs in sorted(sel.items()):
        u = units.get(un)
        if not u or "base_path" not in u:
            continue
        try:
            d = run_diff(u)
        except SystemExit:
            continue
        left, right = d["left"], d["right"]
        src = (u.get("metadata") or {}).get("source_path") or ""
        for s in left["symbols"]:
            if s.get("kind") != "SYMBOL_FUNCTION" or s["name"] not in fs:
                continue
            ti = s.get("target_symbol")
            pct = s.get("match_percent")
            r = right["symbols"][ti] if ti is not None else None
            row = {"unit": un.split("/", 1)[1], "fn": s["name"], "size": int(s.get("size", 0)),
                   "old": fs[s["name"]][2], "pct": pct}
            if r is None:
                row.update(cls="missing", tags=[], detail="")
                rows.append(row)
                continue
            t, o = insn_list(left, s), insn_list(right, r)
            cls, _ = classify(t, o, reloc_pairs(s, r, left, right))
            if pct == 100:
                cls = "match"
            row["cls"] = cls
            base = cls.split(" + ")[0]
            T, O = [noreloc(i) for i in t], [noreloc(i) for i in o]
            tags, detail = [], ""
            if base == "regalloc-only":
                tags, detail = reg_tags(T, O)
            elif base in ("scheduling", "scheduling+regalloc"):
                tags, detail = sched_tags(T, O, base != "scheduling")
                if base == "scheduling+regalloc":
                    tags.append("ra:with-order")
            if "reloc-name" in cls:
                tags.append("reloc-name")
            tags += src_tags(src, s["name"], s.get("demangled_name"))
            row.update(tags=tags, detail=detail)
            rows.append(row)
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1))
    show = argv[argv.index("--show") + 1] if "--show" in argv else None
    live = [r for r in rows if r["cls"] not in ("match", "missing")]
    print(f"{len(rows)} functions, {len(live)} still differing "
          f"({sum(1 for r in rows if r['cls'] == 'match')} now match)")
    cnt, byt, ex = Counter(), Counter(), defaultdict(list)
    for r in live:
        for tg in r["tags"]:
            cnt[tg] += 1
            byt[tg] += r["size"]
            ex[tg].append(r)
    for tg, n in cnt.most_common():
        eg = sorted(ex[tg], key=lambda r: r["size"])
        egs = ", ".join(f"{r['unit'].split('/')[-1]}:{r['fn'][:28]}" for r in eg[:3])
        print(f"  {tg:24} {n:4} {byt[tg]:7}  {egs}")
    if show:
        for r in sorted(ex.get(show, []), key=lambda r: r["size"]):
            print(f"{r['unit']:32} {r['fn'][:40]:40} {r['size']:6} {r['pct']:6.2f} {' '.join(r['tags'])} | {r['detail']}")


if __name__ == "__main__":
    main()
