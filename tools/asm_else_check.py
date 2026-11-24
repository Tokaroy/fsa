#!/usr/bin/env python3
"""Flag `#ifdef __MWERKS__` blocks that hold asm but have no `#else`.

A portable (non-MWCC) build of these sources compiles such a block to
nothing, silently: a TVec3 copy written as paired-single asm became a no-op
on the PC port and gave a black screen.  Every MWERKS-only block that contains
asm (``asm``/``__asm`` keywords, ``psq_*``/``ps_*`` instructions, ``frsqrte``)
must therefore have an ``#else`` branch with a portable C body, or
``#error "needs portable body"`` when none can be written yet.  See
docs/PORTABLE.md.

A block counts as MWERKS-only when its ``#if``/``#ifdef`` condition names
``__MWERKS__`` without negating it.  Asm anywhere in its first branch,
including inside nested conditionals, marks it.

Which files are checked: by default, the sources and headers the build
actually compiles, read from ``ninja -t deps`` for the ``.o`` targets (needs a
completed ``ninja``).  Files outside that set are listed with ``--skipped``.
If ninja has no dependency data, every source under include/, src/ and libs/
is checked.  ``--all`` checks every file regardless.

Usage:
    python3 tools/asm_else_check.py            # report, exit 1 on any flag
    python3 tools/asm_else_check.py --skipped  # also list unchecked hits
    python3 tools/asm_else_check.py --all      # ignore the build's dep set
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ("include", "src", "libs")
EXTS = (".h", ".hpp", ".c", ".cpp", ".inc")
DIRECTIVE = re.compile(r"\s*#\s*(ifdef|ifndef|if|elif|else|endif)\b(.*)")
ASM = re.compile(r"\b(asm|__asm|__asm__)\b|\bpsq_\w+|\bps_\w+|\bfrsqrte\b")
NEGATED = re.compile(r"!\s*(defined\s*\(?\s*)?__MWERKS__")


def mwerks_only(kind, cond):
    if kind == "ifndef" or "__MWERKS__" not in cond:
        return False
    return not NEGATED.search(cond)


def scan_file(path):
    """Return the 1-based line numbers of flagged blocks in `path`."""
    try:
        with open(path, errors="replace") as f:
            lines = f.read().split("\n")
    except OSError:
        return []
    hits = []
    # frame: [line, is_mwerks, seen_else, has_asm]
    stack = []
    in_comment = False
    for i, line in enumerate(lines):
        code = line
        if in_comment:
            end = code.find("*/")
            if end < 0:
                continue
            code = code[end + 2:]
            in_comment = False
        code = re.sub(r"/\*.*?\*/", " ", code)
        if "/*" in code:
            code = code[:code.index("/*")]
            in_comment = True
        code = code.split("//", 1)[0]
        m = DIRECTIVE.match(code)
        if m:
            kind, rest = m.groups()
            if kind in ("if", "ifdef", "ifndef"):
                stack.append([i + 1, mwerks_only(kind, rest), False, False])
            elif kind in ("else", "elif") and stack:
                stack[-1][2] = True
            elif kind == "endif" and stack:
                start, mw, seen_else, has_asm = stack.pop()
                if mw and has_asm and not seen_else:
                    hits.append(start)
            continue
        if stack and ASM.search(code):
            # Mark every enclosing MWERKS-only frame still in its first branch,
            # up to the first frame already past its #else.
            for fr in reversed(stack):
                if fr[2]:
                    break
                if fr[1]:
                    fr[3] = True
    return sorted(hits)


def all_sources():
    out = []
    for d in SCAN_DIRS:
        for root, _, files in os.walk(os.path.join(ROOT, d)):
            for f in files:
                if f.endswith(EXTS):
                    out.append(os.path.relpath(os.path.join(root, f), ROOT))
    return sorted(out)


def compiled_set():
    """Files the build compiles (sources + included headers), or None."""
    try:
        res = subprocess.run(["ninja", "-t", "deps"], cwd=ROOT, capture_output=True,
                             text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    files, take = set(), False
    for line in res.stdout.split("\n"):
        if not line.startswith(" "):
            take = line.split(":", 1)[0].endswith(".o")
            continue
        if take and line.strip():
            p = os.path.normpath(os.path.join(ROOT, line.strip()))
            files.add(os.path.relpath(p, ROOT))
    return files or None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="check every file")
    ap.add_argument("--skipped", action="store_true",
                    help="also list hits in files the build does not compile")
    args = ap.parse_args()

    compiled = None if args.all else compiled_set()
    flagged, skipped = [], []
    for rel in all_sources():
        for line in scan_file(os.path.join(ROOT, rel)):
            if compiled is None or rel in compiled:
                flagged.append(f"{rel}:{line}")
            else:
                skipped.append(f"{rel}:{line}")
    if compiled is None and not args.all:
        print("asm_else_check: no ninja deps; checked every file", file=sys.stderr)
    for h in flagged:
        print(f"{h}: #ifdef __MWERKS__ asm block has no #else portable body")
    if args.skipped:
        for h in skipped:
            print(f"{h}: (not compiled by configure.py; skipped)")
    print(f"asm_else_check: {len(flagged)} flagged, {len(skipped)} in uncompiled files")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
