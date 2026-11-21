"""Targeted static interference check: every candidate pair (overlapping bounding boxes) that involves a part matching one
of the given part-number patterns (regular expressions, matched from the start), with the same boolean / clipped-solid
logic and expected-contact rules as the full check (w16.cad.export.check_pairs).  For verifying a local fix without the
full run; the full check (python -m w16.cad.export interference) remains the acceptance evidence.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\check_interference_parts.py "W16-07-" "W16-13-pipe_" [--json out.json]
"""
from __future__ import annotations
import argparse
import collections
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from w16.cad import assembly as ASM, export as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--json", help="write all non-clear results here")
    a = ap.parse_args()
    pats = [re.compile(p) for p in a.patterns]
    hit = lambda pn: any(p.match(pn) for p in pats)
    t0 = time.time()
    reg, info = ASM.build(0.0)
    inst = E.instances(reg)
    pairs = E.candidate_pairs(inst, only=hit)
    print(f"build {time.time() - t0:.0f} s; {len(inst)} instances; {len(pairs)} candidate pairs involving {a.patterns}", flush=True)
    t1 = time.time()
    res = E.check_pairs(inst, pairs)
    cnt = collections.Counter(r["status"] for r in res)
    print(f"checked in {time.time() - t1:.0f} s: {dict(cnt)}", flush=True)
    agg = {}
    for r in res:
        if r["status"] in ("clash", "error"):
            k = (r["a"], r["b"], r["status"])
            e = agg.setdefault(k, dict(n=0, vmax=0.0, reason=r.get("reason")))
            e["n"] += 1
            e["vmax"] = max(e["vmax"], r.get("volume_mm3") or 0.0)
    for (pa, pb, st), e in sorted(agg.items(), key=lambda kv: -kv[1]["vmax"]):
        print(f"  {st.upper():5s} {pa} | {pb} x{e['n']} max {e['vmax']:.2f} mm3" + (f" ({e['reason']})" if e["reason"] else ""))
    if not agg:
        print("  no clashes, no errors")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(dict(patterns=a.patterns, counts=dict(cnt), results=[r for r in res if r["status"] != "clear"]), fh, indent=1)


if __name__ == "__main__":
    main()
