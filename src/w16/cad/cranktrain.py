"""Crank train CAD: crankshaft (with distributed counterweights), connecting rod assembly, piston assembly."""
from __future__ import annotations
import math
import numpy as np
from build123d import Align, Box, Circle, Cylinder, Location, Plane, Pos, Rot, Torus, extrude, make_hull, revolve

from ..params import P, MATERIALS
from .. import layout as L
from .common import CMIN, MAT, V, box_at, cyl_between, hex_bolt, mass_props, poly

RHO_STEEL = MATERIALS[MAT["steel_qt"]]["rho"]
D2R = math.pi / 180


# ====================================================================== crankshaft
R_MAIN_WEB = 41.0      # web boss radius around the main journal
R_PIN_WEB = 35.0       # web boss radius around the crankpin
R_CW_IN = 30.0
REAR_SEAT, REAR_SEAL = 67.0, 12.0    # rear shaft: sprocket seat length, seal-land length (then a 14 mm flange)
CW_THETA_MAX = 82.0    # deg, half-angle limit of the counterweight sector


def _yz(angle_deg, r):
    """(y, z) at angle phi (from +Z towards +Y)."""
    a = angle_deg * D2R
    return (r * math.sin(a), r * math.cos(a))


def web_sketch(psi, cw_dir=None, theta=0.0):
    """2-D web outline in the Y-Z plane for a pin at angle psi; optional counterweight sector centred on cw_dir."""
    py, pz = _yz(psi, P.throw)
    sk = make_hull((Circle(R_MAIN_WEB) + Pos(py, pz) * Circle(R_PIN_WEB)).edges())
    cwp = None
    if theta > 1.0:
        pts = [_yz(cw_dir - theta, R_CW_IN)]
        for a in np.linspace(cw_dir - theta, cw_dir + theta, max(int(theta / 2.5), 6)):
            pts.append(_yz(a, P.cw_radius))
        pts.append(_yz(cw_dir + theta, R_CW_IN))
        pts.append((0.0, 0.0))
        cwp = poly(pts)
    return sk, cwp


def fillet_ring(r, rf):
    """Concave journal fillet as a body of revolution about +X: fills the corner between a journal (radius r)
    and the web face at x = 0, extending to x = rf."""
    pts = [(0.0, r - 0.5), (rf, r - 0.5), (rf, r)]
    for a in np.linspace(0, 90, 7)[1:]:
        pts.append((rf - rf * math.sin(a * D2R), r + rf - rf * math.cos(a * D2R)))
    prof = Plane.XY * poly(pts)                       # (x, y) profile, revolve about X
    from build123d import Axis
    return revolve(prof, axis=Axis.X)


def throw_solid(k, cw=None):
    """Pin k with its two webs.  cw = (direction deg, half-angle deg) of the counterweight sectors or None."""
    psi = L.PIN_PHASE[k]
    px = L.pin_x(k)
    py, pz = _yz(psi, P.throw)
    hw = P.pin_width / 2
    pin = Pos(px - hw, py, pz) * Rot(Y=90) * Cylinder(P.pin_dia / 2, P.pin_width, align=CMIN)
    sk, cwp = web_sketch(psi, *(cw or (None, 0.0)))
    ex = lambda face, x0: extrude(Plane.YZ.offset(x0) * face, amount=P.web_thk, dir=(1, 0, 0))     # always towards +X
    wa = ex(sk, px - hw - P.web_thk)
    wb = ex(sk, px + hw)
    body = pin + wa + wb
    if cwp is not None:                               # counterweight sectors fused as solids (they overlap the web boss)
        body = body + ex(cwp, px - hw - P.web_thk) + ex(cwp, px + hw)
    # stress-relief fillets pin/web (R2.5)
    fr = Pos(px - hw, py, pz) * fillet_ring(P.pin_dia / 2, 2.5)
    fr2 = Pos(px + hw, py, pz) * Rot(Z=180) * fillet_ring(P.pin_dia / 2, 2.5)
    body = body + fr + fr2
    # lightening bore through the pin (plugged in service)
    body = body - Pos(px - hw - P.web_thk - 1, py, pz) * Rot(Y=90) * Cylinder(P.pin_bore / 2, P.pin_width + 2 * P.web_thk + 2, align=CMIN)
    return body


