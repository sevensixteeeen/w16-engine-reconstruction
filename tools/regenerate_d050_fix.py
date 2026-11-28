"""D-050 correction (2026-11-27, option (a) of the user): the crank FE stage, then the R2.5 mesh convergence - both with the
corrected bearing-land load (fea.crank_solve.fn_land) and the per-node support guard (a run stops if a single support
node carries more than 1 % of the pin load).
    run_crank_fix_d050.cmd      (or: set PYTHONPATH=src & .venv\\Scripts\\python.exe tools\\regenerate_d050_fix.py)
Overnight, with nothing else open.  Stages, each its own process, in order, stopping at the first failure (runner of
tools/regenerate_d042.py; logs and peak memory per stage in regen_logs_d050_fix/):
  1 fea_crank           standard 1.0 mm mesh -> 08_SIMULATIONS/fea/crank.json, crank_throw_vm.png   (~60 min, peak ~6 GB)
  2 crank_convergence   tools/crank_groove_convergence.py: R2.5, local 1.0 / 0.7 / 0.5 / 0.35 mm
                        -> 08_SIMULATIONS/fea/crank_groove_convergence.json ("semicircle"; the R1.6 run of option (c)
                        stays as it was)                                                              (~4 h)
Afterwards (no FE): tools/crank_main_fillet_torsion.py (combined bending + torsion), python -m w16.docs, the D-050 records,
the scoped commit with the duct-A record, tools/publish_github.py --push.
"""
from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regenerate_d042 as R  # noqa: E402

R.LOGS = os.path.join(R.ROOT, "regen_logs_d050_fix")


def main():
    os.makedirs(R.LOGS, exist_ok=True)
    s = []
    R.run(1, "fea_crank", ["-m", "w16.sim.fea", "crank"], s)
    R.run(2, "crank_convergence", [os.path.join("tools", "crank_groove_convergence.py")], s)
    print("all stages finished - logs in", R.LOGS, flush=True)


if __name__ == "__main__":
    main()
