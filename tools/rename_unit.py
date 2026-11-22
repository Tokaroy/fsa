#!/usr/bin/env python3
"""Apply or revert the unit (file) rows of the names manifest (docs/names/names.tsv,
kind `unit`): `src/game/tu_<addr>.cpp` -> `src/game/<name>.cpp` and everything
that spells the file name.

Usage:
  python3 tools/rename_unit.py                # dry run: APPLY / done / BLOCKED / REFUSED per row
  python3 tools/rename_unit.py --apply        # tu_<addr> -> name for every applicable row
  python3 tools/rename_unit.py --revert       # name -> tu_<addr> (exact: git diff is empty afterwards)
  python3 tools/rename_unit.py ... --only tu_80123456,other_name   # restrict to these rows (old or new)
  python3 tools/rename_unit.py ... --verify   # then configure.py, ninja and the DOL SHA-1
  python3 tools/rename_unit.py --suggest      # candidate rows for units without one (stdout, nothing written)

Method and the naming convention: docs/names/METHOD.md, "Unit (file) names".

A row (7 columns, as rename.py's): address (the unit's .text start, the hex of
its `tu_` name), kind `unit`, old `tu_<address>`, new (snake_case, ending in
`_<address>` below high confidence), confidence, apply, evidence.

What a row rewrites, in every tracked text file except the excluded ones:
  * the token `tu_<addr>` wherever it is not part of a longer word
    (`game/tu_X.cpp`, `game__tu_X`, `__sinit_tu_X_cpp`, `tu_X.h`, prose), except
    where it names something outside this repository: a review file
    (`.../_reviews/game__tu_X.review.md`), a branch (`unit/game__tu_X`) or a
    worktree (`fsa-wt/game__tu_X`) keep the old spelling;
  * the include guard part `_TU_<addr>_` (GAME_ACT_TU_X_H) -> `_<NEW>_`;
  * every tracked path containing the token (the source, its unit-local
    headers include/game/act/tu_X.h, include/game/tu_X.h, tu_X_elems.h, and
    progress/game__tu_X.md), moved with `git mv`.
symbols.txt's `__sinit_tu_<addr>_cpp` follows (MWCC names the static
initializer after the file), so the link and the SHA-1 stay unchanged.

Never rewritten (records that cite the old name on purpose, or generated):
build/, orig/, site/, names.tsv, METHOD.md, LOW_CONFIDENCE.md,
config/G4SE01/{tu_map,lib_map}.tsv (address-keyed analysis records),
approved_symbol_changes.txt and provenance_reviewed.txt (review citations).

A row is BLOCKED when its token occurs in a file whose edit needs a separate
coordinator decision: the gate-protected tools (gate.py, gen_game.py,
honest_report.py, ...), config.yml (blob headers under assets/), gen_game.tsv.

The new name must not occur anywhere in the tree before the rename (so the
revert, a plain rename back, is exact) and no path may exist under it. Rows
already applied are re-run for leftover old tokens (a merged branch's text).
"""

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

MANIFEST = ROOT / "docs/names/names.tsv"
EXCLUDE_PREFIX = ("build/", "orig/", "site/", ".github/")
EXCLUDE_FILES = {"docs/names/names.tsv", "docs/names/METHOD.md", "docs/names/LOW_CONFIDENCE.md",
                 "config/G4SE01/tu_map.tsv", "config/G4SE01/lib_map.tsv",
                 "config/G4SE01/approved_symbol_changes.txt", "config/G4SE01/provenance_reviewed.txt",
                 "objdiff.json"}
BLOCK_FILES = {"tools/gate.py", "tools/fdiff.py", "tools/progress.py", "tools/project.py",
               "tools/honest_report.py", "tools/link_check.py", "tools/try.py", "tools/data_splits.py",
               "tools/gen_game.py", "config/G4SE01/gen_game.tsv", "config/G4SE01/config.yml",
               "config/G4SE01/build.sha1"}
SELF = {"tools/rename_unit.py"}
TEXT_SUFFIX = {".c", ".cpp", ".cp", ".h", ".hpp", ".inc", ".s", ".md", ".txt", ".tsv", ".py", ".yml",
               ".json", ".sh", ".toml", ""}
CODE_SUFFIX = {".c", ".cpp", ".cp", ".h", ".hpp", ".inc"}
NEW_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*_([0-9A-F]{8})\Z")
NEW_HIGH = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
# The token names something outside the repo when its whitespace-delimited run says so.
EXTERNAL = re.compile(r"(?:_reviews/|(?:^|[^\w])unit/|fsa-wt/)[^\s]*\Z")
RUN_START = re.compile(r"[\s\"'`(\[<]")


def git_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [f for f in out.stdout.decode().split("\0") if f]


