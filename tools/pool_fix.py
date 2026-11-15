#!/usr/bin/env python3
"""tools/pool.py --fix: find the plain functions a unit's literal pool asks for.

At the first literal where our pool leaves the original's, the original created a literal that
ours creates later: some code was generated EARLIER than the function we have it in. The search
takes every candidate for that code (an `inline` helper of the file, a helper that is already a
plain function but stands elsewhere, a loop, block, case body or run of statements of the
functions that load the literal) and writes it as a plain function directly below the function
that currently creates the wrong literal, so that it is generated right before it. The candidate
that makes the pools agree furthest is kept, and the search goes on from the next difference.

A step is kept only if no function that matched stops matching; the end result only if the
whole-unit objdiff verdict has more matching functions and none fewer.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permute as P  # noqa: E402
import pool  # noqa: E402
import scratch  # noqa: E402

K = P.K
ENC = ("utf-8", "surrogateescape")


def top_of(d, fn):
    """Start of fn's definition including the comment block directly above it."""
    top = d.rfind(b"\n", 0, P.ext(fn)[0]) + 1
    if d[top:P.ext(fn)[0]].strip():
        return None
    while top > 0:
        prev = d.rfind(b"\n", 0, top - 1) + 1
        if not d[prev:top].lstrip().startswith(b"//"):
            break
        top = prev
    return top


def end_of(d, fn):
    """Just past fn's definition and the rest of its line."""
    e = P.ext(fn)[1]
    nl = d.find(b"\n", e)
    return len(d) if nl < 0 else nl + 1


def head_of(d, fn):
    """(text before the body: the signature, offset of the body's opening brace)"""
    body = P.body_of(fn)
    s = P.ext(fn)[0]
    return d[s:P.ext(body)[0]], P.ext(body)[0]


def source_fn(p, d, sym):
    """The definition in this file that emits the object symbol `sym` (a mangled name)."""
    if sym in d.fn:
        f = d.fn[sym]
        return p.locate(f.demangled, next((r[3] for r in f.rows if r[3]), None))
    base = sym.split("__")[0] if not sym.startswith("__") else None
    if base is None:
        return None
    cands = [f for f in p.functions() if f.spelling == base and P.body_of(f) is not None]
    return cands[0] if len(cands) == 1 else None


def is_inline_helper(d, fn):
    head, _ = head_of(d, fn)
    words = head.split(b"(")[0].split()
    return fn.kind == K.FUNCTION_DECL and (b"inline" in words[:3])


def case_runs(c):
    """The statements of each case of each switch (without the closing break)."""
    out = []
    for sw in (n for n in c.nodes if n.kind == K.SWITCH_STMT):
        comp = next((x for x in sw.get_children() if x.kind == K.COMPOUND_STMT), None)
        if comp is None:
            continue
        kids = list(comp.get_children())
        i = 0
        while i < len(kids):
            n = kids[i]
            if n.kind not in (K.CASE_STMT, K.DEFAULT_STMT):
                i += 1
                continue
            inner = n
            while inner.kind in (K.CASE_STMT, K.DEFAULT_STMT):
                ch = list(inner.get_children())
                if not ch:
                    break
                inner = ch[-1]
            run = [inner] if inner.kind not in (K.CASE_STMT, K.DEFAULT_STMT) else []
            j = i + 1
            while j < len(kids) and kids[j].kind not in (K.CASE_STMT, K.DEFAULT_STMT):
                run.append(kids[j])
                j += 1
            i = j
            if len(run) == 1 and run[0].kind == K.COMPOUND_STMT:
                run = list(run[0].get_children())
            while run and run[-1].kind == K.BREAK_STMT:
                run.pop()
            if run and run[0].kind != K.BREAK_STMT:
                out.append(run)
    return out


def sites_of(c):
    """Every statement, block, case body or run of c.fn that can stand as a function of its own."""
    top = P.helper_top(c)
    if top is None:
        return []
    out = P.outline_sites(c) + P.outline_sites(c, (K.IF_STMT, K.COMPOUND_STMT, K.SWITCH_STMT)) + P.run_sites(c)
    # every stretch of consecutive statements of a block or of a case (a function seldom begins or ends
    # where a declaration does): whole case bodies first, then the stretches, shortest blocks first
    groups = [(r, True) for r in case_runs(c)]
    groups += [(list(comp.get_children()), comp != c.body) for comp in sorted(c.compounds(), key=lambda n: len(list(n.get_children())))]
    budget = 260
    for kids, whole_ok in groups:
        n = len(kids)
        if n == 0 or n > 14:
            continue
        spans = [(0, n - 1)] if whole_ok else []
        spans += [(i, j) for i in range(n) for j in range(i, n) if (i, j) != (0, n - 1)]
        for i, j in spans:
            if budget <= 0:
                break
            run = kids[i:j + 1]
            if run[-1].kind == K.BREAK_STMT or run[0].kind in (K.CASE_STMT, K.DEFAULT_STMT, K.BREAK_STMT):
                continue
            budget -= 1
            try:
                s = P.outline_site(c, run, top)
            except Exception:  # noqa: BLE001
                s = None
            if s is not None:
                out.append(s)
    seen, uniq = set(), []
    for s in out:
        if s["span"] not in seen:
            seen.add(s["span"])
            uniq.append(s)
    return uniq


