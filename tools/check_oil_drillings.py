"""Check of the crankshaft oil drillings (D-049, 2026-11-24).

1. Big-end load polar of every rod (dynamics model, full load at 2,000 / 3,750 / 6,700 rpm) in the crank-fixed pin frame
   (phi 0 = outer side of the pin, away from the crank axis, measured towards psi + 90 deg; CAD point _yz(psi + phi)):
   load index per surface angle = max over the cycle of |F| cos(phi - phi_F) (cos > 0 only); the load at the outlet angle
   `cranktrain.OIL_PHI` as a fraction of the peak, and the least-loaded angle.
2. Walls of every drilling on its throw (pin + webs + counterweights + the two mains, as built), exact distances
   (BRepExtrema) from the drilling cylinder to each face of the undrilled throw, by face type: relief groove (torus), web
   faces, web contour, pin and main surfaces.  Only the pin surface (outlet) and the main surface (inlet) may be cut.
3. Exit angles (drilling axis vs surface normal), opening sizes with the chamfer, opening to bearing-shell edges.
4. Drill access from the pin side: clearance of the drill axis beyond the outlet to the opposite web's contour and to
   the counterweight radius.
5. The two drillings that share a main journal (mains 2-8): distance between them and angle between their inlets.
   The mains are not cross-drilled (D-049): a cross-drilling through every inlet would come within 0.08 mm of the
   neighbouring drilling on mains 2, 4, 5, 6 and 8.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\check_oil_drillings.py

Output: 08_SIMULATIONS/analytical/oil_drillings.json.  The crank FE has no oil drillings (stress at the drilling exits
is not assessed - D-049 limitation).
"""
from __future__ import annotations
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build123d import Align, Cylinder, Pos, Rot  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Surface  # noqa: E402
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_SurfaceOfRevolution, GeomAbs_Torus  # noqa: E402
from w16.params import P  # noqa: E402
from w16 import layout as L  # noqa: E402
from w16.analysis import dynamics as D  # noqa: E402
from w16.cad import cranktrain as CT  # noqa: E402
from w16.cad.assembly import _cw  # noqa: E402
from w16.cad.common import cyl_between  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "oil_drillings.json")
CMIN = (Align.CENTER, Align.CENTER, Align.MIN)


def polar(rpms=(2000.0, 3750.0, 6700.0)):
    phis = np.arange(0, 360, 1.0)
    _, m_rod_rot = D.masses()
    rows, worst = {}, np.zeros_like(phis)
    for rpm in rpms:
        R = D.run(rpm)
        om = rpm * math.pi / 30
        for c in L.CYLS:
            k = c.pin
            er, et = L.vec(L.PIN_PHASE[k] - D.AL), L.vec(L.PIN_PHASE[k] - D.AL + 90.0)
            be = R["cf"][c.no]["F_pin"] + m_rod_rot * P.throw * 1e-3 * om ** 2 * er        # force of rod c on the pin (y, z), N
            fr, ft = (be * er).sum(1), (be * et).sum(1)
            phn = np.degrees(np.arctan2(-ft, -fr)) % 360                                  # shell pressure centre on the pin
            mag = np.hypot(fr, ft)
            Lmax = (mag[None, :] * np.clip(np.cos(np.radians(phis[:, None] - phn[None, :])), 0, None)).max(1)
            rel = Lmax / mag.max()
            worst = np.maximum(worst, rel)
            i = int(np.argmin(Lmax))
            rows.setdefault(str(c.no), {})[str(int(rpm))] = dict(
                peak_kN=float(mag.max()) / 1e3, peak_at_phi=float(phn[int(np.argmax(mag))]), least_loaded_phi=float(phis[i]),
                load_at_outlet_pct_of_peak=float(100 * np.interp(CT.OIL_PHI, phis, rel)))
    j = int(np.argmin(worst))
    return dict(rods=rows, over_all_rods_and_speeds=dict(least_loaded_phi=float(phis[j]), its_load_pct_of_peak=float(100 * worst[j]),
                                                          outlet_phi=CT.OIL_PHI, outlet_load_pct_of_peak=float(100 * np.interp(CT.OIL_PHI, phis, worst))))


def dist(a, b):
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return float(d.Value())


