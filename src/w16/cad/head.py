"""Cylinder head and valve-train CAD (head-local frame: x along the crank, u lateral (+ outboard), w up from the
head joint face).  One head casting geometry serves both banks; only end features differ.
"""
from __future__ import annotations
import math
import numpy as np
from build123d import Align, Axis, Box, Circle, Cylinder, Helix, Location, Plane, Pos, Rot, Sphere, extrude, revolve, sweep
from scipy.optimize import brentq

from ..params import P
from .. import layout as L
from ..analysis import valvetrain as VT
from .common import CMIN, box_at, cyl_between, head_plane, hex_bolt, poly, tube
from .block import DRAIN_XY, W_TOP, XH, coolant_hole_xy, head_bolt_xy, loc_x, rho

D2R = math.pi / 180
G = 0.5 * P.vr_angle * D2R
LAY = VT.head_layout()
W_FLOOR = 62.0            # floor of the valve-gear chamber
W_JKT = (11.0, 50.0)      # water-jacket band
SEAT_DROP = P.spring_seat_drop   # spring seat below the valve tip, along the stem
R_PORT = {"in": 12.5, "ex": 11.0}
WEB_X = [loc_x(1) - 36.5, loc_x(2) + 36.5, loc_x(4) + 36.5, loc_x(6) + 36.5, loc_x(8) + 36.5]
W_PIV = 110.0             # hydraulic support element ball centre
ROLLER_W = P.cam_w - P.cam_base_r - P.roller_dia / 2


def row_of(i):
    return "outer" if i % 2 == 1 else "inner"


def valve_geo(i, kind, s):
    """Head point H, tip point T and unit axis a of a valve (head-local).  s = -1 / +1: front / rear valve."""
    v = LAY[row_of(i)][kind]
    dx = P.valve_dx_in if kind == "in" else P.valve_dx_ex
    x = loc_x(i) + s * dx
    H = np.array([x, v["u_head"], v["w_head"]])
    T = np.array([x, v["u_tip"], P.valve_tip_w])
    a = (T - H) / np.linalg.norm(T - H)
    return H, T, a


def plug_geo(i):
    pl = LAY[row_of(i)]["plug"]
    p0 = np.array([loc_x(i), pl["u0"], pl["w0"]])
    p1 = np.array([loc_x(i), pl["u1"], pl["w1"]])
    return p0, (p1 - p0) / np.linalg.norm(p1 - p0)


def roof(i):
    """Low-edge point and upward normal of the chamber roof plane of cylinder position i."""
    d = LAY[row_of(i)]
    t = math.tan(abs(d["roof_tilt"]) * D2R)
    n = np.array([0.0, -rho(i) * t, 1.0])
    return np.array([loc_x(i), d["roof_edge_u"], P.roof_low_w]), n / np.linalg.norm(n)


def bore_cyl(i, w0, w1, r):
    """Cylinder on the bore axis between the axis heights w0 and w1 (head-local).  The axis pierces the joint face at the
    head-face bore centre (D-039: the deck value was used before, 0.13 mm too far in, so the crown edge that rises into
    the head at TDC scraped the chamber wall).  The end faces are normal to the 7.5 deg axis, i.e. not level."""
    c = np.array([loc_x(i), rho(i) * P.u_bore_head, 0.0])
    d = np.array([0.0, rho(i) * math.sin(G), math.cos(G)])
    return cyl_between(c + d * (w0 / d[2]), c + d * (w1 / d[2]), r)


def above_plane(pt, n, offset=0.0):
    return Plane(origin=tuple(pt + n * offset), x_dir=(1, 0, 0), z_dir=tuple(n)) * Box(400, 400, 200, align=CMIN)


def fuse_all(shapes):
    """Balanced pairwise fuse (much more robust in OpenCascade than accumulating into one growing tool)."""
    items = [x for x in shapes if x is not None]
    while len(items) > 1:
        nxt = [a + b for a, b in zip(items[::2], items[1::2])]
        if len(items) % 2:
            nxt.append(items[-1])
        items = nxt
    return items[0]


R_DUCT = {"in": 16.5, "ex": 14.5}     # common duct radius after the two valve branches have merged


