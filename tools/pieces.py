#!/usr/bin/env python3
"""A large function cut into pieces, to be solved one at a time.

  python3 tools/pieces.py <unit> <function>            # the scoreboard: every piece, how far it is
  python3 tools/pieces.py <unit> <function> <N> [-v]   # one piece: our source, the original's
                                                       # instructions for exactly that stretch, the rows that differ
  python3 tools/pieces.py <unit> <function> --open     # only the pieces that still differ, worst first

A 5 KB function at 85 % is not one problem but thirty small ones. This cuts OUR source of the
function into pieces (its top-level statements; an if, loop or switch longer than --max lines is cut
into the statements inside it, its head becoming a piece of its own; short neighbours are joined),
compiles the unit with line numbers (`-sym on`, tools/scratch.py) and assigns every aligned row of
objdiff's diff to the piece its source line belongs to. Instructions only the original has go to the
piece of the row before them.

Work on the worst piece first: look at it (`pieces.py ... N`), change those lines, run
`tools/try.py`, look at the scoreboard again. A piece that reads `ok` matches the original
instruction for instruction; the function is done when every piece is. To search one piece
mechanically: `python3 tools/permute.py <unit> <function> --lines A-B`.

Pieces follow our source, so they are only as good as its structure: when a stretch of the original
has no counterpart in our source at all, its instructions pile up in the piece before the gap (that
piece then shows `target +N`). Code inlined from another function of this file counts for the
piece that calls it. A piece that differs in registers or stack slots only usually follows from a
structural difference elsewhere (a frame of another size shifts every slot): fix the pieces with
`target +N`, `ours +N`, another opcode or another value first; --open lists those first.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permute as P  # noqa: E402
import scratch  # noqa: E402

K = P.K


def inner_statements(st):
    """The statements one level inside st's blocks (through if/else chains, loop bodies, cases)."""
    out = []

    def down(n):
        for c in n.get_children():
            if c.kind == K.COMPOUND_STMT:
                out.extend(c.get_children())
            elif c.kind in (K.IF_STMT, K.CASE_STMT, K.DEFAULT_STMT, K.FOR_STMT, K.WHILE_STMT, K.DO_STMT, K.SWITCH_STMT,
                            K.CXX_TRY_STMT, K.CXX_CATCH_STMT, K.LABEL_STMT):
                down(c)
    down(st)
    return [x for x in out if x.extent.start.line >= st.extent.start.line]


def cut(fn, max_lines=24, join=8):
    """[(first line, last line)] covering fn from its signature to its closing brace."""
    body = P.body_of(fn)
    raw = []

    def add(st):
        l1, l2 = st.extent.start.line, st.extent.end.line
        subs = inner_statements(st) if st.kind != K.COMPOUND_STMT else list(st.get_children())
        if l2 - l1 + 1 <= max_lines or not subs:
            raw.append((l1, l2))
            return
        if subs[0].extent.start.line > l1:
            raw.append((l1, subs[0].extent.start.line - 1))  # the head: condition, loop header, switch value
        for x in subs:
            add(x)
    for st in body.get_children():
        add(st)
    raw.sort()
    # close the gaps (else lines, closing braces) and join short neighbours
    pieces = []
    for l1, l2 in raw:
        if pieces and l1 <= pieces[-1][1]:
            pieces[-1] = (pieces[-1][0], max(pieces[-1][1], l2))
        elif pieces and (l2 - pieces[-1][0] + 1) <= join:
            pieces[-1] = (pieces[-1][0], l2)
        else:
            pieces.append((l1, l2))
    for k in range(len(pieces) - 1):
        pieces[k] = (pieces[k][0], pieces[k + 1][0] - 1)
    first, last = fn.extent.start.line, fn.extent.end.line
    if not pieces:
        return [(first, last)]
    pieces[0] = (first, pieces[0][1])
    pieces[-1] = (pieces[-1][0], last)
    return pieces


def assign(f, pieces):
    """rows of f per piece: {piece index: [row]}; a row without a usable line goes with the row before it."""
    out = {k: [] for k in range(len(pieces))}
    cur = 0
    for row in f.rows:
        line = row[3]
        if line is not None:
            k = next((i for i, (a, b) in enumerate(pieces) if a <= line <= b), None)
            if k is not None:
                cur = k
        out[cur].append(row)
    return out


def summary(rows):
    """(original instructions, differing rows, score, structural differences, text)."""
    n = sum(1 for r in rows if r[1] is not None)
    diff = [r for r in rows if r[0]]
    score = sum(scratch.row_score(r[0], r[1], r[2]) for r in diff)
    tgt = sum(1 for r in diff if r[2] is None)
    ours = sum(1 for r in diff if r[1] is None)
    ops = regs = stack = imm = 0
    for kind, t, o, _, _ in diff:
        if t is None or o is None:
            continue
        if t[0] != o[0]:
            ops += 1
            continue
        kinds = set()
        for x, y in zip(t[1], o[1]):
            if x == y:
                continue
            if scratch.T.REG.match(x) and scratch.T.REG.match(y):
                kinds.add("r")
            elif "r1" in t[1] and "r1" in o[1] and x.lstrip("-").isdigit() and y.lstrip("-").isdigit():
                kinds.add("s")  # a displacement off the stack pointer
            elif x.startswith("@") and y.startswith("@"):
                kinds.add("b")
            else:
                kinds.add("i")
        if "i" in kinds or (t[2] != o[2] and not kinds):
            imm += 1
        elif "r" in kinds:
            regs += 1
        elif "s" in kinds:
            stack += 1
    structural = tgt + ours + ops + imm
    parts = [f"target +{tgt}" if tgt else "", f"ours +{ours}" if ours else "", f"{ops} other opcode" if ops else "",
             f"{imm} value/symbol" if imm else ""]
    soft = [f"{regs} registers" if regs else "", f"{stack} stack slots" if stack else ""]
    text = ", ".join(x for x in parts if x)
    softt = ", ".join(x for x in soft if x)
    if not text and softt:
        text = softt + " only (often follows from another piece)"
    elif softt:
        text += "; " + softt
    return n, len(diff), score, structural, text