def classify(f, k):
    s = BRepAdaptor_Surface(f.wrapped)
    t = s.GetType()
    psi = math.radians(L.PIN_PHASE[k])
    C = P.throw * np.array([math.sin(psi), math.cos(psi)])
    if t == GeomAbs_Torus:                       # pin relief groove (axis through the pin centre) or main fillet (crank axis)
        loc = s.Torus().Location()
        return "main fillet" if math.hypot(loc.Y(), loc.Z()) < 1e-3 else "relief groove"
    if t == GeomAbs_SurfaceOfRevolution:
        return "relief groove"
    if t == GeomAbs_Cylinder:
        cy = s.Cylinder()
        if abs(abs(cy.Axis().Direction().X()) - 1) < 1e-6:
            yz = np.array([cy.Location().Y(), cy.Location().Z()])
            if abs(cy.Radius() - P.pin_dia / 2) < 1e-3 and np.linalg.norm(yz - C) < 1e-3:
                return "pin surface"
            if abs(cy.Radius() - P.main_dia / 2) < 1e-3 and np.linalg.norm(yz) < 1e-3:
                return "main surface"
        return "web contour"
    if t == GeomAbs_Plane:
        return "web face" if abs(abs(s.Plane().Axis().Direction().X()) - 1) < 1e-6 else "web contour"
    return f"other ({t})"


def walls(cw):
    hm = P.main_width / 2
    out = []
    for k in range(1, 9):
        thr = CT.fe_throw(k, (cw[k][0], cw[k][1]))          # with the D-050 main fillets at both webs
        faces = thr.faces()
        for d in [d for d in CT.oil_drillings() if d["pin"] == k]:
            H = cyl_between(d["I"] - 2.0 * d["e"], d["O"] + 2.0 * d["e"], CT.OIL_R)
            bb = H.bounding_box()
            cat, cut = {}, set()
            for f in faces:
                fb = f.bounding_box()
                if fb.min.X > bb.max.X + 20 or fb.max.X < bb.min.X - 20:
                    continue
                v, c = dist(f, H), classify(f, k)
                if v < 1e-6:
                    cut.add(c)
                else:
                    cat[c] = min(cat.get(c, 1e9), v)
            # web faces: towards the main (main / web corner, sharp in the CAD) or towards the pin (outside the groove)
            x_main_face = L.main_x(d["main"]) + (hm if d["main"] == k else -hm)
            wf = {}
            for f in faces:
                s = BRepAdaptor_Surface(f.wrapped)
                if s.GetType() != GeomAbs_Plane or abs(abs(s.Plane().Axis().Direction().X()) - 1) > 1e-6:
                    continue
                x0 = s.Plane().Location().X()
                if abs(x0 - x_main_face) < 1e-6:
                    key = "web face at the main journal (main / web corner)"
                elif abs(x0 - (L.pin_x(k) + (-1 if d["main"] == k else 1) * P.pin_width / 2)) < 1e-6:
                    key = "web face at the pin (outside the groove opening)"
                elif abs(abs(x0 - L.main_x(d["main"])) - hm) < 1e-6:
                    key = "main / web corner at the other end of the main"
                else:
                    continue
                wf[key] = min(wf.get(key, 1e9), dist(f, H))
            rec = dict(cyl=d["cyl"], pin=k, main=d["main"], inlet_angle_deg=d["theta"], length_mm=d["length"],
                       axis_to_outlet_normal_deg=d["a_out"], axis_to_inlet_normal_deg=d["a_in"], faces_cut=sorted(cut),
                       wall_mm={c: v for c, v in sorted(cat.items()) if c not in ("pin surface", "main surface")}, wall_web_faces_mm=wf)
            out.append(rec)
            print(f"pin {k} cyl {d['cyl']:2d} main {d['main']}: cut {sorted(cut)}, walls "
                  f"{ {c: round(v, 2) for c, v in rec['wall_mm'].items()} } { {c[:22]: round(v, 2) for c, v in wf.items()} }", flush=True)
    return out


def openings():
    d = CT.oil_drillings()[0]
    r_out = CT.OIL_R / math.cos(math.radians(d["a_out"])) + CT.OIL_CHAMFER
    r_in = CT.OIL_R / math.cos(math.radians(d["a_in"])) + CT.OIL_CHAMFER
    shell_be = (P.rod_be_width - 1.5) / 2                 # big-end shell half-width (rod_solids: shell_w = w - 1.5)
    shell_main = P.main_shell_width / 2 - P.main_shell_chamfer   # main shell land half-width (D-050 option (b): 12.2 mm, unchamfered)
    return dict(outlet_radius_with_chamfer_mm=r_out, inlet_radius_with_chamfer_mm=r_in,
                outlet_to_big_end_shell_edge_mm=shell_be - r_out, outlet_to_pin_end_mm=P.pin_width / 2 - P.bank_offset / 2 - r_out,
                inlet_to_main_shell_land_edge_mm=shell_main - r_in, main_shell_groove_width_mm=4.0,
                inlet_to_main_fillet_tangent_mm=P.main_width / 2 - P.main_fillet_r - r_in)