def port_points(i, kind):
    """Key points of the port of one cylinder: per valve (seat side, bowl top), merge point, flange point."""
    side = -1.0 if kind == "in" else 1.0                       # intake to the valley (-u), exhaust outboard (+u)
    br = []
    for s in (-1, 1):
        H, T, a = valve_geo(i, kind, s)
        br.append((H - a * 1.0, H + a * 12.0))
    mid = 0.5 * (br[0][1] + br[1][1])
    F = np.array([loc_x(i), side * (W_TOP + 2), 36.0])
    far = (side * mid[1]) < 0                                   # valves on the far side from the flange -> long port
    M = mid + (F - mid) * (0.25 if far else 0.45)
    M[2] = F[2]                                                 # common duct runs parallel to the joint face
    return br, M, F


def port_solid(i, kind, grow=0.0):
    """Gas volume of the siamesed port of one cylinder: two bowls and branches merging into one common duct.
    Built from cylinders and spheres that meet at large angles (robust booleans)."""
    br, M, F = port_points(i, kind)
    r, rc = R_PORT[kind] + grow, R_DUCT[kind] + grow
    # D-039: the joint spheres are 0.05 mm smaller than the cylinders they join.  With equal radii the sphere is tangent to
    # both cylinders along their end circles - a degenerate case for OpenCascade: after the 0.13 mm layout shift of D-039
    # the cylinder-4 exhaust port fused into an invalid solid, and with other seam orientations the slab-7 seat-pocket cuts
    # failed.  Oversized spheres (+0.3 mm) leave sliver faces at the inside of the bends; other sizes broke other ports.
    # The 0.05 mm steps this leaves are below the FE mesh size and are removed before meshing (sim/fea.py, case_head).
    parts = []
    for p0, p1 in br:
        parts += [cyl_between(p0, p1, r), Pos(*[float(v) for v in p1]) * Rot(X=31, Y=17) * Sphere(r - 0.05), cyl_between(p1, M, r)]   # seam turned away
    parts += [Pos(*[float(v) for v in M]) * Rot(X=53, Y=29) * Sphere(rc - 0.05), cyl_between(M, F, rc)]
    sol = fuse_all(parts)
    if not (sol.is_valid and len(sol.solids()) == 1):
        raise RuntimeError(f"port {i} {kind} (grow {grow}): invalid fuse")
    return sol


def chamber_tool(i):
    """Gas side of the chamber: the bore below the roof plane.  D-039: the tool starts 10 mm below the joint face on the
    axis.  It started 1 mm below before; with the end face normal to the leaning axis that left the tool up to 4.6 mm
    above the joint face on the inboard side, i.e. a wedge of head material over the bore that the opening long valves
    and the piston crown ran into."""
    pt, n = roof(i)
    return bore_cyl(i, -10.0, 60.0, P.bore / 2) - above_plane(pt, n)


CUT_LOG = []


def cut_seq(base, tools, what):
    """Subtract tool solids one after another, checking every result.  A cut that OpenCascade cannot do cleanly is
    retried at the end and, if necessary, with the tool shifted by a few hundredths of a millimetre (which breaks the
    geometric degeneracy; the shift is logged in CUT_LOG).  Raises if a cut still fails."""
    shifts = [None, (0.03, 0.02, 0.01), (-0.05, 0.03, -0.02), (0.02, -0.06, 0.04)]
    bb = base.bounding_box()

    def touches(t):
        tb = t.bounding_box()
        return not (tb.min.X > bb.max.X or tb.max.X < bb.min.X or tb.min.Y > bb.max.Y or tb.max.Y < bb.min.Y or tb.min.Z > bb.max.Z or tb.max.Z < bb.min.Z)
    todo = [(k, t) for k, t in enumerate(tools) if touches(t)]
    for sh in shifts:
        failed = []
        for k, t in todo:
            tt = t if sh is None else Pos(*sh) * t
            try:
                new = base - tt
                ok = new.is_valid and 0 < new.volume <= base.volume * (1 + 1e-7) + 1e-2
            except Exception:
                ok = False
            if ok:
                base = new
                if sh is not None:
                    CUT_LOG.append((what, k, sh))
            else:
                failed.append((k, t))
        todo = failed
        if not todo:
            return base
    raise RuntimeError(f"{what}: cuts {[k for k, _ in todo]} failed")


