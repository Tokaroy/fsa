#!/usr/bin/env python3
"""Apply or revert the evidence-based names manifest (docs/names/names.tsv).

Usage:
  python3 tools/rename.py                 # dry run: state of every row, nothing written
  python3 tools/rename.py --apply         # old -> new for every applicable row
  python3 tools/rename.py --revert        # new -> old for every applicable row
  python3 tools/rename.py ... --verify    # then run ninja and compare the DOL SHA-1
  python3 tools/rename.py ... --only NAME[,NAME]   # restrict to rows whose old or new name is listed

Method and evidence rules: docs/names/METHOD.md. The manifest is the only
input: the tool is re-runnable after other branches merge (rows already
applied are skipped, rows a merge reintroduced old names for are finished)
and --revert undoes it exactly, because every new name carries its address
(or, at high confidence, was checked to exist nowhere else) and so never
occurred in the tree before the rename.

Manifest columns (tab separated, `#` comments allowed):
  address     8 hex digits: the vtable (class, member), the function, or the object (global)
  kind        class | function | global | member
  old         the current identifier (dtk placeholder or provisional name)
  new         the new identifier; must end in _<address> unless confidence is high
              (member: in _0x<slot>, the slot offset of the old `vfunc_0x<slot>`)
  confidence  high | med | low   the honest evidence grade; never relabelled to get a row applied
  apply       yes | no           whether the row is applied; decided per row, not by the grade.
                                 Low rows are applied (owner decision 2026-11-05) and stay low:
                                 docs/names/LOW_CONFIDENCE.md lists them (tools/names_low.py)
  evidence    citations (string address + text, donor file + function, msg#, actor ID, ...)

What a row rewrites, in every tracked text file except the excluded ones:
  * the plain identifier `old` (word-bounded; `old__...` mangled tails count,
    `old.h` / `old.cpp` file names do not), and
  * for a class, its CodeWarrior-mangled form `<len(old)>old` (e.g.
    `__dt__12cls_804B1378Fv`), with the length prefix re-computed.
A class name inside a mangled template argument (`<...>`) would change the
template's own length prefix: such a row is refused.

A row is BLOCKED (reported, not applied) when its old name occurs in a file
the rename must not touch: the tools (tools/**/*.py), configure.py outside
its `#` comment lines, or the protected config files. Such names need a
coordinator change to the tool first (refer to the entity by address).

Generator-owned files (the units of config/G4SE01/gen_game.tsv: their
sources and act headers) are renamed like any source: tools/gen_game.py
follows the manifest. It takes the names it emits from symbols.txt (by
address) and reads its own records, the gen_game.tsv rows and the
pre-generation blobs they pin, through to_current() below, which brings a
text to the names the tree currently uses (an applied row's old name ->
new, an unapplied row's new name -> old). So gen_game.tsv and the pinned
blobs stay as recorded, and --apply / --revert need no generator edit.
configure.py's comment lines are renamed too (its code never is).

A member row names a virtual slot once, at the class that declares it (the
row's address is that class's vtable): `vfunc_0x54` of EnemyBase_804A4808
and of every class derived from it (the hierarchy is read from the
`class X : public Y` declarations in include/ and src/). The same placeholder
is also a different slot of unrelated classes (EscortBase_8049E0C8 declares
its own vfunc_0x54), so the forward rename is scoped: an occurrence is
renamed when its class is a descendant: `Cls::old`, the mangled `old__<n>Cls`,
or the class body / `Cls::fn` definition it sits in. Occurrences with no
such context (comments, docs) follow the file: renamed when every class
the file resolves for `old` is a descendant (for progress/game__<unit>.md,
the classes of src/game/<unit>.cpp), else left and counted. When no class
outside the hierarchy has the member at all the rename is plain, as for a
function. A wrong scope cannot pass unnoticed in code: the compiler (member
not found) and the link (symbols.txt names) fail. --revert is plain: the new
name is unique. to_current() renames plainly too: the generator's records
are actors of ActorBase / EnemyBase only.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs/names/names.tsv"
SYMBOLS = "config/G4SE01/symbols.txt"
SHA1_FILE = ROOT / "config/G4SE01/build.sha1"

KINDS = {"class", "function", "global", "member", "field"}
SLOT = re.compile(r"_?(0x[0-9A-Fa-f]+)\Z")

# Never rewritten. Paths are relative to the repository root.
EXCLUDE_PREFIX = ("build/", "orig/", "site/", ".github/", "tools/", "config/")
EXCLUDE_FILES = {"docs/names/names.tsv", "docs/names/METHOD.md", "docs/names/LOW_CONFIDENCE.md",
                 "objdiff.json", "progress/claims.json"}
INCLUDE_EXTRA = {SYMBOLS}  # the one config file that is rewritten
COMMENT_ONLY = {"configure.py"}  # only its full-line `#` comments are rewritten
TEXT_SUFFIX = {".c", ".cpp", ".cp", ".h", ".hpp", ".inc", ".s", ".md", ".txt", ".tsv", ".py", ".yml", ""}

# Blocking: an old name here means "do not rename" (generator / tooling / protected).
BLOCK_PREFIX = ("tools/",)
BLOCK_FILES = {"config/G4SE01/config.yml",
               "config/G4SE01/approved_symbol_changes.txt", "config/G4SE01/provenance_reviewed.txt",
               "config/G4SE01/splits.txt"}

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ADDR_SUFFIX = re.compile(r"_([0-9A-F]{8})\Z")


def git_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [f for f in out.stdout.decode().split("\0") if f]


def comment_lines(text, keep):
    """configure.py: its full-line `#` comments (keep=True) or everything
    else (keep=False), the other lines blanked so line structure stays."""
    return "\n".join(l if l.lstrip().startswith("#") == keep else ""
                     for l in text.split("\n"))


def on_comments(text, a, b, kind):
    """substitute() on the full-line comments of text only."""
    out, n = [], 0
    for l in text.split("\n"):
        if l.lstrip().startswith("#"):
            l, k = substitute(l, a, b, kind)
            n += k
        out.append(l)
    return "\n".join(out), n


def read_manifest():
    rows, problems = [], []
    for n, line in enumerate(MANIFEST.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        if f[0] == "address":
            continue
        if len(f) != 7:
            problems.append(f"names.tsv:{n}: expected 7 columns, got {len(f)}")
            continue
        addr, kind, old, new, conf, ap, ev = f
        r = {"line": n, "apply": ap == "yes", "addr": addr, "kind": kind, "old": old, "new": new, "conf": conf, "ev": ev}
        if not re.fullmatch(r"[0-9A-F]{8}", addr):
            problems.append(f"names.tsv:{n}: address {addr!r} is not 8 upper-case hex digits")
        if ap not in ("yes", "no"):
            problems.append(f"names.tsv:{n}: apply {ap!r} is not yes|no")
        if kind not in KINDS:
            problems.append(f"names.tsv:{n}: kind {kind!r} not one of {sorted(KINDS)}")
        if conf not in ("high", "med", "low"):
            problems.append(f"names.tsv:{n}: confidence {conf!r}")
        for x in (old, new):
            if not IDENT.match(x):
                problems.append(f"names.tsv:{n}: {x!r} is not an identifier")
        if kind == "field":
            fo = re.fullmatch(r"field_(0x[0-9A-Fa-f]+)", old)
            if not fo:
                problems.append(f"names.tsv:{n}: field {old} is not a field_0x<offset> placeholder")
            elif conf != "high" and not new.endswith("_" + fo[1]):
                problems.append(f"names.tsv:{n}: {new} must keep its offset (_{fo[1]}) below high confidence")
            elif new.startswith("field_"):
                problems.append(f"names.tsv:{n}: {new} is still a placeholder")
        elif kind == "member":
            so = SLOT.search(old)
            if not so:
                problems.append(f"names.tsv:{n}: member {old} does not carry its slot (vfunc_0xNN)")
            elif conf != "high" and not new.endswith("_" + so[1]):
                problems.append(f"names.tsv:{n}: {new} must keep its slot (_{so[1]}) below high confidence")
        elif conf != "high":
            m = ADDR_SUFFIX.search(new)
            if not m or m[1] != addr:
                problems.append(f"names.tsv:{n}: {new} must keep its address (_{addr}) below high confidence")
        if not ev.strip():
            problems.append(f"names.tsv:{n}: no evidence")
        rows.append(r)
    seen_old, seen_new = {}, {}
    seen_field = {}
    for r in rows:
        if r["kind"] == "field":  # unique per class; the same placeholder is in many classes
            for key in ("old", "new"):
                k = (r["addr"], r[key])
                if k in seen_field:
                    problems.append(f"names.tsv:{r['line']}: {key} name {r[key]} of {r['addr']} also on line {seen_field[k]}")
                seen_field[k] = r["line"]
            continue
        for key, seen in (("old", seen_old), ("new", seen_new)):
            if r[key] in seen:
                problems.append(f"names.tsv:{r['line']}: {key} name {r[key]} also on line {seen[r[key]]}")
            seen[r[key]] = r["line"]
    for r in rows:
        if r["kind"] == "field":
            continue
        if r["new"] in seen_old or r["old"] in seen_new:
            problems.append(f"names.tsv:{r['line']}: chained rename ({r['old']} -> {r['new']}); not allowed")
    return rows, problems


def patterns(a, kind):
    """Regexes for identifier a: (plain, mangled or None)."""
    plain = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(a) +
                       r"(?=__|(?![A-Za-z0-9_]))(?!\.(?:h|hpp|cpp|cp|c|s|inc|o|md)\b)")
    mangled = None
    if kind == "class":
        # The length prefix delimits a mangled name; what follows is the
        # next mangled component (F, C, Fv, ...), so no lookahead.
        mangled = re.compile(re.escape(f"{len(a)}{a}"))
    return plain, mangled


def substitute(text, a, b, kind):
    plain, mangled = patterns(a, kind)
    n = 0
    if mangled:
        text, k = mangled.subn(f"{len(b)}{b}", text)
        n += k
    text, k = plain.subn(b, text)
    return text, n + k


def count(text, a, kind):
    plain, mangled = patterns(a, kind)
    return len(plain.findall(text)) + (len(mangled.findall(text)) if mangled else 0)


def parse_symbols(text):
    """{name: address} plus the list of (name, address)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"(\S+) = [^:]+:0x([0-9A-Fa-f]{8});", line)
        if m:
            out.append((m[1], m[2].upper()))
    return out


