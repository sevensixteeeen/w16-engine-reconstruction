"""Timing drive at the flywheel end: primary duplex chain crank -> intermediate shaft, four single secondary chains
intermediate shaft -> camshafts (the camshafts of a head are only 54 mm apart, so their sprockets sit in separate
planes), guides, hydraulic tensioners, phasers, chain cover."""
from __future__ import annotations
import math
import numpy as np
from build123d import Align, Box, Circle, Cylinder, Location, Plane, Pos, Rot, extrude, make_hull

from ..params import P
from .. import layout as L
from .common import CMIN, box_at, cyl_between, poly
from .block import XH

D2R = math.pi / 180
INTER = (0.0, 118.0)                       # intermediate shaft axis (y, z)
P1, Z_CRANK, Z_INT1 = 9.525, 28, 42        # primary: 3/8" duplex roller chain, ratio 1.5
P2, Z_INT2, Z_CAM = 8.0, 21, 28            # secondary: 8 mm sleeve chains, ratio 4/3  (total 2.0)
X_PRIM = XH + 12.0                         # centre plane of the primary chain
ROWS = {(1, "ex"): XH + 25.0, (2, "in"): XH + 29.0, (1, "in"): XH + 35.0, (2, "ex"): XH + 39.0}


def pitch_r(p, z):
    return p / (2 * math.sin(math.pi / z))


def cam_axis_yz(bank, kind):
    cam_u = -P.cam_u if kind == "in" else P.cam_u
    g = L.to_global(bank, 0.0, cam_u, P.head_face_height + P.cam_w)
    return float(g[1]), float(g[2])


def sprocket(p, z, width, bore_r, rows=1, row_gap=0.0):
    rp = pitch_r(p, z)
    rr, rt = rp - 0.3 * p, rp + 0.28 * p
    pts = []
    for k in range(z):
        a0 = 2 * math.pi * k / z
        da = 2 * math.pi / z
        for f, r in ((0.0, rr), (0.22, rr), (0.40, rt), (0.60, rt), (0.78, rr)):
            a = a0 + f * da
            pts.append((r * math.cos(a), r * math.sin(a)))
    disc = extrude(poly(pts), amount=width)
    body = None
    for i in range(rows):
        d = Pos(0, 0, i * (width + row_gap)) * disc
        body = d if body is None else body + d
    tot = rows * width + (rows - 1) * row_gap
    body = body + Cylinder(rr - 2.0, tot, align=CMIN)
    return body - Pos(0, 0, -1) * Cylinder(bore_r, tot + 2, align=CMIN)


def chain_path(c1, r1, c2, r2, pitch):
    """Link centre positions and tangents of an open chain loop around two sprockets (2-D, in the chain plane)."""
    c1, c2 = np.array(c1, float), np.array(c2, float)
    d = np.linalg.norm(c2 - c1)
    e = (c2 - c1) / d
    th = math.acos((r1 - r2) / d)
    rot = lambda v, a: np.array([v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)])
    na, nb = rot(e, th), rot(e, -th)
    A1, A2, B1, B2 = c1 + r1 * na, c2 + r2 * na, c1 + r1 * nb, c2 + r2 * nb
    span = np.linalg.norm(A2 - A1)
    arc1 = r1 * (2 * math.pi - 2 * th)
    arc2 = r2 * 2 * th
    total = 2 * span + arc1 + arc2
    n = int(round(total / pitch))
    step = total / n
    out = []
    a_na = math.atan2(na[1], na[0])
    for k in range(n):
        s = k * step
        if s < span:                                        # span A: A1 -> A2
            t = (A2 - A1) / span
            out.append((A1 + t * s, t))
        elif s < span + arc2:                               # around sprocket 2 from A2 to B2 (short way, through e)
            a = a_na - (s - span) / r2
            out.append((c2 + r2 * np.array([math.cos(a), math.sin(a)]), np.array([math.sin(a), -math.cos(a)])))
        elif s < 2 * span + arc2:                           # span B: B2 -> B1
            t = (B1 - B2) / span
            out.append((B2 + t * (s - span - arc2), t))
        else:                                               # around sprocket 1 from B1 back to A1 (long way)
            a = a_na - 2 * th - (s - 2 * span - arc2) / r1
            out.append((c1 + r1 * np.array([math.cos(a), math.sin(a)]), np.array([math.sin(a), -math.cos(a)])))
    return out, dict(n_links=n, length=total, span=span, wrap1=math.degrees(2 * math.pi - 2 * th), wrap2=math.degrees(2 * th),
                     A1=A1, A2=A2, B1=B1, B2=B2, na=na, nb=nb)


