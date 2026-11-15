#!/usr/bin/env python3
"""Shared instruction blocks in the original game code: the footprints of inlined helpers.

  python3 tools/clones.py [--min 10] [--units part,...] [--top 15] [--json FILE] [-v] [--no-status]
  python3 tools/clones.py --helpers [--top 15]              # only the "inlined copy of <function>" table
  python3 tools/clones.py --fn <unit> <function> [-v]       # one function: its shared stretches and the rest

MWCC (-inline auto,deferred) inlines header inlines, same-file helpers and macros. Such a helper
leaves the same instruction block, up to register numbers, in every function that used it. Finding
those blocks breaks a big function into shared pieces: write the helper once and every function
that contains the block gets closer. (Player_804A6F38::fn_80248970's 45-instruction loop sits
inlined in about 50 functions of game/tu_8023FBF0, and how that one helper was written decided
whether its callers match.)

Method. Every function of build/G4SE01/asm/game/*.s is read into one instruction stream.
Instructions compare by mnemonic and operands with
  * registers renamed consistently and one-to-one (Baker's parameterised matching: a register
    operand is encoded as the distance to the previous use of the same register inside the
    block, 0 for its first use; r1, r2, r13, crN and qrN stay literal);
  * immediates, field displacements and relocation targets kept as they are (an anonymous
    .sdata2 constant, lbl_XXXXXXXX@sda21, by its value instead of its address-named label, so
    the same 1.0f in two units compares equal);
  * stack displacements off r1 and branch targets wildcards; a backward branch inside the block
    must go to the same relative place, forward branches are checked when the block is reported
    (occurrences whose internal forward branches disagree are split apart).
Prologue and epilogue instructions (frame, saved registers, mflr/mtlr, blr, the moves of
arguments into saved registers at the top and of the result into r3/f1 at the bottom) never
belong to a block. All windows of --min instructions are hashed; windows that occur twice seed a
trie that grows every group one instruction at a time and splits it where occurrences diverge.
A reported block is maximal (it cannot grow left or right in all its occurrences), at least
--min long, not made only of moves and constant loads, and contains one distinctive element: a
call, a relocation, a non-zero field displacement or an immediate outside -16..16. Blocks are
ranked by occurrences x length.

Known helpers: for every original function of up to 60 instructions, its body (without
prologue, epilogue and return) is looked for inside other functions; a function where blocks
shared with the helper cover >= 75 % of the body holds an "inlined copy of <helper>".

The index (build/clones/, keyed by the .s files' mtimes and the options) takes about a minute
the first time; --fn then answers in seconds. --fn compiles the unit once with `-sym on`
(tools/scratch.py) to show our source lines for each shared stretch and whether our rows there
match. The game-wide report counts, for the top clusters, how many occurrences match in our
current objects (build/G4SE01/src/*.o as ninja last built them; --no-status skips it).

Limits: an inlined copy that MWCC scheduled differently (instructions interleaved with the
caller's code, or reordered) breaks into shorter blocks or is missed; a helper specialised by a
constant argument (folded branches, a different immediate) only matches in the parts the
constant did not touch; short helpers (< --min instructions) are not seen at all.
"""

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
import time
from array import array
from collections import defaultdict
import multiprocessing

Pool = multiprocessing.get_context("fork").Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ASM = Path("build/G4SE01/asm")
CACHE = Path("build/clones")
VERSION = "1"
SMALL = 60          # a "small" function, candidate helper (instructions in all)
COVER = 0.75        # share of a helper's body a copy must cover

LINE = re.compile(r"^/\* ([0-9A-F]{8}) [0-9A-F]{8}  (?:[0-9A-F]{2} ){4}\*/\t(\S+)\s*(.*)$")
REGX = re.compile(r"^(r|f)(\d+)$")
MEM = re.compile(r"^(.*)\((r\d+)\)$")
HEXNUM = re.compile(r"^-?(0x[0-9a-fA-F]+|\d+)$")
SAVE_BL = re.compile(r"^_(save|rest)(gpr|fpr)")
MOVES = {"li", "lis", "mr", "fmr", "ori", "nop", "oris", "crclr", "crset", "ps_mr"}
OUT, FWD = 1 << 40, (1 << 40) + 1   # branch codes: backward out of the block / forward (wildcard)


# ---------------------------------------------------------------- reading the asm

def split_args(s):
    out, cur, q = [], "", False
    for ch in s:
        if ch == '"':
            q = not q
        if ch == "," and not q:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def sdata2_values(text):
    """{name: '=float 1.0'} of the anonymous .sdata2 constants of one .s file."""
    out, sec, name = {}, None, None
    for ln in text.splitlines():
        if ln.startswith(".section"):
            sec = ln.split()[1].rstrip(",")
        elif sec == ".sdata2" and ln.startswith(".obj "):
            name = ln[5:].split(",")[0].strip().strip('"')
        elif name and ln.startswith("\t.") and not ln.startswith("\t.hidden"):
            d = ln.split(None, 1)
            if (name.startswith("lbl_") or name.startswith("@")) and d[0] in (".float", ".double", ".4byte") and len(d) == 2:
                out[name] = f"={d[0][1:]} {d[1].strip()}"
            name = None
        elif ln.startswith(".endobj"):
            name = None
    return out