def base_name(sym):
    """fn_801F666C__21ActorManager_804A5800Fl -> fn_801F666C; __vt__... unchanged."""
    if sym.startswith("__"):
        return sym
    i = sym.find("__")
    return sym if i <= 0 else sym[:i]


def symbol_problems(r, syms, name):
    """Does symbols.txt agree that `name` (old or new) is the entity at r['addr']?"""
    a, kind = r["addr"], r["kind"]
    if kind in ("function", "global"):
        hits = [ad for s, ad in syms if base_name(s) == name]
        if not hits:
            return None  # not in symbols.txt (yet); checked by the caller
        bad = [ad for ad in hits if ad != a]
        return f"{name} names symbol(s) at {', '.join(bad)}, not {a}" if bad else ""
    if kind == "member":
        hits = [s for s, _ in syms if base_name(s) == name]
        return "" if hits else None
    vt = [ad for s, ad in syms if s == f"__vt__{len(name)}{name}"]
    if vt:
        return "" if vt == [a] else f"__vt__ of {name} is at {', '.join(vt)}, not {a}"
    return None


def row_state(r, syms):
    """True when symbols.txt holds the row's new name (applied), False when
    it holds the old one, None when it holds neither."""
    def present(name):
        if r["kind"] == "class":
            pre = f"{len(name)}{name}"
            return any(pre in s for s, _ in syms)
        if r["kind"] == "member":
            return any(base_name(s) == name for s, _ in syms)
        return any(base_name(s) == name and ad == r["addr"] for s, ad in syms)
    if present(r["new"]):
        return True
    if present(r["old"]):
        return False
    return None