def cyl_tools(i):
    """Primitive tool solids belonging to cylinder position i: gas-side cuts, jacket keep-outs, valve-gear chamber
    keep-ins and drillings."""
    gas, keep, stay, drill = [], [], [], []
    pt, n = roof(i)
    gas.append(chamber_tool(i))
    keep.append(bore_cyl(i, 0.0, 70.0, P.bore / 2 + 4.0) - above_plane(pt, n, 9.0))
    p0, pd = plug_geo(i)
    gas.append(cyl_between(p0 - pd * 1.0, p0 + pd * 14.0, P.plug_thread / 2))
    gas.append(cyl_between(p0 + pd * 14.0, p0 + pd * 175.0, P.plug_well_dia / 2))
    keep.append(cyl_between(p0, p0 + pd * 60.0, P.plug_well_dia / 2 + 3.5))
    stay.append(cyl_between(p0 + pd * 45.0, p0 + pd * 140.0, P.plug_well_dia / 2 + 1.5))
    for kind in ("in", "ex"):
        rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
        v = LAY[row_of(i)][kind]
        gas.insert(0, port_solid(i, kind))                      # ports first: this cut order is the robust one
        keep.insert(0, port_solid(i, kind, 4.5))
        for s in (-1, 1):
            H, T, a = valve_geo(i, kind, s)
            gas.append(cyl_between(H - a * 1.5, H + a * 6.0, rv + 1.7))                    # seat-insert pocket
            S = T - a * SEAT_DROP
            gas.append(cyl_between(H + a * 10.0, S + a * 1.0, P.valve_guide_od / 2))        # guide bore
            keep.append(cyl_between(H + a * 6.0, H + a * 62.0, P.valve_guide_od / 2 + 3.5))
            stay.append(cyl_between(S - a * 16.0, S, P.spring_od / 2 + 2.0))                # spring seat pad
            if v["far"]:
                # long valve: support element outboard of its camshaft - boss stands on the gear-chamber floor
                stay.append(Pos(H[0], v["u_piv"], W_FLOOR - 1) * Cylinder(8.0, W_PIV - 4.0 - W_FLOOR + 1, align=CMIN))
            else:
                # short valve: support element between the camshafts, above the long valve's spring.  The boss hangs from
                # the spark-plug tower through a web, so it does not reach down to the long valve's spring seat (D-034).
                stay.append(Pos(H[0], v["u_piv"], P.hla_boss_w0) * Cylinder(8.0, W_PIV - 4.0 - P.hla_boss_w0, align=CMIN))
                stay.append(box_at(min(loc_x(i), H[0]), max(loc_x(i), H[0]), v["u_piv"] - 5.0, v["u_piv"] + 5.0,
                                   P.hla_boss_w0 + 2.0, W_PIV - 6.0))
            drill.append(Pos(H[0], v["u_piv"], W_PIV - 26.0) * Cylinder(6.0, 23.0, align=CMIN))   # support-element bore
    return gas, keep, stay, drill


SPRING_POCKET_R = P.spring_od / 2 + 1.5    # retainer (spring_od / 2 + 0.5) + 1 mm


def web_solid(xw):
    """Camshaft bearing web of the gear chamber at x = xw (18 mm thick), with a pocket for the spring and retainer of every
    valve next to it (D-039: the retainers of the valves beside a web ran 2 mm into it, and the springs 1.5 mm)."""
    web = box_at(xw - 9, xw + 9, -W_TOP + 8, W_TOP - 8, W_FLOOR, P.head_height)
    for i in range(1, 9):
        for kind in ("in", "ex"):
            for s in (-1, 1):
                H, T, a = valve_geo(i, kind, s)
                if abs(H[0] - xw) < 9.0 + SPRING_POCKET_R:
                    web = web - cyl_between(T - a * (SEAT_DROP + 0.5), T + a * 1.0, SPRING_POCKET_R)
    return web


