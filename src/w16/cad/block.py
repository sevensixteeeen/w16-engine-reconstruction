"""Crankcase CAD: upper section (cylinder block), lower section (bearing support / bedplate), dry-sump pan,
main-bearing shells, head gasket, piston-cooling jets.

Bank-specific features are modelled once in bank-local coordinates (x_l, u, v) and placed for both banks
(the engine is symmetric under a 180 deg rotation about Z).
"""
from __future__ import annotations
import math
import numpy as np
from build123d import Align, Box, Cylinder, Location, Plane, Pos, Rot, Sphere, extrude

from ..params import P
from .. import layout as L
from .common import CMIN, bank_plane, box_at, cyl_between, poly

D2R = math.pi / 180
XH = 330.0                 # half length of the block / heads
W_TOP = 110.0              # bank half width at the deck
R_CAV = 97.0               # crank chamber radius
GAL_C = (0.0, 140.0)       # central main oil gallery (y, z)
GAL_S = (128.0, 13.0)      # side galleries for the piston-cooling jets (+/- y, z)
MOUNT_X = 250.0            # engine-mount pads (one per side, near the flywheel end)
INTER_YZ = (0.0, 118.0)    # intermediate shaft of the timing drive
G = 0.5 * P.vr_angle * D2R


def loc_x(i):
    """Bank-local axial position of cylinder position i = 1..8 (both banks)."""
    return L.pin_x(i) - 0.5 * P.bank_offset


def rho(i):
    return 1.0 if i % 2 == 1 else -1.0          # +1 outer row, -1 inner row


def axis_local(i):
    """Row axis in bank-local coordinates: point at v = 0 and unit direction."""
    r = rho(i)
    return np.array([loc_x(i), r * P.row_offset, 0.0]), np.array([0.0, r * math.sin(G), math.cos(G)])


def axis_pt(i, v):
    p, d = axis_local(i)
    return p + d * (v / d[2])


def head_bolt_xy():
    """Head-bolt positions (x_l, u): 9 on the bank centre line, 16 on the outer sides."""
    pts = [(loc_x(1) - 36.5, 0.0)] + [(loc_x(i) + 36.5, 0.0) for i in range(1, 9)]
    for i in range(1, 9):
        uc = rho(i) * (P.u_bore_deck + 54.0)
        pts += [(loc_x(i) - 36.5, uc), (loc_x(i) + 36.5, uc)]
    return pts


def coolant_hole_xy():
    pts = []
    for i in range(1, 9):
        uc = rho(i) * P.u_bore_deck
        r = P.bore / 2 + P.liner_wall + P.jacket_width / 2
        pts += [(loc_x(i) - r, uc), (loc_x(i) + r, uc),
                (loc_x(i) - 0.5 * r, uc + rho(i) * 0.866 * r), (loc_x(i) + 0.5 * r, uc + rho(i) * 0.866 * r)]
    return pts


DRAIN_XY = [(-255.0, -50.0), (255.0, 50.0)]