def _cw_capacity_curve(k=1):
    """m*r (kg mm, along the sector direction) added by the two counterweight sectors of a throw vs half-angle."""
    base = throw_solid(k, None)
    m0, c0 = mass_props(base, RHO_STEEL)
    psi = L.PIN_PHASE[k]
    cw_dir = psi + 180.0
    ed = np.array(_yz(cw_dir, 1.0))
    th = [15.0, 35.0, 55.0, 70.0, CW_THETA_MAX]
    out = []
    for t in th:
        s = throw_solid(k, (cw_dir, t))
        m, c = mass_props(s, RHO_STEEL)
        out.append((m * c[1:] - m0 * c0[1:]) @ ed)
    e_pin = np.array(_yz(psi, 1.0))
    return np.array(th), np.array(out), float(m0 * (c0[1:] @ e_pin)), float(m0)


def design_counterweights(mr_dyn, cw_angle):
    """Distribute the counterweights.

    mr_dyn[k]  : m*r (kg mm) of the counterweight that would fully balance the rods + pistons of throw k
    cw_angle[k]: its direction measured from the pin (deg, towards +phi)
    Returns dict k -> (direction deg, half-angle deg, m*r provided) and a report dict.
    """
    th, cap, mr_geom, m_throw = _cw_capacity_curve(1)
    c_max = float(cap[-1])
    ks = range(1, 9)
    # unbalance of each throw in the crank frame (y, z components): geometry (pin + webs) + dynamic equivalent
    U = {}
    for k in ks:
        psi = L.PIN_PHASE[k]
        u_geo = mr_geom * np.array(_yz(psi, 1.0))
        u_dyn = -mr_dyn[k] * np.array(_yz(psi + cw_angle[k], 1.0))        # unbalance = minus the ideal counterweight
        U[k] = u_geo + u_dyn
    x = np.array([L.pin_x(k) for k in ks])
    A = np.zeros((4, 16))
    for i in range(8):
        A[0, 2 * i] = 1; A[1, 2 * i + 1] = 1
        A[2, 2 * i] = x[i]; A[3, 2 * i + 1] = x[i]
    frac = 1.0
    for _ in range(60):
        r0 = np.concatenate([U[k] * max(1 - frac * c_max / np.linalg.norm(U[k]), 0.0) for k in ks])   # residual after max. CW
        r = r0 - A.T @ np.linalg.solve(A @ A.T, A @ r0)                   # nearest residual with zero force and couple
        W = {k: r[2 * i:2 * i + 2] - U[k] for i, k in enumerate(ks)}       # counterweight vectors
        if max(np.linalg.norm(w) for w in W.values()) <= c_max * 1.0001:
            break
        frac -= 0.01
    res = {}
    for k in ks:
        w = W[k]
        mag = float(np.linalg.norm(w))
        direction = math.degrees(math.atan2(w[0], w[1]))
        theta = float(np.interp(mag, cap, th))
        res[k] = (direction, theta, mag)
    rep = dict(c_max=c_max, mr_geom=mr_geom, m_throw_bare=m_throw, frac=frac,
               unbalance={k: float(np.linalg.norm(U[k])) for k in ks},
               provided={k: res[k][2] for k in ks},
               internal_balance={k: res[k][2] / float(np.linalg.norm(U[k])) for k in ks},
               residual_force_kgmm=float(np.linalg.norm(A[:2] @ r)), residual_couple_kgmm2=float(np.linalg.norm(A[2:] @ r)),
               U=U, W=W)
    return res, rep