def head_slab(i, tools):
    """Head casting between the mid-planes around cylinder position i (end slabs run to the head ends)."""
    hh = P.head_height
    x0 = -XH if i == 1 else loc_x(i) - 36.5
    x1 = XH if i == 8 else loc_x(i) + 36.5
    near = lambda x, m=14.0: x0 - m <= x <= x1 + m
    nb = [j for j in (i - 1, i, i + 1) if 1 <= j <= 8]
    gas = [t for j in nb for t in tools[j][0][:2]] + [t for j in nb for t in tools[j][0][2:]]
    keep = [t for j in nb for t in tools[j][1][:2]] + [t for j in nb for t in tools[j][1][2:]]
    keep += [Pos(x, u, 0) * Cylinder(10.0, W_FLOOR, align=CMIN) for x, u in head_bolt_xy() if near(x)]
    keep += [Pos(x, u, 0) * Cylinder(12.0, W_FLOOR, align=CMIN) for x, u in DRAIN_XY if near(x)]
    jx0, jx1 = max(x0, -XH + 8), min(x1, XH - 8)
    jacket = cut_seq(box_at(jx0, jx1, -W_TOP + 10, W_TOP - 10, W_JKT[0], W_JKT[1]), keep, f"jacket {i}")
    stay = [t for j in nb for t in tools[j][2]]
    stay += [web_solid(xw) for xw in WEB_X if near(xw)]
    gear = cut_seq(box_at(jx0, jx1, -W_TOP + 8, W_TOP - 8, W_FLOOR, hh + 1), stay, f"gear chamber {i}")
    dr = [t for j in nb for t in tools[j][3]]
    dr += [Pos(x, u, -1) * Cylinder(4.0, W_JKT[0] + 2, align=CMIN) for x, u in coolant_hole_xy() if near(x)]
    dr += [Pos(x, u, -1) * Cylinder(5.8, W_FLOOR + 2, align=CMIN) for x, u in head_bolt_xy() if near(x)]
    dr += [Pos(x, u, -1) * Cylinder(8.0, W_FLOOR + 2, align=CMIN) for x, u in DRAIN_XY if near(x)]
    gx0, gx1 = max(x0 - 1, -XH + 14), min(x1 + 1, XH - 14)
    for su in (-1, 1):
        dr.append(cyl_between((gx0, su * 84.0, 55.5), (gx1, su * 84.0, 55.5), 3.5))                      # oil gallery
        dr += [cyl_between((xw, su * 84.0, 55.5), (xw, su * P.cam_u, hh - P.cam_journal_dia / 2 + 1), 2.5) for xw in WEB_X if near(xw)]
        dr.append(cyl_between((max(x0 - 1, -XH + 7), su * P.cam_u, hh), (min(x1 + 1, XH - 7), su * P.cam_u, hh), P.cam_journal_dia / 2))   # cam saddle
    body = box_at(x0, x1, -W_TOP, W_TOP, 0, hh)
    slab = cut_seq(body, gas, f"slab {i} gas side")
    slab = cut_seq(slab, [jacket, gear], f"slab {i} jacket/gear")
    slab = cut_seq(slab, dr, f"slab {i} drillings")
    sol = slab.solids()
    if not sol or not slab.is_valid:
        raise RuntimeError(f"head slab {i}: boolean failed")
    return max(sol, key=lambda q: q.volume), jacket


def head_core():
    """Head casting without end-specific features (head-local).  Built as eight slabs (one per cylinder position)
    that are fused afterwards - this keeps every boolean operation small and robust."""
    tools = {i: cyl_tools(i) for i in range(1, 9)}
    slabs, jackets = [], []
    for i in range(1, 9):
        sl, jk = head_slab(i, tools)
        slabs.append(sl)
        jackets.append(jk)
    head = fuse_all(slabs)
    jacket = fuse_all(jackets)
    if not head.is_valid or head.volume < 3.0e6:
        raise RuntimeError("cylinder-head fuse failed (invalid result)")
    return head, jacket


def head_for_bank(core, front_sign):
    """Add the end-specific features: coolant outlet + oil feed at the engine front, camshaft openings at the rear."""
    hh = P.head_height
    xf = front_sign * XH
    cut = cyl_between((xf + front_sign, -60.0, 30.0), (xf - front_sign * 14, -60.0, 30.0), 17.0)                 # coolant outlet
    for su in (-1, 1):
        cut = cut + cyl_between((xf + front_sign, su * 84.0, 55.5), (xf - front_sign * 16, su * 84.0, 55.5), 3.5)  # oil feed
        # camshaft exit at the drive end: lower half of a 32 mm seal bore through the 8 mm end wall into the gear chamber
        # (D-039: the cut reached only 1 mm into the wall, so the shaft ran through 6 mm of end wall)
        cut = cut + cyl_between((-xf - front_sign * 1.0, su * P.cam_u, hh), (-xf + front_sign * 12.0, su * P.cam_u, hh), CAM_EXIT_R)
    return core - cut


CAM_EXIT_R = 16.0     # camshaft seal bore at the drive end (shaft 24 mm)


# ====================================================================== valve-train parts
def valve_solid(kind, length):
    """Poppet valve; local: origin at the centre of the head face, +Z along the stem to the tip."""
    rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
    rs = P.valve_stem_dia / 2
    pts = [(0, 0), (rv, 0), (rv, 1.2), (rv - 2.6, 3.8), (rs + 2.5, 11.0), (rs, 17.0), (rs, length - 6.5), (rs - 0.6, length - 6.0),
           (rs - 0.6, length - 4.6), (rs, length - 4.1), (rs, length), (0, length)]
    return revolve(Plane.XZ * poly(pts), axis=Axis.Z)


