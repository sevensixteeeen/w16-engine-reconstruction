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
    n = 2 * int(round(total / pitch / 2))          # even link count (no offset link); the tensioner takes up the difference
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
    """Hydraulic chain tensioner (local: plunger axis +Z, plunger tip at z = 0; local x = crank axis).  The mounting flange
    lies in the chain plane (8 mm across it): it used to run 34 mm along the crank axis, through the neighbouring chain planes
    (Fix B2, 2026-11-21)."""
    return Pos(0, 0, -44) * Cylinder(9.0, 36.0, align=CMIN) + Pos(0, 0, -10) * Cylinder(5.0, 10.0, align=CMIN) + \
        Pos(0, 0, -44) * Box(8, 26, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))


def _tens_axis(a, b, n_out, phi):
    s = (np.array(b) - np.array(a)) / np.linalg.norm(np.array(b) - np.array(a))
    return math.cos(math.radians(phi)) * np.array(n_out) + math.sin(math.radians(phi)) * s, s


def _tens_tip(a, b, n_out, pitch, t, phi):
    """Plunger tip on the back of the tensioner rail; an inclined plunger stands off by its radius x sin(phi)."""
    a, b = np.array(a), np.array(b)
    return a + t * (b - a) + np.array(n_out) * (0.41 * pitch + 0.6 + 6.0 + 5.0 * math.sin(math.radians(phi)) + 0.2 * (phi > 0))


def tensioner_location(a, b, n_out, x_plane, pitch, t=0.5, phi=0.0):
    """Tensioner on the slack span a -> b (a at the driving sprocket), at fraction t, body inclined by phi deg from the span
    normal towards b (the plunger still acts on the rail)."""
    ax, _ = _tens_axis(a, b, n_out, phi)
    tip = _tens_tip(a, b, n_out, pitch, t, phi)
    return Location(Plane(origin=(x_plane, float(tip[0]), float(tip[1])), x_dir=(1, 0, 0), z_dir=(0, float(-ax[0]), float(-ax[1]))))


def tensioner_footprint(a, b, n_out, pitch, t, phi, step=2.0):
    """In-plane points of the tensioner envelope (body, plunger, flange) for clearance checks."""
    ax, _ = _tens_axis(a, b, n_out, phi)
    lat = np.array([-ax[1], ax[0]])
    tip = _tens_tip(a, b, n_out, pitch, t, phi)
    pts = []
    for u0, u1, w in ((0.0, 10.0, 5.0), (8.0, 44.0, 9.0), (36.0, 44.0, 13.0)):
        for u in np.arange(u0, u1 + 1e-9, step):
            for v in np.arange(-w, w + 1e-9, step):
                pts.append(tip + u * ax + v * lat)
    return np.array(pts)


def part_points(inf, pth, pitch, r_int, r_cam, c_int, c_cam):
    """In-plane sample points with their half-size (mm) of one secondary drive: chain links, guide and tensioner rails,
    intermediate sprocket, cam sprocket / phaser."""
    out = [(np.array(p), 0.41 * pitch) for p, _ in pth]
    for a, b, n in ((inf["A1"], inf["A2"], inf["na"]), (inf["B1"], inf["B2"], inf["nb"])):
        a, b, n = np.array(a), np.array(b), np.array(n)
        mid = 0.5 * (a + b) + n * (0.41 * pitch + 0.6 + 3.0)
        t = (b - a) / np.linalg.norm(b - a)
        ln = np.linalg.norm(b - a) * 0.78
        for u in np.linspace(-ln / 2, ln / 2, int(ln / 2) + 2):
            out.append((mid + u * t, 3.0))
    out.append((np.array(c_int), r_int + 4.0))
    out.append((np.array(c_cam), r_cam + 4.0))
    return out


R2I, R2C = None, None


