"""External systems CAD: exhaust, intake / charge-air cooling, fuel, lubrication, cooling, accessories, sensors.

Everything here is an engineering proposal (EST) packaged around the long block.  Side-specific parts are
generated per side with sy = +1 (bank 1 side, +Y) or -1 (bank 2 side, -Y): geometry is written in global
coordinates with y multiplied by sy, so the two sides are mirror images except where they attach to the heads
(the port stations of the two banks differ by the bank offset and the zig-zag order).
"""
from __future__ import annotations
import math
import numpy as np
from build123d import Align, Box, Circle, Cylinder, Location, Plane, Pos, Rot, Sphere, extrude, make_hull, mirror, offset

from ..params import P
from .. import layout as L
from .common import CMIN, box_at, cyl_between, head_plane, poly, tube
from .block import GAL_C, GAL_S, MOUNT_X, SCAV_Y, W_TOP, XH, loc_x, rho
from . import turbo as TB

Y_T, Z_T = 333.0, -20.0                 # turbocharger shaft axis (|y|, z)
X_TA, X_TB = -150.0, 150.0              # turbo A (front, permanently active) / turbo B (rear, switchable)
PLEN_Y = (22.0, 152.0)
PLEN_Z = (345.0, 390.0)
CAC_Z = (390.0, 570.0)
TANK_Z = (570.0, 640.0)
CAC_X = 210.0


def bank_of(sy):
    return 1 if sy > 0 else 2


def hg(bank, xl, u, w):
    """Head-local point -> global numpy array."""
    return L.to_global(bank, xl, u, P.head_face_height + w)


def port_stations(sy, kind):
    """Global flange-centre points of the eight intake or exhaust ports of a side, sorted front to rear,
    plus the outward flange normal."""
    b = bank_of(sy)
    u = -W_TOP if kind == "in" else W_TOP
    pts = sorted([hg(b, loc_x(i), u, 36.0) for i in range(1, 9)], key=lambda p: p[0])
    ex, eu, ev = L.bank_axes(b)
    n = -eu if kind == "in" else eu
    return pts, n


def P3(x, y, z, sy):
    return np.array([x, sy * y, z])


def s_pipe(p0, p1, ro, ri):
    """S-bend pipe between two points whose end tangents are both along -X (smooth spline sweep)."""
    from build123d import Spline, sweep
    path = Spline(tuple(p0), tuple(p1), tangents=[(-1, 0, 0), (-1, 0, 0)], tangent_scalars=[1.6, 1.6])
    sec = lambda r: Plane(origin=path @ 0, z_dir=path % 0) * Circle(r)
    outer = sweep(sec(ro), path=path)
    inner = sweep(sec(ri), path=path)
    cap = lambda q, d: cyl_between(np.array(q) - 2 * d, np.array(q) + 2 * d, ri)
    return outer - inner - cap(p0, np.array([1.0, 0, 0])) - cap(p1, np.array([1.0, 0, 0]))