def seat_insert(kind):
    """Valve seat insert in valve coordinates (z = 0 at the valve head face): surrounds the valve margin with
    0.25 mm clearance and carries the 45 deg seat that the valve face closes on."""
    rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
    # D-039: throat at rv - 2.9 behind a short top cut (was rv - 3.4 behind a 45 deg continuation of the seat): the back
    # of the exhaust valve head (27 mm valve, flatter tulip) ran into the old throat corner with the valve closed
    pts = [(rv + 0.25, -1.0), (rv + 1.7, -1.0), (rv + 1.7, 6.0), (rv - 2.9, 6.0), (rv - 2.9, 4.6), (rv - 2.6, 3.8), (rv, 1.2), (rv + 0.25, 1.2)]
    return revolve(Plane.XZ * poly(pts), axis=Axis.Z)


def guide_solid(length=44.0):
    return Cylinder(P.valve_guide_od / 2, length, align=CMIN) - Cylinder(P.valve_stem_dia / 2 + 0.02, length, align=CMIN)


def spring_solid(height):
    """Helical valve spring between the seat (z = 0) and the retainer (z = height)."""
    wire = 3.4
    rm = P.spring_od / 2 - wire / 2
    coils = 6.5
    h = height - wire
    helix = Helix(h / coils, h, rm)
    return Pos(0, 0, wire / 2) * sweep(Plane(origin=helix @ 0, z_dir=helix % 0) * Circle(wire / 2), path=helix)


def retainer_solid():
    pts = [(P.valve_stem_dia / 2 + 0.6, -3.0), (7.0, -3.0), (7.0, 0.0), (P.spring_od / 2 + 0.5, 0.0), (P.spring_od / 2 + 0.5, 2.2),
           (P.valve_stem_dia / 2 + 2.2, 3.4), (P.valve_stem_dia / 2 + 0.6, 3.4)]
    return revolve(Plane.XZ * poly(pts), axis=Axis.Z)


# ---------------------------------------------------------------------- finger-follower kinematics (D-039)
# The finger turns about the support-element ball.  Its valve pad is a crown (cylinder along x, radius finger_pad_r)
# that stays tangent to the flat valve tip, so the finger angle follows from the lift exactly; the cam lobes are the
# envelope of the roller over the resulting roller-centre path.  Before D-039 the pad was flat and level (the tilted tip
# cut into it by up to 19 mm3), the finger angle was asin(lift cos(tilt) / arm) and the lobes assumed a roller moving
# straight towards the cam centre - small cam / roller overlaps at some angles.
LIFT_REF = 4.9                    # lift at which the pad touches the centre of the tip (about half lift)
RW_LOC = ROLLER_W - W_PIV         # roller axis above the ball centre, finger-local


def _valve_uw(v):
    """Closed tip point T and unit axis a (towards the tip) of a valve in the (u, w) plane."""
    hd = np.array([v["u_head"], v["w_head"]])
    T = np.array([v["u_tip"], P.valve_tip_w])
    return T, (T - hd) / np.linalg.norm(T - hd)


def finger_pt(v, delta, y, z):
    """(u, w) in the head of the finger-local point (y, z) with the finger turned by delta (deg) - the transform of
    finger_location (the finger of a valve whose tip lies on the +u side of its pivot is placed mirrored)."""
    d = math.radians(delta)
    return np.array([v["u_piv"] - v["side"] * (y * math.cos(d) - z * math.sin(d)), W_PIV + y * math.sin(d) + z * math.cos(d)])


def _to_finger(v, delta, p):
    d = math.radians(delta)
    du, dw = -v["side"] * (p[0] - v["u_piv"]), p[1] - W_PIV
    return np.array([du * math.cos(d) + dw * math.sin(d), -du * math.sin(d) + dw * math.cos(d)])


def _pad_centre(far):
    """Finger-local centre of the pad crown, placed so that the crown touches the tip centre at LIFT_REF.  The valves a
    finger type serves are mirror images in the head, so any of them gives the same point."""
    v = next(LAY[r][k] for r in ("inner", "outer") for k in ("in", "ex") if LAY[r][k]["far"] == far)
    T, a = _valve_uw(v)
    dm = math.degrees(math.asin(LIFT_REF * math.cos(abs(v["tilt"]) * D2R) / (v["tip_len"] + v["piv_len"])))
    return _to_finger(v, dm, T - a * LIFT_REF + a * P.finger_pad_r)