def candidates(unit, text, d, ours, k, want):
    """[(what, kind, lines, new text)] for the literal the original creates at #k."""
    p = P.Parsed(unit, text)
    cr = ours.creator()
    if k not in cr:
        return [], "nothing loads our literal at the first difference"
    hsym = cr[k][0]
    H = source_fn(p, d, hsym)
    if H is None:
        return [], f"the function that creates our literal #{k} ({hsym}) is not a definition of this file"
    at = end_of(text, H)
    Q = ours.values()
    j = next((i for i in range(k, len(Q)) if Q[i] == want), None)
    if j is None:
        return [], "ours never creates that literal: a function computes with another constant"
    loaders = [name for name, seq in ours.funcs if j in seq]
    out = []
    fns = [f for f in p.functions() if P.body_of(f) is not None and P.good(p, f)]
    extra = set(d.extra)
    # helpers that exist already: inline ones made plain, plain ones moved
    for g in fns:
        if g == H:
            continue
        top = top_of(text, g)
        if top is None:
            continue
        end = end_of(text, g)
        if top <= at <= end and at != end:
            continue
        inline = is_inline_helper(text, g)
        plain_extra = any(x.split("__")[0] == g.spelling for x in extra)
        if not inline and not plain_extra:
            continue
        body = text[top:end]
        proto = b""
        if inline:
            head, _ = head_of(text, g)
            sig = re.sub(rb"^\s*(static\s+inline|inline\s+static|inline)\s+", b"", head.strip())
            start = P.ext(g)[0]
            body = text[top:start] + sig + b" " + text[P.ext(P.body_of(g))[0]:end]
            proto = sig + b";\n"
        elif g.kind == K.FUNCTION_DECL:
            head, _ = head_of(text, g)
            proto = head.strip() + b";\n"
        new = P.Edit("pool", "", [(top, end, proto), (at, at, b"\n" + body.rstrip(b"\n") + b"\n")]).apply(text)
        if new is not None:
            what = (f"`{g.spelling}` as a plain function" if inline else f"`{g.spelling}` moved") + f" below `{H.spelling}`"
            out.append((what, "move", end - top, new))
    # code that is written into a function: a plain function of its own
    hosts = []
    for name in loaders:
        f = source_fn(p, d, name)
        if f is not None and all(f != x for x in hosts):
            hosts.append(f)
    for g in fns:
        if is_inline_helper(text, g) and all(g != x for x in hosts):
            hosts.append(g)
    for g in hosts:
        try:
            c = P.Ctx(p, g)
            sites = sites_of(c)
        except Exception:  # noqa: BLE001
            continue
        for s in sites:
            name = c.fresh(f"part{s['line']}_" + re.sub(r"\W", "", g.spelling)).encode()
            sig = b"void " + name + b"(" + s["params"] + b")"
            body = sig + b" {\n" + s["body"] + b"\n}\n"
            reps = [(s["top"], s["top"], sig + b";\n\n"), (s["span"][0], s["span"][1], s["ind"] + name + b"(" + s["args"] + b");\n"),
                    (at, at, b"\n" + body)]
            if s["top"] == at:
                reps = [(at, at, sig + b";\n\n"), (s["span"][0], s["span"][1], s["ind"] + name + b"(" + s["args"] + b");\n")]
                continue  # the function would stand above its own user: generated after it, not before
            new = P.Edit("pool", "", reps).apply(text)
            if new is not None:
                out.append((f"lines {s['line']}-{s['end']} of `{g.spelling}` as a plain function `{name.decode()}` below `{H.spelling}`",
                            "site", s["end"] - s["line"] + 1, new))
    return out, ""


def pool_of(unit, text):
    try:
        return pool.Obj(unit.compile(text.decode(*ENC)))
    except scratch.CompileError:
        return None