# ====================================================================== exhaust (group 10)
def exhaust_side(sy):
    """Front and rear log manifolds, cross-over, shut-off valve, down-pipes and close-coupled pre-catalysts."""
    pts, n = port_stations(sy, "ex")
    out = {}
    b = bank_of(sy)
    logc = [p + n * 34.0 for p in pts]                               # log centre line passes 34 mm off the flange face
    y_l, z_l = abs(logc[0][1]), logc[0][2]
    for name, grp in (("front", pts[:4]), ("rear", pts[4:])):
        xs = [p[0] for p in grp]
        x0, x1 = min(xs) - 30.0, max(xs) + 30.0
        log = cyl_between((x0, sy * y_l, z_l), (x1, sy * y_l, z_l), 30.0)
        cav = cyl_between((x0 + 3, sy * y_l, z_l), (x1 - 3, sy * y_l, z_l), 26.5)
        pl = None
        for p in grp:
            log = log + cyl_between(p + n * 9.0, p + n * 34.0, 23.0)
            cav = cav + cyl_between(p + n * 8.0, p + n * 34.0, 20.0)
            # flange plate around each port pair
            f = Location(head_plane(b)) * Pos(float(L.to_local(b, p)[0]), W_TOP + 5.0, 36.0) * Box(64, 10, 46)
            pl = f if pl is None else pl + f
        xt = (X_TA if name == "front" else X_TB) + TB.X_T
        neck_top = (xt, sy * y_l, z_l)
        neck_bot = (xt, sy * (Y_T + TB.Y_IN), Z_T + TB.Z_IN)
        log = log + cyl_between(neck_top, neck_bot, 29.0) + cyl_between((xt, sy * (Y_T + TB.Y_IN), Z_T + TB.Z_IN + 9), neck_bot, 40.0)
        cav = cav + cyl_between(neck_top, (neck_bot[0], neck_bot[1], neck_bot[2] - 1), 25.0)
        zf = Z_T + TB.Z_IN
        out[f"manifold_{name}"] = ((log + pl) - cav) - box_at(xt - 60, xt + 60, sy * (Y_T + TB.Y_IN) - 60, sy * (Y_T + TB.Y_IN) + 60, zf - 40, zf)
        out[f"_x_{name}"] = (x0, x1)
    xa, xb = out.pop("_x_front")[1], out.pop("_x_rear")[0]
    out["crossover"] = cyl_between((xa - 4, sy * y_l, z_l), (xb + 4, sy * y_l, z_l), 22.0) - cyl_between((xa - 5, sy * y_l, z_l), (xb + 5, sy * y_l, z_l), 19.5)
    # exhaust shut-off valve on the neck of the rear manifold (flap valve body + electric actuator)
    xt = X_TB + TB.X_T
    zc = 0.5 * (z_l + Z_T + TB.Z_IN) + 2.0
    val = cyl_between((xt - 22, sy * (y_l - 8), zc), (xt + 22, sy * (y_l - 8), zc), 6.0) + \
        cyl_between((xt + 22, sy * (y_l - 8), zc + 3.0), (xt + 62, sy * (y_l - 8), zc + 3.0), 20.0)   # Fix F4 (2026-11-21): actuator 3 mm up (was 1 mm into the turbine housing)
    out["shutoff_valve"] = val
    # turbine A outlet -> pre-catalyst A (close coupled, straight out to the free end)
    xo = X_TA + TB.X_TO
    r_o = TB.S["dte"] / 2 + 14.0
    can = cyl_between((xo, sy * Y_T, Z_T), (xo - 12, sy * Y_T, Z_T), r_o) + cyl_between((xo - 12, sy * Y_T, Z_T), (xo - 95, sy * Y_T, Z_T), 55.0) + \
        cyl_between((xo - 95, sy * Y_T, Z_T), (xo - 125, sy * Y_T, Z_T), 38.0)
    can = can - cyl_between((xo + 1, sy * Y_T, Z_T), (xo - 13, sy * Y_T, Z_T), r_o - 4) - cyl_between((xo - 13, sy * Y_T, Z_T), (xo - 94, sy * Y_T, Z_T), 52.5) - \
        cyl_between((xo - 94, sy * Y_T, Z_T), (xo - 126, sy * Y_T, Z_T), 35.5)
    out["precat_A"] = can
    out["substrate_A"] = cyl_between((xo - 20, sy * Y_T, Z_T), (xo - 88, sy * Y_T, Z_T), 52.3)
    # turbine B outlet -> tunnel pipe between crankcase and turbo A -> pre-catalyst B ahead of the engine
    xb_o = X_TB + TB.X_TO
    pa, pd, pe = P3(xb_o + 2, Y_T, Z_T, sy), P3(xb_o - 150, 208.0, -45.0, sy), P3(-XH - 105, 208.0, -45.0, sy)
    out["downpipe_B"] = s_pipe(pa, pd, 33.0, 31.0) + (cyl_between(pd, pe, 33.0) - cyl_between(pd + np.array([1.0, 0, 0]), pe - np.array([1.0, 0, 0]), 31.0))
    xc = -XH - 105
    canb = cyl_between((xc, sy * 208, -45), (xc - 12, sy * 208, -45), 33.0) + cyl_between((xc - 12, sy * 208, -45), (xc - 92, sy * 208, -45), 52.0) + \
        cyl_between((xc - 92, sy * 208, -45), (xc - 120, sy * 208, -45), 38.0)
    canb = canb - cyl_between((xc + 1, sy * 208, -45), (xc - 13, sy * 208, -45), 31.0) - cyl_between((xc - 13, sy * 208, -45), (xc - 91, sy * 208, -45), 49.5) - \
        cyl_between((xc - 91, sy * 208, -45), (xc - 121, sy * 208, -45), 35.5)
    out["precat_B"] = canb
    out["substrate_B"] = cyl_between((xc - 20, sy * 208, -45), (xc - 86, sy * 208, -45), 49.3)
    return out


