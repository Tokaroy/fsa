"""Field rows of the names manifest (kind `field`), for tools/rename.py.

A field row names one data member of one class: address = the declaring
class's vtable, old = its `field_0x<off>` placeholder, new = the name (below
high it keeps `_0x<off>` spelled as in the old name). The same placeholder
is a different member of hundreds of other classes, so where a use refers to
the row's class can only be decided from the expression's type. The compiler
decides it:

 1. Textual pass: the declaration in the class body, and every bare or
    `this->` use inside a class body or `Cls::fn(...)` body (constructor
    init lists included) of the class or a descendant, are renamed.
 2. Compiler pass: every game TU is compiled (the build's own command, with
    -maxerrors raised and the object thrown away). Before the rename the tree
    compiled, and only this class's member changed name, so an error whose
    token is the old name is a use of this class's member (renamed now) and
    an error on the new name is a use of another class's member (put back).
    Repeated until the tree compiles; any other error stops the run and
    restores every file.
 3. Comments: an old name in a comment is renamed when it sits in such a
    class context, or when every use in its file's code was renamed.

Rows that share an old name go in separate passes (an error's token then
names its row). --revert is the same with old and new swapped, so it is
scoped and exact too. Docs outside source files are left (counted).
"""

import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FIELD = re.compile(r"field_(0x[0-9A-Fa-f]+)\Z")
CODE_SUFFIX = (".h", ".hpp", ".cpp", ".cp", ".c", ".inc")
CLASS_RE = re.compile(r"\b(?:class|struct)\s+(\w+)\s*(?::\s*(?:public\s+|private\s+|protected\s+)?([\w:]+)[^{;]*)?\{")
# Cls::fn(...) [const] [: init-list] {   (the init list may hold parentheses)
DEF_RE = re.compile(r"\b(\w+)::~?\w+\s*\([^;{}]*\)\s*(?:const\s*)?(?::[^;{}]*)?\{")
COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def ident(name):
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")


def brace_end(t, i):
    d = 1
    while d and i < len(t):
        c = t[i]
        d += (c == "{") - (c == "}")
        i += 1
    return i


def spans(t):
    """[(start, end, class)]: class bodies and member-function bodies (from the
    `Cls::fn(` so a constructor's init list counts), outer first."""
    out = []
    for m in CLASS_RE.finditer(t):
        out.append((m.start(), brace_end(t, m.end()), m[1]))
    for m in DEF_RE.finditer(t):
        out.append((m.start(), brace_end(t, m.end()), m[1]))
    out.sort(key=lambda s: (s[0], -s[1]))
    return out


def class_of(sp, pos):
    c = None
    for s, e, k in sp:
        if s <= pos < e:
            c = k
    return c


def comment_ranges(t):
    return [(m.start(), m.end()) for m in COMMENT.finditer(t)]


def in_ranges(rs, p):
    return any(a <= p < b for a, b in rs)