def parse_file(path):
    """[(name, demangled, addr, [(addr, mnemonic, args)], {label addr: index})] of one .s file."""
    fns, cur, dem = [], None, None
    for ln in path.read_text(errors="replace").splitlines():
        if ln.startswith(".fn "):
            cur = (ln[4:].split(",")[0].strip().strip('"'), dem, None, [], {})
        elif ln.startswith(".endfn"):
            if cur and cur[3]:
                fns.append((cur[0], cur[1], cur[3][0][0], cur[3], cur[4]))
            cur = None
        elif cur is None:
            dem = ln[2:].strip() if ln.startswith("# ") else (dem if not ln.strip() else None)
        elif ln.startswith(".L_") and ln.endswith(":"):
            cur[4][int(ln[3:-1], 16)] = len(cur[3])
        else:
            m = LINE.match(ln)
            if m:
                cur[3].append((int(m.group(1), 16), m.group(2), split_args(m.group(3))))
    return fns


def is_barrier_pro(mn, a):
    if mn == "stwu" and a and a[0] == "r1":
        return True
    if mn == "mflr" or (mn == "addi" and len(a) == 3 and a[0] == "r11" and a[1] == "r1"):
        return True
    if mn == "bl" and a and SAVE_BL.match(a[0]):
        return True
    if len(a) >= 2 and a[1].endswith("(r1)"):
        r = REGX.match(a[0])
        if mn == "stw" and a[0] == "r0":
            return True
        if r and int(r.group(2)) >= 14 and mn in ("stw", "stmw", "stfd", "psq_st"):
            return True
    if mn in ("mr", "fmr") and len(a) == 2:
        d, s = REGX.match(a[0]), REGX.match(a[1])
        if d and s and int(d.group(2)) >= 14 and (3 <= int(s.group(2)) <= 10 if s.group(1) == "r" else 1 <= int(s.group(2)) <= 8):
            return True
    return False


def is_barrier_epi(mn, a):
    if mn in ("blr", "mtlr"):
        return True
    if mn == "addi" and len(a) == 3 and a[1] == "r1" and a[0] in ("r1", "r11"):
        return True
    if mn == "bl" and a and SAVE_BL.match(a[0]):
        return True
    if len(a) >= 2 and a[1].endswith("(r1)"):
        r = REGX.match(a[0])
        if mn == "lwz" and a[0] == "r0":
            return True
        if r and int(r.group(2)) >= 14 and mn in ("lwz", "lmw", "lfd", "psq_l"):
            return True
    if (mn == "mr" and a and a[0] == "r3") or (mn == "fmr" and a and a[0] == "f1"):
        return True
    return False


def barriers(insns):
    n = len(insns)
    bar = [False] * n
    for i, (_, mn, a) in enumerate(insns):    # prologue: up to the first branch or call
        if mn.startswith("b") and not (mn == "bl" and a and SAVE_BL.match(a[0])):
            break
        if is_barrier_pro(mn, a):
            bar[i] = True
    for i, (_, mn, a) in enumerate(insns):    # epilogue: backwards from every blr
        if mn != "blr":
            continue
        j = i
        while j >= 0 and is_barrier_epi(insns[j][1], insns[j][2]):
            bar[j] = True
            j -= 1
    return bar


def norm_insn(mn, args, labels, consts):
    """(shape string, [register ids], branch target index or -1, distinctive)"""
    shape, regs, tgt, dist = [mn], [], -1, False
    branch = mn.startswith("b") and mn not in ("bl",)
    for k, a in enumerate(args):
        r = REGX.match(a)
        if r:
            n = int(r.group(2))
            if r.group(1) == "r" and n in (1, 2, 13):
                shape.append(a)
            else:
                regs.append(n if r.group(1) == "r" else 32 + n)
                shape.append("R" if r.group(1) == "r" else "F")
            continue
        m = MEM.match(a)
        if m:
            disp, base = m.group(1), m.group(2)
            if base == "r1":
                shape.append("*(r1)")
                continue
            if "@" in disp:
                sym = disp.rsplit("@", 1)[0].strip('"')
                disp = consts.get(sym, sym) + "@" + disp.rsplit("@", 1)[1]
                dist = True
            elif HEXNUM.match(disp) and int(disp, 0) != 0:
                dist = True
            if base in ("r2", "r13", "r0") and "@" in m.group(1):
                shape.append(f"{disp}({base})")
            else:
                regs.append(int(base[1:]))
                shape.append(f"{disp}(R)")
            continue
        if a.startswith(".L_") and branch:
            tgt = labels.get(int(a[3:], 16), -2)
            shape.append("L")
            continue
        if "@" in a:
            sym, _, rel = a.rpartition("@")
            sym = sym.strip('"')
            shape.append(consts.get(sym, sym) + "@" + rel)
            dist = True
            continue
        if HEXNUM.match(a):
            v = int(a, 0)
            if abs(v) > 16 and not (mn.startswith("rlw") or mn.startswith("clr") or mn.startswith("ext") or mn.startswith("psq")):
                dist = True
            shape.append(a)
            continue
        if mn in ("bl", "b") or branch:  # a call or tail call by name
            dist = True
        shape.append(a)
    return " ".join(shape), regs, tgt, dist


