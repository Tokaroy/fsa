#!/usr/bin/env python3
"""Scratch builds: compile a changed copy of one unit outside ninja and diff it with the original.

The mechanical search tools (tools/permute.py, tools/diag.py, tools/flagsweep.py) stand on this.
A scratch build never touches the worktree's source, objects or ninja state: the changed text is
written under build/scratch/<unit>/<tag>/ at the unit's own relative path (so __FILE__ and
same-directory includes behave as in the real build), compiled with the unit's exact command line
(from `ninja -t commands`, include paths made absolute) and diffed with objdiff-cli in two-file
mode under the report's relocation setting. Many scratch builds can run at once.

  python3 tools/scratch.py <unit> [--sym] [--flag "-O4,s" ...] [--drop "-inline auto,deferred" ...]
                                  [--src FILE] [--fn NAME]

prints every function below 100 % (or the one named) for the unit as it stands, or for FILE
compiled in its place; --sym adds `-sym on` (line numbers and DWARF, see tools/diag.py).

As a library:
    u = scratch.Unit("game/act_rat.cpp")
    d = u.build(text)                 # Diff, or raises CompileError
    d.fn["update__12Rat_8049C400Fv"].pct, .score, .cls, .rows
    scratch.pmap(lambda t: u.build(t), texts)   # in parallel

Score (lower is better, 0 = the function matches): 100 per instruction only one side has, 60 per
aligned pair with different opcodes, 20 per differing immediate or relocation, 5 per differing
register, 1 per differing stack offset. It falls smoothly where the match % is flat, which is what
a search needs (the weights are decomp-permuter's).
"""

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib

T = importlib.import_module("try")  # tools/try.py: find_unit, insn_list, classify, reloc_pairs

