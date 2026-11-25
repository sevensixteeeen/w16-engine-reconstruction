"""Partial regeneration after D-048 / D-049 / D-050 (2026-11-25): only the stages the crank changes reach.

    run_regeneration_d050.cmd      (or: set PYTHONPATH=src & .venv\\Scripts\\python.exe tools\\regenerate_d050.py)

Stages, each its own process, in order, stopping at the first failure (runner of tools/regenerate_d042.py; logs and peak
memory per stage in regen_logs_d050/):
  1 reports          analytical package: torsional model with the CAD throw inertia, main-bearing width = 12.2 mm shell
  2 assembly         CAD build + summary (solid pins, oil drillings, R2.5 main fillets, 12.2 mm main shells - D-050 option (b))
  3 export           STEP / BREP / STL exports, hierarchy, validation (as-built crank balance)
  4 fea_crank        crank FE, standard 1.0 mm mesh, bearing-reaction supports (~2 h, 488k tets)
  5 oil_drillings    tools/check_oil_drillings.py
  6 main_fillet_torsion  tools/crank_main_fillet_torsion.py (hand calc, bending + torsion; needs the R2.5 convergence record)
  7 ic_static        targeted static interference: crankshaft, main shells, big-end shells (all their candidate pairs)
  8 ic_kinematic     targeted kinematic interference: pistons / rods / shells (groups 03, 04) vs crankshaft, 12 crank angles
  9 render, 10 drawings, 11 docs
Not run: the other FE cases (unchanged parts), the full interference check (section 9 of the report keeps the D-047 run
and states it), the system diagrams (unchanged).
"""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regenerate_d042 as R  # noqa: E402

R.LOGS = os.path.join(R.ROOT, "regen_logs_d050")
IC = os.path.join("06_ASSEMBLIES", "interference")


def main():
    os.makedirs(R.LOGS, exist_ok=True)
    s = []
    R.run(1, "reports", ["-m", "w16.reports"], s)
    R.run(2, "assembly", ["-m", "w16.cad.assembly"], s)
    R.run(3, "export", ["-m", "w16.cad.export", "all"], s)
    R.run(4, "fea_crank", ["-m", "w16.sim.fea", "crank"], s)
    R.run(5, "oil_drillings", [os.path.join("tools", "check_oil_drillings.py")], s)
    R.run(6, "main_fillet_torsion", [os.path.join("tools", "crank_main_fillet_torsion.py")], s)
    R.run(7, "ic_static", [os.path.join("tools", "check_interference_parts.py"), "W16-05-001", "W16-01-005", "W16-04-003",
                           "--json", os.path.join(IC, "targeted_d050_static.json")], s)
    R.run(8, "ic_kinematic", [os.path.join("tools", "check_kinematic_parts.py"), "W16-0[34]-", "W16-05-001",
                              "--json", os.path.join(IC, "targeted_d050_kinematic.json")], s)
    R.run(9, "render", ["-m", "w16.cad.render"], s)
    R.run(10, "drawings", ["-m", "w16.cad.drawings"], s)
    R.run(11, "docs", ["-m", "w16.docs"], s)
    print(f"[{time.strftime('%H:%M:%S')}] partial regeneration complete - regen_logs_d050/summary.json", flush=True)


if __name__ == "__main__":
    main()