_current = None


def current_renames():
    """[(from, to, kind)] that bring a text to the tree's current names: an
    applied row old -> new, an unapplied one new -> old (rows with apply=yes, whose
    state symbols.txt shows)."""
    global _current
    if _current is None:
        rows, problems = read_manifest()
        if problems:
            raise SystemExit("names.tsv: " + "; ".join(problems[:3]))
        syms = parse_symbols((ROOT / SYMBOLS).read_text())
        _current = []
        for r in rows:
            if r["kind"] == "field":  # scoped by the compiler; generator records are left to gen_game.py
                continue
            st = row_state(r, syms) if r["apply"] else None
            if st is True:
                _current.append((r["old"], r["new"], r["kind"]))
            elif st is False:
                _current.append((r["new"], r["old"], r["kind"]))
    return _current


def to_current(text):
    """text (a generator record: a pinned blob, a gen_game.tsv field) in the
    names the tree uses now. Every new name carries its address (or is
    unique, for high rows), so neither direction can hit another name."""
    if text is None:
        return None
    for a, b, kind in current_renames():
        text, _ = substitute(text, a, b, kind)
    return text


# ---------------------------------------------------------------- member rows (virtual slots)

CODE_SUFFIX = (".h", ".hpp", ".cpp", ".cp", ".c", ".inc")
CLASS_RE = re.compile(r"\b(?:class|struct)\s+(\w+)\s*(?::\s*(?:public\s+|private\s+|protected\s+)?([\w:]+))?\s*\{")
DEF_RE = re.compile(r"\b(\w+)::~?\w+\s*\([^;{}]*\)\s*(?:const\s*)?\{")