# ====================================================================== intake + charge-air cooling (group 09)
def intake_side(sy):
    pts, n = port_stations(sy, "in")
    b = bank_of(sy)
    out = {}
    # lower manifold: eight runners + head flange plate + plenum (one CFRP/aluminium part)
    y0, y1 = PLEN_Y
    plen = box_at(-290, 290, sy * y0, sy * y1, PLEN_Z[0], PLEN_Z[1])
    cav = box_at(-286.5, 286.5, sy * (y0 + 3.5), sy * (y1 - 3.5), PLEN_Z[0] + 3.5, PLEN_Z[1] + 1)
    body = plen
    for p in pts:
        a = p + n * 30.0
        top = np.array([p[0], sy * 88.0, PLEN_Z[0] + 2.0])
        body = body + cyl_between(p + n * 9.0, a, 25.0) + Pos(*[float(v) for v in a]) * Sphere(25.0) + cyl_between(a, top, 25.0)
        cav = cav + cyl_between(p + n * 8.0, a, 22.0) + Pos(*[float(v) for v in a]) * Sphere(22.0) + cyl_between(a, top + np.array([0, 0, 3.0]), 22.0)
        body = body + Location(head_plane(b)) * Pos(float(L.to_local(b, p)[0]), -W_TOP - 5.0, 36.0) * Box(66, 10, 48)
    out["intake_manifold"] = body - cav
    # charge-air cooler: core block, top tank with two entries (one per compressor), LT water stubs
    core = box_at(-CAC_X, CAC_X, sy * y0, sy * y1, CAC_Z[0], CAC_Z[1])
    slots = None
    for k in range(27):                                                   # air passages through the core (representative pitch)
        s = box_at(-CAC_X + 12 + k * 15.0, -CAC_X + 12 + k * 15.0 + 9.0, sy * (y0 + 6), sy * (y1 - 6), CAC_Z[0] - 1, CAC_Z[1] + 1)
        slots = s if slots is None else slots + s
    core = core - slots
    for zz in (CAC_Z[0] + 30, CAC_Z[1] - 30):
        core = core + (cyl_between((-CAC_X - 30, sy * 87, zz), (-CAC_X, sy * 87, zz), 14.0) - cyl_between((-CAC_X - 31, sy * 87, zz), (-CAC_X + 4, sy * 87, zz), 11.0))
    out["cac_core"] = core
    tank = box_at(-CAC_X, CAC_X, sy * y0, sy * y1, TANK_Z[0], TANK_Z[1]) - box_at(-CAC_X + 3, CAC_X - 3, sy * (y0 + 3), sy * (y1 - 3), TANK_Z[0] - 1, TANK_Z[1] - 3)
    zin = 0.5 * (TANK_Z[0] + TANK_Z[1])
    for xc in (X_TA + TB.X_C, X_TB + TB.X_C):
        tank = tank + cyl_between((xc, sy * y1, zin), (xc, sy * (y1 + 12), zin), 34.0) - cyl_between((xc, sy * (y1 - 4), zin), (xc, sy * (y1 + 13), zin), 30.0)
    out["cac_tank"] = tank
    # throttle bodies (B-side unit doubles as the compressor cut-in valve), charge pipes, clean-air ducts, air box
    thr = None
    for i, (xt, nm) in enumerate(((X_TA, "A"), (X_TB, "B"))):
        xc = xt + TB.X_C
        t = cyl_between((xc, sy * (y1 + 12), zin), (xc, sy * (y1 + 58), zin), 39.0) - cyl_between((xc, sy * (y1 + 11), zin), (xc, sy * (y1 + 59), zin), 31.0)
        t = t + box_at(xc - 30, xc + 30, sy * (y1 + 18), sy * (y1 + 52), zin + 36, zin + 62)       # actuator
        t = t + cyl_between((xc, sy * (y1 + 35), zin - 31), (xc, sy * (y1 + 35), zin + 31), 3.0)   # spindle
        out[f"throttle_{nm}"] = t
        co = P3(xc + 2.0, Y_T + TB.Y_CO, Z_T + TB.Z_CO, sy)
        path = [co, co + np.array([0, 0, 40.0]), P3(xc + 2.0, 415.0, 205.0, sy), P3(xc + 2.0, 415.0, 300.0, sy),
                P3(xc, 300.0, 425.0, sy), P3(xc, 250.0, zin, sy), P3(xc, y1 + 58.0, zin, sy)]
        out[f"charge_pipe_{nm}"] = tube(path, 32.0, 29.5, bend=58.0)
    ci_a = P3(X_TA + TB.X_CI, Y_T, Z_T, sy)
    path = [ci_a, ci_a + np.array([14.0, 0, 0]), P3(-20.0, 400.0, 26.0, sy), P3(-10.0, 415.0, 130.0, sy), P3(-10.0, 415.0, 330.0, sy), P3(-10.0, 335.0, 404.0, sy)]
    out["air_duct_A"] = tube(path, 35.0, 32.5, bend=60.0)
    ci_b = P3(X_TB + TB.X_CI, Y_T, Z_T, sy)
    # Fix E (2026-11-21): crosses above the charge pipe's diagonal (11 mm clear; it ran through charge pipe B, 1,487 mm3) - the
    # outboard alternatives reach 19 mm only by widening the dressed engine by 90 mm
    path = [ci_b, ci_b + np.array([45.0, 0, 0]), P3(312.0, 415.0, 60.0, sy), P3(312.0, 415.0, 330.0, sy), P3(260.0, 410.0, 500.0, sy), P3(112.0, 335.0, 460.0, sy)]
    out["air_duct_B"] = tube(path, 35.0, 32.5, bend=60.0)
    box = box_at(-65, 118, sy * 225, sy * 335, 400, 640) - box_at(-62, 115, sy * 228, sy * 332, 403, 637)
    box = box + (cyl_between((118, sy * 280, 590), (158, sy * 280, 590), 40.0) - cyl_between((113, sy * 280, 590), (159, sy * 280, 590), 37.0))   # snorkel
    out["air_box"] = box
    out["air_filter"] = box_at(-58, 111, sy * 232, sy * 328, 520, 548)
    # recirculation (anti-surge) valve on compressor B
    xr = X_TB + TB.X_C + 2.0
    out["recirc_valve"] = cyl_between((xr + 26, sy * (Y_T + TB.Y_CO), Z_T + TB.Z_CO + 18), (xr + 62, sy * (Y_T + TB.Y_CO), Z_T + TB.Z_CO + 18), 15.0)
    return out