PAD_C = {far: _pad_centre(far) for far in (False, True)}


def finger_delta(v, lift):
    """Finger angle (deg) at which the pad crown is tangent to the valve tip at this lift."""
    T, a = _valve_uw(v)
    c = PAD_C[v["far"]]
    f = lambda d: float(a @ (finger_pt(v, d, c[0], c[1]) - T)) + lift - P.finger_pad_r
    return brentq(f, -20.0, 50.0, xtol=1e-10)


def pad_contact(v, lift):
    """Offset (mm) of the pad contact from the tip centre, along the tip face in the (u, w) plane."""
    T, a = _valve_uw(v)
    c = PAD_C[v["far"]]
    k = finger_pt(v, finger_delta(v, lift), c[0], c[1]) - a * P.finger_pad_r
    return float(np.array([a[1], -a[0]]) @ (k - (T - a * lift)))


def finger_solid(far):
    """Roller finger follower; local: origin at the support-element ball centre, valve tip at u = -(tip+pivot arm),
    w = +2 (valve tip plane), roller axis at u = -pivot arm.  far=True: long-valve finger, far=False: short-valve finger.
    D-039: crowned valve pad; the underside stays 1.5 mm above the tip plane over the valve end and clears the retainer
    before it drops towards the pivot (it was 2.5 mm below the tip plane from 6 mm off the tip centre, over the retainer)."""
    d = P.valve_tip_w - W_PIV
    lp = P.finger_piv_far if far else P.finger_piv_near
    lt = lp + (P.finger_tip_far if far else P.finger_tip_near)
    rw = ROLLER_W - W_PIV
    prof = poly([(-lt - 3, d + 1.5), (-lt + 4.5, d + 1.5), (-lt + 12, d - 1.0), (-7, d - 2.5), (-6, 0.5), (6, 0.5), (6, 8.0),
                 (-lp + 9, rw + 5.5), (-lp - 9, rw + 5.5), (-lt - 3, d + 6.5)])
    body = extrude(Plane(origin=(-6, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * prof, amount=12.0)
    body = body - box_at(-4.3, 4.3, -lp - 9.5, -lp + 9.5, d - 6, rw + 12)                          # roller slot
    body = body - Sphere(4.05)                                                                      # ball socket
    c = PAD_C[far]
    pad = Pos(0, float(c[0]), float(c[1])) * Rot(Y=90) * Cylinder(P.finger_pad_r, 12.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    body = body + (pad & box_at(-6, 6, -lt - 3.0, -lt + 3.0, float(c[1]) - P.finger_pad_r - 0.5, d + 1.6))   # crown below the underside
    roller = Pos(-4.0, -lp, rw) * Rot(Y=90) * (Cylinder(P.roller_dia / 2, 8.0, align=CMIN) - Cylinder(3.0, 8.0, align=CMIN))
    axle = Pos(-6.0, -lp, rw) * Rot(Y=90) * Cylinder(3.0, 12.0, align=CMIN)
    return body + roller + axle


def hla_solid():
    """Hydraulic support element; local: ball centre at the origin, body downwards."""
    return Pos(0, 0, -26.0) * Cylinder(5.98, 20.0, align=CMIN) + Pos(0, 0, -7.0) * Cylinder(4.2, 4.5, align=CMIN) + Sphere(4.0)


def cam_lobe_profile(kind, far, bank=1):
    """2-D lobe outline (u, w) in the camshaft frame with the nose pointing to -w: inner envelope of the roller over the
    roller-centre path of the finger (D-039; see finger_delta).  The lobe turns by +theta about +x_l on bank 1 and by
    -theta on bank 2, so the two banks get mirror-image lobes."""
    row = next(r for r in ("inner", "outer") if LAY[r][kind]["far"] == far)
    v = LAY[row][kind]
    T = VT.TIMING
    to, tc, lm = (T["ivo"], T["ivc"], P.valve_lift_in) if kind == "in" else (T["evo"], T["evc"], P.valve_lift_ex)
    mid = 0.5 * (to + tc)
    th = np.linspace(-180.0, 180.0, 361)[:-1]                   # cam angle from the nose (deg)
    lift, _, _ = VT.lift_curve(mid + 2 * th, to, tc, lm)        # crank angle = 2 x cam angle
    cam_c = np.array([-P.cam_u if kind == "in" else P.cam_u, P.cam_w])
    sg = 1.0 if bank == 1 else -1.0
    memo = {}
    px, py = np.empty_like(th), np.empty_like(th)
    for k, (t, li) in enumerate(zip(th, lift)):
        key = round(float(li), 9)
        if key not in memo:
            memo[key] = finger_pt(v, finger_delta(v, float(li)), -v["piv_len"], RW_LOC) - cam_c   # roller centre - cam centre
        q = memo[key]
        ps = math.radians(sg * t)                               # undo the lobe rotation: head frame -> camshaft frame
        px[k], py[k] = q[0] * math.cos(ps) + q[1] * math.sin(ps), -q[0] * math.sin(ps) + q[1] * math.cos(ps)
    rp = np.hypot(px, py)
    drop = rp.max() - rp
    tx, ty = np.gradient(px), np.gradient(py)
    nrm = np.hypot(tx, ty)
    nx, ny = ty / nrm, -tx / nrm                                 # outward normal (curve is traversed counter-clockwise)
    out = (px * nx + py * ny) > 0
    nx, ny = np.where(out, nx, -nx), np.where(out, ny, -ny)
    sx, sy = px - P.roller_dia / 2 * nx, py - P.roller_dia / 2 * ny
    if 0.5 * float(np.sum(sx * np.roll(sy, -1) - np.roll(sx, -1) * sy)) < 0:
        sx, sy = sx[::-1], sy[::-1]          # counter-clockwise, so the face normal (extrude direction) is +x on both banks
    return list(zip(sx.tolist(), sy.tolist())), float(drop.max())


def lobe_angle(bank, i, kind):
    """Rotation (deg, about local +x) to apply to a nose-down lobe so that it is correctly phased at crank angle 0."""
    c = L.CYL[i if bank == 1 else 17 - i]
    T = VT.TIMING
    mid = 0.5 * (T["ivo"] + T["ivc"]) if kind == "in" else 0.5 * (T["evo"] + T["evc"])
    a_max = c.fire + 360.0 + mid                                 # crank angle of maximum lift
    # the cam turns by alpha/2 about +x_l (bank 1) or -x_l (bank 2); it must be nose-down at alpha = a_max
    return (-a_max / 2.0) if bank == 1 else (a_max / 2.0)


def camshaft(bank, kind):
    """Camshaft in head-local orientation at crank angle 0, axis through the origin along x."""
    drive = 1.0 if bank == 1 else -1.0                           # drive (flywheel) end in local x
    x0, x1 = -drive * (XH - 12), drive * (XH + 46)
    shaft = cyl_between((x0, 0, 0), (x1, 0, 0), 12.0)
    for xw in WEB_X:
        shaft = shaft + cyl_between((xw - 9.0, 0, 0), (xw + 9.0, 0, 0), P.cam_journal_dia / 2 - 0.03)
    dx = P.valve_dx_in if kind == "in" else P.valve_dx_ex
    cam_u = -P.cam_u if kind == "in" else P.cam_u
    for i in range(1, 9):
        far = LAY[row_of(i)][kind]["far"]
        pts, _ = cam_lobe_profile(kind, far, bank)
        lobe = extrude(Plane(origin=(-5.5, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * poly(pts), amount=11.0)
        lobe = Rot(X=lobe_angle(bank, i, kind)) * lobe
        for s in (-1, 1):
            shaft = shaft + Pos(loc_x(i) + s * dx, 0, 0) * lobe
    shaft = shaft - cyl_between((x0 - 1, 0, 0), (x1 + 1, 0, 0), 6.5)                               # hollow shaft / oil way
    return shaft


def cam_location(bank, kind, alpha):
    cam_u = -P.cam_u if kind == "in" else P.cam_u
    rot = alpha / 2.0 if bank == 1 else -alpha / 2.0
    return Location(head_plane(bank)) * Pos(0, cam_u, P.cam_w) * Rot(X=rot)


def cam_cap():
    """Camshaft bearing cap; local: journal axis = x through the origin, cap above."""
    cap = box_at(-9, 9, -23, 23, 0.0, 21.0) - Rot(Y=90) * Cylinder(P.cam_journal_dia / 2, 30, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    for su in (-1, 1):
        cap = cap - Pos(0, su * 18.0, -1) * Cylinder(3.3, 24, align=CMIN)
    return cap


def cam_cover(bank):
    """Cam cover of one head with the eight coil towers (head-local).  D-039: one per bank - the end wall at the camshaft
    drive end (+x for bank 1, -x for bank 2 in head-local) carries the upper halves of the camshaft seal bores; before,
    one cover served both banks and the shafts ran through its closed end wall."""
    hh = P.head_height
    top = hh + 44.0
    cov = box_at(-XH, XH, -W_TOP, W_TOP, hh, top) - box_at(-XH + 4, XH - 4, -W_TOP + 4, W_TOP - 4, hh - 1, top - 4)
    xd = XH if bank == 1 else -XH
    sd = 1.0 if bank == 1 else -1.0
    cut = None
    for su in (-1, 1):
        c = cyl_between((xd + sd * 1.0, su * P.cam_u, hh), (xd - sd * 12.0, su * P.cam_u, hh), CAM_EXIT_R)
        cut = c if cut is None else cut + c
    for i in range(1, 9):
        p0, pd = plug_geo(i)
        a = p0 + pd * ((hh + 0.0 - p0[2]) / pd[2])
        b = p0 + pd * ((top + 6 - p0[2]) / pd[2])
        cov = cov + (cyl_between(a - pd * 8, b, P.plug_well_dia / 2 + 1.5) & box_at(-XH, XH, -W_TOP, W_TOP, hh, top))
        c = cyl_between(a - pd * 3, b + pd * 3, P.plug_well_dia / 2 + 0.4)
        cut = c if cut is None else cut + c
    cut = cut + Pos(-220.0, 60.0, top - 6) * Cylinder(17.0, 12, align=CMIN)                         # oil filler / breather
    return cov - cut


def spark_plug():
    """M10 spark plug; local: electrode end at origin, +Z up the well."""
    pts = [(0, 0), (4.9, 0), (4.9, 19.0), (6.9, 19.0), (6.9, 31.0), (4.5, 33.0), (4.5, 56.0), (3.0, 58.0), (0, 58.0)]
    return revolve(Plane.XZ * poly(pts), axis=Axis.Z)


def ignition_coil():
    """Pencil coil with ion-current sensing electronics; local: bottom at origin (sits on the plug), +Z up."""
    pts = [(5.2, 0), (8.5, 0), (8.5, 158.0), (13.0, 160.0), (13.0, 184.0), (0, 184.0), (0, 27.0), (5.2, 27.0)]
    body = revolve(Plane.XZ * poly(pts), axis=Axis.Z)
    return body + box_at(-9, 9, 6, 30, 166.0, 184.0)                                                # connector


# ====================================================================== kinematics of one valve
def lifts(c, alpha):
    th = np.array([((alpha - c.fire) % 720.0) - 360.0])
    (li, _, _), (le, _, _) = VT.valve_lifts(th)
    return float(li[0]), float(le[0])


def valve_location(bank, i, kind, s, lift):
    H, T, a = valve_geo(i, kind, s)
    o = H - a * lift
    return Location(head_plane(bank)) * Location(Plane(origin=tuple(o), x_dir=(1, 0, 0), z_dir=tuple(a)))


def seat_location(bank, i, kind, s):
    H, T, a = valve_geo(i, kind, s)
    return Location(head_plane(bank)) * Location(Plane(origin=tuple(H), x_dir=(1, 0, 0), z_dir=tuple(a)))


def along_valve(bank, i, kind, s, dist_from_tip):
    """Location on the valve axis at a distance below the (closed) tip, +Z towards the tip."""
    H, T, a = valve_geo(i, kind, s)
    return Location(head_plane(bank)) * Location(Plane(origin=tuple(T - a * dist_from_tip), x_dir=(1, 0, 0), z_dir=tuple(a)))


def finger_location(bank, i, kind, s, lift):
    v = LAY[row_of(i)][kind]
    H, T, a = valve_geo(i, kind, s)
    delta = finger_delta(v, lift)                                # pad crown tangent to the tip (D-039)
    base = Location(head_plane(bank)) * Pos(float(H[0]), v["u_piv"], W_PIV)
    if v["side"] < 0:                                            # tip on the -u side of the pivot
        return base * Rot(X=delta)
    return base * Rot(X=-delta) * Rot(Z=180)


def hla_location(bank, i, kind, s):
    v = LAY[row_of(i)][kind]
    H, T, a = valve_geo(i, kind, s)
    return Location(head_plane(bank)) * Pos(float(H[0]), v["u_piv"], W_PIV)


def plug_location(bank, i, up=0.0):
    p0, pd = plug_geo(i)
    return Location(head_plane(bank)) * Location(Plane(origin=tuple(p0 + pd * up), x_dir=(1, 0, 0), z_dir=tuple(pd)))