def load_unit(path):
    """Everything about one .s file the index needs, as plain data (runs in a worker)."""
    text = path.read_text(errors="replace")
    return str(path), sdata2_values(text), parse_file(path)


# ---------------------------------------------------------------- the index

class Index:
    """One stream of all game instructions (functions separated by a barrier).
    shp[i] shape id (-1 barrier), roff[i]/rlen[i] its register operands in regs/prev,
    br[i] local branch target (global index) or -1, flags[i] 1 = distinctive, 2 = move/constant."""

    def __init__(self):
        self.shapes, self.shape_id = [], {}
        self.shp, self.roff, self.br, self.flags = array("i"), array("i"), array("i"), array("b")
        self.regs, self.prev = array("b"), array("i")
        self.fn_of = array("i")
        self.fns = []          # (unit, name, demangled, addr, start, n)
        self.text = []         # raw instruction text per index (for listings)
        self.small_body = {}   # fn id -> body length (non-barrier instructions), small functions only

    def add_fn(self, unit, name, dem, addr, insns, labels, consts):
        fid, start = len(self.fns), len(self.shp)
        bar = barriers(insns)
        last = {}
        for i, (a, mn, args) in enumerate(insns):
            self.roff.append(len(self.regs))
            shape, regs, tgt, dist = norm_insn(mn, args, labels, consts)
            if bar[i]:
                sid = -1
            else:
                sid = self.shape_id.get(shape)
                if sid is None:
                    sid = self.shape_id[shape] = len(self.shapes)
                    self.shapes.append(shape)
            self.shp.append(sid)
            for r in regs:
                g = len(self.regs)
                self.regs.append(r)
                self.prev.append(last.get(r, -1))
                last[r] = g
            self.br.append(start + tgt if tgt >= 0 else -1)
            self.flags.append((1 if dist else 0) | (2 if mn in MOVES or (mn in ("lfs", "lfd") and "@sda21" in shape) else 0))
            self.fn_of.append(fid)
            self.text.append(f"{mn} {', '.join(args)}".strip())
        # a barrier after the function
        self.roff.append(len(self.regs))
        self.shp.append(-1)
        self.br.append(-1)
        self.flags.append(0)
        self.fn_of.append(fid)
        self.text.append("")
        self.fns.append((unit, name, dem, addr, start, len(insns)))
        if len(insns) <= SMALL:
            self.small_body[fid] = sum(1 for b in bar if not b)


# globals for the forked workers
IX = None


def enc(i, s):
    """Instruction i encoded relative to a block that starts at s."""
    ix = IX
    g0 = ix.roff[i]
    g1 = ix.roff[i + 1]
    gs = ix.roff[s]
    prev = ix.prev
    rs = tuple((g - prev[g]) if prev[g] >= gs else 0 for g in range(g0, g1))
    b = ix.br[i]
    if b < 0:
        bc = -1
    elif b <= i:
        bc = (i - b) if b >= s else OUT
    else:
        bc = FWD
    return (ix.shp[i], rs, bc)


def window_keys(rng):
    """(positions, hashes) of every --min window inside [lo, hi) that holds no barrier."""
    lo, hi, k = rng
    shp = IX.shp
    pos, keys = array("q"), array("q")
    run = 0
    # run = number of consecutive non-barriers ending at i
    for i in range(lo, hi):
        if shp[i] < 0:
            run = 0
            continue
        run += 1
        if run >= k:
            s = i - k + 1
            pos.append(s)
            keys.append(hash(tuple(enc(j, s) for j in range(s, s + k))))
    return pos, keys


def left_maximal(members, L):
    shp = IX.shp
    for s in members:
        if s == 0 or shp[s - 1] < 0:
            return True
    ref = [enc(j, members[0] - 1) for j in range(members[0] - 1, members[0] + L)]
    for s in members[1:]:
        for d, j in enumerate(range(s - 1, s + L)):
            if enc(j, s - 1) != ref[d]:
                return True
    return False


def interesting(s, L):
    fl = IX.flags
    seg = fl[s:s + L]
    return any(f & 1 for f in seg) and not all(f & 2 for f in seg)


def fwd_split(members, L):
    """Members grouped by where their internal forward branches go (-1 = out of the block)."""
    br = IX.br
    groups = defaultdict(list)
    for s in members:
        sig = tuple((j, (br[s + j] - s) if br[s + j] < s + L else -1)
                    for j in range(L) if br[s + j] > s + j)
        groups[sig].append(s)
    return [g for g in groups.values() if len(g) >= 2]


def expand(task):
    """Grow one root group (positions whose first k instructions p-match); maximal blocks found."""
    members, k = task
    shp = IX.shp
    out = []
    stack = [(members, k)]
    while stack:
        mem, L = stack.pop()
        while True:
            buckets = defaultdict(list)
            ended = 0
            for s in mem:
                i = s + L
                if shp[i] < 0:
                    ended += 1
                    continue
                buckets[enc(i, s)].append(s)
            if ended == 0 and len(buckets) == 1:
                mem = next(iter(buckets.values()))
                L += 1
                continue
            break
        # (mem, L) is right-maximal
        if interesting(mem[0], L) and left_maximal(mem, L):
            for g in fwd_split(mem, L):
                out.append((tuple(g), L))
        for b in buckets.values():
            if len(b) >= 2:
                stack.append((b, L + 1))
    return out