# ====================================================================== fuel + ignition (group 11)
def fuel_side(sy):
    pts, n = port_stations(sy, "in")
    out = {}
    inj = []
    xs = [p[0] for p in pts]
    for rail, dx, top in (("P", -11.0, (158.0, 331.0)), ("S", 11.0, (176.0, 352.0))):
        r = cyl_between((min(xs) - 30, sy * top[0], top[1]), (max(xs) + 30, sy * top[0], top[1]), 9.5) - \
            cyl_between((min(xs) - 26, sy * top[0], top[1]), (max(xs) + 26, sy * top[0], top[1]), 6.5)
        # damper / pressure sensor at the rear end; Fix D2 (2026-11-21): on the primary rail it is the rail's own diameter
        # (r 9.5, was 13 - its lower side ran 5.8 mm into the head's rear end; now 2.8 mm clear)
        r = r + cyl_between((max(xs) + 30, sy * top[0], top[1]), (max(xs) + 62, sy * top[0], top[1]), 9.5 if rail == "P" else 13.0)
        out[f"rail_{rail}"] = r
        for p in pts:
            a = p + n * 22.0
            tip = np.array([p[0] + dx, a[1] + sy * 14.0, a[2] + 12.0])
            t = np.array([p[0] + dx, sy * top[0], top[1]])
            d = (t - tip) / np.linalg.norm(t - tip)
            ln = float(np.linalg.norm(t - tip)) - 8.0
            # Fix D1 (2026-11-21): the connector (local +y) points away from the partner injector of the same port; with the
            # default frame it pointed at it and overlapped its body by 1 mm (tips and spray targeting unchanged)
            away = np.array([np.sign(dx), 0.0, 0.0])
            xd = np.cross(away, d)
            inj.append((Location(Plane(origin=tuple(tip), x_dir=tuple(xd / np.linalg.norm(xd)), z_dir=tuple(d))), ln))
    out["_injectors"] = inj
    return out


