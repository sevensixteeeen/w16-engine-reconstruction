"""Shared CAD helpers: frames, primitive builders, the part registry and mass properties."""
from __future__ import annotations
import math
import os
from dataclasses import dataclass, field
import numpy as np
from build123d import (Align, Axis, Box, Circle, Color, Compound, Cylinder, FilletPolyline, Helix, Line, Location, Part,
                       Plane, Polygon, Polyline, Pos, Rectangle, Rot, Sphere, Spline, Torus, Vector, extrude, loft,
                       make_hull, revolve, sweep)

from ..params import P, MATERIALS
from .. import layout as L

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CMIN = (Align.CENTER, Align.CENTER, Align.MIN)
CCC = (Align.CENTER, Align.CENTER, Align.CENTER)

MAT = {  # short keys -> material table names
    "al_cast": "AlSi7Mg0.3-T6 (A356)", "al_forged": "AlSi12CuMgNi (forged 4032-T6)", "steel_qt": "42CrMo4 QT + nitrided",
    "ti": "Ti-6Al-4V", "inconel": "Inconel 713C", "cast_steel": "D5S Ni-resist / 1.4849 cast steel",
    "case_steel": "16MnCr5 case hardened", "cfrp": "CFRP (prepreg, quasi-iso)", "steel": "Steel (generic fastener 10.9/12.9)",
    "polymer": "Elastomer / polymer",
}
COLORS = {
    "al_cast": (0.72, 0.74, 0.77), "al_forged": (0.80, 0.80, 0.78), "steel_qt": (0.45, 0.47, 0.50), "ti": (0.62, 0.60, 0.56),
    "inconel": (0.50, 0.42, 0.36), "cast_steel": (0.40, 0.33, 0.30), "case_steel": (0.55, 0.56, 0.58), "cfrp": (0.12, 0.12, 0.13),
    "steel": (0.35, 0.36, 0.38), "polymer": (0.10, 0.10, 0.10),
}


def V(p):
    if isinstance(p, Vector):
        return p
    return Vector(float(p[0]), float(p[1]), float(p[2]))


def bank_plane(bank, v0=0.0):
    """Plane whose local (X, Y, Z) are the bank-local (x_l, u, v - v0) coordinates."""
    ex, eu, ev = L.bank_axes(bank)
    return Plane(origin=tuple(v0 * ev), x_dir=tuple(ex), z_dir=tuple(ev))


def head_plane(bank):
    """Bank-local frame with its origin on the head joint face (w = v - head_face_height)."""
    return bank_plane(bank, P.head_face_height)


def cyl_between(p0, p1, r):
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    return Plane(origin=p0, z_dir=d.normalized()) * Cylinder(r, d.length, align=CMIN)


def box_at(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))


def _rod_chain(pts, r):
    """Fallback pipe body: cylinders joined by spheres (always a valid solid)."""
    body = None
    for a, b in zip(pts[:-1], pts[1:]):
        c = cyl_between(a, b, r)
        body = c if body is None else body + c
    for p in pts[1:-1]:
        body = body + Pos(p.X, p.Y, p.Z) * Sphere(r)
    return body


def _sweep_solid(pts, r, bend):
    """Swept round bar along a filleted poly-line, or None if the sweep is not possible / not valid."""
    if len(pts) == 2:
        return cyl_between(pts[0], pts[1], r)
    seg = min((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))
    rb = min(bend or 1.6 * r, 0.45 * seg)
    if rb < 1.15 * r:
        return None
    try:
        path = FilletPolyline(*pts, radius=rb)
        s = sweep(Plane(origin=path @ 0, z_dir=path % 0) * Circle(r), path=path)
        if s.is_valid and len(s.solids()) == 1 and s.volume > 0:
            return s
    except Exception:
        pass
    return None


