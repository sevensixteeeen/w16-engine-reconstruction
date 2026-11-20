"""Post-processing of the D-042 piston FE (2026-11-18): the thinnest crown section under the long-valve pockets and a
temperature-dependent fatigue estimate.

The production run (python -m w16.sim.fea piston) keeps only summary values.  This tool re-solves the same case on the
same mesh with a preconditioned conjugate-gradient solver (about 2 GB instead of the ~10 GB of the direct solver; on the
coarse test mesh it agrees with the direct solution to 1e-11) into a scratch folder, and stops unless its global
results reproduce 08_SIMULATIONS/fea/piston.json.  Then:

  section   elements under the pocket floors (inside the pocket footprint) and above the oil-gallery roof, inside the
            gallery ring: thickness, temperature, von Mises (gas; gas + thermal)
  fatigue   per element: alternating stress sigma_a = half the gas-case von Mises (gas load 0 -> design pressure each
            cycle, as in the FE record), against a temperature-dependent fatigue strength
              sigma_f(T) = sigma_f,RT * UTS(T) / UTS(RT)
            with UTS(T) of 4032-T6 after 10,000 h at temperature (ASM_4032_UTS below) - an EST scaling (no elevated-
            temperature fatigue data for 4032 in that source), conservative because the data are for the fully
            overaged state.  Factors without mean stress, and with a Goodman mean-stress correction for the 0 -> max gas
            cycle (sigma_m = sigma_a against UTS(T)).

    PYTHONPATH=src python tools/piston_section_fatigue.py      (about 1 h; writes 08_SIMULATIONS/fea/piston_section_fatigue.json)
"""
from __future__ import annotations
import json
import math
import os
import sys
import tempfile
import time

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

from w16.sim import fea as F
from w16.params import P

# ASM Handbook Vol. 2 (1990), "Properties of Wrought Aluminum and Aluminum Alloys", alloy 4032: typical tensile
# properties of 4032-T6 at temperature after 10,000 h at that temperature; fatigue strength 110 MPa at 5e8 cycles
# (R.R. Moore rotating beam, room temperature).  degC -> MPa.
ASM_4032_UTS = [(24, 380.0), (100, 345.0), (150, 255.0), (205, 90.0), (260, 55.0), (315, 35.0), (370, 22.0)]
ASM_4032_FATIGUE_RT = 110.0
SOURCE = ("ASM Handbook Vol. 2, Properties and Selection: Nonferrous Alloys and Special-Purpose Materials (ASM "
          "International, 1990), wrought alloy 4032: typical tensile properties of 4032-T6 at elevated temperature "
          "(after 10,000 h at temperature) and fatigue strength 110 MPa at 5e8 cycles (R.R. Moore). Also tabulated in "
          "J.G. Kaufman, Properties of Aluminum Alloys: Tensile, Creep, and Fatigue Data at High and Low Temperatures "
          "(ASM International / The Aluminum Association, 1999).")


def uts(T_c):
    t, s = zip(*ASM_4032_UTS)
    return np.interp(T_c, t, s)          # held at the end values outside 24-370 degC (flagged in the output)


class CGSolver:
    """Drop-in for fea.spd_factor: Jacobi-preconditioned conjugate gradients."""
    def __init__(self, A):
        self.A = A.tocsr()
        self.M = sp.diags(1.0 / self.A.diagonal())

    def solve(self, b):
        t, it = time.time(), [0]
        x, info = cg(self.A, b, rtol=1e-11, maxiter=400000, M=self.M, callback=lambda xk: it.__setitem__(0, it[0] + 1))
        if info != 0:
            raise RuntimeError(f"CG did not converge (info {info}, {it[0]} iterations)")
        print(f"CG converged: {it[0]} iterations, {time.time() - t:.0f} s", flush=True)
        return x