OBJDIFF = "build/tools/objdiff-cli"
SCRATCH = Path("build/scratch")
JOBS = int(os.environ.get("SCRATCH_JOBS", "0")) or max(4, min(16, (os.cpu_count() or 8) // 2))
INSERT, OPCODE, IMM, REG, STACK = 100, 60, 20, 5, 1
_STACK = re.compile(r"^-?(0x)?[0-9a-fA-F]+\(r1\)$")


class CompileError(Exception):
    pass


def _lines(msg, n=12):
    keep = [l for l in msg.splitlines() if l.strip() and not l.startswith(("User break", "build/tools/"))]
    return "\n".join(keep[-n:])


class Fn:
    """One target function against ours: pct (objdiff), score, cls (tools/try.py), rows.
    rows: [(kind, target insn or None, our insn or None, our line number or None, target offset or None)],
    an insn being (mnemonic, args, reloc target, index of the reloc arg) as tools/try.py's insn_list gives."""
    __slots__ = ("name", "demangled", "size", "pct", "score", "cls", "detail", "rows", "addr", "our_addr", "our_size")

    def __repr__(self):
        return f"<{self.name} {self.pct:.2f}% score {self.score} {self.cls}>"


def row_score(kind, t, o):
    if t is None or o is None:
        return INSERT
    if t[0] != o[0]:
        return OPCODE
    s = 0
    if len(t[1]) != len(o[1]):
        return IMM
    for k, (a, b) in enumerate(zip(t[1], o[1])):
        if a == b:
            continue
        if T.REG.match(a) and T.REG.match(b):
            s += REG
        elif a.startswith("@") and b.startswith("@"):
            s += 0 if kind is None else 2  # a branch target moved: counted where the rows moved
        elif "r1" in t[1] and "r1" in o[1] and a.lstrip("-").isdigit() and b.lstrip("-").isdigit():
            s += STACK  # a displacement off the stack pointer
        else:
            s += IMM
    if t[2] != o[2] and kind:
        s += IMM // 2
    return s


class Diff:
    """objdiff's verdict on one object: fn {mangled name: Fn}, sections {name: match %}, extra (our
    functions the target lacks)."""

    def __init__(self, data, want=None):
        left, right = data["left"], data["right"]
        self.fn, self.extra = {}, []
        self.sections = {s["name"]: float(s.get("match_percent", 0)) for s in left["sections"]
                         if s.get("kind") in ("SECTION_CODE", "SECTION_DATA", "SECTION_BSS")}
        self.symbols = {s["name"]: float(s.get("match_percent", 0)) for s in left["symbols"]
                        if s.get("kind") in ("SYMBOL_OBJECT",) and int(s.get("size", 0))}
        for s in left["symbols"]:
            if s.get("kind") != "SYMBOL_FUNCTION":
                continue
            f = Fn()
            f.name, f.demangled, f.size = s["name"], s.get("demangled_name", s["name"]), int(s.get("size", 0))
            f.addr = int(s.get("address", 0))
            k = s.get("target_symbol")
            r = right["symbols"][k] if k is not None else None
            f.rows, f.our_addr, f.our_size = [], None, None
            if r is None:
                f.pct, f.score, f.cls, f.detail = 0.0, INSERT * max(1, f.size // 4), "missing", "not in our object"
                self.fn[f.name] = f
                continue
            f.our_addr, f.our_size = int(r.get("address", 0)), int(r.get("size", 0))
            f.pct = float(s.get("match_percent") or 0)
            if f.pct == 100 and (want is None or f.name not in want):
                f.score, f.cls, f.detail = 0, "match", ""
                self.fn[f.name] = f
                continue
            t, o = T.insn_list(left, s), T.insn_list(right, r)
            ti, oi, score = iter(t), iter(o), 0
            for a, b in zip(s.get("instructions", []), r.get("instructions", [])):
                ia, ib = a.get("instruction"), b.get("instruction")
                kind = (a.get("diff_kind") or b.get("diff_kind") or "").replace("DIFF_", "").lower() or None
                ta = next(ti) if ia else None
                tb = next(oi) if ib else None
                line = ib.get("line_number") if ib else None
                off = int(ia["address"]) - f.addr if ia and "address" in ia else None
                f.rows.append((kind, ta, tb, line, off))
                if kind:
                    score += row_score(kind, ta, tb)
            if f.pct == 100:
                f.score, f.cls, f.detail = 0, "match", ""
            else:
                f.score = max(1, score)
                f.cls, f.detail = T.classify(t, o, T.reloc_pairs(s, r, left, right))
            self.fn[f.name] = f
        for x in right["symbols"]:
            if (x.get("kind") == "SYMBOL_FUNCTION" and x.get("target_symbol") is None and int(x.get("size", 0))
                    and not (x.get("flags") or {}).get("weak")):
                self.extra.append(x["name"])

    def find(self, want):
        """The one function `want` names (mangled, demangled without arguments, or a unique part)."""
        fs = list(self.fn.values())
        hits = [f for f in fs if f.name == want] or [f for f in fs if f.demangled.split("(")[0] == want] or \
               [f for f in fs if want in f.name or want in f.demangled]
        if len(hits) != 1:
            raise KeyError(f"{want!r} matches {len(hits)} functions: " + ", ".join(f.name for f in (hits or fs)[:10]))
        return hits[0]

    def worse_than(self, base, skip=(), eps=0.005):
        """What this build does worse than `base` outside the functions in `skip`: a list of strings."""
        out = []
        for n, f in base.fn.items():
            if n in skip:
                continue
            g = self.fn.get(n)
            if g is None or g.pct < f.pct - eps:
                out.append(f"{n}: {f.pct:.2f} -> {g.pct if g else 0:.2f}")
        for n, p in base.sections.items():
            if not n.startswith(".text") and self.sections.get(n, 0) < p - eps:
                out.append(f"section {n}: {p:.2f} -> {self.sections.get(n, 0):.2f}")
        for n in self.extra:
            if n not in base.extra:
                out.append(f"new function not in the target: {n}")
        return out


class Unit:
    def __init__(self, arg, root="."):
        self.root = Path(root).resolve()
        units = json.loads((self.root / "objdiff.json").read_text())["units"]
        u = T.find_unit(units, arg)
        if u is None or "base_path" not in u:
            raise KeyError(f"no built unit matches {arg!r}")
        self.name, self.target, self.base = u["name"], u["target_path"], u["base_path"]
        self.src = (u.get("metadata") or {}).get("source_path")
        self.slug = T.slug_of(self.name)
        self._cmd, self._lock, self._n = None, threading.Lock(), 0

    # -- the unit's compile command, as ninja would run it
    def command(self):
        if self._cmd is None:
            out = subprocess.run(["ninja", "-t", "commands", self.base], cwd=self.root, capture_output=True, text=True)
            line = next((l for l in reversed(out.stdout.splitlines()) if f"-c {self.src}" in l), None)
            if line is None:
                raise CompileError(f"no compile command for {self.base}:\n{out.stderr[-300:]}")
            argv = shlex.split(line.split(" && ")[0])
            argv = [a for a in argv if a != "-MMD"]
            self._cmd = argv
        return list(self._cmd)

    def source(self):
        return (self.root / self.src).read_text(errors="surrogateescape")

    def _argv(self, src, outdir, sym, flags, drop):
        argv, out, k = self.command(), [], 0
        srcdir = str((self.root / self.src).parent)
        while k < len(argv):
            a = argv[k]
            if a in ("-i", "-I") and k + 1 < len(argv):
                out += [a, str((self.root / argv[k + 1]).resolve())]
                k += 2
            elif a == "-c":
                out += ["-i", srcdir, "-c", str(src)]
                k += 2
            elif a == "-o":
                out += ["-o", str(outdir) + "/"]
                k += 2
            elif k < 3:
                out.append(str(self.root / a))  # wibo, sjiswrap, the compiler
                k += 1
            else:
                out.append(a)
                k += 1
        for d in drop:
            dv = shlex.split(d)
            for i in range(len(out) - len(dv) + 1):
                if out[i:i + len(dv)] == dv:
                    del out[i:i + len(dv)]
                    break
        c = out.index("-c")
        extra = [x for f in flags for x in shlex.split(f)] + (["-sym", "on"] if sym else [])
        return out[:c] + extra + out[c:]

    def compile(self, text=None, tag=None, sym=False, flags=(), drop=()):
        """Compile `text` (default: the source as it stands) in the unit's place; the object's path."""
        if text is None:
            text = self.source()
        if tag is None:
            key = hashlib.sha1(("\0".join([text, str(sym), *flags, "|", *drop])).encode("utf-8", "surrogateescape"))
            tag = key.hexdigest()[:16]
        d = self.root / SCRATCH / self.slug / tag
        src = d / self.src
        obj = d / "out" / (Path(self.src).stem + ".o")
        if obj.exists():
            return obj
        src.parent.mkdir(parents=True, exist_ok=True)
        (d / "out").mkdir(exist_ok=True)
        src.write_text(text, errors="surrogateescape")
        argv = self._argv(src.relative_to(d), d / "out", sym, flags, drop)
        try:
            p = subprocess.run(argv, cwd=d, capture_output=True, text=True, timeout=300, errors="replace")
        except subprocess.TimeoutExpired:
            raise CompileError("compiler timed out")
        if p.returncode or not obj.exists():
            shutil.rmtree(d, ignore_errors=True)
            raise CompileError(_lines(p.stdout + p.stderr) or f"compiler exit {p.returncode}")
        return obj

    def diff(self, obj, want=None):
        p = subprocess.run([str(self.root / OBJDIFF), "diff", "-1", str(self.root / self.target), "-2", str(obj),
                            "-o", "-", "-c", T.CONFIG], cwd=self.root, capture_output=True, text=True)
        if p.returncode:
            raise CompileError("objdiff-cli: " + p.stderr.strip()[-300:])
        return Diff(json.loads(p.stdout), want)

    def build(self, text=None, sym=False, flags=(), drop=(), want=None, keep=False):
        """Compile and diff; the scratch directory is removed again unless keep=True."""
        obj = self.compile(text, sym=sym, flags=flags, drop=drop)
        try:
            d = self.diff(obj, want)
            d.obj = obj if keep else None
            return d
        finally:
            if not keep:
                shutil.rmtree(obj.parent.parent, ignore_errors=True)

    def clean(self):
        shutil.rmtree(self.root / SCRATCH / self.slug, ignore_errors=True)


FNSCORE = Path("build/tools/fnscore")


def fnscore_bin(root):
    """The native scorer and candidate farm (tools/fnscore.cpp), built on first use."""
    exe, src = Path(root) / FNSCORE, Path(root) / "tools/fnscore.cpp"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        tmp = exe.with_suffix(f".{os.getpid()}.tmp")
        p = subprocess.run(["g++", "-O2", "-std=c++17", "-pthread", "-o", str(tmp), str(src)], capture_output=True, text=True)
        if p.returncode:
            raise CompileError("building tools/fnscore.cpp failed:\n" + p.stderr[-600:])
        tmp.replace(exe)
    return exe


def farm(unit, texts, names=None, sym=False, flags=(), drop=(), jobs=None, keep=False, hashes=False):
    """Compile every text in the unit's place and score it natively (tools/fnscore.cpp farm): the fast
    path of a search. Returns (names, results) with one result per text, in order: a list of scores
    (one per name; -1 = that function is missing; with hashes=True (score, hash of our code)) or a
    CompileError. names=None scores every function of the target. A score is fnscore's, not objdiff's: confirm what matters with Unit.build()."""
    exe = fnscore_bin(unit.root)
    d = unit.root / SCRATCH / unit.slug / f"farm-{os.getpid()}-{threading.get_ident()}"
    d.mkdir(parents=True, exist_ok=True)
    cmd = ["timeout", "300"] + unit._argv("{SRC}", "{OUT}", sym, flags, drop)
    cmd = ["{OUT}" if a == "{OUT}/" else a for a in cmd]
    argv = [str(exe), "farm", "--target", str(unit.root / unit.target), "--dir", str(d), "--src", unit.src,
            "--jobs", str(jobs or JOBS)] + (["--keep"] if keep else []) + (["--hash"] if hashes else [])
    argv += ["--all"] if names is None else [x for n in names for x in ("--sym", n)]
    blob = bytearray()
    for k, t in enumerate(texts):
        b = t if isinstance(t, bytes) else t.encode("utf-8", "surrogateescape")
        blob += b"C %d %d\n" % (k, len(b)) + b
    p = subprocess.run(argv + ["--"] + cmd, input=bytes(blob), capture_output=True)
    out_names, res = [], [CompileError("no result")] * len(texts)
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        kind, _, rest = line.partition(" ")
        if kind == "N":
            out_names = rest.split(" ") if rest else []
        elif kind == "R":
            parts = rest.split(" ")
            res[int(parts[0])] = [tuple(int(y) for y in x.split("/")) if hashes else int(x) for x in parts[1:]]
        elif kind == "E":
            k, _, msg = rest.partition(" ")
            res[int(k)] = CompileError(msg)
    if not keep:
        shutil.rmtree(d, ignore_errors=True)
    if p.returncode:
        raise CompileError("fnscore farm: " + p.stderr.decode("utf-8", "replace")[-300:])
    return out_names, res


def pmap(fn, items, jobs=None):
    """fn over items in parallel; an exception becomes the item's result."""
    def one(x):
        try:
            return fn(x)
        except Exception as e:  # noqa: BLE001  (a failed candidate is a result, not a crash)
            return e
    with ThreadPoolExecutor(max_workers=jobs or JOBS) as ex:
        return list(ex.map(one, items))


def main():
    import argparse
    import grind_broker
    grind_broker.maybe_delegate("scratch", sys.argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("unit")
    ap.add_argument("--src", help="compile this file's text in the unit's place")
    ap.add_argument("--fn")
    ap.add_argument("--sym", action="store_true")
    ap.add_argument("--flag", action="append", default=[])
    ap.add_argument("--drop", action="append", default=[])
    a = ap.parse_args()
    u = Unit(a.unit)
    try:
        d = u.build(Path(a.src).read_text(errors="surrogateescape") if a.src else None, sym=a.sym, flags=a.flag, drop=a.drop)
    except CompileError as e:
        sys.exit(f"compile failed:\n{e}")
    fs = [d.find(a.fn)] if a.fn else [f for f in d.fn.values() if f.pct < 100]
    print(f"{u.name.split('/', 1)[-1]}: {sum(1 for f in d.fn.values() if f.pct == 100)}/{len(d.fn)} functions match")
    for f in sorted(fs, key=lambda f: f.addr):
        print(f"  {f.name[:56]:56} {f.pct:7.2f}%  score {f.score:5}  {f.cls}")


if __name__ == "__main__":
    main()