def secondary_layout(clear=3.0):
    """The four secondary drives with their tensioner placements: list of dicts (key, x_plane, path, info, t, phi, resolved).
    Each tensioner is placed on its slack span (B) at the first (phi, t) - smallest inclination, then t nearest 0.6 - whose
    envelope keeps `clear` mm from every part of the other drives within axial reach (Fix B2, 2026-11-21: on each bank the
    two loops are nested 10 mm apart, and the inner drive's tensioner used to cross the outer drive's chain and rail)."""
    r2i, r2c = pitch_r(P2, Z_INT2), pitch_r(P2, Z_CAM)
    drives = []
    for (b, kind), xr in ROWS.items():
        cy, cz = cam_axis_yz(b, kind)
        pth, inf = chain_path(INTER, r2i, (cy, cz), r2c, P2)
        drives.append(dict(key=(b, kind), x_plane=xr, path=pth, info=inf, cam=(cy, cz),
                           pts=part_points(inf, pth, P2, r2i, r2c, INTER, (cy, cz))))
    reach = 9.0 + 3.75 + 1.0                           # tensioner half-width across the plane + rail half-width + margin
    for d in drives:
        inf = d["info"]
        others = [o for o in drives if o is not d and abs(o["x_plane"] - d["x_plane"]) < reach]
        obst = [(p, r) for o in others for p, r in o["pts"]] + [(p, 9.0) for o in others if "tens_pts" in o for p in o["tens_pts"]]
        P_o = np.array([p for p, r in obst]); R_o = np.array([r for p, r in obst])
        dmin_at = lambda t, phi: float((np.sqrt(((tensioner_footprint(inf["B1"], inf["B2"], inf["nb"], P2, t, phi)[:, None, :]
                                                  - P_o[None, :, :]) ** 2).sum(-1)) - R_o[None, :]).min())
        best = None
        for phi in (0.0, 15.0, 30.0, 45.0):            # beyond ~45 deg the plunger no longer tensions the chain
            for t in sorted(np.linspace(0.3, 0.9, 25), key=lambda x: abs(x - 0.6)):
                dm = dmin_at(t, phi)
                if dm >= clear:
                    best = (t, phi, dm)
                    break
            if best:
                break
        # no clear position (inner drive of a nested pair: the free depth inside the neighbouring loop is smaller than a
        # hydraulic tensioner) -> keep the original mid-span perpendicular position and report it as unresolved
        d["resolved"] = best is not None
        d["t"], d["phi"], d["clearance"] = best if best else (0.5, 0.0, dmin_at(0.5, 0.0))
        d["tens_pts"] = tensioner_footprint(inf["B1"], inf["B2"], inf["nb"], P2, d["t"], d["phi"])
    return drives


def phaser():
    """Vane-type cam phaser with its sprocket (local: cam axis = Z, sprocket plane centred at z = 0, phaser body at z < 0)."""
    sp = Pos(0, 0, -1.75) * sprocket(P2, Z_CAM, 3.5, 12.0)
    body = Pos(0, 0, -18.0) * (Cylinder(26.0, 16.5, align=CMIN) - Cylinder(12.0, 16.5, align=CMIN))
    return sp + body


def intermediate_shaft():
    """Intermediate shaft with its three sprocket seats (global, axis along X)."""
    y, z = INTER
    return Pos(XH - 24, y, z) * Rot(Y=90) * Cylinder(12.5, 65.0, align=CMIN)


def _hull_poly(points):
    from scipy.spatial import ConvexHull
    pts = np.array(points)
    h = ConvexHull(pts)
    return poly([(float(x), float(y)) for x, y in pts[h.vertices]])


def chain_cover():
    """Rear chain housing (CFRP, per the published Chiron description), global frame.
    Fix B1 (2026-11-21): the secondary-drive region is the convex hull, per bank, of the real chain, guide-rail, sprocket and
    tensioner footprints plus 5 mm clearance and the 3.5 mm wall (the old outline - circles round the cam axes and a lower lobe -
    left the chain spans and guide rails outside the housing); that region and the crank / intermediate region are 50 mm deep
    (46.5 mm inside: 3.75 mm behind the outermost guide rail, 14 mm in front of the flex plate at XH + 64); the cam / phaser
    region stays 64 mm deep."""
    wall, gap = 3.5, 5.0
    base_pts = []
    for (c, r) in (((0.0, 0.0), 66.0), (INTER, 78.0), ((0.0, 215.0), 60.0)):
        for a in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            base_pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    ring = [(math.cos(a), math.sin(a)) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    lower = None
    for side in (1, -1):
        pts = list(base_pts)
        for d in secondary_layout():
            if np.sign(d["cam"][0]) != side:
                continue
            for p, r in d["pts"] + [(q, 0.0) for q in d["tens_pts"]]:
                rr = r + gap + wall
                pts += [(p[0] + rr * cx, p[1] + rr * cy) for cx, cy in ring]
        h = _hull_poly(pts)
        lower = h if lower is None else lower + h
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
    d_lo, d_up = 50.0, 64.0
    from build123d import offset
    shell = (extrude(pl * lower, amount=d_lo) + extrude(pl * upper, amount=d_up))
    inner = (extrude(pl * offset(lower, amount=-wall), amount=d_lo - wall) + extrude(pl * offset(upper, amount=-wall), amount=d_up - wall))
    cover = shell - inner
    cover = cover - Pos(XH - 1, 0, 0) * Rot(Y=90) * Cylinder(48.5, d_up + 2, align=CMIN)            # crank seal bore
    return cover
