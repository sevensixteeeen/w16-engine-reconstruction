"""Full regeneration on the D-041 / D-042 geometry (approved 2026-11-20).  The piston FE is NOT run (fea/piston.json is
the valid D-042 run of 2026-11-18).

    run_regeneration.cmd          (or: set PYTHONPATH=src & .venv\\Scripts\\python.exe tools\\regenerate_d042.py)

Each stage runs as its own process, in order, with its output in regen_logs/<nn>_<stage>.log; the chain stops at the first
stage that fails (non-zero exit), so later stages never run on stale inputs.  regen_logs/summary.json records exit code,
time and peak memory (whole process tree) per stage.  The interference check uses 3 kinematic workers only if the measured
peak of the export stage (one full assembly build) times the number of worker processes fits in the RAM available at that
moment with a 1.5 GB reserve; otherwise 2, else 1 (2 static workers in every case).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

import psutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGS = os.path.join(ROOT, "regen_logs")
PY = sys.executable
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONUNBUFFERED="1")
N_STATIC = 2
RESERVE_GB = 1.5


def run(n, name, args, summary):
    log = os.path.join(LOGS, f"{n:02d}_{name}.log")
    t0, peak = time.time(), 0
    print(f"[{time.strftime('%H:%M:%S')}] {n:02d} {name}: {' '.join(args)}", flush=True)
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen([PY] + args, cwd=ROOT, env=ENV, stdout=fh, stderr=subprocess.STDOUT)
        pp = psutil.Process(p.pid)
        while p.poll() is None:
            try:
                rss = pp.memory_info().rss + sum(c.memory_info().rss for c in pp.children(recursive=True))
                peak = max(peak, rss)
            except psutil.Error:
                pass
            time.sleep(2)
    rec = dict(stage=name, args=args, exit=p.returncode, minutes=round((time.time() - t0) / 60, 1), peak_gb=round(peak / 2**30, 2), log=log)
    summary.append(rec)
    with open(os.path.join(LOGS, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(f"           exit {p.returncode}, {rec['minutes']} min, peak {rec['peak_gb']} GB", flush=True)
    if p.returncode != 0:
        print(f"STOPPED at {name} - see {log}", flush=True)
        sys.exit(p.returncode)
    return rec


def main():
    os.makedirs(LOGS, exist_ok=True)
    summary = []
    run(1, "reports", ["-m", "w16.reports"], summary)
    run(2, "assembly", ["-m", "w16.cad.assembly"], summary)
    exp = run(3, "export", ["-m", "w16.cad.export", "all"], summary)
    run(4, "fea_rod_crank_insert_block_head", ["-m", "w16.sim.fea", "rod", "crank", "insert", "block", "head"], summary)
    per = max(exp["peak_gb"], 1.0)
    avail = psutil.virtual_memory().available / 2**30
    n_kin = next(k for k in (3, 2, 1) if (N_STATIC + k) * per * 1.15 + RESERVE_GB <= avail or k == 1)
    note = dict(stage="interference_workers", peak_per_build_gb=per, available_gb=round(avail, 2), n_static=N_STATIC, n_kin=n_kin)
    summary.append(note)
    print(f"           interference: {N_STATIC} static + {n_kin} kinematic workers (build peak {per} GB, {avail:.1f} GB available)", flush=True)
    run(5, "interference", ["-c", f"from w16.cad import export as E; E.interference({N_STATIC}, {n_kin})"], summary)
    run(6, "render", ["-m", "w16.cad.render"], summary)
    run(7, "drawings", ["-m", "w16.cad.drawings"], summary)
    run(8, "diagrams", ["-m", "w16.diagrams"], summary)
    run(9, "docs", ["-m", "w16.docs"], summary)
    print(f"[{time.strftime('%H:%M:%S')}] regeneration complete - regen_logs/summary.json", flush=True)


if __name__ == "__main__":
    main()