def _brace_end(t, i):
    """Index just past the brace block whose `{` is at t[i-1]."""
    d = 1
    while d and i < len(t):
        c = t[i]
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
        i += 1
    return i


_spans = {}


def code_spans(t):
    """[(start, end, class)] of class bodies and `Cls::fn(...) {` bodies, innermost last."""
    key = hash(t)
    if key in _spans:
        return _spans[key]
    out = []
    for rx in (CLASS_RE, DEF_RE):
        for m in rx.finditer(t):
            out.append((m.end(), _brace_end(t, m.end()), m[1]))
    out.sort(key=lambda s: (s[0], -s[1]))
    _spans[key] = out
    return out


class Hierarchy:
    """Class bases from the `class X : public Y {` declarations of the tree,
    and which classes have a member called `old` (a class body that names
    it, a `Cls::old` in code, or a symbols.txt symbol `old__<n>Cls...`)."""

    def __init__(self, texts):
        self.base, self.has = {}, {}
        self.texts = {f: t for f, t in texts.items() if f.endswith(CODE_SUFFIX)}
        for t in self.texts.values():
            for m in CLASS_RE.finditer(t):
                if m[2]:
                    self.base[m[1]] = m[2].split("::")[-1]
        self.syms = texts.get(SYMBOLS, "")

    def unit_classes(self, unit):
        """The classes whose bodies or member definitions src/game/<unit>.cpp holds."""
        for suf in (".cpp", ".c"):
            t = self.texts.get(f"src/game/{unit}{suf}")
            if t is not None:
                return {c for _, _, c in code_spans(t)}
        return set()

    def ancestors(self, c):
        seen = [c]
        while c in self.base and self.base[c] not in seen:
            c = self.base[c]
            seen.append(c)
        return seen

    def descends(self, c, root):
        return root in self.ancestors(c)

    def members(self, old):
        if old not in self.has:
            cls = set()
            for t in self.texts.values():
                if old not in t:
                    continue
                decl = re.compile(r"(?<![\w>.:])" + re.escape(old) + r"\s*\(")
                for m in CLASS_RE.finditer(t):  # declared in the class body (not a call, not a comment)
                    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", t[m.end():_brace_end(t, m.end())], flags=re.S)
                    body = re.sub(r"\{[^{}]*\}", "{}", body)  # inline bodies hold calls
                    if decl.search(body):
                        cls.add(m[1])
                for m in re.finditer(r"(\w+)::" + re.escape(old) + r"(?![A-Za-z0-9_])", t):
                    cls.add(m[1])
            for m in re.finditer(r"(?<![A-Za-z0-9_])" + re.escape(old) + r"__(\d+)(\w+)", self.syms):
                cls.add(m[2][:int(m[1])])
            self.has[old] = cls
        return self.has[old]


