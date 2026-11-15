#!/usr/bin/env python3
"""What kind of difference is left in one function, and where in OUR source it comes from.

  python3 tools/diag.py <unit> <function> [-v]
  python3 tools/diag.py <unit>                  # every function below 100 %: root or derived

Compiles the unit as it stands twice outside ninja (tools/scratch.py; with and without `-sym on`)
and prints at most ~60 lines (-v lifts the caps):
  * match %, class (tools/try.py) and score (tools/scratch.py);
  * registers: each of our named locals, parameters and `this` that lives in a callee-saved
    register (r14-r31, f14-f31; names and registers from the object's DWARF), with the register
    the target uses for the same role (the majority over aligned rows with the same mnemonic),
    and which ones are swapped; compiler temporaries in one line;
  * stack frame: size ours vs target, slots only one side uses (with DWARF's names);
  * the differing rows grouped by our source line (from `-sym on`'s line table): the line, the
    rows target | ours and the kind (registers only, order, target/ours has N more with
    tools/drift_patterns.py's pattern and hint, opcode pair);
  * functions of this file MWCC inlined into it (tools/permute.py's inlined_callees) with their
    own %: when one is below 100 %, fix that one first (this one is "derived");
  * the next command worth running.

Line numbers carry no file: code inlined from a header shows the header's line number (printed
as "header line N"), code inlined from a function of this file shows the line of the call.
`-sym on` is checked not to change this function's code (tools/fnscore.cpp); if it does, diag
falls back to the plain object, without lines and names, and says so.

Without a function: one line per function below 100 %, roots first; derived = it inlines a
function of this file that is itself below 100 % (fixing that one usually fixes this one).
"""

import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drift_patterns as DP  # noqa: E402
import scratch  # noqa: E402

T = scratch.T
DTK = "build/tools/dtk"
SAVED = DP.SAVED
REG = T.REG
CAP_HUNKS, CAP_ROWS = 8, 5
REGISH = ("regalloc-only", "scheduling", "scheduling+regalloc", "same-text")


# ---------------------------------------------------------------- DWARF (dtk dwarf dump)

