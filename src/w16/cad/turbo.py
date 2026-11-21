"""Turbocharger CAD (four identical-size units, two mirror-image hands).

Local frame: shaft axis = X, turbine at -X (axial outlet facing -X), compressor at +X (axial inlet facing +X).
Sizes come from the 1-D matching (08_SIMULATIONS/analytical/results.json).  Wheel geometry is representative
(straight radial blades between a hub and a shroud contour) - it is NOT an aerodynamic design.
"""
from __future__ import annotations
import json
import math
import os
import numpy as np
from build123d import Align, Axis, Box, Circle, Cylinder, Location, Plane, Pos, Rot, extrude, loft, revolve

from .common import CMIN, ROOT, box_at, cyl_between, poly

D2R = math.pi / 180


def sizing():
    with open(os.path.join(ROOT, "08_SIMULATIONS", "analytical", "results.json"), encoding="utf-8") as fh:
        c = json.load(fh)["compressor"]
    return dict(d2c=c["D2_comp"], d1c=c["D1_comp"], dt=c["D_turb"], dte=c["D_turb_exd"])


S = sizing()
X_C, X_T = 45.0, -46.0            # volute centre planes of compressor / turbine
Y_IN = -48.0                      # turbine inlet flange lateral offset
Z_IN = 78.0                       # turbine inlet flange height
Y_CO, Z_CO = 52.0, 96.0           # compressor outlet position (points +Z)
X_TO, X_CI = -85.0, 95.0          # turbine outlet face, compressor inlet face


def _section(theta, r_center, r_tube, x):
    """Circle of radius r_tube in the meridional plane at angle theta (about X), centre at radius r_center."""
    c, s = math.cos(theta), math.sin(theta)
    origin = (x, r_center * c, r_center * s)
    return Plane(origin=origin, x_dir=(1, 0, 0), z_dir=(0, -s, c)) * Circle(r_tube)


def volute(x, r_wheel, r0, r1, th0, th1, n=9):
    """Solid scroll around the X axis whose tube radius grows from r0 to r1 between angles th0 and th1 (deg)."""
    secs = []
    for t in np.linspace(th0, th1, n):
        f = (t - th0) / (th1 - th0)
        rt = r0 + (r1 - r0) * f
        secs.append(_section(t * D2R, r_wheel + rt, rt, x))
    return loft(secs)


def wheel(kind):
    """Compressor ('c') or turbine ('t') wheel: hub of revolution + straight radial blades.  Axis X."""
    if kind == "c":
        r2, r1, ln, nb = S["d2c"] / 2, S["d1c"] / 2, 30.0, 12
        hub = [(0, 0), (0, 9.0), (8, 10.5), (18, 16.0), (25, 26.0), (28, r2 - 1.0), (30, r2 - 1.0), (30, 0)]
        blade = [(1, 9.5), (1, r1), (9, r1 + 1.0), (18, r1 + 4.5), (24, r2 - 3.5), (27.5, r2), (29.5, r2), (29.5, r2 - 2), (25, 26.0), (18, 16.0), (8, 10.5)]
    else:
        r2, r1, ln, nb = S["dt"] / 2, S["dte"] / 2, 32.0, 11
        hub = [(0, 0), (0, 10.0), (10, 12.0), (20, 18.0), (27, 28.0), (30, r2 - 1.0), (32, r2 - 1.0), (32, 0)]
        blade = [(1, 10.5), (1, r1), (10, r1 + 0.5), (20, r1 + 2.5), (27, r2 - 2.0), (30, r2), (31.5, r2), (31.5, r2 - 2), (27, 28.0), (20, 18.0), (10, 12.0)]
    body = revolve(Plane.XY * poly(hub), axis=Axis.X)
    bl = extrude(Plane.XY.offset(-0.6) * poly(blade), amount=1.2)
    for k in range(nb):
        b = Rot(X=360.0 * k / nb) * bl
        if kind == "c" and k % 2 == 1:                       # splitter blades start further downstream
            b = b - box_at(-1, 11, -100, 100, -100, 100)
        body = body + b
    return body