_hier = None


def hierarchy(texts):
    global _hier
    if _hier is None:
        _hier = Hierarchy(texts)
    return _hier


def class_at(syms, addr):
    """The class whose vtable symbols.txt places at addr."""
    for s, ad in syms:
        m = re.match(r"__vt__(\d+)(\w+)", s)
        if m and ad == addr and len(m[2]) == int(m[1]):
            return m[2]
    return None


def member_plan(f, t, old, inside, hier):
    """Positions of `old` in text t (file f) that belong to the hierarchy:
    (rename, left) lists of match objects. inside(cls) -> True / False /
    None (a class that has no such member)."""
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?=__|(?![A-Za-z0-9_]))")
    spans = code_spans(t) if f.endswith(CODE_SUFFIX) else []
    yes, no, unknown = [], [], []
    for m in pat.finditer(t):
        cls = None
        q = re.search(r"(\w+)::\s*\Z", t[max(0, m.start() - 80):m.start()])
        mg = re.match(r"__(\d+)(\w+)", t[m.end():m.end() + 80])
        if q:
            cls = q[1]
        elif mg:
            cls = mg[2][:int(mg[1])]
        else:
            for s, e, c in spans:
                if s <= m.start() < e:
                    cls = c  # innermost wins (sorted outer first)
        state = inside(cls) if cls else None
        (yes if state else no if state is False else unknown).append(m)
    if unknown:
        ctx = set()
        if f.startswith("progress/game__") and f.endswith(".md"):
            ctx = {inside(c) for c in hier.unit_classes(f[len("progress/game__"):-3])} - {None}
        decided = {True for _ in yes} | {False for _ in no} | ctx
        if decided == {True}:
            yes += unknown
            unknown = []
    return sorted(yes, key=lambda m: m.start()), unknown