def dwarf(root, obj):
    """[(start, end, signature, {reg or 'r1+0xN': [names]})] from dtk's dump of `obj`."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "d.txt"
        p = subprocess.run([str(root / DTK), "dwarf", "dump", str(obj), "-o", str(out)], capture_output=True, text=True)
        if p.returncode or not out.exists():
            return None
        lines = out.read_text(errors="replace").splitlines()
    res, k = [], 0
    while k < len(lines):
        m = re.match(r"// Range: 0x([0-9A-Fa-f]+) -> 0x([0-9A-Fa-f]+)", lines[k])
        k += 1
        if not m:
            continue
        locs = defaultdict(list)
        if k < len(lines) and (t := re.match(r"// this: (\S+)", lines[k])):
            locs[t.group(1)].append("this")
            k += 1
        sig = lines[k] if k < len(lines) else ""
        for pm in re.finditer(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*/\*\s*(\S+)\s*\*/", sig):
            locs[pm.group(2)].append(pm.group(1))
        k += 1
        while k < len(lines) and not sig.rstrip().endswith("{}") and lines[k] != "}":
            lm = re.match(r"^\s+[^/].*?([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*);\s*//\s*(\S+)\s*$", lines[k])
            if lm:
                name = lm.group(1) + ("[]" if lm.group(2) else "")
                if name not in locs[lm.group(3)]:
                    locs[lm.group(3)].append(name)
            k += 1
        res.append((int(m.group(1), 16), int(m.group(2), 16), sig, locs))
    return res


def dwarf_for(blocks, f):
    if not blocks or f.our_addr is None:
        return {}
    short = f.demangled.split("(")[0]
    hits = [b for b in blocks if b[0] == f.our_addr and b[1] - b[0] == f.our_size]
    if len(hits) > 1:
        hits = [b for b in hits if short in b[2]] or hits
    return hits[0][3] if hits else {}


# ---------------------------------------------------------------- formatting

def fmt(i, w=34):
    if i is None:
        return ""
    mn, args, rel, ri = i
    a = list(args)
    if ri is not None and ri < len(a):
        a[ri] = (rel or "?")[:36]
    base = mn.rstrip(".")
    if base == "addi" and len(a) == 3 and a[1] == "r1" and re.fullmatch(r"\d+", a[2]):
        a[2] = hex(int(a[2]))
    if len(a) == 3 and (DP.MEMOPS.match(base) or base.startswith("psq")) and REG.match(a[2]) and not REG.match(a[1]):
        off = a[1]
        if re.fullmatch(r"-?\d+", off):
            off = hex(int(off)) if int(off) >= 0 else "-" + hex(-int(off))
        a = [a[0], f"{off}({a[2]})"]
    s = f"{mn} {', '.join(a)}".strip()
    return s[:w]


def fake(i):
    """An insn tuple as the objdiff-JSON shape drift_patterns.bucket() reads."""
    return {"parts": [{"opcode": {"mnemonic": i[0]}}] + [{"arg": {"opaque": a}} for a in i[1]]}


def norm(i):
    return (i[0], tuple("R" if REG.match(a) else a for a in i[1]), i[2])


def pair_pattern(t, o):
    ma, mb = t[0].rstrip("."), o[0].rstrip(".")
    if ma in DP.CMP and mb in DP.CMP:
        return "cmp-sign"
    if {ma, mb} <= (DP.MUL | {"add"}):
        return "mul"
    return DP.bucket(fake(t))


def reg_only(t, o):
    if t is None or o is None or t[0] != o[0] or len(t[1]) != len(o[1]) or t[2] != o[2]:
        return False
    return all(a == b or (REG.match(a) and REG.match(b)) or (a[:1] == b[:1] == "@") for a, b in zip(t[1], o[1]))


def arg_diffs(t, o):
    """What differs between two rows with the same mnemonic: {'reg', 'stack slots', 'immediates', 'symbols'}."""
    out = set()
    if t[2] != o[2]:
        out.add("symbols")
    if len(t[1]) != len(o[1]):
        return out | {"immediates"}
    r1 = "r1" in t[1] and "r1" in o[1]
    for a, b in zip(t[1], o[1]):
        if a == b or a[:1] == b[:1] == "@" or a == "RELOC" or b == "RELOC":
            continue
        out.add("reg" if REG.match(a) and REG.match(b) else "stack slots" if r1 else "immediates")
    return out


def frame_row(t, o):
    """A prologue/epilogue row that differs only in its stack offset (the frame size differs)."""
    if t is None or o is None or t[0] != o[0] or t[2] != o[2] or arg_diffs(t, o) - {"stack slots"}:
        return False
    a = o[1]
    return t[0] == "stwu" or (t[0] == "addi" and a[:2] == ("r1", "r1")) or bool(a and (SAVED.match(a[0]) or a[0] == "r0")
                                                                             and t[0] in ("stw", "lwz", "stfd", "lfd", "psq_st", "psq_l", "stmw", "lmw"))


def branch_only(t, o):
    """Only a branch destination differs: the code between moved, nothing to fix here."""
    if t is None or o is None or t[0] != o[0] or len(t[1]) != len(o[1]) or t[2] != o[2]:
        return False
    return all(a == b or (a[:1] == b[:1] == "@") for a, b in zip(t[1], o[1]))


def regs_of(i):
    return [a for a in i[1] if REG.match(a)]


# ---------------------------------------------------------------- the analysis

class Src:
    """Our source: line texts, the function's extent and the extents of its inlined callees."""

    def __init__(self, unit, f, called):
        self.lines = unit.source().split("\n")
        self.fn, self.callees, self.err, self.p = None, [], None, None
        try:
            import permute
            p = self.p = permute.Parsed(unit, unit.source().encode("utf-8", "surrogateescape"))
            first = next((r[3] for r in f.rows if r[3]), None)
            self.fn = p.locate(f.demangled, first)
            if self.fn is not None:
                self.callees = permute.inlined_callees(p, self.fn, called)
        except Exception as e:  # noqa: BLE001  (no libclang, a parse problem: diag still works)
            self.err = f"{type(e).__name__}: {e}"

    def ext(self, c):
        return c.extent.start.line, c.extent.end.line

    def where(self, line):
        """(text or None, note) for one of our line numbers."""
        if line is None:
            return None, "no line"
        inside = self.fn is None or self.ext(self.fn)[0] <= line <= self.ext(self.fn)[1]
        callee = next((c for c in self.callees if self.ext(c)[0] <= line <= self.ext(c)[1]), None)
        if not inside and callee is None:
            return None, f"header line {line}"
        text = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        return text, f"in inlined `{callee.spelling}`" if callee is not None and not inside else ""


