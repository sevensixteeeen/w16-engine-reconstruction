"""Piston clearance checks on the CAD (exact OCC distances), written 2026-11-17 for D-042 / D-043.

  piston-to-valve  the four valve types (long / short intake and exhaust) at mid phaser and both phaser extremes (intake
                   +/-26, exhaust +/-11 deg crank), cylinder positions 1 and 2 of both banks, both valves of each pair.
                   Crank angle swept over +/-90 deg around gas-exchange TDC in 3 deg steps, every local minimum within
                   0.5 mm of the lowest refined to 0.25 and then 0.05 deg.  The closest feature on the valve and on the
                   piston is named.
  pocket depth     outer-row long intake at full intake advance for pocket depths 1.6 ... 4.0 mm, crown otherwise as built
                   (no CR refit): where the closest point goes once the pocket floor no longer binds.
  crown-to-head    piston at firing TDC against the head casting (whole piston top, and the crown faces alone: crown
                   plane + valve pockets), the seat inserts, the closed valves and the spark plug.

    PYTHONPATH=src python tools/check_piston_clearances.py [--out file.json] [--crown-only] [--workers N]

--crown-only runs only the crown-to-head check; with PYTHONPATH pointing at a source snapshot (git archive pre-D041
bugatti_w16_engine/src) it gives the D-040 baseline.  The default output is 08_SIMULATIONS/clearance/ of the source tree.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import time
from multiprocessing import Pool

import numpy as np
from build123d import Align, Box, Compound, Location, Plane, Pos

from w16.params import P
from w16 import layout as L
from w16.analysis import valvetrain as VT
from w16.cad import cranktrain as CT, head as H
from w16.cad.cache import cached
from w16.cad.common import ROOT, head_plane

PHASER = {"in": 0.5 * VT.TIMING["intake_phaser_range"], "ex": 0.5 * VT.TIMING["exhaust_phaser_range"]}   # deg crank
REQ = {"in": 1.5, "ex": 2.0}           # mm, piston-to-valve criteria (valvetrain.piston_valve_clearance)
TOL = 0.03                              # mm, tolerance when naming the feature a closest point lies on
CMIN = (Align.CENTER, Align.CENTER, Align.MIN)
POCKET_X = 17.6                         # pocket centre offset along the pin axis (cranktrain.piston_solids)


def pocket_depth():
    """Valve-pocket depth (mm): a parameter since D-042; 1.6 mm hard-coded in cranktrain.piston_solids before."""
    return getattr(P, "piston_valve_pocket_depth", 1.6)


# ------------------------------------------------------------------ geometry
def cyl(b, i):
    """Cylinder of head position i (1 = outer row, 2 = inner row) in bank b - the convention of the interference subset."""
    c = L.CYL[i if b == 1 else 17 - i]
    assert c.row == H.row_of(i), (b, i, c.row)
    return c


def piston_top():
    """Piston above the bottom of the top-ring groove (all that can approach a valve or the head), piston frame."""
    pis, _, _, _, _, pinfo = CT.piston_solids()
    z0 = pinfo["g1"] - 0.5
    return pis & (Pos(0, 0, z0) * Box(140, 140, 80, align=CMIN))


def crown_slab(depth=4.5):
    """Piston down to `depth` below the crown plane, normal to it (piston-to-valve only).  The valve meets the crown plane,
    the pockets or the upper top land first; the cut face lies inside the piston, so it never carries the minimum, and the
    oil gallery (5.5 mm below the pocket floors) drops out of the distance computation."""
    t = math.radians(P.crown_tilt_axis)
    n = (0.0, -math.sin(t), math.cos(t))
    org = (-n[0] * depth, -n[1] * depth, P.comp_height - n[2] * depth)
    return CT.piston_solids()[0] & (Plane(origin=org, x_dir=(1, 0, 0), z_dir=n) * Box(200, 200, 40, align=CMIN))


def valve_head(i, kind):
    """Valve head and neck (first 20 mm from the face), valve frame."""
    return H.valve_solid(kind, H.LAY[H.row_of(i)][kind]["length"]) & (Pos(0, 0, -0.5) * Box(80, 80, 20.5, align=CMIN))


def lift_at(kind, theta, shift):
    """Valve lift (mm) at theta deg after gas-exchange TDC with the cam timing moved by shift deg (negative = advanced)."""
    (li, _, _), (le, _, _) = VT.valve_lifts(np.array([theta - shift]))
    return float((li if kind == "in" else le)[0])


# ------------------------------------------------------------------ naming the closest features
def piston_feature(q):
    """Feature of the piston at the piston-frame point q (origin pin centre, +Z cylinder axis up, +Y high side of the crown)."""
    t = math.radians(P.crown_tilt_axis)
    nrm = np.array([0.0, -math.sin(t), math.cos(t)])
    q = np.array([q.X, q.Y, q.Z])
    d = (P.comp_height + q[1] * math.tan(t) - q[2]) * math.cos(t)          # depth below the crown plane, normal to it
    rho = math.hypot(q[0], q[1])
    r_tl = P.bore / 2 - P.piston_clear_dia / 2 - P.piston_top_land_relief
    pd, Rp, y0 = pocket_depth(), P.valve_in_dia / 2 + 1.8, -P.valve_du_in
    dax = 1e9
    for sx in (-1, 1):
        v = q - np.array([sx * POCKET_X, y0, P.comp_height + y0 * math.tan(t)])
        dax = min(dax, float(np.linalg.norm(v - (nrm @ v) * nrm)))
    on = lambda a, b: abs(a - b) < TOL
    if on(rho, r_tl) and on(d, 0.0):
        return "crown edge (crown plane / top land)"
    if on(rho, r_tl):
        return "top land"
    if on(d, pd) and on(dax, Rp):
        return "pocket floor corner (floor / wall)"
    if on(d, pd) and dax < Rp:
        return "pocket floor"
    if on(d, 0.0) and on(dax, Rp):
        return "pocket rim edge (wall / crown plane)"
    if on(dax, Rp) and 0.0 < d < pd:
        return "pocket wall"
    if on(d, 0.0):
        return "crown plane"
    return f"other (depth {d:.2f}, radius {rho:.2f}, from pocket axis {dax:.2f} mm)"


def valve_feature(ql, kind):
    """Feature of the valve at the valve-frame point ql (origin centre of the face, +Z along the stem)."""
    rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
    z, rad = ql.Z, math.hypot(ql.X, ql.Y)
    on = lambda a, b: abs(a - b) < TOL
    if on(z, 0.0) and on(rad, rv):
        return "rim edge (face / margin)"
    if on(z, 0.0):
        return "valve face"
    if on(rad, rv) and 0.0 < z < 1.2:
        return "margin"
    if on(z, 1.2) and on(rad, rv):
        return "margin / back-cone edge"
    return f"other (z {z:.2f}, radius {rad:.2f} mm)"


def head_feature(b, i, p, shape):
    """Feature of the head casting at the global point p."""
    hl = head_plane(b).to_local_coords(p)
    x = np.array([hl.X, hl.Y, hl.Z])
    pt, n = H.roof(i)
    c = np.array([H.loc_x(i), H.rho(i) * P.u_bore_head, 0.0])
    d = np.array([0.0, H.rho(i) * math.sin(H.G), math.cos(H.G)])
    v = x - c
    radial = float(np.linalg.norm(v - (v @ d) * d))
    on = lambda a, b: abs(a - b) < TOL
    if on(float((x - pt) @ n), 0.0) and on(radial, P.bore / 2):
        name = "roof / chamber-wall edge"
    elif on(float((x - pt) @ n), 0.0):
        name = "chamber roof"
    elif on(radial, P.bore / 2):
        name = "chamber wall (bore cylinder in the head)"
    elif on(x[2], 0.0):
        name = "joint face"
    else:
        f = min(shape.faces(), key=lambda f: f.distance_to(p))
        name = f"other face ({f.geom_type})"
    return name, dict(head_local=[round(float(a), 3) for a in x], radial_from_bore_axis=round(radial, 3),
                      above_roof_plane=round(float((x - pt) @ n), 3))


# ------------------------------------------------------------------ piston-to-valve
_SHAPES = {}


def _shapes(depth=None):
    key = depth
    if key not in _SHAPES:
        if depth is not None:
            P.piston_valve_pocket_depth = depth
        _SHAPES[key] = dict(piston=crown_slab(), valve={(i, k): valve_head(i, k) for i in (1, 2) for k in ("in", "ex")})
    return _SHAPES[key]


def evaluate(b, i, kind, s, theta, shift, sh):
    c = cyl(b, i)
    alpha = theta + c.fire + 360.0
    lift = lift_at(kind, theta, shift)
    pl, vl = CT.piston_location(c, alpha), H.valve_location(b, i, kind, s, lift)
    d, pa, pb = (vl * sh["valve"][(i, kind)]).distance_to_with_closest_points(pl * sh["piston"])
    return dict(theta=float(theta), lift=lift, dist=float(d), pa=pa, pb=pb, alpha=alpha, vl=vl, c=c)


def sweep(job):
    """Minimum piston-to-valve distance over the crank angle for one valve and one phaser setting."""
    b, i, kind, s, shift, depth = job
    if depth is not None:
        P.piston_valve_pocket_depth = depth
    sh = _shapes(depth)
    f = lambda th: evaluate(b, i, kind, s, th, shift, sh)
    grid = [f(th) for th in np.arange(-90.0, 90.0 + 1e-9, 3.0)]
    ds = np.array([g["dist"] for g in grid])
    lo = [k for k in range(len(grid)) if (k == 0 or ds[k] <= ds[k - 1]) and (k == len(grid) - 1 or ds[k] <= ds[k + 1])
          and ds[k] < ds.min() + 0.5]
    best = None
    for k in lo:
        th0 = grid[k]["theta"]
        for step, half in ((0.25, 3.0), (0.05, 0.3)):
            g = min((f(t) for t in np.arange(th0 - half, th0 + half + 1e-9, step)), key=lambda e: e["dist"])
            th0 = g["theta"]
        if best is None or g["dist"] < best["dist"]:
            best = g
    c = best["c"]
    q = CT.piston_frame(c, best["alpha"]).to_local_coords(best["pb"])
    ql = (best["vl"].inverse() * Location(best["pa"])).position
    v = H.LAY[H.row_of(i)][kind]
    return dict(bank=b, cyl=c.no, row=c.row, kind=kind, valve="long" if v["far"] else "short", side=s, shift_deg=shift,
                pocket_depth=pocket_depth(), min_clearance_mm=round(best["dist"], 3),
                theta_deg_after_gas_exchange_tdc=round(best["theta"], 2), lift_mm=round(best["lift"], 3),
                valve_feature=valve_feature(ql, kind), piston_feature=piston_feature(q),
                piston_point=[round(q.X, 2), round(q.Y, 2), round(q.Z, 2)], at_grid_edge=abs(best["theta"]) > 89.0,
                required_mm=REQ[kind])


def phaser_label(kind, shift):
    return "mid" if shift == 0 else (f"advanced {abs(shift):.0f}" if shift < 0 else f"retarded {abs(shift):.0f}")


# ------------------------------------------------------------------ crown-to-head at TDC
def crown_faces(ptop):
    """The crown proper: crown plane, pocket floors and walls (a point inside each face named by piston_feature)."""
    keep = []
    for f in ptop.faces():
        name = piston_feature(f.position_at(0.5, 0.5))
        if name.startswith(("crown plane", "pocket")):
            keep.append(f)
    return Compound(keep)


def crown_to_head():
    ptop = piston_top()
    crown = crown_faces(ptop)
    core = cached("head_core", lambda: H.head_core()[0], ["cad/head.py", "cad/block.py"])
    out = []
    for b, fs in ((1, -1), (2, 1)):
        hd = max(H.head_for_bank(core, fs).solids(), key=lambda s: s.volume)
        for i in (1, 2):
            c = cyl(b, i)
            pl = CT.piston_location(c, c.fire)                         # firing TDC
            hcrop = Location(head_plane(b)) * (hd & (Pos(H.loc_x(i), 0, -20) * Box(100, 400, 70, align=CMIN)))
            # the head's chamber surfaces without the bore-cylinder wall and the joint face: the top land runs 0.43 mm (radially)
            # inside that wall wherever it rises into the head, and its edge crosses the joint-face level part of the way round,
            # so both give 0.43 mm and hide the axial crown-to-roof clearance in the plain minimum
            c_ax = np.array([H.loc_x(i), H.rho(i) * P.u_bore_head, 0.0])
            dd = np.array([0.0, H.rho(i) * math.sin(H.G), math.cos(H.G)])          # bore axis, head-local, upwards

            def radial_wall_or_joint(f):
                q = head_plane(b).to_local_coords(f.position_at(0.5, 0.5))
                v = np.array([q.X, q.Y, q.Z]) - c_ax
                on_wall = f.geom_type.name == "CYLINDER" and abs(float(np.linalg.norm(v - (v @ dd) * dd)) - P.bore / 2) < 0.05
                return on_wall or (f.geom_type.name == "PLANE" and abs(q.Z) < 0.01)
            hroof = Compound([f for f in hcrop.faces() if not radial_wall_or_joint(f)])
            top_w = (Location(head_plane(b)).inverse() * (pl * ptop)).bounding_box().max.Z
            # axial gap (along the bore axis) from the crown plane to the roof plane over the crown disc r <= r_tl
            t = math.radians(P.crown_tilt_axis)
            r_tl = P.bore / 2 - P.piston_clear_dia / 2 - P.piston_top_land_relief
            pf, (rp, rn) = CT.piston_frame(c, c.fire), H.roof(i)
            best = None
            for rr in np.linspace(0.0, r_tl, 44):
                for ph in np.linspace(0.0, 2 * math.pi, 145)[:-1]:
                    x, y = rr * math.cos(ph), rr * math.sin(ph)
                    g = pf.from_local_coords((x, y, P.comp_height + y * math.tan(t)))
                    q = head_plane(b).to_local_coords(g)
                    q = np.array([q.X, q.Y, q.Z])
                    gap = float((rp - q) @ rn / (dd @ rn))
                    if best is None or gap < best[0]:
                        best = (gap, float(x), float(y), q)
            row = dict(bank=b, cyl=c.no, row=c.row, crown_top_above_joint_face_mm=round(float(top_w), 3),
                       crown_plane_to_roof_plane_axial_min_mm=round(best[0], 3),
                       axial_min_at_piston_xy=[round(best[1], 2), round(best[2], 2)],
                       axial_min_at_head_local=[round(float(a), 2) for a in best[3]])
            for what, shape, other in (("piston top", ptop, hcrop), ("crown faces", crown, hcrop),
                                       ("crown faces to chamber surfaces without the bore-cylinder wall and joint face", crown, hroof)):
                d, pp, ph = (pl * shape).distance_to_with_closest_points(other)
                name, where = head_feature(b, i, ph, hcrop)
                q = CT.piston_frame(c, c.fire).to_local_coords(pp)
                row[what] = dict(min_mm=round(float(d), 3), head_feature=name, piston_feature=piston_feature(q),
                                 piston_point=[round(q.X, 2), round(q.Y, 2), round(q.Z, 2)], **where)
            parts = []
            for kind in ("in", "ex"):
                for s in (-1, 1):
                    parts.append((f"seat insert {kind} {s:+d}", H.seat_location(b, i, kind, s) * H.seat_insert(kind)))
                    parts.append((f"valve {kind} {s:+d} (closed)", H.valve_location(b, i, kind, s, 0.0) * valve_head(i, kind)))
            parts.append(("spark plug", H.plug_location(b, i) * H.spark_plug()))
            others = {}
            for name, shape in parts:
                d, pp, _ = (pl * ptop).distance_to_with_closest_points(shape)
                q = CT.piston_frame(c, c.fire).to_local_coords(pp)
                others[name] = dict(min_mm=round(float(d), 3), piston_feature=piston_feature(q))
            row["other_parts"] = others
            out.append(row)
            ax = row["crown faces to chamber surfaces without the bore-cylinder wall and joint face"]
            oth = min(others, key=lambda k: others[k]["min_mm"])
            print(f"  bank {b} cyl {c.no:2d} ({c.row}): piston top {row['piston top']['min_mm']:.3f} mm "
                  f"[{row['piston top']['piston_feature']} / {row['piston top']['head_feature']}]; crown to roof etc. "
                  f"{ax['min_mm']:.3f} mm [{ax['piston_feature']} / {ax['head_feature']}, head-local {ax['head_local']}]; "
                  f"crown plane to roof plane, axial, min {best[0]:.3f} mm at piston xy {row['axial_min_at_piston_xy']}; crown top "
                  f"{top_w:.3f} mm above the joint face; nearest other part {oth} {others[oth]['min_mm']:.3f} mm "
                  f"[{others[oth]['piston_feature']}]", flush=True)
    return out


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "08_SIMULATIONS", "clearance", "piston_clearances.json"))
    ap.add_argument("--crown-only", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    rec = dict(source=ROOT, crown_tilt_axis_deg=P.crown_tilt_axis, pocket_depth_mm=pocket_depth(),
               crown_rise_axis_mm=getattr(P, "crown_rise_axis", None), deck_height_mm=P.deck_height,
               head_face_height_mm=P.head_face_height, phaser_half_range_deg=PHASER, tolerance_feature_mm=TOL)
    if not a.crown_only:
        d0 = pocket_depth()
        jobs = [(b, i, k, s, sh, None) for b in (1, 2) for i in (1, 2) for k in ("in", "ex") for s in (-1, 1)
                for sh in (-PHASER[k], 0.0, PHASER[k])]
        depth_jobs = [(1, 1, "in", s, -PHASER["in"], d) for d in (1.6, 2.2, 2.4, 2.6, 3.0, 4.0) for s in (-1, 1)]
        with Pool(a.workers) as pool:
            rows = pool.map(sweep, jobs, chunksize=1)
            depth_rows = pool.map(sweep, depth_jobs, chunksize=1)
        P.piston_valve_pocket_depth = d0
        rec["piston_to_valve"] = rows
        rec["pocket_depth_sweep_outer_long_intake_full_advance"] = depth_rows
        print("\npiston-to-valve (min over both banks and both valves of the pair; spread = max - min of those 4)")
        for i in (1, 2):
            for k in ("in", "ex"):
                for sh in (-PHASER[k], 0.0, PHASER[k]):
                    g = [r for r in rows if r["row"] == H.row_of(i) and r["kind"] == k and r["shift_deg"] == sh]
                    m = min(g, key=lambda r: r["min_clearance_mm"])
                    print(f"  {H.row_of(i):5s} {m['valve']:5s} {k} {phaser_label(k, sh):12s} {m['min_clearance_mm']:6.3f} mm "
                          f"(spread {max(r['min_clearance_mm'] for r in g) - m['min_clearance_mm']:.3f}) at {m['theta_deg_after_gas_exchange_tdc']:+6.2f} deg, "
                          f"lift {m['lift_mm']:5.2f}: {m['valve_feature']} / {m['piston_feature']}  (req {m['required_mm']})")
        print("\npocket-depth sweep, outer long intake, full advance (crown as built, no CR refit)")
        for r in depth_rows:
            print(f"  depth {r['pocket_depth']:.1f} side {r['side']:+d}: {r['min_clearance_mm']:6.3f} mm at {r['theta_deg_after_gas_exchange_tdc']:+6.2f} deg, "
                  f"lift {r['lift_mm']:5.2f}: {r['valve_feature']} / {r['piston_feature']} at {r['piston_point']}")
    print("\ncrown-to-head at firing TDC")
    rec["crown_to_head_tdc"] = crown_to_head()
    rec["run_s"] = round(time.time() - t0, 1)
    if a.crown_only and os.path.exists(a.out):                 # keep the piston-to-valve results of an earlier full run
        with open(a.out, encoding="utf-8") as fh:
            old = json.load(fh)
        rec = {**old, **rec}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print("written", a.out, rec["run_s"], "s")


if __name__ == "__main__":
    main()