def run(unit, a, log=print):
    data = unit.source().encode(*ENC)
    dec = lambda b: b.decode(*ENC)  # noqa: E731
    tgt = pool.Obj(unit.root / unit.target)
    Pv = tgt.values()
    res = {"unit": unit.name if hasattr(unit, "name") else str(unit.src), "text": None, "trace": [], "fixed": [], "note": "", "lcp": [0, 0],
           "pool": len(Pv), "tried": 0}
    ours = pool_of(unit, data)
    if ours is None:
        res["note"] = "does not compile"
        return finish(unit, a, res, data, log)
    k0 = pool.lcp(Pv, ours.values())
    res["lcp"] = [k0, k0]
    kind, extra, missing = pool.verdict(Pv, ours.values())
    if kind == "same":
        res["note"] = "the pools are the same"
        return finish(unit, a, res, data, log)
    names, r0 = scratch.farm(unit, [data], None)
    if isinstance(r0[0], Exception):
        res["note"] = "does not compile"
        return finish(unit, a, res, data, log)
    base = r0[0]
    text, k = data, k0
    for _ in range(a.rounds):
        Q = ours.values()
        if Q == Pv or k >= len(Pv):
            break
        try:
            d = unit.build(dec(text), sym=True)
        except scratch.CompileError:
            break
        cands, why = candidates(unit, text, d, ours, k, Pv[k])
        if not cands:
            res["note"] = why or f"no candidate for literal #{k} ({pool.show(*Pv[k])})"
            break
        objs = scratch.pmap(lambda c: pool_of(unit, c[3]), cands)
        res["tried"] += len(cands)
        scored = []
        for c, o in zip(cands, objs):
            if o is None:
                continue
            n = pool.lcp(Pv, o.values())
            if n > k:
                scored.append((n, c, o))
        if not scored:
            res["note"] = f"{len(cands)} candidates, none creates literal #{k} ({pool.show(*Pv[k])}) at its place"
            break
        best_n = max(s[0] for s in scored)
        # of those that reach furthest: an existing helper before new code, then the shortest
        top = sorted((s for s in scored if s[0] == best_n), key=lambda s: (s[1][1] != "move", s[1][2]))[:6]
        _, rs = scratch.farm(unit, [s[1][3] for s in top], None)
        pick = None
        for s, r in zip(top, rs):
            if isinstance(r, list) and not any(b == 0 and x != 0 for b, x in zip(base, r)):
                pick = s
                break
        if pick is None:
            res["note"] = f"literal #{k}: every candidate breaks a function that matched"
            break
        k, text, ours = pick[0], pick[1][3], pick[2]
        res["trace"].append(f"#{k0 if not res['trace'] else res['lcp'][1]} -> #{k}: {pick[1][0]}")
        res["lcp"][1] = k
        if a.verbose:
            log("  " + res["trace"][-1])
    if text is not data:
        try:
            x, y = unit.build(dec(data)), unit.build(dec(text))
        except scratch.CompileError as e:
            res["note"] = str(e)[:100]
            return finish(unit, a, res, data, log)
        fixed = sorted(n for n, f in y.fn.items() if f.pct == 100 and n in x.fn and x.fn[n].pct < 100)
        broke = [n for n, f in x.fn.items() if f.pct == 100 and (n not in y.fn or y.fn[n].pct < 100)]
        worse = [n for n, f in y.fn.items() if n in x.fn and f.pct < x.fn[n].pct - 0.005]
        res["worse"] = len(worse)
        if broke:
            res["note"] = f"objdiff: breaks {len(broke)} ({broke[0]})"
        else:
            res.update(text=text, fixed=fixed, fixed_bytes=sum(y.fn[n].size for n in fixed), same=(ours.values() == Pv))
    return finish(unit, a, res, data, log)


def finish(unit, a, res, data, log):
    name = str(unit.src).split("/")[-1].replace(".cpp", "")
    saved = None
    if res["text"] is not None:
        out = Path(a.save)
        out.mkdir(parents=True, exist_ok=True)
        saved = out / (name + (".pool.hand.diff" if res["fixed"] else ".pool.lead.diff"))
        saved.write_text(P.diff_text(data, res["text"], unit.src))
        if a.apply and res["fixed"]:
            (unit.root / unit.src).write_bytes(res["text"])
    res["diff"] = str(saved) if saved else None
    state = ("the pools are the same now" if res.get("same") else f"pools equal up to #{res['lcp'][1]} of {res['pool']} (was #{res['lcp'][0]})")
    log(f"{name}: {state}; fixes {len(res['fixed'])} ({res.get('fixed_bytes', 0)} B), {res.get('worse', 0)} open ones worse, "
        f"{res['tried']} tried" + (f" ({res['note']})" if res["note"] else ""))
    for t in res["trace"]:
        log("  - " + t)
    if saved:
        log(f"  diff: {saved}")
    if getattr(a, "json", None):
        with open(a.json, "a") as f:
            import json
            f.write(json.dumps({k: v for k, v in res.items() if k != "text"}) + "\n")
    return 0 if res["fixed"] else 1