def qual(c):
    par = c.semantic_parent
    if par is not None and par.kind.name in ("CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE", "NAMESPACE"):
        return f"{par.spelling}::{c.spelling}"
    return c.spelling


def callee_fn(d, c):
    q = qual(c)
    hits = [g for g in d.fn.values() if g.demangled.split("(")[0] == q]
    if len(hits) > 1:
        n = len(list(c.get_arguments()))
        hits = [g for g in hits if (g.demangled.count(",") + 1 if not re.search(r"\((void)?\)", g.demangled) else 0) == n] or hits
    return hits[0] if hits else None


def below_of(p, d, f, cursor=None):
    """Fns of this file's functions inlined into f that are below 100 %, nearest first."""
    import permute
    if cursor is None:
        cursor = p.locate(f.demangled, next((r[3] for r in f.rows if r[3]), None))
    if cursor is None:
        return []
    out = []
    for g in permute.inlined_callees(p, cursor, called_of(f)):
        gf = callee_fn(d, g)
        if gf is not None and gf.pct < 100 and gf not in out:
            out.append(gf)
    return out


def root_of(p, d, below):
    """Of the below-100 % callees, the one to fix first: a root (it inlines nothing below 100 %), lowest %."""
    roots = [g for g in below if g.cls == "missing" or not below_of(p, d, g)]
    return min(roots or below, key=lambda g: g.pct)


def called_of(f):
    return {r[2][2] for r in f.rows if r[2] is not None and r[2][0] in ("bl", "b") and r[2][2]}