def member_substitute(f, t, r, src, dst, forward, syms, texts):
    """(new text, renamed, left) for a member row."""
    if src not in t:
        return t, 0, 0
    hier = hierarchy(texts)
    if not forward:
        return (*substitute(t, src, dst, "function"), 0)
    root = class_at(syms, r["addr"])
    if root is None:
        return t, 0, 0
    has = hier.members(src)
    def inside(c):
        if hier.descends(c, root):
            return True
        return False if c in has else None
    if all(hier.descends(c, root) for c in has):
        return (*substitute(t, src, dst, "function"), 0)
    ren, left = member_plan(f, t, src, inside, hier)
    out, last = [], 0
    for m in ren:
        out += [t[last:m.start()], dst]
        last = m.end()
    out.append(t[last:])
    return "".join(out), len(ren), len(left)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true")
    ap.add_argument("--verify", action="store_true", help="run ninja and compare the DOL SHA-1 afterwards")
    ap.add_argument("--only", default="", help="comma-separated old or new names")
    ap.add_argument("--kind", default="", help="restrict to rows of these kinds (comma-separated)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    rows, problems = read_manifest()
    if problems:
        print("\n".join(problems))
        return 2
    only = {x for x in args.only.split(",") if x}
    if only:
        rows = [r for r in rows if r["old"] in only or r["new"] in only]
    if args.kind:
        rows = [r for r in rows if r["kind"] in args.kind.split(",")]
    frows = [r for r in rows if r["kind"] == "field"]
    rows = [r for r in rows if r["kind"] != "field"]

    files = git_files()
    scan = [f for f in files if (f in INCLUDE_EXTRA or not (f.startswith(EXCLUDE_PREFIX) or f in EXCLUDE_FILES))
            and Path(f).suffix in TEXT_SUFFIX]
    self_ = {"tools/rename.py", "tools/rename_fields.py", "tools/names_compare.py"}  # their docs cite example names
    block = [f for f in files if f.startswith(BLOCK_PREFIX) and f.endswith(".py") and f not in self_] + \
            [f for f in BLOCK_FILES if (ROOT / f).exists()]
    texts = {}
    for f in scan:
        try:
            texts[f] = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            pass
    btexts = {}
    # blobs.txt: only a `blob` line's symbol column is functional (array lines are prose).
    blobs = ROOT / "config/G4SE01/blobs.txt"
    if blobs.exists():
        btexts["config/G4SE01/blobs.txt"] = "\n".join(
            l.split()[1] for l in blobs.read_text().splitlines() if l.startswith("blob ") and len(l.split()) > 1)
    for f in block:
        try:
            btexts[f] = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            pass
    for f in COMMENT_ONLY:  # code blocks, comments are renamed
        if f in texts:
            btexts[f] = comment_lines(texts[f], keep=False)
    ctexts = {f: comment_lines(t, keep=True) if f in COMMENT_ONLY else t for f, t in texts.items()}
    syms = parse_symbols(texts[SYMBOLS])

    forward = not args.revert
    todo, report = [], {"apply": 0, "done": 0, "blocked": 0, "not-applied": 0, "missing": 0, "refused": 0}
    for r in rows:
        src, dst = (r["old"], r["new"]) if forward else (r["new"], r["old"])
        tag = f"{r['old']} -> {r['new']}"
        if not r["apply"]:
            report["not-applied"] += 1
            continue
        # Blocked: the old name is spelled out where the rename must not go.
        hits = [f for f, t in btexts.items() if count(t, r["old"], r["kind"])]
        if hits:
            report["blocked"] += 1
            if not args.quiet:
                print(f"BLOCKED  {tag}: in {', '.join(hits[:4])}{' ...' if len(hits) > 4 else ''}")
            continue
        left = 0
        if r["kind"] == "member":
            n_src = 0
            for f, t in texts.items():
                if f in COMMENT_ONLY:
                    continue
                _, k, u = member_substitute(f, t, r, src, dst, forward, syms, texts)
                n_src, left = n_src + k, left + u
        else:
            n_src = sum(count(t, src, r["kind"]) for t in ctexts.values())
        n_dst = sum(count(t, dst, r["kind"]) for t in ctexts.values())
        why = []
        if r["kind"] == "member" and class_at(syms, r["addr"]) is None:
            why.append(f"no __vt__ at {r['addr']} in symbols.txt")
        if r["kind"] == "class":
            tmpl = re.compile(r"<[^<>]*" + re.escape(f"{len(src)}{src}"))
            if any(tmpl.search(t) for t in texts.values()):
                why.append("used inside a mangled template argument")
        # symbols.txt must agree on the address for whichever name it holds.
        s_src = symbol_problems(r, syms, src)
        s_dst = symbol_problems(r, syms, dst)
        for s in (s_src, s_dst):
            if s:
                why.append(s)
        if r["kind"] in ("function", "global", "member") and s_src is None and s_dst is None:
            why.append(f"neither {src} nor {dst} is a symbol at {r['addr']} in symbols.txt")
        if r["kind"] == "class" and s_src is None and s_dst is None and not src.endswith(r["addr"]):
            why.append(f"no __vt__ for {src} and its name does not carry {r['addr']}")
        if why:
            report["refused"] += 1
            print(f"REFUSED  {tag}: {'; '.join(why)}")
            continue
        if n_src == 0:
            report["done" if n_dst else "missing"] += 1
            if not n_dst:
                print(f"MISSING  {tag}: neither name occurs")
            continue
        report["apply"] += 1
        todo.append((r, src, dst))
        if not args.quiet:
            print(f"{'APPLY ' if forward else 'REVERT'}   {tag}: {n_src} occurrence(s)"
                  + (f" ({n_dst} already renamed)" if n_dst else "")
                  + (f" ({left} left: no class context)" if left else ""))

    ftodo = field_plan(frows, forward, syms, texts, report, args.quiet)
    print("rename: " + ", ".join(f"{k} {v}" for k, v in report.items()))
    if report["refused"]:
        print("rename: refused rows above; nothing written")
        return 1
    if not (args.apply or args.revert):
        return 0

    changed = set()
    global _hier
    _hier = None  # class rows above may have renamed classes: re-read the hierarchy
    for r, src, dst in todo:
        if r["kind"] == "member":
            msyms = parse_symbols(texts[SYMBOLS])
            for f, t in texts.items():
                if f in COMMENT_ONLY:
                    continue
                t2, k, _ = member_substitute(f, t, r, src, dst, forward, msyms, texts)
                if k:
                    texts[f] = t2
                    changed.add(f)
            continue
        for f, t in texts.items():
            t2, k = (on_comments if f in COMMENT_ONLY else substitute)(t, src, dst, r["kind"])
            if k:
                texts[f] = t2
                changed.add(f)
    for f in sorted(changed):
        (ROOT / f).write_text(texts[f], encoding="utf-8")
    print(f"rename: {len(changed)} file(s) written")
    if ftodo:
        if field_apply(ftodo, forward, texts):
            return 1

    if args.verify:
        return verify()
    return 0


# ---------------------------------------------------------------- field rows (data members)

def field_plan(frows, forward, syms, texts, report, quiet):
    """State of each field row; [(row, root class)] to do. See tools/rename_fields.py."""
    import rename_fields as rf
    if not frows:
        return []
    tree = rf.Tree(ROOT, {f: t for f, t in texts.items() if f.endswith(rf.CODE_SUFFIX)})
    todo = []
    for r in frows:
        tag = f"{r['old']} -> {r['new']}"
        if not r["apply"]:
            report["not-applied"] += 1
            continue
        root = class_at(syms, r["addr"])
        if root is None:
            report["refused"] += 1
            print(f"REFUSED  {tag}: no __vt__ at {r['addr']} in symbols.txt")
            continue
        st = rf.state(tree, r, root)
        if st is None:
            report["refused"] += 1
            print(f"REFUSED  {tag}: {root} declares neither name")
            continue
        if st == forward:
            report["done"] += 1
            continue
        report["apply"] += 1
        todo.append((r, root))
        if not quiet:
            print(f"{'APPLY ' if forward else 'REVERT'}   {root}::{tag}")
    return todo


def field_apply(todo, forward, texts):
    import rename_fields as rf
    tree = rf.Tree(ROOT, {f: (ROOT / f).read_text(encoding="utf-8") for f in texts if f.endswith(rf.CODE_SUFFIX)})
    rows = {id(r): (r, root) for r, root in todo}
    total = left = 0
    for p in rf.passes([r for r, _ in todo]):
        try:
            counts, k = rf.run_pass(tree, [rows[id(r)] for r in p], forward)
        except RuntimeError as e:
            print(f"rename: field pass failed, its files restored: {e}")
            return 1
        total += sum(counts.values())
        left += k
    print(f"rename: fields: {total} use(s) renamed in code, {left} doc mention(s) left")
    return 0


def verify():
    out = subprocess.run(["ninja"], cwd=ROOT)
    if out.returncode:
        print("verify: ninja failed")
        return 1
    want, path = SHA1_FILE.read_text().split()[:2]
    have = hashlib.sha1((ROOT / path).read_bytes()).hexdigest()
    print(f"verify: {path} {have} {'== build.sha1' if have == want else '!= build.sha1 ' + want}")
    return 0 if have == want else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
