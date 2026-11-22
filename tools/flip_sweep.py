#!/usr/bin/env python3
"""Find NonMatching units that are ready to become Matching.

A unit is a candidate when every function in build/G4SE01/report_honest.json is at 100 %, it is
not Object(Matching, ...) in configure.py and its source has no FAKEMATCH tag (gate.py refuses
those). For each candidate this runs the trial link (`tools/link_check.py --unit`), which records
the weak-duplicate evidence the honest report needs (CLAUDE.md), then rebuilds the report once and
prints which candidates now have every section at 100 %: those are ready to flip. 11 of the 15
units flipped on 2026-11-22 only needed this trial link (docs/analysis/UNIT_FLIPS.md).

  python3 tools/flip_sweep.py            # trial-link every candidate, then list the ready ones
  python3 tools/flip_sweep.py --list     # only list candidates and their sections below 100 %

It never edits configure.py: flip a ready unit by hand, then `ninja` (SHA-1) and
`tools/gate.py --all-units`.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "build/G4SE01/report_honest.json"


def candidates():
    cfg = (ROOT / "configure.py").read_text()
    rep = json.loads(REPORT.read_text())
    out = []
    for u in rep["units"]:
        fns = u.get("functions", [])
        if not fns or any(float(f.get("fuzzy_match_percent") or 0) < 100 for f in fns):
            continue
        name = u["name"].split("/", 1)[-1]
        m = re.search(r'Object\(\s*(\w+)\s*,\s*"' + re.escape(name) + r'\.(c|cpp|cp)"', cfg)
        if not m or m.group(1) == "Matching":
            continue
        src = next((p for p in (ROOT / "src", ROOT / "libs") for p in p.rglob(name.split("/")[-1] + ".*")
                    if p.suffix in (".c", ".cpp", ".cp") and str(p).endswith(name + p.suffix)), None)
        if src and "fakematch" in src.read_text(errors="ignore").lower():
            continue
        bad = {s["name"]: float(s.get("fuzzy_match_percent") or 0) for s in u.get("sections", [])
               if float(s.get("fuzzy_match_percent") or 0) < 100}
        out.append((name + "." + m.group(2), bad))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    cands = candidates()
    for unit, bad in cands:
        print(f"{unit:60s} " + (", ".join(f"{k} {v:.2f}" for k, v in bad.items()) or "all sections 100 %"))
    if a.list or not cands:
        return
    for unit, _ in cands:
        r = subprocess.run([sys.executable, "tools/link_check.py", "--unit", unit], cwd=ROOT, capture_output=True, text=True)
        print(f"trial link {unit}: " + ((r.stdout + r.stderr).strip().splitlines() or ["(no output)"])[-1][:160])
    subprocess.run(["ninja", "build/G4SE01/report_honest.json"], cwd=ROOT, capture_output=True)
    ready = [u for u, bad in candidates() if not bad]
    print(f"\nready to flip ({len(ready)}):")
    for u in ready:
        print("  " + u)


if __name__ == "__main__":
    main()