def main():
    prod = json.load(open(os.path.join(F.OUT, "piston.json"), encoding="utf-8"))
    cap = {"elastic": [], "thermal": []}
    se, st = F.solve_elastic, F.solve_thermal
    F.solve_elastic = lambda *a, **k: cap["elastic"].append(se(*a, **k)) or cap["elastic"][-1]
    F.solve_thermal = lambda *a, **k: cap["thermal"].append(st(*a, **k)) or cap["thermal"][-1]
    ms = F.mesh_shape
    F.mesh_shape = lambda *a, **k: cap.setdefault("mesh", ms(*a, **k))
    F.spd_factor = CGSolver
    F.OUT = tempfile.mkdtemp(prefix="w16_piston_cg_")          # production files are not touched
    F.case_piston()
    rec = json.load(open(os.path.join(F.OUT, "piston.json"), encoding="utf-8"))
    m = cap["mesh"][0]
    T = cap["thermal"][0][0] - 273.15                          # nodal temperature, degC (main thermal case)
    s_g, s_gt = cap["elastic"]

    # ---- the re-solve must reproduce the production run
    pairs = [("gas_pressure", "vm_max_MPa"), ("gas_pressure", "vm_p999_MPa"), ("gas_pressure", "crown_deflection_mm"),
             ("gas_plus_thermal", "vm_max_MPa"), ("gas_plus_thermal", "vm_p999_MPa"),
             ("gas_plus_thermal", "top_land_radial_growth_max_mm"), ("thermal", "T_crown_mean_C")]
    repro = {f"{a}.{b}": dict(production=prod["results"][a][b], re_solve=rec["results"][a][b],
                              rel_diff=abs(rec["results"][a][b] / prod["results"][a][b] - 1.0)) for a, b in pairs}
    worst = max(v["rel_diff"] for v in repro.values())
    print("reproduction of the production run: worst relative difference", f"{worst:.2e}", flush=True)
    if worst > 1e-4 or rec["mesh"]["tets"] != prod["mesh"]["tets"]:
        raise SystemExit("re-solve does not reproduce fea/piston.json - stop")

    # ---- element data
    cen = m.p[:, m.t].mean(axis=1)                             # element centroids
    Tel = T[m.t].mean(axis=0)
    vg, vgt = s_g["vm"], s_gt["vm"]
    vol = np.abs(np.einsum("ij,ij->j", np.cross(m.p[:, m.t[1]] - m.p[:, m.t[0]], m.p[:, m.t[2]] - m.p[:, m.t[0]], axis=0),
                           m.p[:, m.t[3]] - m.p[:, m.t[0]])) / 6
    pis, *_, pinfo = F.CT.piston_solids()
    t = math.radians(P.crown_tilt_axis)
    nrm = np.array([0.0, -math.sin(t), math.cos(t)])
    depth = (P.comp_height + cen[1] * math.tan(t) - cen[2]) * math.cos(t)
    rho = np.hypot(cen[0], cen[1])
    pd, Rp, y0 = P.piston_valve_pocket_depth, P.valve_in_dia / 2 + 1.8, -P.valve_du_in
    dg0 = pinfo["gallery_depth"][0]

    def pocket_axis_dist(sx):
        v = cen - np.array([sx * 17.6, y0, P.comp_height + y0 * math.tan(t)]).reshape(3, 1)
        return np.linalg.norm(v - nrm.reshape(3, 1) * (nrm @ v), axis=0)

    sections = {}
    for sx in (-1, 1):
        sel = (pocket_axis_dist(sx) < Rp) & (depth > pd) & (depth < dg0) & (rho > P.gallery_r_in) & (rho < P.gallery_r_out)
        k = np.flatnonzero(sel)
        i_g, i_gt = k[np.argmax(vg[k])], k[np.argmax(vgt[k])]
        nodes = np.unique(m.t[:, k])
        sections[f"pocket x {'+' if sx > 0 else '-'}"] = dict(
            elements=int(len(k)), volume_mm3=float(vol[k].sum()), thickness_mm=float(dg0 - pd),
            T_min_C=float(T[nodes].min()), T_mean_C=float(T[nodes].mean()), T_max_C=float(T[nodes].max()),
            vm_gas_max_MPa=float(vg[i_g]), vm_gas_mean_MPa=float(np.average(vg[k], weights=vol[k])),
            vm_gas_max_at=cen[:, i_g].round(2).tolist(), T_at_vm_gas_max_C=float(Tel[i_g]),
            vm_gas_thermal_max_MPa=float(vgt[i_gt]), vm_gas_thermal_mean_MPa=float(np.average(vgt[k], weights=vol[k])),
            vm_gas_thermal_max_at=cen[:, i_gt].round(2).tolist(), T_at_vm_gas_thermal_max_C=float(Tel[i_gt]),
            fatigue=None, _k=k)

    # ---- temperature-dependent fatigue, per element
    sa = 0.5 * vg
    sf = ASM_4032_FATIGUE_RT * uts(Tel) / uts(20.0)
    n_plain = sf / np.maximum(sa, 1e-9)
    n_goodman = 1.0 / (sa / sf + sa / uts(Tel))              # sigma_m = sigma_a (0 -> max gas cycle)

    def summary(k, label):
        j, jg = k[np.argmin(n_plain[k])], k[np.argmin(n_goodman[k])]
        return dict(region=label, min_factor=float(n_plain[j]), at=cen[:, j].round(2).tolist(), T_C=float(Tel[j]),
                    sigma_a_MPa=float(sa[j]), sigma_f_T_MPa=float(sf[j]),
                    factor_0p1_percentile=float(np.quantile(n_plain[k], 0.001)) if len(k) > 1000 else None,
                    min_factor_goodman=float(n_goodman[jg]), goodman_at=cen[:, jg].round(2).tolist(), goodman_T_C=float(Tel[jg]))
    allk = np.arange(m.t.shape[1])
    g1 = pinfo["g1"]
    regions = dict(
        whole_piston=allk,
        crown_above_gallery=np.flatnonzero(depth < dg0),
        ring_belt_top_groove=np.flatnonzero((rho > P.bore / 2 - 6.0) & (np.abs(cen[2] - (g1 + 0.5 * P.ring1_h)) < 3.0)),
        pin_bosses=np.flatnonzero((np.hypot(cen[1], cen[2]) < P.pin_dia_piston / 2 + 8.0) & (np.abs(cen[0]) > 10.0)),
    )
    # slot-end corner: the gas-case peak element and its neighbourhood (3 mm)
    i_pk = int(np.argmax(vg))
    regions["slot_end_corner"] = np.flatnonzero(np.linalg.norm(cen - cen[:, i_pk:i_pk + 1], axis=0) < 3.0)
    fat = {name: summary(k, name) for name, k in regions.items()}
    for name, s in sections.items():
        s["fatigue"] = summary(s.pop("_k"), name)
    T_out = dict(elements_above_370C=int((Tel > 370).sum()), note="UTS held at 22 MPa above 370 degC (end of the data)")
    out = dict(date="2026-11-18", basis="fea/piston.json (D-042 piston), re-solved with CG on the same mesh", source=SOURCE,
               uts_table_degC_MPa=ASM_4032_UTS, fatigue_strength_rt_MPa=ASM_4032_FATIGUE_RT, reproduction=repro,
               section_under_long_valve_pockets=sections, fatigue=fat, temperature_range=T_out,
               method=("sigma_a = 0.5 x gas-case element von Mises; sigma_f(T) = 110 MPa x UTS(T) / UTS(RT), UTS of 4032-T6 "
                       "after 10,000 h at temperature (EST scaling); factor = sigma_f(T) / sigma_a; Goodman: 1 / (sigma_a / "
                       "sigma_f(T) + sigma_m / UTS(T)) with sigma_m = sigma_a. Element means (no extrapolation to the "
                       "surface); the slot-end corner is unradiused in the concept CAD, so its value is mesh-dependent."))
    path = os.path.join(F.ROOT, "08_SIMULATIONS", "fea", "piston_section_fatigue.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(dict(sections=sections, fatigue=fat), indent=1))
    print("written", path)


if __name__ == "__main__":
    main()