def bank_body():
    """Solid outline of one cylinder bank (bank-local)."""
    vb = L.v_of_s(P.s_bore_foot) - 1.0
    prof = poly([(-82, vb), (82, vb), (97, 150), (W_TOP, P.deck_height), (-W_TOP, P.deck_height), (-97, 150)])
    body = extrude(Plane(origin=(-XH, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * prof, amount=2 * XH)
    return body


def jacket_void():
    """Water-jacket volume of one bank (bank-local): annuli around the eight bores, siamesed, with bolt columns."""
    v0 = P.deck_height - P.deck_thk - P.jacket_depth
    v1 = P.deck_height - P.deck_thk
    r_in = P.bore / 2 + P.liner_wall
    r_out = r_in + P.jacket_width
    outer = inner = None
    for i in range(1, 9):
        a, b = axis_pt(i, v0 - 5), axis_pt(i, v1 + 5)
        o = cyl_between(a, b, r_out)
        n = cyl_between(axis_pt(i, v0 - 10), axis_pt(i, v1 + 10), r_in)
        outer = o if outer is None else outer + o
        inner = n if inner is None else inner + n
    void = (outer - inner) & box_at(-XH, XH, -W_TOP, W_TOP, v0, v1)
    for x, u in head_bolt_xy()[:9]:
        void = void - Pos(x, u, v0 - 1) * Cylinder(9.5, v1 - v0 + 2, align=CMIN)
    return void


def bank_cut(front_sign):
    """Everything removed from one bank (bank-local).  front_sign = -1: engine front is at local -x (bank 1)."""
    dk = P.deck_height
    cut = jacket_void()
    for i in range(1, 9):
        p, d = axis_local(i)
        cut = cut + cyl_between(p + d * P.s_bore_foot, p + d * (P.s_deck + 14), P.bore / 2)       # cylinder bore, through the deck
        cut = cut + cyl_between(p + d * 55.0, p + d * P.s_bore_foot, P.bore / 2 + 1.5)             # relief below the bore
    for x, u in coolant_hole_xy():
        cut = cut + Pos(x, u, dk - P.deck_thk - 2) * Cylinder(4.0, P.deck_thk + 4, align=CMIN)
    for x, u in head_bolt_xy():
        cut = cut + Pos(x, u, dk - 64) * Cylinder(4.75, 66, align=CMIN)                              # M11 thread bore
    for x, u in DRAIN_XY:
        cut = cut + Pos(x, u, 70.0) * Cylinder(8.0, dk - 68, align=CMIN)                             # oil drain from the head
    # coolant inlet at the engine front end into the jacket of the first cylinder
    i_f = 1 if front_sign < 0 else 8
    uc = rho(i_f) * P.u_bore_deck
    xa = front_sign * (XH + 1)
    xb = loc_x(i_f) + front_sign * (P.bore / 2 + P.liner_wall + 1.0)
    cut = cut + cyl_between((xa, uc, dk - 45), (xb, uc, dk - 45), 17.0)
    return cut


def block_upper():
    """Crankcase upper section with both cylinder banks (global frame).  Returns (solid, jacket volume per bank)."""
    k = 164.05
    prism = extrude(Plane(origin=(-XH, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) *
                    poly([(-150, 0), (150, 0), (150, k - 150), (0, k), (-150, k - 150)]), amount=2 * XH)
    bb = bank_body()
    body = prism
    for b in (1, 2):
        body = body + bank_plane(b) * bb
    # external ribs at the bulkheads and engine-mount pads
    rib = poly([(150, 0), (162, 0), (224, 62), (212, 76), (150, 22)])
    for j in range(1, P.n_main + 1):
        for sy in (1, -1):
            r = extrude(Plane(origin=(L.main_x(j) - 4, 0, 0), x_dir=(0, sy, 0), z_dir=(sy, 0, 0)) * rib, amount=sy * 8.0)
            body = body + r
    for sx in (MOUNT_X,):
        for sy in (1, -1):
            body = body + box_at(sx - 36, sx + 36, sy * 148, sy * 176, 2, 46)                        # mount pads
    for b in (1, 2):
        for xk in (-146.0, 146.0):                                                                   # knock-sensor bosses, valley side
            body = body + bank_plane(b) * (Pos(xk, -97.0, 185.0) * Rot(X=90) * Cylinder(11.0, 20.0, align=CMIN))
    # ---- cuts
    cuts = None
    for b, fs in ((1, -1), (2, 1)):
        c = bank_plane(b) * bank_cut(fs)
        cuts = c if cuts is None else cuts + c
    hm = P.main_width / 2
    for j in range(1, P.n_main):                                                                     # crank chamber bays
        x0, x1 = L.main_x(j) + hm, L.main_x(j + 1) - hm
        cuts = cuts + Pos(x0, 0, 0) * Rot(Y=90) * Cylinder(R_CAV, x1 - x0, align=CMIN)
    r_mb = P.main_dia / 2 + P.main_shell_thk
    cuts = cuts + Pos(L.main_x(1) - hm - 0.5, 0, 0) * Rot(Y=90) * Cylinder(r_mb, 2 * L.main_x(P.n_main) + 2 * hm + 1, align=CMIN)
    cuts = cuts + Pos(-XH - 1, 0, 0) * Rot(Y=90) * Cylinder(40.0, XH + L.main_x(1) - hm + 1.5, align=CMIN)      # front seal carrier bore
    cuts = cuts + Pos(L.main_x(P.n_main) + hm - 0.5, 0, 0) * Rot(Y=90) * Cylinder(40.0, 60, align=CMIN)           # rear shaft bore
    for sy in (1, -1):                                                                               # breathing windows through bulkheads
        cuts = cuts + Pos(L.main_x(1) + hm - 1, sy * 62, 58) * Rot(Y=90) * Cylinder(14.0, 2 * (L.main_x(P.n_main) - hm) + 2, align=CMIN)
    # oil galleries
    cuts = cuts + Pos(-XH - 1, GAL_C[0], GAL_C[1]) * Rot(Y=90) * Cylinder(P.oil_gallery_dia / 2, XH + 1 + 300.0, align=CMIN)
    cuts = cuts + Pos(XH - 26, INTER_YZ[0], INTER_YZ[1]) * Rot(Y=90) * Cylinder(12.6, 27.0, align=CMIN)      # intermediate-shaft bearing bore
    for sy in (1, -1):
        cuts = cuts + Pos(-XH - 1, sy * GAL_S[0], GAL_S[1]) * Rot(Y=90) * Cylinder(6.0, 2 * XH - 12, align=CMIN)
    for j in range(1, P.n_main + 1):                                                                 # gallery -> main bearing
        cuts = cuts + cyl_between((L.main_x(j), 0, GAL_C[1]), (L.main_x(j), 0, r_mb - 1), 3.5)
        for sy in (-1, 1):                                                                           # main bolt threads (4 per bulkhead)
            for yb in (50.0, 108.0):
                cuts = cuts + Pos(L.main_x(j), sy * yb, -1) * Cylinder(5.1, 44, align=CMIN)
    for c in L.CYLS:                                                                                 # piston-cooling jet feeds
        base, gal = jet_points(c)
        cuts = cuts + cyl_between(gal, base, 2.0)
    for sx in (MOUNT_X,):
        for sy in (1, -1):
            for dx in (-22, 22):
                cuts = cuts + Pos(sx + dx, sy * 162, 24) * Rot(X=-sy * 90) * Cylinder(5.1, 30, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    # valley breather port
    cuts = cuts + Pos(0, 0, 100) * Cylinder(12.0, 70, align=CMIN)
    body = body - cuts
    # keep only z >= 0 (split plane through the crank axis)
    body = body - box_at(-XH - 5, XH + 5, -400, 400, -200, 0)
    return body


JET_PAD = dict(y0=40.6, y1=44.2, z0=72.0, z1=84.0, half_w=5.0)      # mounting pad on the bore-relief wall (relief radius bore/2 + 1.5)
JET_TUBE_R, JET_NOZ_R, JET_ORIFICE_R = 3.0, 2.5, 1.1


def _jet_axes(c):
    """Cylinder frame used by the jet: origin q3 (crank-plane point of the bore axis), z along the bore,
    y = piston +Y (away from the bank centre plane, the rod-swing plane), x = y x z (piston +X)."""
    ex, eu, ev = L.bank_axes(c.bank)
    away = eu if c.row == "outer" else -eu
    d = c.d3
    lat = away - (away @ d) * d
    lat = lat / np.linalg.norm(lat)
    return np.cross(lat, d), lat, d


def jet_stream_tilt():
    """Inward tilt of the jet stream (rad) so that it crosses the gallery inlet (piston y = jet_inlet_y) when the
    inlet mouth is at mid stroke.  D-036: the nozzle exit has to sit outside the rod's swept envelope, 3 mm further out
    than the inlet, so the stream leans inwards by about 2 deg; over the stroke the spot moves +/-1.7 mm about the inlet."""
    hs = []                                                                    # pin height along the bore above q3
    for c in (L.CYL[1], L.CYL[2]):
        for a in range(0, 360, 5):
            pp = L.piston_pin_pos(c, a)
            hs.append(float((np.array([c.x, *pp]) - c.q3) @ c.d3))
    r = P.bore / 2 - P.piston_clear_dia / 2                                    # inlet mouth = z_belt - 1 = g3 - 3 in the piston frame
    g3 = P.comp_height - r * math.tan(math.radians(P.crown_tilt_axis)) - P.top_land - P.ring1_h - 3.2 - P.ring2_h - 2.3 - P.ring3_h
    lo, hi = min(hs) + g3 - 3.0, max(hs) + g3 - 3.0
    return math.atan2(P.jet_tip_lateral - P.jet_inlet_y, 0.5 * (lo + hi) - P.jet_tip_height), (lo, hi)


def jet_points(c):
    """(jet mounting point on the bore-relief wall, feeding point on the gallery) for cylinder c, global."""
    xp, lat, d = _jet_axes(c)
    base = c.q3 + d * (0.5 * (JET_PAD["z0"] + JET_PAD["z1"])) + lat * JET_PAD["y1"]
    if c.row == "outer":
        gal = np.array([c.x, (1 if c.bank == 1 else -1) * GAL_S[0], GAL_S[1]])
    else:
        gal = np.array([c.x, GAL_C[0], GAL_C[1]])
    return base, gal


def jet_solid():
    """Piston-cooling jet, local frame of _jet_axes (origin q3, z along the bore, y towards the gallery inlet side).
    Mounting pad on the bore-relief wall, a 6 mm tube that climbs inwards outside the rod's swept envelope and a short
    nozzle whose stream leans inwards by jet_stream_tilt() onto the piston's gallery inlet."""
    b, _ = jet_stream_tilt()
    s = np.array([0.0, -math.sin(b), math.cos(b)])
    tip = np.array([0.0, P.jet_tip_lateral, P.jet_tip_height])
    n0 = tip - 4.0 * s
    a0 = np.array([0.0, 41.4, 79.0])
    pad = box_at(-JET_PAD["half_w"], JET_PAD["half_w"], JET_PAD["y0"], JET_PAD["y1"], JET_PAD["z0"], JET_PAD["z1"])
    tube = cyl_between(tuple(a0), tuple(n0), JET_TUBE_R) + Pos(*n0) * Sphere(JET_TUBE_R)
    noz = cyl_between(tuple(n0), tuple(tip), JET_NOZ_R)
    bore = cyl_between(tuple(n0 - 2.0 * s), tuple(tip + 1.0 * s), JET_ORIFICE_R)
    return pad + tube + noz - bore


def jet_location(c):
    xp, lat, d = _jet_axes(c)
    return Location(Plane(origin=tuple(c.q3), x_dir=tuple(xp), z_dir=tuple(d)))


def bearing_insert():
    """Cast-in iron lower main-bearing cover (SSP 248), local: bearing axis = X through the origin."""
    r_mb = P.main_dia / 2 + P.main_shell_thk
    ins = box_at(-P.main_width / 2, P.main_width / 2, -64, 64, -58, 0)
    ins = ins - Rot(Y=90) * Cylinder(r_mb, 40, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    for sy in (-1, 1):
        ins = ins - Pos(0, sy * 50.0, -60) * Cylinder(6.3, 62, align=CMIN)
    return ins


def bedplate():
    """Crankcase lower section: one-piece bearing support (pockets for the nine cast-in bearing covers)."""
    zb = -72.0
    body = box_at(-XH, XH, -150, 150, zb, 0)
    hm = P.main_width / 2
    cuts = None
    for j in range(1, P.n_main):
        x0, x1 = L.main_x(j) + hm, L.main_x(j + 1) - hm
        c = Pos(x0, 0, 0) * Rot(Y=90) * Cylinder(R_CAV, x1 - x0, align=CMIN)
        c = c + box_at(x0, x1, -84, 84, zb - 1, -40)                                               # drain windows to the sump
        cuts = c if cuts is None else cuts + c
    r_mb = P.main_dia / 2 + P.main_shell_thk
    cuts = cuts + Pos(-XH - 1, 0, 0) * Rot(Y=90) * Cylinder(40.0, XH + L.main_x(1) - hm + 1.5, align=CMIN)
    cuts = cuts + Pos(L.main_x(P.n_main) + hm - 0.5, 0, 0) * Rot(Y=90) * Cylinder(40.0, 60, align=CMIN)
    ins = bearing_insert()
    for j in range(1, P.n_main + 1):
        cuts = cuts + Pos(L.main_x(j), 0, 0) * ins
        cuts = cuts + Pos(L.main_x(j), 0, 0) * Rot(Y=90) * Cylinder(r_mb, P.main_width, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        for sy in (-1, 1):
            for yb in (50.0, 108.0):
                cuts = cuts + Pos(L.main_x(j), sy * yb, zb - 1) * Cylinder(6.3, -zb + 2, align=CMIN)
    for i in range(14):                                                                              # perimeter bolts to the upper section
        for sy in (-1, 1):
            cuts = cuts + Pos(-305 + i * 46.9, sy * 140, zb - 1) * Cylinder(4.5, -zb + 2, align=CMIN)
    return body - cuts


SCAV_Y = (-105.0, -35.0, 35.0, 105.0)


def sump():
    """Dry-sump pan with four scavenge ports on the front face (one per longitudinal collector channel)."""
    z0, z1 = -106.0, -72.0
    pan = box_at(-XH, XH, -150, 150, z0, z1)
    cav = box_at(-XH + 8, XH - 8, -140, 140, z0 + 6, z1 + 1)
    for xb in (-146.0, 0.0, 146.0):                                                                  # baffles separating the scavenge bays
        cav = cav - box_at(xb - 2.5, xb + 2.5, -140, 140, z0 + 6, z1 - 10)
    pan = pan - cav
    for ys in SCAV_Y:                                                                                # scavenge ports on the front face
        pan = pan + (Pos(-XH - 20, ys, z0 + 17) * Rot(Y=90) * Cylinder(15.0, 22.0, align=CMIN))
        pan = pan - (Pos(-XH - 21, ys, z0 + 17) * Rot(Y=90) * Cylinder(10.0, 34.0, align=CMIN))
    for i in range(14):
        for sy in (-1, 1):
            pan = pan - Pos(-305 + i * 46.9, sy * 145, z0 - 1) * Cylinder(3.4, 40, align=CMIN)
    return pan


def main_shell():
    """Half main-bearing shell (upper half; local: axis X, shell in z >= 0).  The lower half is the same part turned 180 deg."""
    r_mb = P.main_dia / 2 + P.main_shell_thk
    w = P.main_width - 2.0
    sh = Rot(Y=90) * (Cylinder(r_mb, w, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                      - Cylinder(P.main_dia / 2 + 0.027, w + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    sh = sh & Pos(0, 0, 0.05) * Box(100, 100, 60, align=CMIN)
    sh = sh - Cylinder(3.5, 60, align=CMIN)                                                          # oil hole
    sh = sh - (Rot(Y=90) * (Cylinder(P.main_dia / 2 + 1.0, 4.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                            - Cylinder(P.main_dia / 2 - 1, 5.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))))   # 180 deg oil groove
    return sh


def head_gasket():
    """Multi-layer steel head gasket of one bank (bank-local, lower face on the deck)."""
    dk = P.deck_height
    g = box_at(-XH, XH, -W_TOP, W_TOP, dk, dk + P.gasket_thk)
    cut = None
    for i in range(1, 9):
        p, d = axis_local(i)
        c = cyl_between(p + d * (P.s_deck - 5), p + d * (P.s_deck + 8), P.gasket_bore / 2)
        cut = c if cut is None else cut + c
    for x, u in coolant_hole_xy():
        cut = cut + Pos(x, u, dk - 1) * Cylinder(3.0, 4, align=CMIN)                                 # metering holes
    for x, u in head_bolt_xy():
        cut = cut + Pos(x, u, dk - 1) * Cylinder(6.0, 4, align=CMIN)
    for x, u in DRAIN_XY:
        cut = cut + Pos(x, u, dk - 1) * Cylinder(8.5, 4, align=CMIN)
    return g - cut