def injector_solid(length):
    """Port fuel injector (local: nozzle tip at the origin, +Z towards the rail)."""
    return Cylinder(4.0, 12.0, align=CMIN) + Pos(0, 0, 12.0) * Cylinder(8.0, length - 22.0, align=CMIN) + \
        Pos(0, 0, length - 10.0) * Cylinder(5.5, 10.0, align=CMIN) + Pos(0, 9, 0.45 * length) * Box(10, 12, 16)


# ====================================================================== lubrication (group 12)
def lubrication():
    out = {}
    pump = box_at(-404, -339.5, -172, -122, -100, -38)
    for k in range(7):                                                    # 1 pressure + 6 scavenge gear stages
        pump = pump - box_at(-401 + k * 9.0 + 6.5, -401 + k * 9.0 + 7.5, -173, -171, -101, -37)
    out["oil_pump_stack"] = pump
    hoses = None
    for i, ys in enumerate(SCAV_Y):
        t = cyl_between((-XH - 22.5, ys, -89.0), (-XH - 26, ys, -89.0), 9.0)
        hoses = t if hoses is None else hoses + t
    rail = cyl_between((-XH - 26, -121.5, -89.0), (-XH - 26, SCAV_Y[-1] + 14, -89.0), 9.0) - \
        cyl_between((-XH - 26, -122.5, -89.0), (-XH - 26, SCAV_Y[-1] + 10, -89.0), 7.0)
    out["scavenge_manifold"] = hoses + rail
    filt = cyl_between((-470, 110, -100), (-470, 110, 20), 43.0)
    out["oil_filter_module"] = filt
    cooler = box_at(-70, 70, -45, 45, 248, 330)
    for xx in (-52.0, 52.0):
        cooler = cooler + cyl_between((xx, -45, 300), (xx, -62, 300), 11.0)
    out["oil_cooler"] = cooler
    out["oil_tank"] = cyl_between((-760, 0, -90), (-760, 0, 390), 115.0) - cyl_between((-760, 0, -86), (-760, 0, 386), 112.0)
    out["oil_line_pressure"] = tube([(-352, -140, -38), (-352, -140, 100), (-352, -60, GAL_C[1]), (-XH - 9, GAL_C[0], GAL_C[1])], 10.0, 8.0, bend=22.0)
    return out