def compile_both(u):
    """(object with -sym on, plain object), compiled at once."""
    tag = f"diag-{threading.get_ident()}-{id(u)}"
    res = {}

    def one(sym):
        try:
            res[sym] = u.compile(tag=f"{tag}-{int(sym)}", sym=sym)
        except Exception as e:  # noqa: BLE001
            res[sym] = e
    ts = [threading.Thread(target=one, args=(s,)) for s in (True, False)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return res[True], res[False]


def same_code(u, a, b, name):
    try:
        out = subprocess.run([str(scratch.fnscore_bin(u.root)), str(a), str(b), name], capture_output=True, text=True,
                             timeout=60).stdout.split("\t")
        return len(out) > 1 and out[1] == "0"
    except Exception:  # noqa: BLE001
        return False


def register_map(f):
    """{our callee-saved register: Counter(target register for the same operand)} over aligned rows."""
    votes = defaultdict(Counter)
    for kind, t, o, _, _ in f.rows:
        if t is None or o is None or t[0] != o[0] or len(t[1]) != len(o[1]):
            continue
        for a, b in zip(t[1], o[1]):
            if REG.match(a) and REG.match(b) and a[0] == b[0] and SAVED.match(b):
                votes[b][a] += 1
    return votes


def reg_section(f, locs, out):
    votes = register_map(f)
    named = lambda r: "/".join(f"`{n}`" for n in locs.get(r, [])[:3])  # noqa: E731
    key = lambda r: (r[0], int(r[1:]))  # noqa: E731
    diff, mixed = {}, {}
    for r, c in votes.items():
        (best, n), *rest = c.most_common(2)
        if best != r:
            diff[r] = best if not rest or rest[0][1] < n else best + "?"
        elif sum(v for t, v in c.items() if t != r) >= 2:
            mixed[r] = c
    if not diff and not mixed:
        return False
    out.append("Registers (callee-saved; ours (target's for the same role)):")
    done, temps_shown = set(), set()
    for r in sorted(diff, key=key):
        if r in done:
            continue
        chain, x = [], r
        while x in diff and x not in chain:
            chain.append(x)
            x = diff[x].rstrip("?")
        cyc = x == r
        done.update(chain)
        if not any(locs.get(c) for c in chain):
            continue
        parts = [f"{named(c) or '(temp)'} {c} (target {diff[c]})" for c in chain]
        temps_shown.update(c for c in chain if not locs.get(c))
        how = ("swapped" if len(chain) == 2 else "rotated") if cyc else "moved"
        out.append("  " + (" <-> " if cyc and len(chain) == 2 else ", ").join(parts) + f": {how}")
    same = [f"{named(r)} {r}" for r in sorted(votes, key=key) if r not in diff and r not in mixed and locs.get(r)]
    if same:
        out.append("  same: " + ", ".join(same[:8]))
    temps = [f"{r}->{diff[r]}" for r in sorted(diff, key=key) if not locs.get(r) and r not in temps_shown]
    if temps:
        out.append("  temporaries (no name) ours->target: " + ", ".join(temps[:10]))
    if mixed:
        out.append("  reused for several values (target's per row): " + "; ".join(
            f"{named(r) + ' ' if locs.get(r) else ''}{r}: " + ", ".join(f"{t} {n}x" for t, n in c.most_common(4))
            for r, c in sorted(mixed.items(), key=lambda kv: key(kv[0]))[:6]))
    return bool(diff)  # a clear map: register-only rows need not be shown


def saved_set(rows, side):
    regs = set()
    for r in rows:
        i = r[side]
        if i is None:
            continue
        if i[0] == "stmw":
            regs.update(f"r{n}" for n in range(int(i[1][0][1:]), 32))
        elif i[0] in ("stw", "stfd", "psq_st") and i[1] and i[1][-1] == "r1" and SAVED.match(i[1][0]):
            regs.add(i[1][0])
    return regs


def stack_section(f, locs, out):
    def info(side):
        frame, slots = None, Counter()
        for r in f.rows:
            i = r[side]
            if i is None:
                continue
            mn, a = i[0], i[1]
            if mn == "stwu" and a[:1] == ("r1",):
                frame = -int(a[1]) if frame is None else frame
            elif len(a) == 3 and a[2] == "r1" and re.fullmatch(r"-?\d+", a[1]) and not SAVED.match(a[0]) \
                    and (DP.MEMOPS.match(mn.rstrip(".")) or mn.startswith("psq")) and mn not in ("stmw", "lmw"):
                slots[int(a[1])] += 1
            elif mn == "addi" and len(a) == 3 and a[1] == "r1" and a[0] != "r1":
                slots[int(a[2])] += 1
        return frame, slots
    (tf, ts), (of, os_) = info(1), info(2)
    lr = {x + 4 for x in (tf, of) if x}
    ts, os_ = Counter({k: v for k, v in ts.items() if k not in lr}), Counter({k: v for k, v in os_.items() if k not in lr})
    tsv, osv = saved_set(f.rows, 1), saved_set(f.rows, 2)
    lines = []
    if tf != of:
        lines.append(f"  frame: target {tf} bytes, ours {of} (prologue/epilogue rows that differ only by it are left out)")
    if tsv != osv:
        k = lambda r: (r[0], int(r[1:]))  # noqa: E731
        lines.append(f"  saved registers: target {len(tsv)} ({', '.join(sorted(tsv - osv, key=k)) or '-'} only target), "
                     f"ours {len(osv)} ({', '.join(sorted(osv - tsv, key=k)) or '-'} only ours)")
    named = {}
    for loc, ns in locs.items():
        m = re.fullmatch(r"r1\+0x([0-9A-Fa-f]+)", loc)
        if m:
            named[int(m.group(1), 16)] = "/".join(ns[:2])

    def label(o):
        if o in named:
            return f"0x{o:X} `{named[o]}`"
        base = max((x for x in named if x < o and named[x].endswith("[]")), default=None)
        return f"0x{o:X} (`{named[base]}`+0x{o - base:X})" if base is not None else f"0x{o:X}"
    only_t, only_o = sorted(set(ts) - set(os_)), sorted(set(os_) - set(ts))
    # slots used by both sides but for other values: our offset -> the target's in aligned rows
    votes = defaultdict(Counter)
    for r in f.rows:
        t, o = r[1], r[2]
        if t is None or o is None or t[0] != o[0] or len(t[1]) != 3 or len(o[1]) != 3 or t[1][2] != "r1" or o[1][2] != "r1":
            continue
        if re.fullmatch(r"-?\d+", t[1][1]) and re.fullmatch(r"-?\d+", o[1][1]) and not SAVED.match(o[1][0]):
            votes[int(o[1][1])][int(t[1][1])] += 1
    moved = {}
    for ours, c in votes.items():
        best, n = c.most_common(1)[0]
        if best != ours and ours not in lr and ours >= 0:
            moved[ours] = best
    parts, done = [], set()
    for o, t in sorted(moved.items()):
        if o in done:
            continue
        if moved.get(t) == o:
            done |= {o, t}
            parts.append(f"{label(o)} (target 0x{t:X}) <-> {label(t)} (target 0x{o:X}): swapped")
        else:
            done.add(o)
            parts.append(f"{label(o)} (target 0x{t:X})")
    if parts:
        lines.append("  slots holding other values, ours (target's): " + "; ".join(parts[:6]))
    if only_t:
        lines.append("  slots only the target uses: " + ", ".join(f"0x{o:X}" for o in only_t[:8]))
    if only_o:
        lines.append("  slots only ours uses: " + ", ".join(label(o) for o in only_o[:8]))
    if lines:
        out.append("Stack frame:")
        out += lines
    return tf != of


def hunks_section(f, src, below, collapse, verbose, out, shifted=False):
    rows, last, groups, order = f.rows, None, defaultdict(list), []
    run, prev = 0, -10  # without line numbers: runs of rows (a gap of 3 equal rows starts a new one)
    for k, r in enumerate(rows):
        if r[3] is not None:
            last = r[3]
        if not r[0] or branch_only(r[1], r[2]) or (shifted and frame_row(r[1], r[2])):
            continue
        line = r[3] if r[3] is not None else (last if last is not None else next((x[3] for x in rows[k:] if x[3]), None))
        if line is None or src is None:
            run += k - prev > 3
            line = -run
        prev = k
        if line not in groups:
            order.append(line)
        groups[line].append(r)
    dels = Counter(norm(r[1]) for r in rows if r[0] and r[2] is None and r[1])
    ins = Counter(norm(r[2]) for r in rows if r[0] and r[1] is None and r[2])
    moved_d, moved_i = dels & ins, dels & ins
    hint_seen, shown, regonly = set(), 0, []
    body = []
    for line in order:
        g = groups[line]
        if all(reg_only(r[1], r[2]) for r in g):
            if collapse:
                regonly.append(line)
                continue
            kind = "registers only"
        else:
            phr, nd, ni, mv, pat_d, pat_i = [], 0, 0, 0, Counter(), Counter()
            for r in g:
                t, o = r[1], r[2]
                if o is None and t is not None:
                    if moved_d[norm(t)] > 0:
                        moved_d[norm(t)] -= 1
                        mv += 1
                    else:
                        nd += 1
                        pat_d[DP.bucket(fake(t))] += 1
                elif t is None and o is not None:
                    if moved_i[norm(o)] > 0:
                        moved_i[norm(o)] -= 1
                        mv += 1
                    else:
                        ni += 1
                        pat_i[DP.bucket(fake(o))] += 1
                elif t[0] != o[0]:
                    p = pair_pattern(t, o)
                    phr.append(f"opcode {t[0]}/{o[0]} ({p}{': ' + DP.HINTS.get(p, '') if p not in hint_seen and DP.HINTS.get(p) else ''})")
                    hint_seen.add(p)

            def pats(c):
                s = []
                for p, n in c.most_common(3):
                    h = DP.HINTS.get(p, "") if p not in hint_seen else ""
                    hint_seen.add(p)
                    s.append(f"{n} {p}" + (f": {h}" if h else ""))
                return "; ".join(s)
            if nd:
                phr.insert(0, f"target has {nd} more ({pats(pat_d)})")
            if ni:
                phr.insert(0, f"ours has {ni} more ({pats(pat_i)})")
            if mv:
                phr.append(f"{mv} moved (order)")
            what = set()
            for r in g:
                if r[1] and r[2] and r[1][0] == r[2][0] and not reg_only(r[1], r[2]):
                    what |= arg_diffs(r[1], r[2])
            if what - {"reg"}:
                phr.append(" and ".join(sorted(what - {"reg"})) + " differ" + (" (registers too)" if "reg" in what else ""))
            if not phr:
                phr = ["registers only"]
            kind = "; ".join(dict.fromkeys(phr))
        shown += 1
        if shown > CAP_HUNKS and not verbose:
            continue
        if line is None or line <= 0 or src is None:
            head = "rows" + (f" at +0x{g[0][4]:X}" if g[0][4] is not None else "")
        else:
            text, note = src.where(line)
            head = f"L{line}" + (f" ({note})" if note else "") + (f": {text[:70]}" if text else "")
            for name, pct in below:
                if text and re.search(r"\b" + re.escape(name) + r"\b", text):
                    head += f"  <- inlined `{name}` ({pct:.1f} %)"
                    break
        body.append(f"{head}")
        body.append(f"  [{kind}]")
        cap = len(g) if verbose else CAP_ROWS
        for r in g[:cap]:
            off = f"+{r[4]:X}" if r[4] is not None else ""
            body.append(f"  {off:>5} {fmt(r[1]):34} | {fmt(r[2])}")
        if len(g) > cap:
            body.append(f"        ... {len(g) - cap} more rows")
    if shown > CAP_HUNKS and not verbose:
        body.append(f"... {shown - CAP_HUNKS} more lines differ (-v)")
    if body:
        by = "by our source line" if src is not None else "(no line numbers)"
        out.append(f"Differences {by} ({sum(len(v) for v in groups.values())} rows, target | ours):")
        out += body
    if regonly:
        ls = ", ".join(f"L{x}" for x in regonly if x is not None and x > 0)
        out.append(f"Registers only (the map above): {ls or len(regonly)} ")


def analyse(arg, name, verbose=False):
    u = scratch.Unit(arg)
    osym, oplain = compile_both(u)
    note = None
    try:
        if isinstance(oplain, Exception):
            raise oplain
        if isinstance(osym, Exception):
            note, osym = f"-sym on failed to compile ({osym}); no lines or names", None
        base = u.diff(oplain)
        f = base.find(name)
        d, blocks = base, None
        if osym is not None:
            if same_code(u, osym, oplain, f.name):
                d = u.diff(osym)
                f = d.fn[f.name]
                blocks = dwarf(u.root, osym)
            else:
                note = "-sym on changes this function's code: no lines or names"
    finally:
        for o in (osym, oplain):
            if isinstance(o, Path):
                shutil.rmtree(o.parent.parent, ignore_errors=True)
    out = [f"{f.name}: {f.pct:.2f} %, {f.cls}, score {f.score}" + (f" ({f.detail})" if f.detail else "")]
    if note:
        out.append(f"note: {note}")
    if f.cls == "missing":
        out.append(f"next: not in our object; write it (or rename it in symbols.txt: python3 tools/try.py {arg})")
        return out
    if f.pct == 100:
        return out
    locs = dwarf_for(blocks, f)
    sobj = Src(u, f, called_of(f))
    src = sobj if blocks is not None else None  # without -sym on there are no lines to point at
    inl = []
    for c in sobj.callees:
        g = callee_fn(d, c)
        inl.append((c.spelling, qual(c), g))
    below = [(s, g.pct) for s, q, g in inl if g is not None and g.pct < 100]
    regmap = reg_section(f, locs, out)
    shifted = stack_section(f, locs, out)
    hunks_section(f, src, below, regmap, verbose, out, shifted)
    if inl:
        out.append("Inlined from this file: " + ", ".join(
            f"`{q}` " + (f"{g.pct:.1f} % {g.cls}" if g is not None else "(no copy of its own)") for _, q, g in inl[:8]))
    bl = [g for _, _, g in inl if g is not None and g.pct < 100]
    if bl:
        g = root_of(sobj.p, d, bl)
        out.append(f"DERIVED: inlined `{g.demangled.split('(')[0]}` is at {g.pct:.2f} % ({g.cls}); fix that one first, "
                   "this one usually follows.")
        out.append(f"next: python3 tools/diag.py {arg} '{g.name}'")
    elif f.cls.split(" + ")[0] in REGISH:
        out.append(f"next: python3 tools/permute.py {arg} '{f.name}'   (then --tier b; a tier b result counts only at 100 %)")
    elif f.cls == "reloc-name":
        out.append("next: only relocation names differ: split the literal into this unit or fix the symbol (splits.txt)")
    else:
        out.append(f"next: fix the hunks above by hand (behaviour: python3 tools/fingerprint.py {arg} '{f.name}'), "
                   f"then python3 tools/permute.py {arg} '{f.name}'")
    return out


def unit_mode(arg):
    u = scratch.Unit(arg)
    d = u.build()
    fs = sorted((f for f in d.fn.values() if f.pct < 100), key=lambda f: f.addr)
    p = None
    try:
        import permute
        p = permute.Parsed(u, u.source().encode("utf-8", "surrogateescape"))
    except Exception as e:  # noqa: BLE001
        print(f"(no source parse: {e}; every function shown as root)")
    roots, derived = [], []
    for f in fs:
        why = None
        if p is not None and f.cls != "missing":
            bl = below_of(p, d, f)
            if bl:
                g = root_of(p, d, bl)
                why = f"inlines `{g.demangled.split('(')[0]}` ({g.pct:.1f} %)" + (f" +{len(bl) - 1} more" if len(bl) > 1 else "")
        line = f"{f.pct:7.2f} %  {f.cls[:28]:28} {f.name}"
        (derived if why else roots).append(("derived " if why else "root    ") + line + (f"  <- {why}" if why else ""))
    print(f"{u.name.split('/', 1)[-1]}: {len(fs)} functions below 100 % ({len(roots)} root, {len(derived)} derived)")
    for l in roots + derived:
        print("  " + l)


def main():
    import grind_broker
    grind_broker.maybe_delegate("diag", sys.argv[1:])
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv[1:] or "--verbose" in sys.argv[1:]
    if not argv or "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    try:
        if len(argv) == 1:
            unit_mode(argv[0])
        else:
            print("\n".join(analyse(argv[0], argv[1], verbose)))
    except (KeyError, scratch.CompileError) as e:
        sys.exit(f"diag: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
