"""Mesh convergence of the crank pin-groove peak (D-048 semicircular relief groove), 2026-11-22.

Crank throw 3 is solved exactly as `fea.case_crank` (same load, supports, standard 1.0 mm fillet-circle mesh, CG solver),
then again with extra local refinement in a ball (default radius 3 mm) centred on the fillet-zone peak of the standard
mesh, at 0.7 / 0.5 / 0.35 mm.  Converged (criterion of the user, 2026-11-23): the peak in the refined ball changes by less
than 5 % between the two finest meshes; otherwise the result is NOT CONVERGED and only the series is reported (no value
is picked).  Each run also gives the web stress (as case_crank) and the stress in the ligament behind the groove (web
9.5 mm, 7.0 mm remaining behind the 2.5 mm groove).  Each record carries the pin bore it was solved with (D-049: solid pin
from 2026-11-24; the D-048 run on the hollow pin is kept as `semicircle_hollow_pin`).

Grooves:
  semicircle - the project geometry (`cranktrain.undercut_ring`, D-048): true R2.5 arc tangent to the journal at the web
               face, 2.5 mm into the web, opening r 28-33 mm on the web face;
  cusp       - the D-047 form, kept here for the record only (`cusp_ring`): the fillet's material region mirrored into the
               web, so the groove ends in a zero-angle, crack-like tip and its peak depends on the mesh (223 / 296 MPa on
               two meshes of the same size - the reason for D-048).

Mesh.MeshSizeMin is set to the smallest requested size: with the `mesh_shape` default (h / 5 = 1.0 mm) gmsh clamps every
finer request to 1.0 mm (first run, 2026-11-22: the "0.7 / 0.5 / 0.35 mm" meshes were all 1.0 mm meshes).  Each run
records the tets in the ball and their mean equivalent edge length as proof that the refinement took effect.
Memory: about 40 kB per tet at the solve peak (235k tets at 0.35 mm in a 3 mm ball -> about 9.5 GB).  Run of 2026-11-23
(hollow pin): 21 / 22 / 24 / 56 min for the 1.0 / 0.7 / 0.5 / 0.35 mm solves.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\crank_groove_convergence.py [--groove semicircle] [--sizes 0.7 0.5 0.35] [--ball 3.0]

Output: 08_SIMULATIONS/fea/crank_groove_convergence.json (written after every solve).  Production files are not touched
(FE pictures go to a temp dir).
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build123d import Align, Axis, Cylinder, Plane, Pos, Rot, revolve  # noqa: E402
from w16.params import P  # noqa: E402
from w16 import layout as L  # noqa: E402
from w16.cad import cranktrain as CT  # noqa: E402
from w16.cad.common import poly  # noqa: E402
from w16.sim import fea as F  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_groove_convergence.json")
CRITERION = 0.05


def cusp_ring(r, rf):
    """The D-047 groove (superseded by D-048), for the record: R rf fillet profile mirrored into the web, faceted."""
    pts = [(0.3, r), (-rf, r)]
    for a in np.linspace(0, 90, 7)[1:]:
        pts.append((-rf + rf * math.sin(math.radians(a)), r + rf - rf * math.cos(math.radians(a))))
    pts.append((0.3, r + rf))
    return revolve(Plane.XY * poly(pts), axis=Axis.X)


def throw(groove):
    from w16.cad.assembly import _cw
    cw, _ = _cw()
    orig = CT.undercut_ring
    if groove == "cusp":
        CT.undercut_ring = cusp_ring
    try:
        thr = CT.throw_solid(3, (cw[3][0], cw[3][1]), pin_fillet="undercut")
    finally:
        CT.undercut_ring = orig
    hm = P.main_width / 2
    for j in (3, 4):
        thr = thr + Pos(L.main_x(j) - hm, 0, 0) * Rot(Y=90) * Cylinder(P.main_dia / 2, P.main_width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return thr


def solve(thr, extra=None):
    k = 3
    psi = math.radians(L.PIN_PHASE[k])
    pc = np.array([L.pin_x(k), P.throw * math.sin(psi), P.throw * math.cos(psi)])
    xa, xb = pc[0] - P.pin_width / 2, pc[0] + P.pin_width / 2
    ref = [((xa, pc[1], pc[2]), 34, 2.4), ((xb, pc[1], pc[2]), 34, 2.4)]
    rf0 = P.pin_dia / 2 + 1.25
    e1, up = np.array([0.0, math.cos(psi), -math.sin(psi)]), np.array([0.0, math.sin(psi), math.cos(psi)])
    for xf in (xa, xb):
        for a in np.linspace(0, 2 * math.pi, 40, endpoint=False):
            ref.append((tuple(np.array([xf, pc[1], pc[2]]) + rf0 * (math.cos(a) * e1 + math.sin(a) * up)), 4.5, F.CRANK_FILLET_MESH))
    if extra:
        ref.append(extra)
    t0 = time.time()
    h_min = min(r[2] for r in ref)
    m, st = F.mesh_shape(thr, 5.0, "crank_conv", h_min=h_min, refine=ref)
    hm = P.main_width / 2
    mains = F.facets(m, lambda x: (np.hypot(x[1], x[2]) < P.main_dia / 2 + 0.05) & ((x[0] < L.main_x(k) + hm + 0.01) | (x[0] > L.main_x(k + 1) - hm - 0.01)))
    pin = F.facets(m, lambda x: (np.hypot(x[1] - pc[1], x[2] - pc[2]) < P.pin_dia / 2 + 0.05) & (np.abs(x[0] - pc[0]) < P.pin_width / 2 - 2.6))
    Fz = F.results()["dynamics"]["F_design_gas"]
    fn, _ = F.cos_load(pc, (1, 0, 0), -np.array([0, math.sin(psi), math.cos(psi)]), Fz, m, pin)
    s = F.solve_elastic(m, F.mat("steel_qt"), mains, tractions=[(pin, fn)], iterative=True)
    vm = np.asarray(s["vm"])
    cen = m.p[:, m.t].mean(axis=1)
    rp = np.hypot(cen[1] - pc[1], cen[2] - pc[2])
    gd = F.GROOVE_DEPTH
    # zones as in fea.case_crank
    fz = (np.hypot(cen[0] - xa, rp - rf0) < 5.0) | (np.hypot(cen[0] - xb, rp - rf0) < 5.0)
    web = (((cen[0] < xa) & (cen[0] > xa - P.web_thk)) | ((cen[0] > xb) & (cen[0] < xb + P.web_thk))) & ~fz & (np.hypot(cen[1], cen[2]) > P.main_dia / 2 + 6.0)
    lig = ((((cen[0] < xa - gd) & (cen[0] > xa - P.web_thk)) | ((cen[0] > xb + gd) & (cen[0] < xb + P.web_thk)))
           & (rp > P.pin_dia / 2) & (rp < P.pin_dia / 2 + 2 * gd) & (np.hypot(cen[1], cen[2]) > P.main_dia / 2 + 6.0))
    i = int(np.argmax(np.where(fz, vm, -1)))
    out = dict(tets=st["tets"], gamma_min=st["quality_gamma_min"], mesh_size_min_mm=h_min,
               fillet_vm_max_MPa=float(vm[i]), at=cen[:, i].round(3).tolist(), fillet_vm_p999_MPa=float(np.percentile(vm[fz], 99.9)),
               r_from_pin_axis_mm=float(rp[i]), x_from_web_face_mm=float(min(abs(cen[0, i] - xa), abs(cen[0, i] - xb))),
               web_vm_max_MPa=float(vm[web].max()), web_vm_p999_MPa=float(np.percentile(vm[web], 99.9)),
               ligament_vm_max_MPa=float(vm[lig].max()), ligament_vm_p999_MPa=float(np.percentile(vm[lig], 99.9)),
               ligament_vm_max_location=cen[:, int(np.argmax(np.where(lig, vm, -1)))].round(2).tolist(),
               minutes=(time.time() - t0) / 60)
    if extra:
        ball = np.sqrt(((cen - np.reshape(extra[0], (3, 1))) ** 2).sum(0)) < extra[1]
        a, b, c, d = (m.p[:, m.t[j]] for j in range(4))
        vol = np.abs(np.einsum("ij,ij->j", np.cross(b - a, c - a, axis=0), d - a)) / 6
        out["ball_vm_max_MPa"] = float(vm[ball].max())
        out["ball_tets"] = int(ball.sum())
        out["ball_edge_mean_mm"] = float(np.mean((6 * math.sqrt(2) * vol[ball]) ** (1 / 3)))
        out["fillet_vm_max_outside_ball_MPa"] = float(vm[fz & ~ball].max())
    return out


def verdict(rows):
    """5 % criterion on the refined-ball peak of the two finest meshes."""
    fat = F.mat("steel_qt")["fatigue"]
    ref = sorted([r for r in rows if "ball_vm_max_MPa" in r], key=lambda r: r["local_size_mm"])
    if len(ref) < 2:
        return dict(converged=False, reason="fewer than two refined meshes")
    f, s = ref[0], ref[1]
    ch = abs(f["ball_vm_max_MPa"] - s["ball_vm_max_MPa"]) / f["ball_vm_max_MPa"]
    v = dict(criterion=f"refined-ball peak changes < {CRITERION:.0%} between the two finest meshes",
             two_finest_mm=[s["local_size_mm"], f["local_size_mm"]], peaks_MPa=[s["ball_vm_max_MPa"], f["ball_vm_max_MPa"]],
             change_pct=100 * ch, converged=bool(ch < CRITERION),
             series=[dict(local_size_mm=r["local_size_mm"], peak_MPa=r.get("ball_vm_max_MPa", r["fillet_vm_max_MPa"])) for r in rows])
    if f["fillet_vm_max_outside_ball_MPa"] > f["ball_vm_max_MPa"]:
        v["converged"] = False
        v["reason"] = (f"the fillet-zone peak outside the refined ball ({f['fillet_vm_max_outside_ball_MPa']:.1f} MPa, 1.0 mm mesh) "
                       f"exceeds the refined peak - re-centre the ball")
    if v["converged"]:
        v["converged_peak_MPa"] = f["ball_vm_max_MPa"]
        v["factor_on_converged_peak"] = fat / (0.5 * f["ball_vm_max_MPa"])
        v["web_vm_max_MPa"], v["ligament_vm_max_MPa"] = f["web_vm_max_MPa"], f["ligament_vm_max_MPa"]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groove", nargs="+", default=["semicircle"], choices=["semicircle", "cusp"])
    ap.add_argument("--sizes", nargs="+", type=float, default=[0.7, 0.5, 0.35])
    ap.add_argument("--ball", type=float, default=3.0, help="radius of the local refinement ball, mm")
    a = ap.parse_args()
    F.OUT = tempfile.mkdtemp(prefix="w16_crank_conv_")
    res = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    res["note"] = __doc__.split("\n\n")[1].replace("\n", " ")
    for g in a.groove:
        thr = throw(g)
        rec = dict(volume_mm3=float(thr.volume), pin_bore_mm=P.pin_bore, web_thk_mm=P.web_thk, groove_depth_mm=F.GROOVE_DEPTH,
                   web_remaining_at_groove_mm=P.web_thk - F.GROOVE_DEPTH, ball_radius_mm=a.ball,
                   date=time.strftime("%Y-%m-%d"), runs=[])
        res[g] = rec

        def save():
            rec["verdict"] = verdict(rec["runs"])
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1)

        base = solve(thr)
        base["local_size_mm"] = F.CRANK_FILLET_MESH
        rec["runs"].append(base)
        save()
        print(f"{g}: standard 1.0 mm -> peak {base['fillet_vm_max_MPa']:.1f} MPa at {base['at']} (r {base['r_from_pin_axis_mm']:.2f}, "
              f"{base['x_from_web_face_mm']:.2f} mm from the web face), web {base['web_vm_max_MPa']:.1f}, ligament {base['ligament_vm_max_MPa']:.1f}, "
              f"{base['tets']} tets, {base['minutes']:.0f} min", flush=True)
        for h in a.sizes:
            r = solve(thr, extra=(tuple(base["at"]), a.ball, h))
            r["local_size_mm"] = h
            rec["runs"].append(r)
            save()
            print(f"{g}: local {h} mm -> ball peak {r['ball_vm_max_MPa']:.1f} MPa ({r['ball_tets']} tets in the ball, mean edge "
                  f"{r['ball_edge_mean_mm']:.2f} mm), outside the ball {r['fillet_vm_max_outside_ball_MPa']:.1f}, web {r['web_vm_max_MPa']:.1f}, "
                  f"ligament {r['ligament_vm_max_MPa']:.1f}, {r['tets']} tets, gamma min {r['gamma_min']:.3f}, {r['minutes']:.0f} min", flush=True)
        v = rec["verdict"]
        if v.get("converged"):
            print(f"{g}: CONVERGED - {v['change_pct']:.1f} % between {v['two_finest_mm']} mm; peak {v['converged_peak_MPa']:.1f} MPa, "
                  f"factor {v['factor_on_converged_peak']:.2f}", flush=True)
        else:
            print(f"{g}: NOT CONVERGED - {v.get('reason', '%.1f %% between the two finest meshes' % v.get('change_pct', float('nan')))}; "
                  f"series {[(s['local_size_mm'], round(s['peak_MPa'], 1)) for s in v.get('series', [])]}", flush=True)
    print("written", OUT)


if __name__ == "__main__":
    main()