# ====================================================================== cooling (group 13)
def cooling():
    out = {}
    ZP = 215.0
    pump = cyl_between((-372, 0, ZP), (-XH - 9.5, 0, ZP), 55.0) + cyl_between((-400, 0, ZP), (-372, 0, ZP), 16.0)
    pump = pump - cyl_between((-368, 0, ZP), (-XH - 14, 0, ZP), 48.0) - cyl_between((-401, 0, ZP), (-360, 0, ZP), 9.5)
    # Fix C (2026-11-21): inlet boss under the volute - the inlet pipe used to end 42.9 mm from the pump axis, inside the
    # impeller (r 44); it now ends on this boss at 56 mm (boss top 5.8 mm below the impeller's lowest point at y = 20)
    pump = pump + cyl_between((-361, 40, ZP - 52.5), (-361, 40, ZP - 45.0), 20.0)
    out["water_pump_housing"] = pump
    imp = cyl_between((-366, 0, ZP), (-360, 0, ZP), 44.0)
    for k in range(7):
        imp = imp + Pos(-360, 0, ZP) * Rot(X=360.0 * k / 7) * box_at(-0.0, 14.0, 10.0, 43.0, -1.5, 1.5)
    out["water_pump_impeller"] = imp + cyl_between((-403, 0, ZP), (-360, 0, ZP), 9.0)
    out["water_pump_pulley"] = cyl_between((-423, 0, ZP), (-403, 0, ZP), 48.0)
    # block inlets (front face of each bank) and head outlets (front end of each head)
    def tgt(bank, xl, u, v):
        return L.to_global(bank, xl, u, v)
    inl = {1: tgt(1, -XH, rho(1) * P.u_bore_deck, P.deck_height - 45), 2: tgt(2, XH, rho(8) * P.u_bore_deck, P.deck_height - 45)}
    outl = {1: hg(1, -XH, -60.0, 30.0), 2: hg(2, XH, -60.0, 30.0)}
    for b in (1, 2):
        sy = 1 if b == 1 else -1
        a = inl[b]
        # Fix C (2026-11-21): the outlet starts radially 56 mm from the pump axis (housing r 55) - it used to start at 50 mm,
        # inside the volute, where the impeller (r 44) sweeps
        d0 = np.array([0.0, sy * 50.0, -30.0]) / math.hypot(50.0, 30.0)
        out[f"pipe_pump_to_block_{b}"] = tube([(-361, 56.0 * d0[1], ZP + 56.0 * d0[2]), (-361, sy * 100.0, 185.0), (-361, a[1], a[2]), (-XH + 4, a[1], a[2])], 19.0, 17.0, bend=30.0)
        o = outl[b]
        out[f"pipe_head_to_thermostat_{b}"] = tube([(-XH + 4, o[1], o[2]), (-361, o[1], o[2]), (-361, sy * 75.0, 318.0), (-361, sy * 31.0, 318.0)], 19.0, 17.0, bend=30.0)
    th = cyl_between((-361, -31, 318), (-361, 31, 318), 30.0) + cyl_between((-361, 0, 318), (-361, 0, 400), 21.0)
    th = th - cyl_between((-361, -27, 318), (-361, 27, 318), 26.0) - cyl_between((-361, 0, 330), (-361, 0, 401), 18.0)
    out["thermostat_housing"] = th
    out["pump_inlet_pipe"] = \
        (cyl_between((-361, 40, ZP - 52.5), (-361, 40, 122), 20.0) + cyl_between((-361, 40, 122), (-470, 40, 122), 20.0) -
         cyl_between((-361, 40, ZP - 51.5), (-361, 40, 122), 17.5) - cyl_between((-361, 40, 122), (-471, 40, 122), 17.5))
    # low-temperature circuit: electric pump and hoses to the two charge-air coolers
    out["lt_pump"] = cyl_between((-300, 0, 285), (-195, 0, 285), 34.0) + cyl_between((-195, 0, 285), (-180, 0, 285), 14.0)
    for sy in (1, -1):
        out[f"lt_hose_supply_{'L' if sy > 0 else 'R'}"] = tube([(-301, sy * 12.0, 285.0), (-316, sy * 87.0, 300.0), (-316, sy * 87.0, CAC_Z[0] + 30.0), (-CAC_X - 30, sy * 87.0, CAC_Z[0] + 30.0)], 13.0, 10.5, bend=22.0)
        out[f"lt_hose_return_{'L' if sy > 0 else 'R'}"] = tube([(-CAC_X - 30, sy * 87.0, CAC_Z[1] - 30.0), (-300, sy * 87.0, CAC_Z[1] - 30.0), (-420, sy * 87.0, CAC_Z[1] - 60.0)], 14.0, 11.0, bend=24.0)
    return out