def assembly_parts():
    """Dict of turbocharger part solids in the turbo frame."""
    r2c, r2t = S["d2c"] / 2, S["dt"] / 2
    # ---------------- compressor housing: scroll + inlet snout + tangential outlet + back flange
    sc = volute(X_C + 2, r2c + 9.0, 9.0, 22.0, 100.0, 440.0)
    out_c = cyl_between((X_C + 2, Y_CO + 0.0, 20.0), (X_C + 2, Y_CO + 0.0, Z_CO), 24.0)
    snout = cyl_between((X_C + 14, 0, 0), (X_CI, 0, 0), S["d1c"] / 2 + 6.0)
    disc = cyl_between((X_C - 12, 0, 0), (X_C + 16, 0, 0), r2c + 12.0)
    ch = sc + out_c + snout + disc
    cav = volute(X_C + 2, r2c + 9.0, 6.5, 19.0, 100.0, 440.0) + cyl_between((X_C + 2, Y_CO, 20.0), (X_C + 2, Y_CO, Z_CO + 1), 20.5)
    cav = cav + cyl_between((X_C - 2, 0, 0), (X_C + 6, 0, 0), r2c + 16.0)                   # vaneless diffuser
    cav = cav + cyl_between((X_C - 13, 0, 0), (X_C + 6, 0, 0), r2c + 0.5)                   # wheel pocket
    cav = cav + cyl_between((X_C + 5, 0, 0), (X_CI + 1, 0, 0), S["d1c"] / 2 + 0.6)          # inducer bore
    comp_housing = ch - cav
    # ---------------- turbine housing: scroll + tangential inlet (twin-entry divider omitted) + outlet + waste-gate port
    st = volute(X_T, r2t + 12.0, 23.0, 9.0, 115.0, 455.0)
    inlet = cyl_between((X_T, Y_IN, 22.0), (X_T, Y_IN, Z_IN), 29.0)
    flange = cyl_between((X_T, Y_IN, Z_IN - 9), (X_T, Y_IN, Z_IN), 40.0)
    outlet = cyl_between((X_T - 10, 0, 0), (X_TO, 0, 0), S["dte"] / 2 + 14.0)
    oflange = cyl_between((X_TO, 0, 0), (X_TO + 8, 0, 0), S["dte"] / 2 + 24.0)
    disc_t = cyl_between((X_T - 14, 0, 0), (X_T + 16, 0, 0), r2t + 13.0)
    # Fix F1/F2 (2026-11-21): the by-pass boss ends inside the outlet body (X_T - 34; it ran to X_T - 44, 5 mm past the outlet
    # face, into the down-pipe / pre-catalyst bolted there); its end (r 13 at 27.2 mm from the axis) lies within the outlet r 46.7
    wg_boss = cyl_between((X_T - 6, Y_IN + 4, 30.0), (X_T - 34, -8.0, 26.0), 13.0)           # by-pass duct inlet -> outlet
    th = st + inlet + flange + outlet + oflange + disc_t + wg_boss
    cav_t = volute(X_T, r2t + 12.0, 19.5, 6.0, 115.0, 455.0) + cyl_between((X_T, Y_IN, 22.0), (X_T, Y_IN, Z_IN + 1), 25.0)
    cav_t = cav_t + cyl_between((X_T - 4, 0, 0), (X_T + 4, 0, 0), r2t + 16.0)                # nozzle ring passage
    cav_t = cav_t + cyl_between((X_T - 15, 0, 0), (X_T + 17, 0, 0), r2t + 0.6)               # wheel pocket
    cav_t = cav_t + cyl_between((X_TO - 1, 0, 0), (X_T - 10, 0, 0), S["dte"] / 2 + 9.0)      # exducer / outlet bore
    cav_t = cav_t + cyl_between((X_T - 6, Y_IN + 4, 30.0), (X_T - 36, -8.0, 26.0), 9.0)      # waste-gate by-pass (opens into the outlet bore)
    turb_housing = th - cav_t
    # ---------------- centre housing (bearing housing, water-cooled) with oil feed/drain and water ports
    chra = cyl_between((X_T + 17, 0, 0), (X_C - 13, 0, 0), 30.0) + cyl_between((X_T + 17, 0, 0), (X_T + 24, 0, 0), r2t + 8.0) + \
        cyl_between((X_C - 20, 0, 0), (X_C - 13, 0, 0), r2c + 6.0)
    chra = chra + cyl_between((0, 0, 20), (0, 0, 44), 9.0) + cyl_between((0, 0, -20), (0, 0, -46), 12.0)       # oil feed boss (top), drain (bottom)
    chra = chra + cyl_between((-10, 22, 0), (-10, 40, 0), 8.0) + cyl_between((10, 22, 0), (10, 40, 0), 8.0)    # coolant in / out
    chra = chra - cyl_between((X_T + 16, 0, 0), (X_C - 12, 0, 0), 9.0)                                          # bearing bore
    chra = chra - cyl_between((0, 0, 8), (0, 0, 45), 3.0) - cyl_between((0, 0, -8), (0, 0, -47), 7.5)
    chra = chra - cyl_between((-10, 14, 0), (-10, 41, 0), 4.5) - cyl_between((10, 14, 0), (10, 41, 0), 4.5)
    # ---------------- rotor: turbine wheel + shaft (friction welded), compressor wheel, bearings
    tw = Pos(X_T - 15.5, 0, 0) * wheel("t")
    shaft = cyl_between((X_T + 16, 0, 0), (X_C + 22, 0, 0), 5.5) + cyl_between((X_T + 16, 0, 0), (X_T + 22, 0, 0), 8.6)
    rotor_t = tw + shaft
    cw = Pos(X_C + 18.0, 0, 0) * Rot(Z=180) * wheel("c")
    cw = cw - cyl_between((X_C - 14, 0, 0), (X_C + 20, 0, 0), 5.5)
    bush = cyl_between((-7, 0, 0), (7, 0, 0), 8.95) - cyl_between((-8, 0, 0), (8, 0, 0), 5.53)
    # ---------------- waste-gate actuator (electric) with rod, mounted on the compressor housing
    act = cyl_between((-20, -52, -42), (20, -52, -42), 21.0) + box_at(-6, 6, -52, -30, -30, -18)          # bracket to the bearing housing
    rod = cyl_between((-20, -52, -42), (X_T - 42, -40.0, -30.0), 3.0)     # Fix F3 (2026-11-21): lever end 10 mm shorter (was 1.6 mm inside the pre-catalyst can)
    return dict(comp_housing=comp_housing, turb_housing=turb_housing, chra=chra, rotor=rotor_t, comp_wheel=cw, bush=bush,
                actuator=act + rod)