class Tree:
    """Text of the code files, the class hierarchy, compile commands."""

    def __init__(self, root, texts):
        self.root, self.texts = root, texts
        self.base = {}
        for f, t in texts.items():
            if f.endswith(CODE_SUFFIX):
                for m in CLASS_RE.finditer(t):
                    if m[2]:
                        self.base[m[1]] = m[2].split("::")[-1]
        self._cmds = None

    def descends(self, c, root):
        seen = set()
        while c and c not in seen:
            if c == root:
                return True
            seen.add(c)
            c = self.base.get(c)
        return False

    def class_body(self, cls):
        for f, t in self.texts.items():
            if not f.endswith(CODE_SUFFIX) or cls not in t:
                continue
            for m in CLASS_RE.finditer(t):
                if m[1] == cls:
                    return f, m.end(), brace_end(t, m.end())
        return None

    def declared(self, cls, name):
        """Is `name` a data member declared in cls's body (not in an inline body)?"""
        b = self.class_body(cls)
        if not b:
            return False
        f, s, e = b
        body = COMMENT.sub("", self.texts[f][s:e])
        while True:
            body2 = re.sub(r"\{[^{}]*\}", "", body)
            if body2 == body:
                break
            body = body2
        return re.search(r"(?<![\w.>])" + re.escape(name) + r"\s*(\[[^\]]*\]\s*)*(:\s*\d+\s*)?[;,]", body) is not None

    # ------------------------------------------------------------ compiler
    def commands(self):
        """{source file: compile command} for the game TUs (ninja's own)."""
        if self._cmds is None:
            out = subprocess.run(["ninja", "-t", "commands"], cwd=self.root, capture_output=True, text=True, check=True)
            self._cmds = {}
            for l in out.stdout.splitlines():
                if "mwcceppc" not in l:
                    continue
                m = re.search(r" -c (src/game/\S+) ", l)
                if m:
                    self._cmds[m[1]] = l.split(" && ")[0]
        return self._cmds

    def compile(self, files):
        """Errors of compiling `files` (sources): [(file, line, col, message)]."""
        tmp = tempfile.mkdtemp(prefix="rename_fields_")
        cmds = self.commands()

        def one(src):
            c = cmds[src]
            c = re.sub(r"-maxerrors \d+", "-maxerrors 400", c)
            c = c.replace(" -MMD", "")
            c = re.sub(r" -o \S+", f" -o {tmp}/{Path(src).stem}.o", c)
            r = subprocess.run(c, shell=True, cwd=self.root, capture_output=True, text=True, errors="replace")
            return src, r.returncode, r.stdout + r.stderr

        errs = []
        with ThreadPoolExecutor(32) as ex:
            for src, rc, out in ex.map(one, sorted(files)):
                e = parse_errors(out, src)
                if rc and not e:
                    raise RuntimeError(f"{src}: compile failed without a parsed error: {out[-300:]}")
                if e:
                    errs.append(e)
        subprocess.run(["rm", "-rf", tmp])
        return errs

    def users(self, changed):
        """Game TUs that include any of the changed files (ninja's deps)."""
        cmds = self.commands()
        out = subprocess.run(["ninja", "-t", "deps"], cwd=self.root, capture_output=True, text=True).stdout
        res, cur, root = set(), None, str(self.root) + "/"
        for l in out.splitlines():
            if not l.startswith(" "):
                cur = None
                continue
            d = l.strip().replace(root, "")
            if cur is None:
                cur = d if d in cmds else ""
            if cur and d in changed:
                res.add(cur)
        res |= {f for f in changed if f in cmds}
        return res


def parse_errors(out, src):
    """MWCC's error blocks -> [(file, line, col in the stripped line, message)]."""
    res, f, cur = [], src, None
    lines = out.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"#\s+(?:File|In): (.+)", l)
        if m:
            f = m[1].strip().replace("\\", "/")
            continue
        m = re.match(r"(#\s*(\d+): )(.*)", l)
        if m:
            cur = (int(m[2]), len(m[1]), m[3])
            continue
        m = re.match(r"#\s+Error:( *)(\^+)", l)
        if m and cur:
            col = l.index("^") - cur[1]
            msg = lines[i + 1][1:].strip() if i + 1 < len(lines) else ""
            res.append((f, cur[0], col, msg, cur[2]))
    return res


def macro_hit(t, line_text, msg, names):
    """[(line, col, name)] of `name` in the bodies of the #define macros the
    line uses, for an error whose message names `name`."""
    out = []
    for name in names:
        if f"'{name}'" not in msg:
            continue
        for m in re.finditer(r"^#\s*define\s+(\w+)(?:\([^)]*\))?((?:[^\n]*\\\n)*[^\n]*)", t, re.M):
            if not re.search(r"(?<![A-Za-z0-9_])" + m[1] + r"\s*\(", line_text) and not ident(m[1]).search(line_text):
                continue
            for k in ident(name).finditer(t, m.start(2), m.end(2)):
                ln = t.count("\n", 0, k.start()) + 1
                col = k.start() - (t.rfind("\n", 0, k.start()) + 1)
                out.append((ln, col, name))
    return out


def rename_at(t, pos, a, b):
    return t[:pos] + b + t[pos + len(a):]


def textual(tree, f, t, src, dst, root):
    """Step 1 for one file: declaration and bare / this-> uses in class context."""
    if src not in t or not f.endswith(CODE_SUFFIX):
        return t, 0
    sp = spans(t)
    out, last, n = [], 0, 0
    for m in ident(src).finditer(t):
        c = class_of(sp, m.start())
        if not c or not tree.descends(c, root):
            continue
        pre = t[max(0, m.start() - 8):m.start()]
        if re.search(r"(->|\.|::)\s*\Z", pre) and not re.search(r"\bthis\s*->\s*\Z", t[max(0, m.start() - 12):m.start()]):
            continue
        out += [t[last:m.start()], dst]
        last, n = m.end(), n + 1
    out.append(t[last:])
    return "".join(out), n