def link_solid(pitch, width):
    """One chain link (two side plates and a roller); local: x along the chain, z across the chain width."""
    h = 0.82 * pitch
    plate = box_at(-0.48 * pitch, 0.48 * pitch, -h / 2, h / 2, 0, 1.0)
    return plate + Pos(0, 0, width - 1.0) * plate + Cylinder(0.3 * pitch, width, align=CMIN)


def chain_locations(path, x_plane, width):
    locs = []
    for p, t in path:
        locs.append(Location(Plane(origin=(x_plane - width / 2, float(p[0]), float(p[1])), x_dir=(0, float(t[0]), float(t[1])), z_dir=(1, 0, 0))))
    return locs


def guide_rail(a, b, n_out, x_plane, width, pitch, bow=0.0):
    """Polymer-faced guide rail along a chain span from point a to b, on the outside (n_out) of the chain."""
    a, b = np.array(a), np.array(b)
    t = (b - a) / np.linalg.norm(b - a)
    ln = np.linalg.norm(b - a) * 0.78
    mid = 0.5 * (a + b) + n_out * (0.41 * pitch + 0.6 + 3.0)
    rail = Box(ln, 6.0, width + 3.0)
    return Location(Plane(origin=(x_plane, float(mid[0]), float(mid[1])), x_dir=(0, float(t[0]), float(t[1])), z_dir=(1, 0, 0))) * rail


def tensioner_body():
    """Hydraulic chain tensioner (local: plunger axis +Z, plunger tip at z = 0)."""
    return Pos(0, 0, -44) * Cylinder(9.0, 36.0, align=CMIN) + Pos(0, 0, -10) * Cylinder(5.0, 10.0, align=CMIN) + \
        Pos(0, 0, -44) * Box(34, 12, 8, align=CMIN)


def tensioner_location(a, b, n_out, x_plane, pitch):
    a, b = np.array(a), np.array(b)
    mid = 0.5 * (a + b) + n_out * (0.41 * pitch + 0.6 + 6.0)
    t = (b - a) / np.linalg.norm(b - a)
    return Location(Plane(origin=(x_plane, float(mid[0]), float(mid[1])), x_dir=(1, 0, 0), z_dir=(0, float(-n_out[0]), float(-n_out[1]))))


def phaser():
    """Vane-type cam phaser with its sprocket (local: cam axis = Z, sprocket plane centred at z = 0, phaser body at z < 0)."""
    sp = Pos(0, 0, -1.75) * sprocket(P2, Z_CAM, 3.5, 12.0)
    body = Pos(0, 0, -18.0) * (Cylinder(26.0, 16.5, align=CMIN) - Cylinder(12.0, 16.5, align=CMIN))
    return sp + body


def intermediate_shaft():
    """Intermediate shaft with its three sprocket seats (global, axis along X)."""
    y, z = INTER
    return Pos(XH - 24, y, z) * Rot(Y=90) * Cylinder(12.5, 65.0, align=CMIN)


def chain_cover():
    """Rear chain housing (CFRP, per the published Chiron description), global frame."""
    lower = make_hull((Circle(66.0) + Pos(INTER[0], INTER[1]) * Circle(78.0) + Pos(0, 215.0) * Circle(60.0)).edges())
    pts = []
    for b in (1, 2):
        for k in ("in", "ex"):
            y, z = cam_axis_yz(b, k)
            pts.append(Pos(y, z) * Circle(50.0))
    sk = pts[0]
    for c in pts[1:]:
        sk = sk + c
    upper = make_hull(sk.edges())
    pl = Plane(origin=(XH, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    d_lo, d_up, wall = 46.0, 64.0, 3.5
    from build123d import offset
    shell = (extrude(pl * lower, amount=d_lo) + extrude(pl * upper, amount=d_up))
    inner = (extrude(pl * offset(lower, amount=-wall), amount=d_lo - wall) + extrude(pl * offset(upper, amount=-wall), amount=d_up - wall))
    cover = shell - inner
    cover = cover - Pos(XH - 1, 0, 0) * Rot(Y=90) * Cylinder(48.5, d_up + 2, align=CMIN)            # crank seal bore
    return cover
