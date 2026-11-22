#!/usr/bin/env python3
"""Leads for header/class inlines the original used but our source writes out by hand.

  python3 tools/inline_leads.py [--src] [--asm] [--top 30] [--min-fns 3] [--json FILE]

A missing inline changes the creation order of values, hence register colouring, stack slots and
scheduling (docs/REGALLOC.md rules 1-4). Proven case (2290324a7): 14 copies of
`getActorManager_801F856C()->findActorBySerial_801F666C(field_0xd68)` became one
`Player_804A6F38::heldActor()` inline with a named local.

Source side (--src, default). Every function body of src/game/*.cpp is cut out (brace matching at
file level and inside class bodies; comments, strings and preprocessor lines removed, whitespace
collapsed). From each body it collects
  * call chains: an expression with two or more calls joined by -> or . (`a()->b(x)`,
    `getFoo()->bar`), or a call whose argument is a call (`f(g(x))`);
  * shapes: the same chains with their arguments elided (`a(…)->b(…)`);
  * statements: every `;`-terminated statement with at least one call;
  * statement pairs: two consecutive statements, at least one with a call.
An expression counts once per function. Kept are those found in >= --min-fns functions.
Strings and character constants are blanked while parsing but shown as written.

Asm side (--asm). The shared instruction blocks of tools/clones.py's index (build/clones/, the
original's asm under build/G4SE01/asm/game), counted the same way per function (__sinit
functions left out). Of blocks found in the same set of functions only the longest is kept.
Each is labelled with its length, the helper clones.py recognises in it, and the calls in it.

Ranking. Each lead is scored by the functions that contain it and are NOT at 100 % in
build/G4SE01/report_honest.json: their count, then their total size in bytes. Functions are
matched to the report by unit and by the last identifier of the demangled name (fn_80273518,
Player_804A6F38::fn_80273518); a name used twice in a unit counts its worst copy.

The report is a lead list, nothing more: an inline is real only when introduced at EVERY site of
the expression, compiled (tools/try.py) and compared function by function (tools/fdiff.py)
with gains and no losses at 100 %.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "game"
REPORT = ROOT / "build" / "G4SE01" / "report_honest.json"

KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case", "new",
            "delete", "static_cast", "reinterpret_cast", "const_cast", "goto", "default"}


# ---------------------------------------------------------------- report

def report_status():
    """{(unit, short name): (pct, size)}; worst copy if a name repeats."""
    out = {}
    if not REPORT.exists():
        sys.exit(f"{REPORT} missing (ninja build/G4SE01/report_honest.json)")
    for u in json.loads(REPORT.read_text()).get("units", []):
        name = u["name"].split("/", 1)[-1]
        if not name.startswith("game/"):
            continue
        unit = name[len("game/"):]
        for f in u.get("functions", []):
            dem = (f.get("metadata") or {}).get("demangled_name") or f["name"]
            short = short_name(dem)
            pct = float(f.get("fuzzy_match_percent") or 0)
            size = int(f.get("size") or 0)
            for key in {(unit, short), (unit, f["name"])}:
                old = out.get(key)
                if old is None or pct < old[0]:
                    out[key] = (pct, size)
    return out


def short_name(dem):
    head = dem.split("(", 1)[0]
    return head.split("::")[-1].strip()


# ---------------------------------------------------------------- source parsing

def strip_source(text, keep_strings=False):
    """Comments, string/char literals and preprocessor lines blanked (lengths kept)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1] if keep_strings else c + "_" * max(0, j - i - 1) + c)
            i = j + 1
        elif c == "#" and (i == 0 or text[i - 1] == "\n" or text[:i].rsplit("\n", 1)[-1].strip() == ""):
            j = i
            while True:
                k = text.find("\n", j)
                if k < 0:
                    k = n
                    break
                if text[k - 1] == "\\":
                    j = k + 1
                    continue
                break
            out.append(re.sub(r"[^\n]", " ", text[i:k]))
            i = k
        else:
            out.append(c)
            i += 1
    return "".join(out)


FN_HEAD = re.compile(r"([~\w]+(?:<[^<>{};]*>)?)\s*\(([^{};]*)\)\s*(?:const\s*)?(?::[^{;]*)?$", re.S)