def read_rows():
    rows, problems = [], []
    for n, line in enumerate(MANIFEST.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) != 7 or f[1] != "unit":
            continue
        addr, _, old, new, conf, ap, ev = f
        r = {"line": n, "addr": addr, "old": old, "new": new, "conf": conf, "apply": ap == "yes", "ev": ev}
        if not re.fullmatch(r"[0-9A-F]{8}", addr):
            problems.append(f"names.tsv:{n}: address {addr!r}")
        if old != f"tu_{addr}":
            problems.append(f"names.tsv:{n}: old {old!r} is not tu_{addr}")
        if conf not in ("high", "med", "low") or ap not in ("yes", "no"):
            problems.append(f"names.tsv:{n}: confidence/apply {conf!r}/{ap!r}")
        if conf == "high":
            if not NEW_HIGH.match(new):
                problems.append(f"names.tsv:{n}: {new!r} is not a file stem")
        else:
            m = NEW_RE.match(new)
            if not m or m[1] != addr:
                problems.append(f"names.tsv:{n}: {new!r} must be snake_case ending in _{addr} below high confidence")
        if not ev.strip():
            problems.append(f"names.tsv:{n}: no evidence")
        rows.append(r)
    for key in ("old", "new"):
        c = collections.Counter(r[key] for r in rows)
        problems += [f"names.tsv: {key} {k} on {v} rows" for k, v in c.items() if v > 1]
    olds = {r["old"] for r in rows}
    problems += [f"names.tsv:{r['line']}: chained ({r['new']} is another row's old name)" for r in rows if r["new"] in olds]
    return rows, problems


def token_re(a):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])")


def guard_re(a):
    return re.compile(r"(?<=_)" + re.escape(a) + r"(?=_)")


def external(text, i):
    j = i
    while j > 0 and not RUN_START.match(text[j - 1]):
        j -= 1
    return bool(EXTERNAL.search(text[j:i]))


def substitute(text, a, b, code, forward):
    """(new text, count). Forward skips external references; the reverse
    needs no such care (the new name never existed before the rename)."""
    n = 0

    def rep(m):
        nonlocal n
        if forward and external(m.string, m.start()):
            return m.group(0)
        n += 1
        return b
    text = token_re(a).sub(rep, text)
    if code:
        au, bu = a.upper(), b.upper()
        text, k = guard_re(au).subn(bu, text)
        n += k
    return text, n


def count(text, a, code, forward):
    return substitute(text, a, a + "\0", code, forward)[1]


def new_path(f, a, b):
    parts = f.split("/")
    parts[-1] = token_re(a).sub(b, parts[-1])
    return "/".join(parts)


def scan_files(files):
    return [f for f in files if not (f.startswith(EXCLUDE_PREFIX) or f in EXCLUDE_FILES or f in SELF)
            and Path(f).suffix in TEXT_SUFFIX and f not in BLOCK_FILES]


def load(files):
    texts = {}
    for f in files:
        try:
            texts[f] = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            pass
    return texts


def run(rows, forward, write):
    files = git_files()
    texts = load(scan_files(files))
    blockt = load([f for f in BLOCK_FILES if f in files])
    allt = {**texts, **blockt}
    problems, plan = [], []
    for r in rows:
        a, b = (r["old"], r["new"]) if forward else (r["new"], r["old"])
        src_a, src_b = f"src/game/{a}.cpp", f"src/game/{b}.cpp"
        have_a, have_b = src_a in files, src_b in files
        if have_a and have_b:
            problems.append(f"REFUSED {r['old']}: both {src_a} and {src_b} exist")
            continue
        if not have_a and not have_b:
            problems.append(f"REFUSED {r['old']}: neither {src_a} nor {src_b} is tracked")
            continue
        blocked = [f for f, t in blockt.items() if count(t, r["old"], False, True)]
        if blocked and forward:
            print(f"BLOCKED {r['old']} -> {r['new']}: named in {', '.join(sorted(blocked))}")
            continue
        if have_a and forward:
            clash = [f for f, t in allt.items() if r["new"] in t or (Path(f).suffix in CODE_SUFFIX and r["new"].upper() in t)]
            clash += [f for f in files if r["new"] in f]
            if clash:
                problems.append(f"REFUSED {r['old']}: {r['new']} already occurs in {', '.join(sorted(set(clash))[:4])}")
                continue
        moves = [(f, new_path(f, a, b)) for f in files if token_re(a).search(f.rsplit("/", 1)[-1])
                 and not f.startswith(EXCLUDE_PREFIX) and f not in EXCLUDE_FILES]
        edits = {}
        for f, t in texts.items():
            t2, k = substitute(t, a, b, Path(f).suffix in CODE_SUFFIX, forward)
            if k:
                edits[f] = (t2, k)
        state = "APPLY" if have_a else "done"
        if have_b and not edits and not moves:
            if not write:
                print(f"done    {r['old']} -> {r['new']}" if forward else f"done    {r['new']} -> {r['old']}")
            continue
        print(f"{state:7} {a} -> {b}: {len(moves)} path(s), {sum(k for _, k in edits.values())} occurrence(s) in {len(edits)} file(s)")
        plan.append((r, a, b, moves, edits))
        for f, (t2, _) in edits.items():  # later rows see this row's result
            texts[f] = t2
    if problems:
        print("\n".join(problems))
        return 2
    if not write:
        return 0
    final = {}
    for _, a, b, moves, edits in plan:
        for f, (t2, _) in edits.items():
            final[f] = t2
    for f, t in final.items():
        (ROOT / f).write_text(t, encoding="utf-8")
    for _, a, b, moves, _ in plan:
        for f, g in moves:
            (ROOT / g).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "mv", f, g], cwd=ROOT, check=True)
    print(f"{'applied' if forward else 'reverted'} {len(plan)} row(s); run python3 configure.py before ninja")
    return 0