def tube(points, ro, ri=0.0, bend=None):
    """Round pipe along a poly-line with filleted corners.  Outer and inner bodies are swept separately along the
    same centre line; if any sweep (or the subtraction) fails, a mitred cylinder/sphere chain is used for both."""
    pts = [V(p) for p in points]
    ext = pts
    if ri > 0:
        d0 = (pts[0] - pts[1]).normalized() * 1.0
        d1 = (pts[-1] - pts[-2]).normalized() * 1.0
        ext = [pts[0] + d0] + pts[1:-1] + [pts[-1] + d1]
    outer = _sweep_solid(pts, ro, bend or 1.6 * ro)
    inner = _sweep_solid(ext, ri, bend or 1.6 * ro) if ri > 0 else None
    if outer is not None and (ri <= 0 or inner is not None):
        res = outer if ri <= 0 else outer - inner
        if res.is_valid and len(res.solids()) == 1:
            return res
    res = _rod_chain(pts, ro)
    return res if ri <= 0 else res - _rod_chain(ext, ri)


def poly(points):
    return Polygon(*points, align=None)


def hex_bolt(d, length, head_h=None, flange=False):
    """Simple hex/flange bolt, shank along -Z from the under-head plane at z = 0."""
    head_h = head_h or 0.65 * d
    af = 1.5 * d
    head = extrude(Polygon(*[(af / math.sqrt(3) * math.cos(math.radians(60 * i)), af / math.sqrt(3) * math.sin(math.radians(60 * i)))
                             for i in range(6)], align=None), amount=head_h)
    b = head + Pos(0, 0, -length) * Cylinder(d / 2, length, align=CMIN)
    if flange:
        b = b + Cylinder(0.95 * d, 0.18 * d, align=CMIN)
    return b


# ------------------------------------------------------------------ registry
@dataclass
class PartDef:
    pn: str                   # part number
    name: str
    shape: object             # geometry in its own local frame
    material: str             # key of MAT
    group: str                # CAD sub-assembly (1..15 of the brief)
    locs: list = field(default_factory=list)      # instance Locations at the reference crank angle
    process: str = ""
    custom: bool = True       # custom-engineered (True) vs. purchased/catalogue (False)
    note: str = ""
    moving: str = ""          # kinematic class: '', 'crank', 'piston', 'rod', 'cam', 'valve', ...
    inst: list = field(default_factory=list)      # per-instance tags (e.g. cylinder numbers)
    mass_override: float | None = None

    @property
    def qty(self):
        return max(len(self.locs), 1)

    @property
    def volume_cm3(self):
        return self.shape.volume / 1000.0

    @property
    def mass(self):
        if self.mass_override is not None:
            return self.mass_override
        return self.shape.volume * 1e-9 * MATERIALS[MAT[self.material]]["rho"]

    def placed(self):
        out = []
        for loc in (self.locs or [Location()]):
            s = loc * self.shape
            out.append(s)
        return out


class Registry:
    def __init__(self):
        self.parts: dict[str, PartDef] = {}

    def add(self, pn, name, shape, material, group, locs=None, **kw):
        if pn in self.parts:
            raise ValueError(f"duplicate part number {pn}")
        pd = PartDef(pn, name, shape, material, group, list(locs) if locs else [Location()], **kw)
        self.parts[pn] = pd
        return pd

    def __getitem__(self, pn):
        return self.parts[pn]

    def by_group(self):
        g = {}
        for p in self.parts.values():
            g.setdefault(p.group, []).append(p)
        return g

    def total_mass(self):
        return sum(p.mass * p.qty for p in self.parts.values())


GROUPS = {
    "01": "Crankcase and cylinder block", "02": "Cylinder heads", "03": "Piston assemblies", "04": "Connecting rods",
    "05": "Crankshaft", "06": "Valvetrain", "07": "Timing system", "08": "Turbochargers", "09": "Intake system",
    "10": "Exhaust system", "11": "Fuel injection and ignition", "12": "Lubrication system", "13": "Cooling system",
    "14": "Accessory system", "15": "Fasteners and interfaces",
}


def rot_x(deg):
    return Rot(X=deg)


def mass_props(shape, rho):
    """Mass (kg) and centre of mass (mm) of a solid of uniform density rho (kg/m3)."""
    from build123d import CenterOf
    c = shape.center(CenterOf.MASS)
    return shape.volume * 1e-9 * rho, np.array([c.X, c.Y, c.Z])