def fmt(i):
    return "" if i is None else (i[0] + " " + ", ".join(a if a != "RELOC" else (i[2] or "?") for a in i[1]))[:38]


def main():
    import grind_broker
    grind_broker.maybe_delegate("pieces", sys.argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("unit")
    ap.add_argument("function")
    ap.add_argument("piece", nargs="?", type=int)
    ap.add_argument("--open", action="store_true", help="only pieces that differ, worst first")
    ap.add_argument("--max", type=int, default=24, help="cut statements longer than this many lines (default 24)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    try:
        unit = scratch.Unit(a.unit)
        d = unit.build(sym=True)
        f = d.find(a.function)
    except (KeyError, scratch.CompileError) as e:
        sys.exit(str(e))
    finally:
        try:
            unit.clean()
        except NameError:
            pass
    if f.cls == "missing":
        sys.exit(f"{f.name}: not in our object yet (nothing to cut)")
    data = unit.source().encode("utf-8", "surrogateescape")
    p = P.Parsed(unit, data)
    fn = p.locate(f.demangled, next((r[3] for r in f.rows if r[3]), None))
    if fn is None or P.body_of(fn) is None:
        sys.exit(f"{f.name}: its definition was not found in {unit.src}")
    pieces = cut(fn, a.max)
    rows = assign(f, pieces)
    src = data.decode("utf-8", "replace").split("\n")
    if not f.rows:
        print(f"{f.name}: {f.pct:.2f} %: every piece matches")
        return 0
    if a.piece is None:
        total = sum(1 for r in f.rows if r[0])
        print(f"{f.name}: {f.pct:.2f} %, {f.cls}; {len(pieces)} pieces, {sum(1 for k in rows if any(r[0] for r in rows[k]))} still differ "
              f"({total} of {len(f.rows)} rows)")
        order = list(range(len(pieces)))
        info = {k: summary(rows[k]) for k in order}
        if a.open:
            order = sorted((k for k in order if info[k][1]), key=lambda k: (-info[k][3], -info[k][2]))
        for k in order:
            n, nd, score, _, what = info[k]
            l1, l2 = pieces[k]
            head = " ".join(src[l1 - 1].split())[:44] if l1 - 1 < len(src) else ""
            offs = [r[4] for r in rows[k] if r[4] is not None]
            span = f"+{offs[0]:X}..+{offs[-1]:X}" if offs else "(no code)"
            state = "ok" if not nd else f"{nd:3} differ: {what}"
            print(f"  #{k:<3} L{l1}-{l2:<6} {span:14} {n:4} insns  {state:62}  {head}")
        worst = max(info, key=lambda k: (info[k][3], info[k][2]))
        if info[worst][1]:
            print(f"worst: python3 tools/pieces.py {a.unit} '{f.name}' {worst}")
        return 0
    if not 0 <= a.piece < len(pieces):
        sys.exit(f"pieces are numbered 0..{len(pieces) - 1}")
    l1, l2 = pieces[a.piece]
    n, nd, score, _, what = summary(rows[a.piece])
    offs = [r[4] for r in rows[a.piece] if r[4] is not None]
    print(f"{f.name} piece #{a.piece} of {len(pieces)}: lines {l1}-{l2}, {n} original instructions"
          + (f" (+{offs[0]:X}..+{offs[-1]:X})" if offs else "") + (f"; {nd} rows differ: {what}" if nd else "; matches"))
    print("== our source ==")
    for ln in range(l1, min(l2, l1 + (400 if a.verbose else 60)) + 1):
        if ln - 1 < len(src):
            print(f"{ln:5}  {src[ln - 1]}")
    if l2 - l1 > 60 and not a.verbose:
        print(f"       ... {l2 - l1 - 60} more lines (-v)")
    print("== original | ours (rows marked > differ) ==")
    cap = 400 if a.verbose else 90
    shown = rows[a.piece] if a.verbose or nd == 0 else None
    if shown is None:  # the differing rows with two rows of context
        keep = set()
        for i, r in enumerate(rows[a.piece]):
            if r[0]:
                keep.update(range(max(0, i - 2), min(len(rows[a.piece]), i + 3)))
        shown, last = [], None
        for i in sorted(keep):
            if last is not None and i != last + 1:
                shown.append(None)
            shown.append(rows[a.piece][i])
            last = i
    for r in shown[:cap]:
        if r is None:
            print("        ...")
            continue
        kind, t, o, line, off = r
        mark = ">" if kind else " "
        print(f"{mark}{('+%X' % off) if off is not None else '':>6}  {fmt(t):38} | {fmt(o):38} {('L%d' % line) if line else '':6} {kind or ''}")
    if len(shown) > cap:
        print(f"        ... {len(shown) - cap} more rows (-v)")
    if nd:
        print(f"search this piece: python3 tools/permute.py {a.unit} '{f.name}' --lines {l1}-{l2}   (then --tier b)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