def crankshaft(cw):
    """Complete crankshaft at crank angle 0.  cw: dict k -> (direction, half-angle, m*r)."""
    parts = []
    seg_props = []
    for k in range(1, 9):
        s = throw_solid(k, (cw[k][0], cw[k][1]))
        seg_props.append(mass_props(s, RHO_STEEL))
        parts.append(s)
    body = parts[0]
    for s in parts[1:]:
        body = body + s
    hm = P.main_width / 2
    for j in range(1, P.n_main + 1):
        mx = L.main_x(j)
        body = body + Pos(mx - hm, 0, 0) * Rot(Y=90) * Cylinder(P.main_dia / 2, P.main_width, align=CMIN)
        if j > 1:
            body = body + Pos(mx - hm, 0, 0) * Rot(Z=180) * fillet_ring(P.main_dia / 2, 2.5)
        if j < P.n_main:
            body = body + Pos(mx + hm, 0, 0) * fillet_ring(P.main_dia / 2, 2.5)
    x_f = L.main_x(1) - hm
    x_r = L.main_x(P.n_main) + hm
    # front: seal/oil-pump-drive journal and damper nose
    body = body + Pos(x_f - 29, 0, 0) * Rot(Y=90) * Cylinder(30.0, 29.0, align=CMIN)
    body = body + Pos(x_f - 29 - 72, 0, 0) * Rot(Y=90) * Cylinder(25.0, 72.0, align=CMIN)
    body = body - Pos(x_f - 29 - 72 - 1, 0, 0) * Rot(Y=90) * Cylinder(7.0, 42.0, align=CMIN)        # M14 damper bolt thread
    # rear: sprocket seat, seal land, flywheel flange
    body = body + Pos(x_r, 0, 0) * Rot(Y=90) * Cylinder(32.0, REAR_SEAT, align=CMIN)
    body = body + Pos(x_r + REAR_SEAT, 0, 0) * Rot(Y=90) * Cylinder(47.5, REAR_SEAL, align=CMIN)
    body = body + Pos(x_r + REAR_SEAT + REAR_SEAL, 0, 0) * Rot(Y=90) * Cylinder(60.0, 14.0, align=CMIN)
    for i in range(9):
        y, z = _yz(40 * i, 45.0)
        body = body - Pos(x_r + REAR_SEAT + REAR_SEAL - 11, y, z) * Rot(Y=90) * Cylinder(5.1, 26.0, align=CMIN)                 # 9 x M12x1.5 flywheel bolts
    body = body - Pos(x_r + REAR_SEAT + REAR_SEAL, 0, 0) * Rot(Y=90) * Cylinder(17.5, 15.0, align=CMIN)                    # pilot bore
    # oil drillings: main j -> pin j (inclined), cross-drilling in the main, outlet in the pin
    for k in range(1, 9):
        psi = L.PIN_PHASE[k]
        mx = L.main_x(k)
        px = L.pin_x(k)
        cy, cz = _yz(psi, P.throw - 21.0)                                  # in the pin wall, crank-centre side
        body = body - cyl_between((mx, 0, 0), (px, cy, cz), 2.5)
        oy, oz = _yz(psi, P.throw - P.pin_dia / 2 - 1)
        body = body - cyl_between((px, cy, cz), (px, oy, oz), 2.5)
        ay, az = _yz(psi + 90, P.main_dia / 2 + 1)
        body = body - cyl_between((mx, -ay, -az), (mx, ay, az), 2.5)
    return body, seg_props


# ====================================================================== connecting rod
BE_BORE_R = P.pin_dia / 2 + P.bearing_shell_thk
SE_BORE_R = P.pin_dia_piston / 2 + 1.25
BOLT_Y = BE_BORE_R + 2.6 + P.rod_bolt_dia / 2