# ====================================================================== accessories (group 14)
def accessories():
    out = {}
    x_n = L.main_x(1) - P.main_width / 2 - 29.0                           # start of the crank nose
    damper = cyl_between((x_n - 72, 0, 0), (x_n - 40, 0, 0), 95.0) - cyl_between((x_n - 73, 0, 0), (x_n - 39, 0, 0), 68.0)      # inertia ring
    hub = cyl_between((x_n - 94, 0, 0), (x_n - 10, 0, 0), 40.0) + cyl_between((x_n - 64, 0, 0), (x_n - 48, 0, 0), 68.0) + \
        cyl_between((x_n - 93, 0, 0), (x_n - 73, 0, 0), 70.0)                                                                   # hub, web, poly-V pulley
    hub = hub - cyl_between((x_n - 95, 0, 0), (x_n - 8, 0, 0), 25.02)
    out["damper_ring"] = damper
    out["damper_hub_pulley"] = hub
    out["damper_bolt"] = cyl_between((x_n - 106, 0, 0), (x_n - 94, 0, 0), 15.0) + cyl_between((x_n - 94, 0, 0), (x_n - 72.5, 0, 0), 12.0)
    from .cranktrain import REAR_SEAL, REAR_SEAT
    x_fl = L.main_x(P.n_main) + P.main_width / 2 + REAR_SEAT + REAR_SEAL + 14.0
    fw = cyl_between((x_fl, 0, 0), (x_fl + 9, 0, 0), 165.0) - cyl_between((x_fl - 1, 0, 0), (x_fl + 10, 0, 0), 17.5)
    for i in range(9):
        a = math.radians(40 * i)
        fw = fw - cyl_between((x_fl - 1, 45 * math.sin(a), 45 * math.cos(a)), (x_fl + 10, 45 * math.sin(a), 45 * math.cos(a)), 6.2)
    for i in range(6):
        a = math.radians(60 * i + 20)
        fw = fw - cyl_between((x_fl - 1, 105 * math.sin(a), 105 * math.cos(a)), (x_fl + 10, 105 * math.sin(a), 105 * math.cos(a)), 28.0)
    out["flex_plate"] = fw
    for sy, nm, r, ln in ((-1, "alternator", 62.0, 125.0), (1, "ac_compressor", 58.0, 150.0)):
        body = cyl_between((-423 - ln, sy * 120.0, 290.0), (-422.5, sy * 120.0, 290.0), r) + cyl_between((-423, sy * 120.0, 290.0), (-403, sy * 120.0, 290.0), 32.0)
        out[nm] = body
    # accessory belt around crank pulley, water pump, alternator and A/C compressor (poly-V, 6 ribs)
    sk = Pos(0, 0) * Circle(70.0) + Pos(0, 215) * Circle(48.0) + Pos(-120, 290) * Circle(32.0) + Pos(120, 290) * Circle(32.0)
    hull = make_hull(sk.edges())
    ring = offset(hull, amount=4.0) - hull
    out["accessory_belt"] = extrude(Plane(origin=(-423, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * ring, amount=20.0, dir=(1, 0, 0))
    # belt planes: the pulleys above are modelled at the same axial station
    for sy in (1, -1):
        # Fix G (2026-11-21): the plate on the block pad ends at z 35 - up to z 40 it cut 2 mm into the crankcase wall, which slopes
        # outwards above the pad (y 176 at z ~37, 178.4 at z 40)
        br = box_at(MOUNT_X - 26, MOUNT_X + 36, sy * 176, sy * 196, 2, 35) + box_at(MOUNT_X - 26, MOUNT_X + 30, sy * 196, sy * 246, 10, 35)
        out[f"mount_bracket_{'L' if sy > 0 else 'R'}"] = br
        out[f"mount_isolator_{'L' if sy > 0 else 'R'}"] = cyl_between((MOUNT_X + 2, sy * 228, -22), (MOUNT_X + 2, sy * 228, 10), 18.0)
    fc = box_at(-XH - 9, -XH, -150, 150, -72, 150) - cyl_between((-XH - 10, 0, 0), (-XH + 1, 0, 0), 30.6) - \
        cyl_between((-XH - 10, GAL_C[0], GAL_C[1]), (-XH + 1, GAL_C[0], GAL_C[1]), 11.5)
    # Fix C (2026-11-21): notch for the coolant pipes pump -> block inlet (r 19 + 3 mm clearance); they ran 2.3 mm into the cover edge
    for bank in (1, 2):
        a = L.to_global(bank, -XH if bank == 1 else XH, rho(1 if bank == 1 else 8) * P.u_bore_deck, P.deck_height - 45)
        fc = fc - cyl_between((-XH - 12, a[1], a[2]), (-XH + 3, a[1], a[2]), 22.0)
    out["front_cover"] = fc
    return out


def sensor_solid(length=38.0, r=6.0):
    """Generic screw-in sensor (local: tip at the origin, +Z outwards)."""
    return Cylinder(r, length * 0.55, align=CMIN) + Pos(0, 0, length * 0.55) * Cylinder(r * 1.7, length * 0.2, align=CMIN) + \
        Pos(0, 0, length * 0.75) * Cylinder(r * 1.2, length * 0.25, align=CMIN)


def harness():
    """Main engine harness trunks along the two cam covers with drops to the coils (routing envelope)."""
    out = {}
    for b in (1, 2):
        a = hg(b, -300.0, 42.0, 196.0)
        c = hg(b, 300.0, 42.0, 196.0)
        t = cyl_between(a, c, 9.0)
        for i in range(1, 9):
            p = hg(b, loc_x(i), 42.0, 196.0)
            q = hg(b, loc_x(i), 14.0 * (1 if i % 2 == 0 else -1), 190.0)
            t = t + cyl_between(p, q, 3.5)
        out[f"harness_trunk_{b}"] = t
    return out
