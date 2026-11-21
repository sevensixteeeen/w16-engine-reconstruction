"""Fix A (big-end shell vs crankpin fillet, 2026-11-21): the two options side by side, for the user's decision.

(a) undercut fillet: the R2.5 pin fillets recessed into the webs (cranktrain.throw_solid(pin_fillet="undercut")); the shell
    keeps its 16.25 mm width.  Crank FE of throw 3, same load and supports as `case_crank` (design gas force on the central
    pin, both main journals fixed), current vs undercut, on the SAME mesh settings with a fine mesh along both fillet
    circles; stress in the fillet zones and in the webs.
(b) narrowed shell: the shell edge moved out of the fillet; big-end specific load and Ocvirk minimum film (as in the
    dynamics report) for the narrowed widths.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\crank_fillet_options.py [--fe-size 1.0]

Output: 08_SIMULATIONS/fea/crank_fillet_options.json (no "case" key: not an FE case record of the report).
Production files (crank.json, crank_throw_vm.png) are not touched.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import tempfile
import time

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build123d import Align, Cylinder, Pos, Rot  # noqa: E402
from w16.params import P  # noqa: E402
from w16 import layout as L  # noqa: E402
from w16.cad import cranktrain as CT  # noqa: E402
from w16.analysis import dynamics as DY  # noqa: E402
from w16.sim import fea as F  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_fillet_options.json")
RF = 2.5                         # pin fillet radius
SHELL_CLEAR = 0.3                # axial clearance shell edge -> fillet (EST)


class CGSolver:
    """Jacobi-preconditioned CG (low memory; matched the direct solver to 1e-11 on the piston)."""
    def __init__(self, A):
        self.A = A.tocsr()
        self.M = sp.diags(1.0 / self.A.diagonal())

    def solve(self, b):
        t, it = time.time(), [0]
        x, info = cg(self.A, b, rtol=1e-10, maxiter=500000, M=self.M, callback=lambda xk: it.__setitem__(0, it[0] + 1))
        if info != 0:
            raise RuntimeError(f"CG did not converge (info {info}, {it[0]} iterations)")
        print(f"    CG converged: {it[0]} iterations, {time.time() - t:.0f} s", flush=True)
        return x


def option_b():
    """Shell edge out of the fillet: at the shell bore radius the fillet reaches x_f from the web face."""
    r, rs = P.pin_dia / 2, P.pin_dia / 2 + 0.022                       # pin radius, shell bore radius (CAD)
    x_f = RF - math.sqrt(RF ** 2 - (r + RF - rs) ** 2)                  # fillet extent at the shell bore
    gap_rod = P.pin_width / 2 - ((P.rod_be_width + P.rod_side_clear) / 2 + P.rod_be_width / 2)   # rod outer face -> web face
    w0 = P.rod_be_width - 1.5                                           # current shell width = effective width in the dynamics report
    edge0 = gap_rod + 0.75                                              # current shell edge -> web face
    need = x_f + SHELL_CLEAR
    cut = max(0.0, need - edge0)
    widths = {"current (16.25 mm, clashes with the fillet)": w0, "narrowed on the web side only (handed position)": w0 - cut,
              "narrowed symmetrically (one shell for both edges)": w0 - 2 * cut}
    # loads from the dynamics report (full load) - recomputed here from the analytical model
    loads = json.load(open(os.path.join(ROOT, "08_SIMULATIONS", "analytical", "results.json"), encoding="utf-8"))
    from w16.analysis import cycle as CY
    A_t = loads["A_turb_cm2"] * 1e-4
    curve, _ = CY.full_load_curve(rpms=[2000, 3750, 6700], A_turb=A_t)      # as the report (turbine-limited points handled)
    be = {}
    for row in curve:
        be[row["rpm"]] = DY.run(row["rpm"], row, A_turb=A_t)["be_peak"]
    rows = {}
    for lab, w in widths.items():
        rows[lab] = dict(width_mm=w, area_change_pct=100 * (w / w0 - 1),
                         spec_load_MPa={n: be[n] / (P.pin_dia * w) for n in be},
                         h_min_um={n: DY.short_bearing_hmin(be[n], P.pin_dia, w, n)[1] for n in be},
                         eps={n: DY.short_bearing_hmin(be[n], P.pin_dia, w, n)[0] for n in be})
    return dict(fillet_extent_at_shell_bore_mm=x_f, rod_face_to_web_mm=gap_rod, shell_edge_to_web_now_mm=edge0,
                shell_edge_to_web_needed_mm=need, shell_clearance_mm=SHELL_CLEAR, narrowing_per_edge_mm=cut,
                big_end_peak_N=be, widths=rows,
                note=("Ocvirk short-bearing quasi-static minimum film (dynamics.short_bearing_hmin, clearance ratio 0.0008, 4.5 mPa s) - "
                      "the method of the dynamics report (2,000 rpm row is its reported value); squeeze film ignored. The rod body "
                      "face clears the fillet by about 0.025 mm at the shell back radius; with a narrowed shell the big-end bore needs a "
                      "side chamfer towards the web."))


def zones(m, pc, xa, xb):
    """Element masks: fillet zones (within 5 mm of either fillet circle) and webs (beyond the fillet zone, clear of the mains)."""
    cen = m.p[:, m.t].mean(axis=1)
    rp = np.hypot(cen[1] - pc[1], cen[2] - pc[2])
    r0 = P.pin_dia / 2 + RF / 2
    fz = np.zeros(cen.shape[1], bool)
    for xf in (xa, xb):
        fz |= np.hypot(cen[0] - xf, rp - r0) < 5.0
    web = ((cen[0] < xa) & (cen[0] > xa - P.web_thk)) | ((cen[0] > xb) & (cen[0] < xb + P.web_thk))
    rc = np.hypot(cen[1], cen[2])
    web &= ~fz & (rc > P.main_dia / 2 + 6.0)
    return fz, web


def run_fe(variant, size):
    from w16.cad.assembly import _cw
    cw, _ = _cw()
    k = 3
    thr = CT.throw_solid(k, (cw[k][0], cw[k][1]), pin_fillet=variant)
    hm = P.main_width / 2
    for j in (k, k + 1):
        thr = thr + Pos(L.main_x(j) - hm, 0, 0) * Rot(Y=90) * Cylinder(P.main_dia / 2, P.main_width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    mt = F.mat("steel_qt")
    psi = math.radians(L.PIN_PHASE[k])
    pc = np.array([L.pin_x(k), P.throw * math.sin(psi), P.throw * math.cos(psi)])
    xa, xb = pc[0] - P.pin_width / 2, pc[0] + P.pin_width / 2
    ref = [((xa, pc[1], pc[2]), 34, 2.4), ((xb, pc[1], pc[2]), 34, 2.4)]
    r0 = P.pin_dia / 2 + RF / 2
    e1 = np.array([0.0, math.cos(psi), -math.sin(psi)]); e2 = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, math.sin(psi), math.cos(psi)])
    for xf in (xa, xb):
        for a in np.linspace(0, 2 * math.pi, 40, endpoint=False):
            pt = np.array([xf, pc[1], pc[2]]) + r0 * (math.cos(a) * e1 + math.sin(a) * up)
            ref.append((tuple(pt), 4.5, size))
    t0 = time.time()
    m, st = F.mesh_shape(thr, 5.0, f"crank_{variant}", refine=ref)
    print(f"  {variant}: mesh {st['tets']} tets ({time.time() - t0:.0f} s)", flush=True)
    mains = F.facets(m, lambda x: (np.hypot(x[1], x[2]) < P.main_dia / 2 + 0.05) & ((x[0] < L.main_x(k) + hm + 0.01) | (x[0] > L.main_x(k + 1) - hm - 0.01)))
    pin = F.facets(m, lambda x: (np.hypot(x[1] - pc[1], x[2] - pc[2]) < P.pin_dia / 2 + 0.05) & (np.abs(x[0] - pc[0]) < P.pin_width / 2 - 2.6))
    Fz = P.p_max_design_bar * 1e5 * math.pi / 4 * (P.bore * 1e-3) ** 2      # = R["dynamics"]["F_design_gas"]
    e_pin = np.array([0, math.sin(psi), math.cos(psi)])
    fn, p0 = F.cos_load(pc, (1, 0, 0), -e_pin, Fz, m, pin)
    s = F.solve_elastic(m, mt, mains, tractions=[(pin, fn)])
    vm = np.asarray(s["vm"])
    fz, web = zones(m, pc, xa, xb)
    cen = m.p[:, m.t].mean(axis=1)
    def zst(mask):
        v = vm[mask]
        i = int(np.argmax(np.where(mask, vm, -1)))
        return dict(elements=int(mask.sum()), vm_max_MPa=float(v.max()), vm_p999_MPa=float(np.percentile(v, 99.9)),
                    vm_p99_MPa=float(np.percentile(v, 99.0)), at=[round(float(c), 2) for c in cen[:, i]],
                    fatigue_factor_on_max=mt["fatigue"] / (0.5 * float(v.max())))
    pk, p999, loc = F.peak(m, vm)
    return dict(variant=variant, mesh=st, force_N=Fz, applied_force_check_N=np.asarray(s["applied"]).tolist(),
                vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc,
                pin_deflection_mm=float(np.sqrt((s["U"] ** 2).sum(0)).max()), fillet_zone=zst(fz), webs=zst(web),
                volume_mm3=float(thr.volume), solve_s=s.get("t_solve"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fe-size", type=float, default=1.0, help="element size along the fillet circles (mm)")
    ap.add_argument("--skip-fe", action="store_true")
    a = ap.parse_args()
    out = dict(date=time.strftime("%Y-%m-%d"), option_b=option_b())
    print(json.dumps(out["option_b"], indent=1, default=float), flush=True)
    if not a.skip_fe:
        F.spd_factor = CGSolver
        F.OUT = tempfile.mkdtemp(prefix="w16_crank_fillet_")
        out["option_a"] = dict(fe_size_fillet_mm=a.fe_size, cases={})
        for v in ("ring", "undercut"):
            r = run_fe(v, a.fe_size)
            out["option_a"]["cases"][v] = r
            print(f"  {v}: fillet zone max {r['fillet_zone']['vm_max_MPa']:.1f} MPa (p99.9 {r['fillet_zone']['vm_p999_MPa']:.1f}) at {r['fillet_zone']['at']}, "
                  f"webs max {r['webs']['vm_max_MPa']:.1f}, overall max {r['vm_max_MPa']:.1f} at {[round(x, 1) for x in r['vm_max_location']]}, "
                  f"pin deflection {r['pin_deflection_mm'] * 1e3:.1f} um", flush=True)
        c, u = out["option_a"]["cases"]["ring"], out["option_a"]["cases"]["undercut"]
        out["option_a"]["mass_change_per_throw_g"] = (u["volume_mm3"] - c["volume_mm3"]) * 7.85e-3
        out["option_a"]["fillet_zone_change_pct"] = 100 * (u["fillet_zone"]["vm_max_MPa"] / c["fillet_zone"]["vm_max_MPa"] - 1)
        out["option_a"]["web_change_pct"] = 100 * (u["webs"]["vm_max_MPa"] / c["webs"]["vm_max_MPa"] - 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=float)
    print("written", OUT)


if __name__ == "__main__":
    main()