def rod_solids():
    """Returns (rod body, cap, shell half, small-end bush, bolt) in the rod frame:
    origin = big-end centre, +Z towards the small end, X = crank-axis direction (thickness)."""
    l = P.rod_length
    w = P.rod_be_width
    be = Rot(Y=90) * Cylinder(P.rod_be_od / 2, w, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    full = be
    for sy in (-1, 1):
        full = full + Pos(0, sy * BOLT_Y, -21.0) * Cylinder(7.6, 47.0, align=CMIN)                    # bolt bosses
        full = full + box_at(-w / 2, w / 2, sy * 20.0, sy * (BOLT_Y + 4.0), -14.0, 24.0)              # shoulder blocks
    # I-beam shank
    t_sh = 15.0
    z0, z1 = 22.0, l - 12.0
    shank = extrude(Plane.YZ.offset(-t_sh / 2) * poly([(-17.0, z0), (17.0, z0), (12.5, z1), (-12.5, z1)]), amount=t_sh)
    pocket = poly([(-11.5, z0 + 24), (11.5, z0 + 24), (7.5, z1 - 20), (-7.5, z1 - 20)])
    shank = shank - extrude(Plane.YZ.offset(3.5) * pocket, amount=5.0) - extrude(Plane.YZ.offset(-8.5) * pocket, amount=5.0)
    full = full + shank
    # small end, trapezoidal (20 mm at the loaded lower side, 14 mm at the top)
    se = Pos(0, 0, l) * Rot(Y=90) * Cylinder(P.rod_se_od / 2, P.rod_se_width, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    ang = math.degrees(math.atan2((P.rod_se_width - 14.0) / 2, P.rod_se_od))
    for sx in (-1, 1):
        cutter = Pos(sx * P.rod_se_width / 2, 0, l - P.rod_se_od / 2) * Rot(Y=-sx * ang) * \
            Pos(sx * 10, 0, 0) * Box(20, 60, 90, align=(Align.CENTER, Align.CENTER, Align.MIN))
        se = se - cutter
    full = full + se
    full = full - Rot(Y=90) * Cylinder(BE_BORE_R, w + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    full = full - Pos(0, 0, l) * Rot(Y=90) * Cylinder(SE_BORE_R, 40, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    for sy in (-1, 1):
        full = full - Pos(0, sy * BOLT_Y, -22.0) * Cylinder(P.rod_bolt_dia / 2 + 0.1, 49.0, align=CMIN)
        # small-end splash-oil bores (two inclined bores, SSP 248)
        a = sy * 32 * D2R
        full = full - cyl_between((0, SE_BORE_R * 0.9 * math.sin(a), l + SE_BORE_R * 0.9 * math.cos(a)),
                                  (0, (P.rod_se_od / 2 + 2) * math.sin(a), l + (P.rod_se_od / 2 + 2) * math.cos(a)), 1.5)
    upper = Box(200, 200, 400, align=CMIN)
    body = full & upper
    cap = full - upper
    shell_w = w - 1.5
    shell = (Rot(Y=90) * (Cylinder(BE_BORE_R, shell_w, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                          - Cylinder(P.pin_dia / 2 + 0.022, shell_w + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER)))) & \
        Pos(0, 0, 0.05) * Box(200, 200, 100, align=CMIN)
    bush = Pos(0, 0, l) * Rot(Y=90) * (Cylinder(SE_BORE_R, 14.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                                        - Cylinder(P.pin_dia_piston / 2 + 0.01, 16.0, align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    bolt = Rot(X=180) * hex_bolt(P.rod_bolt_dia, 44.0, head_h=6.0)          # shank along +Z, head below z = 0
    return body, cap, shell, bush, bolt


def rod_location(c, alpha):
    cp = L.pin_pos(c.pin, alpha)
    pp = L.piston_pin_pos(c, alpha)
    d = pp - cp
    return Location(Plane(origin=(c.x, float(cp[0]), float(cp[1])), x_dir=(1, 0, 0), z_dir=(0, float(d[0]), float(d[1]))))


# ====================================================================== piston
def piston_solids():
    """Returns (piston, compression ring, oil ring, pin, circlip) in the piston frame:
    origin = pin centre, +Z = cylinder axis (up), X = pin axis, +Y = high side of the crown (away from the bank
    centre plane)."""
    r = P.bore / 2 - P.piston_clear_dia / 2
    ch = P.comp_height
    ta = math.tan(P.crown_tilt_axis * D2R)
    n = (0.0, -math.sin(P.crown_tilt_axis * D2R), math.cos(P.crown_tilt_axis * D2R))
    z_bot = ch - P.piston_height
    z_top = ch + r * ta + 2.0
    outer = Pos(0, 0, z_bot) * Cylinder(r, z_top - z_bot, align=CMIN)
    crown_cut = Plane(origin=(0, 0, ch), x_dir=(1, 0, 0), z_dir=n) * Box(300, 300, 80, align=CMIN)
    env = outer - crown_cut
    z_low = ch - r * ta
    g1 = z_low - P.top_land - P.ring1_h
    g2 = g1 - 3.2 - P.ring2_h
    g3 = g2 - 2.3 - P.ring3_h
    for z, h in ((g1, P.ring1_h), (g2, P.ring2_h), (g3, P.ring3_h)):
        env = env - Pos(0, 0, z - 0.02) * (Cylinder(r + 2, h + 0.04, align=CMIN) - Cylinder(r - P.ring_radial - 0.5, h + 0.04, align=CMIN))
    # D-040: land reliefs.  The top land runs far hotter than the skirt (gas + thermal FE: 0.35 mm radial growth at the crown
    # edge against 0.03 mm cold skirt clearance) and on the high side it rises up to 11 mm into the head at TDC, so it is
    # turned down; the second land a little less.
    for z0, z1, dr in ((g1 + P.ring1_h, z_top + 1.0, P.piston_top_land_relief), (g2 + P.ring2_h, g1, P.piston_second_land_relief)):
        env = env - Pos(0, 0, z0) * (Cylinder(r + 2, z1 - z0, align=CMIN) - Cylinder(r - dr, z1 - z0, align=CMIN))
    # slipper skirt: remove the pin-end sides up to piston_pin_end_land below the oil-ring groove (D-037: 1.5 mm before -
    # with load-controlled pin bores the ring belt bends over the bosses and that ledge carried the peak)
    for sx in (-1, 1):
        env = env - box_at(sx * 33.0, sx * 60.0, -60, 60, z_bot - 1, g3 - P.piston_pin_end_land)
    # D-035: the ring belt is solid out from the under-crown cavity (radius piston_uc_r); only the skirt below the oil-ring
    # groove keeps the thin slipper wall.  (The first design carried the 4.6 mm skirt wall up into the ring belt, which
    # left 1 mm behind the ring grooves.)
    z_belt = g3 - 2.0
    crown_under = Plane(origin=(0, 0, ch - P.piston_crown_thk), x_dir=(1, 0, 0), z_dir=n) * Box(300, 300, 80, align=CMIN)
    cav = (Pos(0, 0, z_bot - 1) * Cylinder(r - P.piston_skirt_wall, z_belt - z_bot + 1, align=CMIN)) + \
        (Pos(0, 0, z_belt - 0.5) * Cylinder(P.piston_uc_r, z_top - z_belt, align=CMIN))
    cav = cav - crown_under
    boss = None
    for sx in (-1, 1):
        b = box_at(sx * 11.5, sx * 40.0, -17.0, 17.0, -15.0, ch + 30)
        boss = b if boss is None else boss + b
    piston = (env - cav) + (env & boss)
    # D-037: above the ring-belt step the bosses are carried out to the under-crown cavity wall.  With the cavity at
    # piston_uc_r = 22 the boss side faces (y = +/-17) met the cavity wall at a shallow angle and left a 1.75 mm wide
    # sliver notch with a 39 deg tip at |x| 11.5-14; the gas-load FE peak (219 MPa) sat at its root.  The cavity is now
    # a plain slot between the bosses (|x| < 11.5) for the rod small end, and the edges where the boss side faces meet
    # the underside of the step carry a fillet (the D-035 peak sat on the same edge, at its outer end).
    fill = Pos(0, 0, z_belt) * Cylinder(P.piston_uc_r + 0.5, z_top - z_belt, align=CMIN)
    rf = P.piston_boss_fillet_r
    for sx in (-1, 1):
        piston = piston + (env & fill & box_at(sx * 11.5, sx * 40.0, -30.0, 30.0, z_belt, z_top))
        for sy in (-1, 1):
            strip = box_at(sx * 11.5, sx * 36.0, sy * 16.95, sy * (17.0 + rf), z_belt - rf, z_belt + 0.05) - \
                Pos(0, sy * (17.0 + rf), z_belt - rf) * Rot(Y=90) * Cylinder(rf, 80, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            piston = piston + (env & strip)
    # oil cooling gallery behind the ring pack.  D-036: the gallery follows the slanted crown at a constant depth
    # (vertical walls, roof and floor parallel to the crown plane); the flat gallery of D-035 lay 14-23 mm below the
    # high side of the crown.  Fed by the cooling jet through an inlet on the +Y side (rod plane), outlet on -Y.
    cos_t = math.cos(P.crown_tilt_axis * D2R)
    dep0, dep1 = P.gallery_top_gap, P.gallery_top_gap + P.gallery_h              # depth below the crown plane, normal
    slab = Plane(origin=(0, 0, ch - dep1 / cos_t), x_dir=(1, 0, 0), z_dir=n) * Box(300, 300, P.gallery_h, align=CMIN)
    ring = Pos(0, 0, z_bot) * (Cylinder(P.gallery_r_out, z_top - z_bot, align=CMIN) - Cylinder(P.gallery_r_in, z_top - z_bot, align=CMIN))
    gallery = ring & slab
    z_floor = lambda y: ch + y * ta - dep1 / cos_t                                # gallery floor height at lateral position y
    zg0 = z_floor(-P.gallery_r_out)                                                # lowest point of the floor (low side)
    zg1 = ch + P.gallery_r_out * ta - dep0 / cos_t                                 # highest point of the roof (high side)
    assert zg0 >= g3 + P.ring3_h + 0.5, ("gallery floor too close to the oil-ring groove", zg0, g3 + P.ring3_h)
    r_mid = 0.5 * (P.gallery_r_in + P.gallery_r_out)
    xj, yj = 0.0, P.jet_inlet_y
    assert P.gallery_r_in <= yj - P.gallery_inlet_dia / 2 and yj + P.gallery_inlet_dia / 2 <= P.gallery_r_out + 0.2
    inlet = cyl_between((xj, yj, z_belt - 1.0), (xj, yj, z_floor(yj) + 1.0), P.gallery_inlet_dia / 2)
    outlet = cyl_between((0, -r_mid, z_belt - 1.0), (0, -r_mid, z_floor(-r_mid) + 1.0), P.gallery_outlet_dia / 2)
    piston = piston - gallery - inlet - outlet
    # under-crown ribs between bosses and skirt keep the crown stiff
    piston = piston - Rot(Y=90) * Cylinder(P.pin_dia_piston / 2 + 0.004, 100, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    for sx in (-1, 1):
        piston = piston - Pos(sx * (P.pin_length / 2 + 0.3), 0, 0) * Rot(Y=sx * 90) * \
            (Cylinder(P.pin_dia_piston / 2 + 1.0, 1.3, align=CMIN) - Cylinder(P.pin_dia_piston / 2 - 0.5, 1.3, align=CMIN))
    # oil-ring drain holes into the piston interior (SSP 248)
    for i in range(8):
        a = (22.5 + 45 * i) * D2R
        piston = piston - cyl_between((0.6 * r * math.cos(a), 0.6 * r * math.sin(a), g3 + 1.0),
                                      ((r - 1.0) * math.cos(a), (r - 1.0) * math.sin(a), g3 + 1.0), 0.9)
    # valve pockets for the far-side valves on the low side of the crown
    for sx in (-1, 1):
        y0 = -P.valve_du_in
        zc = ch + y0 * ta
        org = (sx * 17.6 - 1.6 * n[0], y0 - 1.6 * n[1], zc - 1.6 * n[2])
        piston = piston - Plane(origin=org, x_dir=(1, 0, 0), z_dir=n) * Cylinder(P.valve_in_dia / 2 + 1.8, 30, align=CMIN)
    gap = Pos(r, 0, 0) * Box(12, 0.35, 10, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    ring_c = (Cylinder(P.bore / 2, P.ring1_h - 0.03, align=CMIN) - Cylinder(P.bore / 2 - P.ring_radial, P.ring1_h, align=CMIN)) - gap
    ring_o = (Cylinder(P.bore / 2, P.ring3_h - 0.03, align=CMIN) - Cylinder(P.bore / 2 - P.ring_radial + 0.4, P.ring3_h, align=CMIN)) - gap
    pin = Rot(Y=90) * (Cylinder(P.pin_dia_piston / 2, P.pin_length, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                       - Cylinder(P.pin_bore_id / 2, P.pin_length + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    clip = Rot(Y=90) * (Torus(P.pin_dia_piston / 2 + 0.25, 0.6) - Pos(P.pin_dia_piston / 2, 0, 0) * Box(6, 4, 3, align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    return piston, ring_c, ring_o, pin, clip, dict(g1=g1, g2=g2, g3=g3, z_low=z_low, z_bot=z_bot, z_belt=z_belt,
                                                     gallery_z=(zg0, zg1), gallery_depth=(dep0, dep1), inlet_xy=(xj, yj),
                                                     gallery_area=(P.gallery_r_out - P.gallery_r_in) * P.gallery_h)


def piston_frame(c, alpha):
    """Plane of the piston frame for cylinder c at crank angle alpha."""
    pp = L.piston_pin_pos(c, alpha)
    ex, eu, ev = L.bank_axes(c.bank)
    d = c.d3
    away = eu if c.row == "outer" else -eu
    y = away - (away @ d) * d
    y = y / np.linalg.norm(y)
    x = np.cross(y, d)
    return Plane(origin=(c.x, float(pp[0]), float(pp[1])), x_dir=tuple(float(v) for v in x), z_dir=tuple(float(v) for v in d))


def piston_location(c, alpha):
    return Location(piston_frame(c, alpha))