def asm_files(units):
    fs = sorted((ASM / "game").glob("*.s"))
    if units:
        parts = [p.strip() for p in units.split(",") if p.strip()]
        fs = [f for f in fs if any(p in str(f) for p in parts)]
    return fs


def cache_key(files, k):
    h = hashlib.sha1(f"{VERSION} {k}".encode())
    for f in files:
        st = f.stat()
        h.update(f"{f} {st.st_mtime_ns} {st.st_size}\n".encode())
    h.update(Path(__file__).read_bytes())
    return h.hexdigest()[:16]


def build_index(files, k, jobs, log):
    global IX
    t0 = time.time()
    with Pool(jobs) as pool:
        loaded = pool.map(load_unit, files, chunksize=4)
    consts = {}
    for _, c, _ in loaded:
        consts.update(c)
    consts.update(sdata2_values("\n".join(f.read_text(errors="replace") for f in ASM.glob("auto_*sdata2*.s"))))
    ix = Index()
    for path, _, fns in loaded:
        unit = str(Path(path).relative_to(ASM).with_suffix(""))
        for name, dem, addr, insns, labels in fns:
            ix.add_fn(unit, name, dem, addr, insns, {a: i for a, i in labels.items()}, consts)
    ix.roff.append(len(ix.regs))
    log(f"read {len(files)} files, {len(ix.fns)} functions, {len(ix.shp) - len(ix.fns)} instructions "
        f"in {time.time() - t0:.1f}s")
    IX = ix
    t1 = time.time()
    n = len(ix.shp)
    step = max(1, n // (jobs * 4))
    rngs = []
    lo = 0
    while lo < n:
        hi = min(n, lo + step)
        while hi < n and ix.shp[hi - 1] >= 0:   # cut at a barrier so no window is lost
            hi += 1
        rngs.append((lo, hi, k))
        lo = hi
    with Pool(jobs) as pool:  # forked: workers inherit IX
        parts = pool.map(window_keys, rngs)
    groups = defaultdict(list)
    for pos, keys in parts:
        for p, h in zip(pos, keys):
            groups[h].append(p)
    log(f"hashed windows in {time.time() - t1:.1f}s")
    t2 = time.time()
    tasks = []
    keycount = {h: len(v) for h, v in groups.items()}
    key_at = {}
    for h, v in groups.items():
        if len(v) >= 2:
            for p in v:
                key_at[p] = h
    for h, v in groups.items():
        if len(v) < 2:
            continue
        # exact re-bucketing (hash collisions)
        sub = defaultdict(list)
        for p in v:
            sub[tuple(enc(j, p) for j in range(p, p + k))].append(p)
        for mem in sub.values():
            if len(mem) < 2:
                continue
            # the same group shifted one to the left is a group of its own: every block found
            # from here is contained in one found from there
            lk = key_at.get(mem[0] - 1)
            if lk is not None and keycount[lk] == len(mem) and all(key_at.get(p - 1) == lk for p in mem):
                continue
            tasks.append((mem, k))
    tasks.sort(key=lambda t: -len(t[0]))
    with Pool(jobs) as pool:  # forked: workers inherit IX
        res = pool.map(expand, tasks, chunksize=16)
    seen, nodes = set(), []
    for r in res:
        for mem, L in r:
            if (mem, L) not in seen:
                seen.add((mem, L))
                nodes.append((mem, L))
    nodes.sort(key=lambda x: (-len(x[0]) * x[1], x[0][0]))
    log(f"{len(tasks)} seed groups grown into {len(nodes)} maximal blocks in {time.time() - t2:.1f}s")
    return ix, nodes


# ---------------------------------------------------------------- helpers and per-function views

def helper_table(ix, nodes):
    """Inlined copies of small functions.

    For a helper H and another function F, every block they share pairs a stretch of H's body with
    a stretch of F; the pairs that put H's start at about the same place of F (within 4
    instructions: a copy may gain or lose a load or a move) form one copy, and it counts when they
    cover >= COVER of H's body. Returns ({H: {F: best cover}}, {F: [(lo, hi, H, cover)]} with lo/hi
    global indices, node -> (H, cover) for blocks that alone cover >= COVER of a helper)."""
    fn_of, small, fns = ix.fn_of, ix.small_body, ix.fns
    pairs = defaultdict(list)
    node_helper = {}
    for nid, (mem, L) in enumerate(nodes):
        hs = [x for x in mem if fn_of[x] in small]
        if not hs:
            continue
        best = None
        for sh in hs:
            h = fn_of[sh]
            cov = min(1.0, L / small[h])
            if cov >= COVER and (best is None or cov > best[1]):
                best = (h, cov)
            if len(mem) > 3000:
                continue
            rel = sh - fns[h][4]
            for sf in mem:
                f = fn_of[sf]
                if f != h:
                    pairs[(h, f)].append((sf - rel, sh, sf, L))
        if best:
            node_helper[nid] = best
    table, by_fn = defaultdict(dict), defaultdict(list)
    for (h, f), ps in pairs.items():
        body = small[h]
        if body < 1:
            continue
        ps.sort()
        groups, cur = [], [ps[0]]
        for p in ps[1:]:
            if p[0] - cur[-1][0] <= 4:
                cur.append(p)
            else:
                groups.append(cur)
                cur = [p]
        groups.append(cur)
        for g in groups:
            covered = set()
            for _, sh, _, L in g:
                covered.update(range(sh, sh + L))
            cov = len(covered) / body
            if cov < COVER:
                continue
            lo = min(p[2] for p in g)
            hi = max(p[2] + p[3] for p in g)
            if hi - lo > 2 * body:      # scattered pieces, not one copy
                continue
            table[h][f] = max(cov, table[h].get(f, 0))
            by_fn[f].append((lo, hi, h, cov))
    return dict(table), dict(by_fn), node_helper


def helper_families(ix, helpers):
    """[(members, {copy fid: cover})]: helpers whose bodies are each other's (same-size small functions,
    duplicates rather than inlines) folded into one family, ranked by inlined copies x body."""
    small = ix.small_body
    parent = {h: h for h in helpers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def twin(h, g):
        return g in helpers and h in helpers[g] and abs(small[g] - small[h]) <= 2

    for h, hits in helpers.items():
        for g in hits:
            if twin(h, g):
                parent[find(g)] = find(h)
    groups = defaultdict(list)
    for h in helpers:
        groups[find(h)].append(h)
    fams = []
    for members in groups.values():
        ms = set(members)
        copies = {}
        for h in members:
            for g, c in helpers[h].items():
                if g not in ms:
                    copies[g] = max(c, copies.get(g, 0))
        members.sort(key=lambda h: (-len(helpers[h]), ix.fns[h][3]))
        fams.append((members, copies))
    fams.sort(key=lambda fc: (-len(fc[1]) * small[fc[0][0]], ix.fns[fc[0][0]][3]))
    return fams


def merge_spans(spans):
    out = []
    for lo, hi in sorted(spans):
        if out and lo < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def occ_by_fn(ix, nodes):
    out = defaultdict(list)
    for nid, (mem, L) in enumerate(nodes):
        for s in mem:
            out[ix.fn_of[s]].append((s, nid))
    return dict(out)


def load(args, log):
    files = asm_files(args.units)
    if not files:
        sys.exit("no .s files under build/G4SE01/asm/game (run ninja once)")
    key = cache_key(files, args.min)
    path = CACHE / f"index-{key}.pkl"
    if path.exists():
        t = time.time()
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        ix = Index.__new__(Index)
        ix.__dict__.update(d["ix"])
        d["ix"] = ix
        log(f"cache {path} loaded in {time.time() - t:.1f}s")
        return d
    ix, nodes = build_index(files, args.min, args.jobs, log)
    t = time.time()
    table, copies, node_helper = helper_table(ix, nodes)
    d = {"ix": ix, "nodes": nodes, "helpers": table, "copies": copies, "node_helper": node_helper,
         "occ": occ_by_fn(ix, nodes)}
    log(f"helper table in {time.time() - t:.1f}s")
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob("index-*.pkl"):
        if old.stat().st_mtime < time.time() - 3600 * 24 * 7:
            old.unlink()
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(dict(d, ix=ix.__dict__), fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    return d


def place(ix, s):
    f = ix.fns[ix.fn_of[s]]
    return f"{f[0]} {f[1]} +0x{(s - f[4]) * 4:X}"


def fnames(ix, mem):
    return {ix.fn_of[s] for s in mem}


def listing(ix, s, L, cap):
    lines = [f"      {ix.text[j]}" for j in range(s, s + L)]
    if cap and len(lines) > cap:
        lines = lines[:cap - 2] + [f"      ... ({L - cap + 3} more)", lines[-1]]
    return lines


# ---------------------------------------------------------------- our side: rows of the current objects

def report_pct():
    p = Path("build/G4SE01/report_honest.json")
    out = {}
    if not p.exists():
        return out
    for u in json.loads(p.read_text()).get("units", []):
        unit = u["name"].split("/", 1)[-1]
        for f in u.get("functions", []):
            out[(unit, f["name"])] = float(f.get("fuzzy_match_percent") or 0)
    return out


def stretch_rows(rows, o1, o2):
    """The rows of one target stretch [o1, o2] (byte offsets of its first and last instruction)."""
    i1 = next((k for k, r in enumerate(rows) if r[4] == o1), None)
    i2 = next((k for k in range(len(rows) - 1, -1, -1) if rows[k][4] == o2), None)
    if i1 is None or i2 is None or i2 < i1:
        return None
    return rows[i1:i2 + 1]


def occurrence_status(ix, groups, jobs, log):
    """groups {key: [(start, length)]} (global indices): {key: (match, differ, not written)}, counting
    the stretches whose rows match in our current objects (a function at 100 % in the honest report
    matches everywhere; the others are diffed with objdiff-cli, ninja's objects as they stand)."""
    import scratch
    pct = report_pct()
    need = defaultdict(set)
    for spans in groups.values():
        for s, _ in spans:
            f = ix.fns[ix.fn_of[s]]
            if pct.get((f[0], f[1])) != 100.0:
                need[f[0]].add(f[1])
    t = time.time()
    root = Path(".").resolve()

    def diff_unit(unit):
        u = scratch.Unit(unit, root)
        obj = root / u.base
        if not obj.exists():
            return {}
        d = u.diff(obj, want=need[unit])
        return {n: g.rows for n, g in d.fn.items() if n in need[unit]}
    res = scratch.pmap(diff_unit, sorted(need), jobs=jobs)
    rows = {}
    for unit, r in zip(sorted(need), res):
        if isinstance(r, dict):
            for n, rr in r.items():
                rows[(unit, n)] = rr
    log(f"our rows: diffed {len(need)} units in {time.time() - t:.1f}s")
    out = {}
    for key, spans in groups.items():
        m = d_ = w = 0
        for s, L in spans:
            f = ix.fns[ix.fn_of[s]]
            if pct.get((f[0], f[1])) == 100.0:
                m += 1
                continue
            rr = rows.get((f[0], f[1]))
            o1 = (s - f[4]) * 4
            seg = stretch_rows(rr, o1, o1 + (L - 1) * 4) if rr else None
            if seg is None:
                w += 1
            elif all(r[0] is None for r in seg):
                m += 1
            else:
                d_ += 1
        out[key] = (m, d_, w)
    return out


# ---------------------------------------------------------------- reports

def game_report(d, args, log):
    ix, nodes, helpers, node_helper = d["ix"], d["nodes"], d["helpers"], d["node_helper"]
    top = args.top
    cap = 0 if args.verbose else 8
    out = []
    if not args.helpers:
        def sinit(nid):
            return all(ix.fns[ix.fn_of[x]][1].startswith("__sinit_") for x in nodes[nid][0])
        hidden = 0
        shown, variants, owner, vlabel = [], defaultdict(int), {}, {}
        for nid in range(len(nodes)):
            if len(shown) >= top:
                break
            if not args.all and sinit(nid):
                hidden += 1
                continue
            mem, L = nodes[nid]
            # the same block again, a little longer or shorter with a few occurrences more or less:
            # counted as a variant of the cluster shown above it
            votes = defaultdict(int)
            for x in mem:
                per = defaultdict(int)
                for j in range(x, x + L):
                    for c in owner.get(j, ()):
                        per[c] += 1
                for c, k in per.items():
                    if 2 * k >= L:
                        votes[c] += 1
            best = max(votes.items(), key=lambda kv: kv[1], default=None)
            if best and 5 * best[1] >= 4 * len(mem):
                variants[best[0]] += 1
                if nid in node_helper and best[0] not in vlabel and best[0] not in node_helper:
                    vlabel[best[0]] = node_helper[nid]
                continue
            shown.append(nid)
            for x in mem:
                for j in range(x, x + L):
                    owner.setdefault(j, []).append(nid)
        fams = helper_families(ix, helpers)
        groups = {("n", nid): [(x, nodes[nid][1]) for x in nodes[nid][0]] for nid in shown}
        for members, copies in fams[:top]:
            ms, spans = set(members), []
            for g in copies:
                for lo, hi in merge_spans((lo, hi) for lo, hi, h, _ in d["copies"].get(g, []) if h in ms):
                    spans.append((lo, hi - lo))
            groups[("h", members[0])] = spans
        status = {} if args.no_status else occurrence_status(ix, groups, args.jobs, log)
        out.append(f"== shared blocks: {len(nodes)} maximal blocks of >= {args.min} instructions in >= 2 places; "
                   f"top {len(shown)} clusters by occurrences x length (variants: the same block a little longer "
                   f"or shorter in most of the same places)"
                   + (f" ({hidden} above them only in __sinit_ functions, the header JASPoolAllocObject "
                      f"guards: --all shows them)" if hidden else ""))
        for nid in shown:
            mem, L = nodes[nid]
            fs = fnames(ix, mem)
            us = {ix.fns[f][0] for f in fs}
            h = node_helper.get(nid) or vlabel.get(nid)
            lab = f"  inlined copy of {ix.fns[h[0]][1]} ({h[1]:.0%} of its body)" if h else ""
            st = status.get(("n", nid))
            sts = f"\n    ours: {st[0]} match, {st[1]} differ, {st[2]} not written/not found" if st else ""
            var = f", +{variants[nid]} variants" if variants[nid] else ""
            out.append(f"#{nid + 1}: {L} insns x {len(mem)} = {L * len(mem)}; {len(fs)} functions in {len(us)} units{var}{lab}{sts}")
            out += listing(ix, mem[0], L, cap)
            for x in mem[:4]:
                out.append(f"    at {place(ix, x)}")
            if len(mem) > 4:
                out.append(f"    ... and {len(mem) - 4} more")
        out.append("")
    else:
        fams = helper_families(ix, helpers)
        status = {}
    out.append(f"== known helpers: {len(helpers)} functions of <= {SMALL} instructions whose body (>= {args.min} insns) "
               f"sits >= {COVER:.0%} inside other functions; {len(fams)} after folding same-code twins, "
               f"{sum(1 for f in fams if f[1])} with inlined copies; top {min(top, len(fams))} by copies x body")
    for members, copies in fams[:top]:
        h = members[0]
        f = ix.fns[h]
        us = {ix.fns[g][0] for g in copies}
        out.append(f"inlined copy of {f[0]} {f[1]}  [{f[2] or ''}] body {ix.small_body[h]} insns: "
                   f"in {len(copies)} functions of {len(us)} unit{'s' if len(us) != 1 else ''}")
        st = status.get(("h", h))
        if st:
            out.append(f"    ours: copies {st[0]} match, {st[1]} differ, {st[2]} not written/not found")
        if len(members) > 1:
            out.append(f"    >= {COVER:.0%} of the body shared with {len(members) - 1} other small function(s) of the same size "
                       f"(the same inlined code or a duplicate): "
                       + ", ".join(ix.fns[m][1] for m in members[1:4]) + (" ..." if len(members) > 4 else ""))
        for g, c in sorted(copies.items(), key=lambda kv: (-kv[1], ix.fns[kv[0]][3]))[:3]:
            out.append(f"    {ix.fns[g][0]} {ix.fns[g][1]} ({c:.0%})")
    return out


def fn_report(d, unit, name, args, log):
    import scratch
    ix, nodes, helpers, node_helper, occ = d["ix"], d["nodes"], d["helpers"], d["node_helper"], d["occ"]
    want_unit = re.sub(r"\.(cpp|c|cp|s)$", "", unit).replace("src/", "", 1)
    if not want_unit.startswith("game/"):
        want_unit = "game/" + want_unit
    cands = [k for k, f in enumerate(ix.fns) if f[0] == want_unit and (f[1] == name or (f[2] or "").split("(")[0] == name)]
    if not cands:
        cands = [k for k, f in enumerate(ix.fns) if f[0] == want_unit and name in f[1]]
    if len(cands) != 1:
        sys.exit(f"{name!r} matches {len(cands)} functions of {want_unit}: " +
                 ", ".join(ix.fns[k][1] for k in cands[:8]))
    fid = cands[0]
    f = ix.fns[fid]
    start, n = f[4], f[5]
    out = [f"{f[0]} {f[1]}  [{f[2] or ''}]  {n} insns"]
    # candidate stretches: (start, length, node id or None, helper fid or None, cover)
    cand = [(lo, hi - lo, None, h, cov) for lo, hi, h, cov in d["copies"].get(fid, [])]
    cand.sort(key=lambda c: (-c[1], -c[4]))
    blocks = sorted(((x, nodes[nid][1], nid, None, 0) for x, nid in occ.get(fid, [])),
                    key=lambda c: (-c[1], -len(nodes[c[2]][0])))
    taken = [False] * n
    chosen = []
    for s, L, nid, h, cov in cand + blocks:
        lo, hi = s - start, s - start + L
        free = [k for k in range(lo, hi) if not taken[k]]
        if not free:
            continue
        # keep the longest free run inside the stretch
        runs, cur = [], [free[0]]
        for k in free[1:]:
            if k == cur[-1] + 1:
                cur.append(k)
            else:
                runs.append(cur)
                cur = [k]
        runs.append(cur)
        r = max(runs, key=len)
        if len(r) < (args.min if h is None else max(4, len(free) // 2)):
            continue
        for k in r:
            taken[k] = True
        chosen.append((r[0], len(r), nid, h, cov))
    chosen.sort()
    # our side
    t = time.time()
    rows, src = None, None
    try:
        u = scratch.Unit(want_unit)
        dd = u.build(sym=True, want={f[1]})
        g = dd.fn.get(f[1])
        rows = g.rows if g else None
        if g is not None:
            import diag
            called = diag.called_of(g)
            src = diag.Src(u, g, called)
            out[0] += f"  ours: {g.pct:.2f}% {g.cls}"
        log(f"scratch -sym build of {want_unit} in {time.time() - t:.1f}s")
    except Exception as e:  # noqa: BLE001
        out.append(f"  (no source view: {type(e).__name__}: {str(e)[:200]})")
    shared, nshown, cap_st = 0, 0, (10 ** 6 if args.verbose else 30)
    for lo, L, nid, h, cov in chosen:
        if h is not None:
            others = set(helpers.get(h, {})) - {fid}
            others.add(h)
            what = f"inlined copy of {ix.fns[h][1]} ({ix.fns[h][0]}, {cov:.0%} of its {ix.small_body[h]}-insn body)"
        else:
            others = fnames(ix, nodes[nid][0]) - {fid}
            what = f"shared block #{nid + 1}"
        units = {ix.fns[x][0] for x in others}
        shared += L
        self_n = sum(1 for x in nodes[nid][0] if ix.fn_of[x] == fid) if nid is not None else 1
        where = (f"also in {len(others)} other function{'s' if len(others) != 1 else ''} "
                 f"({len(units)} unit{'s' if len(units) != 1 else ''})") if others else ""
        if self_n > 1:
            where += (", and " if where else "") + f"{self_n} times in this function"
        nshown += 1
        if nshown > cap_st:
            continue
        out.append(f"+0x{lo * 4:X}..+0x{(lo + L - 1) * 4:X}, {L} insns: {what}, {where}")
        # other helpers whose copies overlap this stretch (a helper inside a helper, or two helpers
        # with the same code: the source lines below say which one our source calls)
        seen = {h}
        for clo, chi, ch, ccov in sorted(d["copies"].get(fid, []), key=lambda c: c[0]):
            a_, b_ = clo - start, chi - start
            inside = max(0, min(b_, lo + L) - max(a_, lo))
            if ch in seen or ch == fid or inside < COVER * min(b_ - a_, L):
                continue
            seen.add(ch)
            rel = "within it" if a_ >= lo and b_ <= lo + L else "overlapping"
            out.append(f"    {rel} +0x{a_ * 4:X}..+0x{(b_ - 1) * 4:X}: inlined copy of {ix.fns[ch][1]} "
                       f"({ccov:.0%} of its {ix.small_body[ch]}-insn body; in {len(helpers.get(ch, {}))} functions)")
        out += source_view(rows, src, lo * 4, (lo + L - 1) * 4, args.verbose)
    if nshown > cap_st:
        out.append(f"... {nshown - cap_st} more shared stretches (-v shows all)")
    # the rest
    rest, k = [], 0
    while k < n:
        if taken[k] or ix.shp[start + k] < 0:
            k += 1
            continue
        j = k
        while j < n and not taken[j] and ix.shp[start + j] >= 0:
            j += 1
        rest.append((k, j - k))
        k = j
    body = sum(1 for k in range(n) if ix.shp[start + k] >= 0)
    uniq = sum(L for _, L in rest)
    out.append(f"unique to it: {uniq} of {body} body insns in {len(rest)} stretches "
               f"(shared: {shared}, {shared / max(1, body):.0%})")
    for lo, L in sorted(rest, key=lambda r: -r[1])[: (None if args.verbose else 8)]:
        out.append(f"  +0x{lo * 4:X}..+0x{(lo + L - 1) * 4:X}, {L} insns")
        if L >= 4:
            out += source_view(rows, src, lo * 4, (lo + L - 1) * 4, args.verbose, short=True)
    return out


def source_view(rows, src, o1, o2, verbose, short=False):
    if rows is None:
        return []
    seg = stretch_rows(rows, o1, o2)
    if seg is None:
        return ["    ours: (offsets not found in the rows)"]
    diff = sum(1 for r in seg if r[0] is not None)
    lines = []
    for r in seg:
        if r[3] is not None and r[3] not in lines:
            lines.append(r[3])
    head = f"    ours: {'matches' if not diff else f'{diff} of {len(seg)} rows differ'}; lines " + \
           (f"{min(lines)}-{max(lines)}" if lines else "none")
    out = [head]
    cap = 99 if verbose else (2 if short else 4)
    for ln in lines[:cap]:
        text, note = src.where(ln) if src else (None, "")
        out.append(f"      {ln:5}: {(text or '')[:90]}" + (f"   [{note}]" if note else ""))
    if len(lines) > cap:
        out.append(f"      ... {len(lines) - cap} more lines")
    return out


def to_json(d, args):
    ix, nodes, helpers, node_helper = d["ix"], d["nodes"], d["helpers"], d["node_helper"]
    blocks = []
    for nid, (mem, L) in enumerate(nodes):
        h = node_helper.get(nid)
        blocks.append({"id": nid + 1, "length": L, "occurrences": [place(ix, s) for s in mem],
                       "helper": ix.fns[h[0]][1] if h else None, "first": ix.text[mem[0]:mem[0] + L]})
    hl = [{"unit": ix.fns[h][0], "function": ix.fns[h][1], "body": ix.small_body[h],
           "copies": [{"unit": ix.fns[g][0], "function": ix.fns[g][1], "cover": round(c, 3)} for g, c in hits.items()]}
          for h, hits in helpers.items()]
    Path(args.json).write_text(json.dumps({"blocks": blocks, "helpers": hl}, indent=1))


def main():
    import grind_broker
    grind_broker.maybe_delegate("clones", sys.argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min", type=int, default=10)
    ap.add_argument("--units", help="only .s files whose path contains one of these (comma-separated)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json")
    ap.add_argument("--fn", nargs=2, metavar=("UNIT", "FUNCTION"))
    ap.add_argument("--helpers", action="store_true", help="only the known-helper table")
    ap.add_argument("--all", action="store_true", help="also show blocks found only in __sinit_ functions")
    ap.add_argument("--no-status", action="store_true", help="skip diffing our objects for the top clusters")
    ap.add_argument("--jobs", type=int, default=max(4, min(24, (os.cpu_count() or 8) * 3 // 4)))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args()
    t0 = time.time()

    def log(msg):
        if not a.quiet:
            print(f"[{time.time() - t0:5.1f}s] {msg}", file=sys.stderr, flush=True)
    d = load(a, log)
    if a.json:
        to_json(d, a)
        log(f"wrote {a.json}")
    lines = fn_report(d, a.fn[0], a.fn[1], a, log) if a.fn else game_report(d, a, log)
    print("\n".join(lines))
    log("done")


if __name__ == "__main__":
    main()