def run_pass(tree, rows, forward, log=print):
    """rows: [(row, root class)] with distinct source names. Returns
    ({file: renamed count}, left count) or raises RuntimeError (files restored)."""
    texts = tree.texts
    orig = dict(texts)
    pairs = {}
    for r, root in rows:
        src, dst = (r["old"], r["new"]) if forward else (r["new"], r["old"])
        pairs[src] = (dst, root)
    back = {dst: src for src, (dst, _) in pairs.items()}
    counts, changed = {}, set()
    for f in list(texts):
        t = texts[f]
        for src, (dst, root) in pairs.items():
            t, k = textual(tree, f, t, src, dst, root)
            if k:
                counts[f] = counts.get(f, 0) + k
        if t != texts[f]:
            texts[f] = t
            changed.add(f)
    write(tree, changed)
    todo = set(tree.commands())
    it = 0
    try:
        while todo:
            it += 1
            errs = tree.compile(todo)
            log(f"  field pass: compile {len(todo)} TU(s), {sum(map(len, errs))} error(s)")
            if not errs:
                break
            fixed, edits = set(), {}
            for tu_errs in errs:
                # The first error of a TU is real; later ones may be a cascade,
                # so take errors only while each names one of our tokens.
                for k, (f, line, col, msg, disp) in enumerate(tu_errs):
                    if f not in texts:
                        raise RuntimeError(f"error in an unknown file {f}:{line}: {msg}")
                    s = texts[f].split("\n")[line - 1] if 0 < line <= texts[f].count("\n") + 1 else ""
                    # MWCC shows a window of a long line: find where it starts.
                    d = disp.rstrip()
                    off = s.find(d) if d else -1
                    while off < 0 and len(d) > 8:
                        d = d[:-1]
                        off = s.find(d)
                    c = (off if off >= 0 else len(s) - len(s.lstrip())) + col
                    hit = None
                    for name in list(pairs) + list(back):
                        for m in ident(name).finditer(s):
                            if m.start() <= c < m.end():
                                hit = (m.start(), name)
                    if hit and not (k == 0 or f"'{hit[1]}'" in msg):
                        hit = None
                    if hit is None:  # a macro used on this line whose body has the name
                        mh = macro_hit(texts[f], s, msg, list(pairs) + list(back))
                        if mh:
                            for mline, mp, name in mh:
                                edits.setdefault(f, {}).setdefault(mline, set()).add((mp, name))
                            continue
                    if hit is None:
                        if k == 0:
                            raise RuntimeError(f"unrelated error {f}:{line}: {s.strip()} / {msg}")
                        break
                    edits.setdefault(f, {}).setdefault(line, set()).add(hit)
            for f, by_line in edits.items():
                ls = texts[f].split("\n")
                for line, hits in by_line.items():
                    s = ls[line - 1]
                    for p, name in sorted(hits, reverse=True):
                        a, b = (name, pairs[name][0]) if name in pairs else (name, back[name])
                        s = s[:p] + b + s[p + len(a):]
                        counts[f] = counts.get(f, 0) + (1 if name in pairs else -1)
                    ls[line - 1] = s
                texts[f] = "\n".join(ls)
                fixed.add(f)
            if not fixed:
                raise RuntimeError("compiler errors that change nothing")
            write(tree, fixed)
            changed |= fixed
            todo = tree.users(fixed)
            if it > 400:
                raise RuntimeError("no convergence after 400 compiles")
    except Exception:
        for f in changed:
            texts[f] = orig[f]
        write(tree, changed)
        raise
    # Step 3: comments.
    left = 0
    for f in list(texts):
        t = texts[f]
        if not f.endswith(CODE_SUFFIX):
            left += sum(len(ident(s).findall(t)) for s in pairs if s in t)
            continue
        for src, (dst, root) in pairs.items():
            if src not in t:
                continue
            cr = comment_ranges(t)
            sp = spans(t)
            code_left = [m for m in ident(src).finditer(t) if not in_ranges(cr, m.start())]
            whole = counts.get(f, 0) > 0 and not code_left
            out, last = [], 0
            for m in ident(src).finditer(t):
                if not in_ranges(cr, m.start()):
                    continue
                c = class_of(sp, m.start())
                if whole or (c and tree.descends(c, root)):
                    out += [t[last:m.start()], dst]
                    last = m.end()
            out.append(t[last:])
            t2 = "".join(out)
            if t2 != t:
                t = t2
                changed.add(f)
        texts[f] = t
    write(tree, changed)
    return counts, left


def write(tree, files):
    for f in files:
        (tree.root / f).write_text(tree.texts[f], encoding="utf-8")


def state(tree, r, root):
    """True: the class declares the new name; False: the old one; None: neither."""
    if tree.declared(root, r["new"]):
        return True
    if tree.declared(root, r["old"]):
        return False
    return None


def passes(rows):
    """Split rows into passes with distinct source names (old and new)."""
    out = []
    for r in rows:
        for p in out:
            if all(r["old"] != q["old"] and r["new"] != q["new"] for q in p):
                p.append(r)
                break
        else:
            out.append([r])
    return out