def functions(text):
    """[(name, body)] for every function definition (top level, namespaces, class bodies)."""
    s = strip_source(text)
    shown = strip_source(text, keep_strings=True)
    out = []

    def scan(lo, hi):
        i, seg = lo, lo
        while i < hi:
            c = s[i]
            if c == ";":
                seg = i + 1
            elif c == "{":
                j = match_brace(s, i)
                head = s[seg:i].strip()
                m = FN_HEAD.search(head)
                if m and not re.search(r"\b(class|struct|union|enum|namespace)\b", head.split("(")[0]) \
                        and "=" not in head.split("(")[0]:
                    name = m.group(1).split("<")[0]
                    if name not in KEYWORDS:
                        out.append((name, s[i + 1:j], shown[i + 1:j]))
                elif re.search(r"\b(class|struct|namespace|union)\b", head) or head.startswith("extern"):
                    scan(i + 1, j)
                i = j
                seg = i + 1
            elif c == "}":
                seg = i + 1
            i += 1
    scan(0, len(s))
    return out


def match_brace(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(s) - 1


def norm(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*(->|\.|\(|\)|\[|\]|,)\s*", lambda m: m.group(1) + (" " if m.group(1) == "," else ""), t)
    return t


def close_paren(s, i, o="(", c=")"):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == o:
            depth += 1
        elif s[j] == c:
            depth -= 1
            if depth == 0:
                return j
    return -1


CALL = re.compile(r"[A-Za-z_]\w*\s*\(")


def call_chains(body, shown):
    """Postfix expressions with >= 2 calls (a()->b(), a.b().c), or a call as call argument."""
    found = set()
    for m in CALL.finditer(body):
        name = m.group(0)[:-1].strip()
        if name in KEYWORDS:
            continue
        st = m.start()
        # walk back over a chain prefix: ident, ::, ->, ., ) ... (
        k = st
        while True:
            p = k
            while p > 0 and body[p - 1] == " ":
                p -= 1
            if body[p - 2:p] in ("->", "::") or body[p - 1:p] == ".":
                p -= 2 if body[p - 2:p] in ("->", "::") else 1
                while p > 0 and body[p - 1] == " ":
                    p -= 1
                q = p
                if p > 0 and body[p - 1] in ")]":
                    o = "(" if body[p - 1] == ")" else "["
                    depth, q = 0, p - 1
                    while q >= 0:
                        if body[q] in ")]":
                            depth += 1
                        elif body[q] in "([":
                            depth -= 1
                            if depth == 0:
                                break
                        q -= 1
                while q > 0 and (body[q - 1].isalnum() or body[q - 1] == "_"):
                    q -= 1
                if q == p:
                    break
                k = q
                continue
            break
        if k != st:
            continue  # this call is inside a chain found from its start
        # walk forward over the chain
        e = body.find("(", m.start())
        e = close_paren(body, e)
        if e < 0:
            continue
        e += 1
        ncalls = 1
        while True:
            r = re.match(r"\s*(->|\.)\s*([A-Za-z_]\w*)\s*", body[e:])
            if r:
                e2 = e + r.end()
                if e2 < len(body) and body[e2] == "(":
                    c = close_paren(body, e2)
                    if c < 0:
                        break
                    e = c + 1
                    ncalls += 1
                else:
                    e = e + r.end() - (len(r.group(0)) - len(r.group(0).rstrip()))
                continue
            r = re.match(r"\s*\[", body[e:])
            if r:
                c = close_paren(body, e + r.end() - 1, "[", "]")
                if c < 0:
                    break
                e = c + 1
                continue
            break
        expr = norm(shown[st:e])
        inner = len(CALL.findall(expr))
        if ncalls >= 2 or inner >= 2:
            found.add(expr)
    return found


def shape(expr):
    """A call chain with its arguments elided: getFoo()->bar(...)."""
    out, depth = [], 0
    for c in expr:
        if c == "(":
            if depth == 0:
                out.append("(")
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                out.append(")")
        elif depth == 0:
            out.append(c)
    return "".join(out).replace("()", "(…)") if depth == 0 else expr


def statements(body, shown):
    """Statements with a call, and consecutive pairs (with a call), normalised."""
    parts, k = [], 0
    for m in re.finditer(r"[;{}]", body):
        parts.append(shown[k:m.end()])
        k = m.end()
    parts.append(shown[k:])
    sts = []
    for p in parts:
        p = norm(p.rstrip("{}"))
        p = re.sub(r"^(else|do)\b\s*", "", p)
        if p.endswith(";") and len(p) > 1:
            sts.append(p)
        elif not p.endswith(";"):
            sts.append(None)  # control-flow boundary
    single, pairs = set(), set()
    for i, st in enumerate(sts):
        if st is None:
            continue
        hascall = any(n[:-1].strip() not in KEYWORDS for n in CALL.findall(st))
        if hascall and not st.startswith("return;"):
            single.add(st)
        if i + 1 < len(sts) and sts[i + 1] is not None:
            nxt = sts[i + 1]
            if hascall or any(n[:-1].strip() not in KEYWORDS for n in CALL.findall(nxt)):
                pairs.add(st + " " + nxt)
    return single, pairs


def src_leads(status):
    occ = {"chain": defaultdict(set), "shape": defaultdict(set), "stmt": defaultdict(set),
           "pair": defaultdict(set)}
    for path in sorted(SRC.glob("*.cpp")):
        unit = path.stem
        for name, body, shown in functions(path.read_text(errors="replace")):
            fn = (unit, name)
            for e in call_chains(body, shown):
                occ["chain"][e].add(fn)
                occ["shape"][shape(e)].add(fn)
            single, pairs = statements(body, shown)
            for e in single:
                occ["stmt"][e].add(fn)
            for e in pairs:
                occ["pair"][e].add(fn)
    return occ


# ---------------------------------------------------------------- asm side

def asm_leads():
    sys.path.insert(0, str(ROOT / "tools"))
    import clones
    import os
    ns = argparse.Namespace(units=None, min=10, jobs=max(4, (os.cpu_count() or 8) // 2))
    d = clones.load(ns, lambda m: print(m, file=sys.stderr))
    ix, nodes, nh = d["ix"], d["nodes"], d["node_helper"]
    out, best = {}, {}
    for nid, (mem, L) in enumerate(nodes):
        fns = set()
        for s in mem:
            f = ix.fns[ix.fn_of[s]]
            if f[1].startswith("__sinit"):
                continue
            fns.add((f[0].replace("game/", "").removesuffix(".s"), f[1]))
        h = nh.get(nid)
        calls = sorted({t.split()[-1] for t in ix.text[mem[0]:mem[0] + L] if t.startswith("bl ")})
        label = f"[{L} insns] " + (f"inlined {ix.fns[h[0]][1]}; " if h else "") + \
            ("calls " + ", ".join(calls[:4]) + "; " if calls else "") + \
            " ; ".join(ix.text[mem[0]:mem[0] + 3]) + " ..."
        key = frozenset(fns)
        if key in best and best[key][0] >= L:
            continue  # a sub-block of a longer one in the same functions
        if key in best:
            out.pop(best[key][1])
        best[key] = (L, (nid, label))
        out[(nid, label)] = fns
    return out


# ---------------------------------------------------------------- ranking

def rank(occ, status, min_fns):
    rows = []
    for expr, fns in occ.items():
        if len(fns) < min_fns:
            continue
        bad, badbytes, known = 0, 0, 0
        for fn in fns:
            st = status.get(fn)
            if st is None:
                continue
            known += 1
            if st[0] < 100.0:
                bad += 1
                badbytes += st[1]
        rows.append({"expr": expr, "fns": len(fns), "known": known, "non100": bad, "bytes": badbytes,
                     "units": sorted({f[0] for f in fns}),
                     "sites": sorted(f"{u}:{n}" for u, n in fns)})
    rows.sort(key=lambda r: (-r["non100"], -r["bytes"], -r["fns"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", action="store_true", help="source-side leads (default when neither is given)")
    ap.add_argument("--asm", action="store_true", help="asm-side leads (clones.py index)")
    ap.add_argument("--kind", default="chain,shape,stmt,pair", help="source kinds: chain,shape,stmt,pair")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--min-fns", type=int, default=3)
    ap.add_argument("--grep", help="only leads whose text matches this regex")
    ap.add_argument("--json")
    a = ap.parse_args()
    if not a.src and not a.asm:
        a.src = True
    status = report_status()
    result = {}
    if a.src:
        occ = src_leads(status)
        for kind in a.kind.split(","):
            result[kind] = rank(occ[kind], status, a.min_fns)
    if a.asm:
        occ = asm_leads()
        rows = rank(occ, status, a.min_fns)
        for r in rows:
            r["expr"] = r["expr"][1]
        result["asm"] = rows
    for kind, rows in result.items():
        if a.grep:
            rows = [r for r in rows if re.search(a.grep, r["expr"])]
        print(f"== {kind}: {len(rows)} leads (in >= {a.min_fns} functions)")
        print(f"{'non100':>6} {'bytes':>7} {'fns':>4} {'units':>5}  expression")
        for r in rows[:a.top]:
            e = r["expr"] if len(r["expr"]) <= 150 else r["expr"][:147] + "..."
            print(f"{r['non100']:>6} {r['bytes']:>7} {r['fns']:>4} {len(r['units']):>5}  {e}")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
