#!/usr/bin/env python3
"""Claude vs Gemini in the grinder, from g2-logs/ledger.tsv.

  python3 tools/grind_stats.py [--since TS] [--round]   # table per model tier (markdown)
  --round: also append one row per tier for the window since the last logged round
           to g2-logs/model_stats.tsv (the running log, one block per publish)

Per tier: sessions, session time, tokens, list-price cost (Claude; Gemini runs on the free
Antigravity quota, so $0; tokens and $ include the tier's review sessions, minutes do not), sessions that kept a change, review outcomes (accepted / repaired /
rejected as tricks), matched bytes gained (size x the %-point gain of each kept change, the
reviewer's repaired figure where there is one, tricks taken out), functions brought to 100 %
and the yield per session, per session-minute and per dollar.
"""
import argparse, datetime, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grind as g

GEM = set(g.GEMINI)
STATS = g.LOGS / "model_stats.tsv"
HEAD = ["round", "since", "tier", "family", "sessions", "minutes", "review_sessions", "review_minutes", "tok_in", "tok_cache_read", "tok_out", "usd",
        "kept", "reviewed_ok", "repaired", "tricks", "bytes_gained", "to_100", "bytes_per_session",
        "bytes_per_min", "bytes_per_usd"]


def num(v):
    return float(v) if re.match(r"^-?\d+(\.\d+)?$", v or "") else 0.0


def table(since, until=None):
    rows = [dict(zip(g.COLS, r)) for r in g.ledger_rows() if len(r) >= len(g.COLS) and r[0] > since
            and (until is None or r[0] <= until)]
    lost = {(r["unit"], r["fn"]) for r in rows if r["verdict"] == "TRICK" and r["why"] == "no verdict from the reviewer"}
    trick = {(r["unit"], r["fn"]) for r in rows if r["verdict"] == "TRICK"} - lost  # lost: the reviewer had no quota
    fixed = {(r["unit"], r["fn"]): num(r["pct1"]) for r in rows if r["verdict"] == "FIXED" and re.match(r"^\d", r["pct1"] or "")}
    t = defaultdict(lambda: defaultdict(float))
    for r in rows:
        tier = r["tier"]
        a = t[tier]
        if r["verdict"] in ("ACCEPT", "REJECT") and r["lane"] != "review" and r["secs"].isdigit():
            a["sessions"] += 1
            a["minutes"] += int(r["secs"]) / 60
            a["tok_in"] += num(r["in"]) + num(r["cache_write"])
            a["tok_cache_read"] += num(r["cache_read"])
            a["tok_out"] += num(r["out"])
            a["usd"] += num(r["cost"])
        if r["verdict"] == "REVIEW" and r["secs"].isdigit():  # the reviewer's own session: cost to its tier
            a["review_sessions"] += 1
            a["review_minutes"] += int(r["secs"]) / 60
            a["tok_in"] += num(r["in"]) + num(r["cache_write"])
            a["tok_cache_read"] += num(r["cache_read"])
            a["tok_out"] += num(r["out"])
            a["usd"] += num(r["cost"])
        if r["verdict"] == "ACCEPT" and r["fn"] != "FILE":
            a["kept"] += 1
            key = (r["unit"], r["fn"])
            if key in lost and not r["why"].startswith("recovered:"):
                a["kept"] -= 1  # counted again by its "recovered:" row once re-reviewed
                continue
            if key in trick:
                a["tricks"] += 1
                continue
            p1 = fixed.get(key, num(r["pct1"]))
            if key in fixed:
                a["repaired"] += 1
            else:
                a["reviewed_ok"] += 1
            a["bytes_gained"] += num(r["size"]) * (p1 - num(r["pct0"])) / 100
            a["to_100"] += p1 >= 100 > num(r["pct0"])
    out = []
    for tier, a in t.items():
        if not a["sessions"] and not a["review_sessions"]:
            continue
        a["bytes_per_session"] = a["bytes_gained"] / a["sessions"] if a["sessions"] else 0
        a["bytes_per_min"] = a["bytes_gained"] / a["minutes"] if a["minutes"] else 0
        a["bytes_per_usd"] = a["bytes_gained"] / a["usd"] if a["usd"] else float("inf") if a["bytes_gained"] else 0
        out.append((tier, "gemini" if tier in GEM else "claude", a))
    order = {k: i for i, k in enumerate(g.ORDER + list(g.GEMINI))}
    return sorted(out, key=lambda x: (x[1], order.get(x[0], 9)))


def fmt(rows):
    lines = ["| tier | sessions | min | reviews (min) | tok in (k) | cache read (k) | tok out (k) | $ | kept | ok/repaired/trick | bytes gained | to 100 % | B/session | B/min | B/$ |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for tier, fam, a in rows:
        bpu = "free" if fam == "gemini" else f"{a['bytes_per_usd']:.0f}"
        lines.append(f"| {tier} | {a['sessions']:.0f} | {a['minutes']:.0f} | {a['review_sessions']:.0f} ({a['review_minutes']:.0f}) | {a['tok_in']/1e3:.0f} | {a['tok_cache_read']/1e3:.0f} | "
                     f"{a['tok_out']/1e3:.0f} | {a['usd']:.2f} | {a['kept']:.0f} | {a['reviewed_ok']:.0f}/{a['repaired']:.0f}/{a['tricks']:.0f} | "
                     f"{a['bytes_gained']:.0f} | {a['to_100']:.0f} | {a['bytes_per_session']:.0f} | {a['bytes_per_min']:.0f} | {bpu} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-14T00:00")
    ap.add_argument("--round", action="store_true")
    args = ap.parse_args()
    print(fmt(table(args.since)))
    if args.round:
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        last = args.since
        if STATS.exists():
            prev = [l.split("\t") for l in STATS.read_text().splitlines()[1:] if l.strip()]
            if prev:
                last = prev[-1][0]
        new = not STATS.exists()
        with open(STATS, "a") as f:
            if new:
                f.write("\t".join(HEAD) + "\n")
            for tier, fam, a in table(last, now):
                f.write("\t".join([now, last, tier, fam] + [f"{a[k]:.2f}" if isinstance(a[k], float) else str(a[k]) for k in HEAD[4:]]) + "\n")
        print(f"\nround {last} -> {now} logged to {STATS}")


if __name__ == "__main__":
    main()
