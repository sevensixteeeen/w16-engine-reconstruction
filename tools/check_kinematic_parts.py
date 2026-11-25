"""Targeted kinematic interference check: at each crank angle of the full sweep (0-660 deg, 60 deg steps), every candidate
pair between parts matching pattern A and parts matching pattern B, with the moving parts placed as in the full check
(w16.cad.export.worker, kinematic subset: the first two cylinders of each bank).  For verifying a local fix of a moving part
without the 14 h sweep; the full check remains the acceptance evidence.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\check_kinematic_parts.py "W16-04-003" "W16-05-001"
"""
from __future__ import annotations
import argparse
import collections
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from w16.cad import assembly as ASM, export as E, render as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--step", type=float, default=60.0)
    ap.add_argument("--json", help="write the counts and the worst clash / error per pair here")
    a = ap.parse_args()
    pa, pb = re.compile(a.a), re.compile(a.b)
    t0 = time.time()
    reg, info = ASM.build(0.0)
    R.RING_Z = (info["piston"]["g1"], info["piston"]["g2"], info["piston"]["g3"])
    print(f"build {time.time() - t0:.0f} s", flush=True)
    tot = collections.Counter()
    worst = {}
    for al in np.arange(0.0, 720.0, a.step):
        inst = E.instances(reg, R.moving_locs(reg, al), subset=True)
        pairs = [(i, j) for i, j in E.candidate_pairs(inst, only=lambda pn: bool(pa.match(pn) or pb.match(pn)))
                 if (pa.match(inst[i][0]) and pb.match(inst[j][0])) or (pb.match(inst[i][0]) and pa.match(inst[j][0]))]
        res = E.check_pairs(inst, pairs)
        c = collections.Counter(r["status"] for r in res)
        tot.update(c)
        for r in res:
            if r["status"] in ("clash", "error"):
                k = (r["a"], r["b"], r["status"])
                worst[k] = max(worst.get(k, 0.0), r.get("volume_mm3") or 0.0)
        print(f"  {al:5.0f} deg: {len(pairs)} pairs {dict(c)}", flush=True)
    print("total", dict(tot))
    for (x, y, st), v in sorted(worst.items(), key=lambda kv: -kv[1]):
        print(f"  {st.upper()} {x} | {y} max {v:.2f} mm3")
    if not worst:
        print("  no clashes, no errors")
    if a.json:
        import json
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(dict(what=f"kinematic {a.a} vs {a.b}, {len(np.arange(0.0, 720.0, a.step))} crank angles", patterns=[a.a, a.b], counts=dict(tot),
                           worst=[dict(a=x, b=y, status=st, max_volume_mm3=v) for (x, y, st), v in sorted(worst.items(), key=lambda kv: -kv[1])]), fh, indent=1)


if __name__ == "__main__":
    main()