def access(cw):
    """Drill axis beyond the outlet, up to the far face of the opposite web: clearance to the opposite web's contour (hull of
    R41 / R35) and to the counterweight radius (sector ignored = conservative)."""
    out = []
    for d in CT.oil_drillings():
        k = d["pin"]
        psi = math.radians(L.PIN_PHASE[k])
        C = P.throw * np.array([math.sin(psi), math.cos(psi)])
        sg = 1.0 if d["main"] == k else -1.0
        x0 = L.pin_x(k) + sg * P.pin_width / 2
        x1 = x0 + sg * P.web_thk
        t0 = (x0 - d["O"][0]) / d["e"][0]
        t1 = (x1 - d["O"][0]) / d["e"][0]
        ts = np.linspace(t0, t1, 200)
        q = d["O"][None, 1:] + ts[:, None] * d["e"][None, 1:]
        r = np.linalg.norm(q, axis=1)
        rp = np.linalg.norm(q - C, axis=1)
        out.append(dict(cyl=d["cyl"], to_web_boss_mm=float(min(np.min(r) - CT.R_MAIN_WEB, np.min(rp) - CT.R_PIN_WEB)) - CT.OIL_R,
                        to_cw_radius_mm=float(np.min(r) - P.cw_radius) - CT.OIL_R))
    return out


def shared_mains():
    D_ = CT.oil_drillings()
    cyl = lambda d: cyl_between(d["I"] - 2.0 * d["e"], d["O"] + 2.0 * d["e"], CT.OIL_R)
    r_in = CT.OIL_R / math.cos(math.radians(D_[0]["a_in"])) + CT.OIL_CHAMFER
    out = []
    for j in range(1, P.n_main + 1):
        ds = [d for d in D_ if d["main"] == j]
        if len(ds) < 2:
            continue
        a, b = ds
        sep = abs((a["theta"] - b["theta"] + 180) % 360 - 180)
        out.append(dict(main=j, cyls=[a["cyl"], b["cyl"]], inlet_angles_deg=[a["theta"], b["theta"]], inlet_separation_deg=sep,
                        drilling_to_drilling_mm=dist(cyl(a), cyl(b)),
                        inlet_openings_arc_gap_mm=P.main_dia / 2 * math.radians(sep) - 2 * r_in))
    return out


def main():
    t0 = time.time()
    cw, rep = _cw()
    res = dict(note=__doc__.split("\n\n")[0].replace("\n", " "), date=time.strftime("%Y-%m-%d"),
               geometry=dict(diameter_mm=2 * CT.OIL_R, outlet_phi_deg=CT.OIL_PHI, inlet_angle_from_pin_deg=CT.OIL_THETA_REL,
                             chamfer_mm=CT.OIL_CHAMFER, pin_bore_mm=P.pin_bore,
                             layout="one drilling per rod: main surface (x = main centre, under the 180-deg groove of the upper "
                                    "main shell) -> pin surface (x = rod centre); drilled from the pin side; mains not cross-drilled"))
    res["load_polar"] = polar()
    o = res["load_polar"]["over_all_rods_and_speeds"]
    print(f"polar: outlet {o['outlet_phi']:.0f} deg at {o['outlet_load_pct_of_peak']:.1f} % of the peak; least-loaded {o['least_loaded_phi']:.0f} deg "
          f"({o['its_load_pct_of_peak']:.1f} %)", flush=True)
    res["drillings"] = walls(cw)
    res["openings"] = openings()
    res["drill_access"] = access(cw)
    res["shared_mains"] = shared_mains()
    W = res["drillings"]
    res["summary"] = dict(
        drillings=len(W), only_pin_and_main_surfaces_cut=all(set(w["faces_cut"]) == {"pin surface", "main surface"} for w in W),
        min_wall_to_relief_groove_mm=min(w["wall_mm"].get("relief groove", 1e9) for w in W),
        min_wall_to_main_fillet_mm=min(w["wall_mm"].get("main fillet", 1e9) for w in W),
        min_wall_to_web_contour_mm=min(w["wall_mm"].get("web contour", 1e9) for w in W),
        min_wall_web_faces_mm={k: min(w["wall_web_faces_mm"].get(k, 1e9) for w in W) for k in W[0]["wall_web_faces_mm"]},
        axis_to_outlet_normal_deg=max(w["axis_to_outlet_normal_deg"] for w in W), axis_to_inlet_normal_deg=max(w["axis_to_inlet_normal_deg"] for w in W),
        drill_access_min_to_web_boss_mm=min(a["to_web_boss_mm"] for a in res["drill_access"]),
        drill_access_min_to_cw_radius_mm=min(a["to_cw_radius_mm"] for a in res["drill_access"]),
        shared_mains_min_drilling_to_drilling_mm=min(s["drilling_to_drilling_mm"] for s in res["shared_mains"]),
        shared_mains_min_inlet_separation_deg=min(s["inlet_separation_deg"] for s in res["shared_mains"]),
        minutes=(time.time() - t0) / 60)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res["summary"], indent=1))
    print(json.dumps(res["openings"], indent=1))
    print("written", OUT)


if __name__ == "__main__":
    main()
