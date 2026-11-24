"""Mesh convergence of the crank throw's two fillet features: the pin relief groove (D-048) and the main-journal fillets
(D-050).  2026-11-22, extended 2026-11-24.

Crank throw 3 is solved exactly as `fea.case_crank` (same solid, load, bearing-reaction supports, standard 1.0 mm mesh
along both pin-groove circles and both main-fillet circles, CG solver), then again with extra local refinement in two
balls (default radius 3 mm), one on the pin-groove peak and one on the main-fillet peak of the standard mesh, at
0.7 / 0.5 / 0.35 mm - both balls in the same mesh.  For each feature: converged (criterion of the user, 2026-11-23) when
its peak in its refined ball changes by less than 5 % between the two finest meshes; otherwise NOT CONVERGED and only
the series is reported (no value is picked).  The feature peak is the maximum over ball and feature zone (the zones of
`fea.crank_zones`), so a stress outside the feature cannot be taken for it; the zone peak outside the ball must stay below
the refined peak.  Decision rule of the user (D-050): if the converged main-fillet factor is below 1.5, the main fillets
switch to option (b) (R2.5 on the journal with narrower main shells).  Each run also gives the web and the ligament
stresses (web 9.5 mm, 7.0 mm remaining behind the 2.5 mm groove).  Each record carries the pin bore and the main fillet
radius it was solved with; earlier records (hollow pin, fixed journals, no main fillets) are kept under their own keys.

Grooves:
  semicircle - the project geometry (`cranktrain.undercut_ring`, D-048): true R2.5 arc tangent to the journal at the web
               face, 2.5 mm into the web, opening r 28-33 mm on the web face;
  cusp       - the D-047 form, kept here for the record only (`cusp_ring`): the fillet's material region mirrored into the
               web, so the groove ends in a zero-angle, crack-like tip and its peak depends on the mesh (223 / 296 MPa on
               two meshes of the same size - the reason for D-048).

Mesh.MeshSizeMin is set to the smallest requested size: with the `mesh_shape` default (h / 5 = 1.0 mm) gmsh clamps every
finer request to 1.0 mm (first run, 2026-11-22: the "0.7 / 0.5 / 0.35 mm" meshes were all 1.0 mm meshes).  Each run
records the tets in each ball and their mean equivalent edge length as proof that the refinement took effect.
Memory: the solver builds the stiffness and the stresses in blocks of elements (`fea.ELASTIC_CHUNK`, D-050), so the
~40 kB per tet of the one-block path (235k tets -> ~9.5 GB on 2026-11-23) does not apply; see D-050 for the measured
figure.  Run of 2026-11-23 (hollow pin, one ball): 21 / 22 / 24 / 56 min for the 1.0 / 0.7 / 0.5 / 0.35 mm solves.

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
from build123d import Axis, Plane, revolve  # noqa: E402
from w16.params import P  # noqa: E402
from w16.cad import cranktrain as CT  # noqa: E402
from w16.cad.common import poly  # noqa: E402
from w16.sim import fea as F  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_groove_convergence.json")
CRITERION = 0.05
MAIN_FACTOR_MIN = 1.5          # D-050: below this converged main-fillet factor the main fillets switch to option (b)
FEATURES = ("pin_groove", "main_fillet")


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
        return CT.fe_throw(3, (cw[3][0], cw[3][1]), pin_fillet="undercut")
    finally:
        CT.undercut_ring = orig


def solve(thr, balls=None):
    """One solve.  balls: {feature: ((x, y, z), radius, size)} extra refinement, or None for the standard mesh."""
    G = F.crank_geometry(3)
    ref = F.crank_refine(G) + list((balls or {}).values())
    h_min = min(r[2] for r in ref)
    t0 = time.time()
    m, st = F.mesh_shape(thr, 5.0, "crank_conv", h_min=h_min, refine=ref)
    s, info = F.crank_solve(m, G, F.results()["dynamics"]["F_design_gas"], F.mat("steel_qt"))
    vm = np.asarray(s["vm"])
    Z, cen = F.crank_zones(m, G)
    a, b, c, d = (m.p[:, m.t[j]] for j in range(4))
    vol = np.abs(np.einsum("ij,ij->j", np.cross(b - a, c - a, axis=0), d - a)) / 6
    edge = (6 * math.sqrt(2) * vol) ** (1 / 3)
    out = dict(tets=st["tets"], gamma_min=st["quality_gamma_min"], mesh_size_min_mm=h_min, supports=info,
               web_vm_max_MPa=float(vm[Z["web"]].max()), web_vm_p999_MPa=float(np.percentile(vm[Z["web"]], 99.9)),
               ligament_vm_max_MPa=float(vm[Z["ligament"]].max()), ligament_vm_p999_MPa=float(np.percentile(vm[Z["ligament"]], 99.9)),
               ligament_vm_max_location=cen[:, int(np.argmax(np.where(Z["ligament"], vm, -1)))].round(2).tolist(), features={})
    for ft in FEATURES:
        z = Z[ft]
        i = int(np.argmax(np.where(z, vm, -1)))
        r = dict(zone_vm_max_MPa=float(vm[i]), at=cen[:, i].round(3).tolist(), zone_vm_p999_MPa=float(np.percentile(vm[z], 99.9)))
        if balls and ft in balls:
            ctr, rad, _ = balls[ft]
            ball = np.sqrt(((cen - np.reshape(ctr, (3, 1))) ** 2).sum(0)) < rad
            bz = ball & z
            r.update(ball_vm_max_MPa=float(vm[bz].max()), ball_at=cen[:, int(np.argmax(np.where(bz, vm, -1)))].round(3).tolist(),
                     ball_tets=int(ball.sum()), ball_edge_mean_mm=float(edge[ball].mean()),
                     zone_vm_max_outside_ball_MPa=float(vm[z & ~ball].max()))
        out["features"][ft] = r
    out["minutes"] = (time.time() - t0) / 60
    return out


def verdict(rows):
    """5 % criterion per feature on its refined-ball peak of the two finest meshes; D-050 switch rule on the main fillet."""
    fat = F.mat("steel_qt")["fatigue"]
    out = {}
    for ft in FEATURES:
        ref = sorted([r for r in rows if "ball_vm_max_MPa" in r["features"][ft]], key=lambda r: r["local_size_mm"])
        series = [dict(local_size_mm=r["local_size_mm"], peak_MPa=r["features"][ft].get("ball_vm_max_MPa", r["features"][ft]["zone_vm_max_MPa"]))
                  for r in rows]
        if len(ref) < 2:
            out[ft] = dict(converged=False, reason="fewer than two refined meshes", series=series)
            continue
        f, s = ref[0]["features"][ft], ref[1]["features"][ft]
        ch = abs(f["ball_vm_max_MPa"] - s["ball_vm_max_MPa"]) / f["ball_vm_max_MPa"]
        v = dict(criterion=f"refined-ball peak changes < {CRITERION:.0%} between the two finest meshes",
                 two_finest_mm=[ref[1]["local_size_mm"], ref[0]["local_size_mm"]], peaks_MPa=[s["ball_vm_max_MPa"], f["ball_vm_max_MPa"]],
                 change_pct=100 * ch, converged=bool(ch < CRITERION), series=series)
        if f["zone_vm_max_outside_ball_MPa"] > f["ball_vm_max_MPa"]:
            v["converged"] = False
            v["reason"] = (f"the zone peak outside the refined ball ({f['zone_vm_max_outside_ball_MPa']:.1f} MPa) exceeds the refined "
                           f"peak - re-centre the ball")
        if v["converged"]:
            v["converged_peak_MPa"] = f["ball_vm_max_MPa"]
            v["factor_on_converged_peak"] = fat / (0.5 * f["ball_vm_max_MPa"])
        out[ft] = v
    mf = out["main_fillet"]
    out["main_fillet_decision"] = (
        "pending (not converged - no factor)" if not mf.get("converged") else
        f"switch to option (b): converged main-fillet factor {mf['factor_on_converged_peak']:.2f} < {MAIN_FACTOR_MIN}"
        if mf["factor_on_converged_peak"] < MAIN_FACTOR_MIN else
        f"keep option (c): converged main-fillet factor {mf['factor_on_converged_peak']:.2f} >= {MAIN_FACTOR_MIN}")
    if rows:
        out["web_vm_max_MPa"], out["ligament_vm_max_MPa"] = rows[-1]["web_vm_max_MPa"], rows[-1]["ligament_vm_max_MPa"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groove", nargs="+", default=["semicircle"], choices=["semicircle", "cusp"])
    ap.add_argument("--sizes", nargs="+", type=float, default=[0.7, 0.5, 0.35])
    ap.add_argument("--ball", type=float, default=3.0, help="radius of the local refinement balls, mm")
    a = ap.parse_args()
    F.OUT = tempfile.mkdtemp(prefix="w16_crank_conv_")
    res = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    res["note"] = __doc__.split("\n\n")[1].replace("\n", " ")
    for g in a.groove:
        thr = throw(g)
        rec = dict(volume_mm3=float(thr.volume), pin_bore_mm=P.pin_bore, main_fillet_r_mm=P.main_fillet_r,
                   main_land_mm=P.main_shell_width - 2 * P.main_shell_chamfer, supports="bearing reactions on the main lands (D-050)",
                   web_thk_mm=P.web_thk, groove_depth_mm=F.GROOVE_DEPTH, web_remaining_at_groove_mm=P.web_thk - F.GROOVE_DEPTH,
                   ball_radius_mm=a.ball, date=time.strftime("%Y-%m-%d"), runs=[])
        res[g] = rec

        def save():
            rec["verdict"] = verdict(rec["runs"])
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1)

        base = solve(thr)
        base["local_size_mm"] = F.CRANK_FILLET_MESH
        rec["runs"].append(base)
        save()
        fb = base["features"]
        print(f"{g}: standard 1.0 mm -> pin groove {fb['pin_groove']['zone_vm_max_MPa']:.1f} MPa at {fb['pin_groove']['at']}, "
              f"main fillet {fb['main_fillet']['zone_vm_max_MPa']:.1f} MPa at {fb['main_fillet']['at']}, web {base['web_vm_max_MPa']:.1f}, "
              f"ligament {base['ligament_vm_max_MPa']:.1f}, {base['tets']} tets, {base['minutes']:.0f} min", flush=True)
        for h in a.sizes:
            balls = {ft: (tuple(fb[ft]["at"]), a.ball, h) for ft in FEATURES}
            r = solve(thr, balls)
            r["local_size_mm"] = h
            rec["runs"].append(r)
            save()
            txt = "; ".join(f"{ft.replace('_', ' ')} {r['features'][ft]['ball_vm_max_MPa']:.1f} MPa ({r['features'][ft]['ball_tets']} tets in the ball, "
                            f"edge {r['features'][ft]['ball_edge_mean_mm']:.2f} mm; outside {r['features'][ft]['zone_vm_max_outside_ball_MPa']:.1f})"
                            for ft in FEATURES)
            print(f"{g}: local {h} mm -> {txt}; web {r['web_vm_max_MPa']:.1f}, ligament {r['ligament_vm_max_MPa']:.1f}, {r['tets']} tets, "
                  f"gamma min {r['gamma_min']:.3f}, {r['minutes']:.0f} min", flush=True)
        v = rec["verdict"]
        for ft in FEATURES:
            x = v[ft]
            if x.get("converged"):
                print(f"{g} {ft}: CONVERGED - {x['change_pct']:.2f} % between {x['two_finest_mm']} mm; peak {x['converged_peak_MPa']:.1f} MPa, "
                      f"factor {x['factor_on_converged_peak']:.2f}", flush=True)
            else:
                print(f"{g} {ft}: NOT CONVERGED - {x.get('reason', '%.2f %% between the two finest meshes' % x.get('change_pct', float('nan')))}; "
                      f"series {[(q['local_size_mm'], round(q['peak_MPa'], 1)) for q in x.get('series', [])]}", flush=True)
        print(f"{g}: main fillets - {v['main_fillet_decision']}", flush=True)
    print("written", OUT)


if __name__ == "__main__":
    main()