def verify():
    subprocess.run([sys.executable, "configure.py"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    p = subprocess.run(["ninja"], cwd=ROOT, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
    print("\n".join(tail))
    return 0 if p.returncode == 0 and any(l.endswith(": OK") for l in tail) else 1


# ---------------------------------------------------------------- --suggest

DEF = re.compile(r"^[^\s#/][^;\n]*?\b([A-Za-z][A-Za-z0-9]*_[0-9A-F]{8})::~?\w+\s*\((?![^\n]*;\s*$)", re.M)
CLASS = re.compile(r"^(?:class|struct)\s+([A-Z][A-Za-z0-9]*_[0-9A-F]{8})\b[^;]*$", re.M)


def snake(c):
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", c)
    s = re.sub(r"([a-z])([A-Z0-9])", r"\1_\2", s)
    s = re.sub(r"([0-9])([A-Za-z])", r"\1_\2", s)
    return s.lower()


def suggest():
    rows, _ = read_rows()
    have = {r["old"] for r in rows}
    names = {}
    for line in MANIFEST.read_text().splitlines():
        f = line.split("\t")
        if len(f) == 7 and f[1] == "class":
            names[f[3]] = f
    decl = {}
    for p in sorted(list((ROOT / "include/game").rglob("*.h")) + list((ROOT / "src/game").glob("*.cpp"))):
        for m in CLASS.finditer(p.read_text(errors="replace")):
            decl.setdefault(m[1], str(p.relative_to(ROOT)))
    units_ev = {}
    for line in (ROOT / "config/G4SE01/game_units.tsv").read_text().splitlines():
        f = line.split("\t")
        if len(f) >= 6:
            units_ev[f[0]] = f[5]
    used = set()
    for p in sorted((ROOT / "src/game").glob("tu_*.cpp")):
        u = p.stem
        if u in have:
            continue
        c = collections.Counter(m[1] for m in DEF.finditer(p.read_text(errors="replace")))
        cand = [(k, v) for k, v in c.items() if k in decl and not k.startswith(("cls_", "Unk_"))]
        placeholder = max([v for k, v in c.items() if k.startswith(("cls_", "Unk_"))], default=0)
        if not cand or max(v for _, v in cand) <= placeholder:
            continue  # the unit's main content has no named class
        own = set()
        for h in (ROOT / f"include/game/act/{u}.h", ROOT / f"include/game/{u}.h"):
            if h.exists():
                own |= set(CLASS.findall(h.read_text()))
        cand.sort(key=lambda kv: (-kv[1], kv[0] not in own, kv[0]))
        cls, n = cand[0]
        addr = u[3:]
        row = names.get(cls)
        conf = row[4] if row else "med"
        if conf == "high":
            conf = "med"  # the class's name is proven, not Nintendo's file name
        ev_cls = row[6] if row else ""
        vtable = int(cls[-8:], 16) >= 0x80490000  # named after a vtable (.data), not a ctor / function
        actor = bool(re.match(r"actor [A-Z0-9]{4} ", ev_cls)) or (vtable and not row and (
            decl[cls].startswith("include/game/act/act_") or units_ev.get(f"game/{u}.cpp", "").startswith("actor spawner")))
        new = f"{'act_' if actor else ''}{snake(cls.rsplit('_', 1)[0])}_{addr}"
        if new in used:
            continue
        used.add(new)
        others = ", ".join(f"{k} {v}" for k, v in sorted(cand[1:], key=lambda kv: -kv[1])[:3])
        ev = (f"main class {cls}: {n} of the unit's {sum(c.values())} method definitions"
              f"{' (others: ' + others + ')' if others else ''}; class declared in {decl[cls]}"
              f"{', names.tsv ' + row[4] if row else ', named before the manifest'}"
              f"{'; an actor unit (act_ prefix: ' + ('actors.tsv ID in the class row' if row else 'actor class declared in ' + decl[cls]) + ')' if actor else ''}"
              f"; .text starts at 0x{addr}")
        print("\t".join([addr, "unit", u, new, conf, "yes", ev]))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true")
    g.add_argument("--suggest", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    if args.suggest:
        return suggest()
    rows, problems = read_rows()
    if problems:
        print("\n".join(problems))
        return 2
    rows = [r for r in rows if r["apply"]]
    only = {x for x in args.only.split(",") if x}
    if only:
        rows = [r for r in rows if r["old"] in only or r["new"] in only]
    rc = run(rows, not args.revert, args.apply or args.revert)
    if rc == 0 and args.verify and (args.apply or args.revert):
        rc = verify()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
