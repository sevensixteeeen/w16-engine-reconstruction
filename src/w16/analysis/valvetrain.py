"""Valve-train engineering model: head layout (transverse-plane geometry), cam/valve lift, timing,
piston-to-valve clearance, spring load requirement.

Layout convention (head-local): u lateral (+ outboard, - towards the valley), w up from the head joint face,
x along the crank.  See DECISIONS D-020.
"""
from __future__ import annotations
import math
import numpy as np

from ..params import P
from .. import layout as L

# ------------------------------------------------------------------ timing (EST; phasers act around these)
TIMING = dict(
    ivo=-12.0,     # deg ATDC gas-exchange TDC (i.e. 12 deg BTDC)
    ivc=230.0,     # deg ATDC gas-exchange TDC (50 deg ABDC)
    evo=-232.0,    # (52 deg BBDC)
    evc=10.0,      # (10 deg ATDC)
    flank_frac=0.17,   # fraction of the event taken by each positive-acceleration flank
    intake_phaser_range=52.0, exhaust_phaser_range=22.0,   # deg crank, VW W-family values (SSP 248)
)


def lift_curve(theta, t_open, t_close, lift_max, flank_frac=None):
    """Valve lift (mm) vs crank angle using a half-sine acceleration law:
    positive half-sine flanks, negative half-sine nose.  Returns lift, velocity (mm/deg), accel (mm/deg^2)."""
    ff = TIMING["flank_frac"] if flank_frac is None else flank_frac
    D = t_close - t_open
    b = ff * D
    x = np.asarray(theta, float) - t_open
    n = 4001
    xs = np.linspace(0, D, n)
    acc = np.where(xs < b, np.sin(math.pi * xs / b), 0.0)
    acc = np.where(xs > D - b, np.sin(math.pi * (D - xs) / b), acc)
    mid = (xs >= b) & (xs <= D - b)
    a2 = 2 * b / (D - 2 * b)                                  # nose amplitude giving zero velocity at mid-event
    acc = np.where(mid, -a2 * np.sin(math.pi * (xs - b) / (D - 2 * b)), acc)
    dx = xs[1] - xs[0]
    vel = np.cumsum(acc) * dx
    vel -= np.linspace(0, vel[-1], n)                         # remove numerical drift
    lift = np.cumsum(vel) * dx
    scale = lift_max / lift.max()
    lift, vel, acc = lift * scale, vel * scale, acc * scale
    inside = (x >= 0) & (x <= D)
    return (np.where(inside, np.interp(x, xs, lift), 0.0), np.where(inside, np.interp(x, xs, vel), 0.0),
            np.where(inside, np.interp(x, xs, acc), 0.0))


def valve_lifts(theta):
    """Intake and exhaust lift for theta = deg ATDC of gas-exchange TDC (range -360..360)."""
    li = lift_curve(theta, TIMING["ivo"], TIMING["ivc"], P.valve_lift_in)
    le = lift_curve(theta, TIMING["evo"], TIMING["evc"], P.valve_lift_ex)
    return li, le


# ------------------------------------------------------------------ head transverse layout
def head_layout():
    """Positions (u, w) of valve heads, valve tips, cams, finger pivots and plug wells for both rows.

    Returns dict keyed by row ('inner'/'outer') with sub-dicts for 'in'/'ex' valves and 'plug'.
    """
    U = P.u_bore_head                                          # bore centre on the head joint face (D-039; was the deck value)
    tip_w = P.valve_tip_w
    out = {}
    # chamber roof: a plane through the low edge, rising towards the side the valves lean away from
    for row, sgn in (("inner", -1.0), ("outer", +1.0)):
        uc = sgn * U                                           # bore centre at the joint face
        d = {}
        for kind in ("in", "ex"):
            u_head = uc + (-P.valve_du_in if kind == "in" else P.valve_du_ex)
            cam_u = -P.cam_u if kind == "in" else P.cam_u
            # finger points from the valve tip towards the cam; the tip lies finger_tip_len beyond the cam,
            # on the side of the cam where this row's valve heads are.
            side = -1.0 if u_head < cam_u else 1.0
            far = side * cam_u < 0                             # valve head on the head-centre side of its camshaft (long valve)
            tip_len = P.finger_tip_far if far else P.finger_tip_near
            piv_len = P.finger_piv_far if far else P.finger_piv_near
            u_tip = cam_u + side * tip_len
            u_piv = cam_u - side * piv_len
            d[kind] = dict(u_head=u_head, u_tip=u_tip, u_piv=u_piv, cam_u=cam_u, side=side, far=far,
                           tip_len=tip_len, piv_len=piv_len, ratio=(tip_len + piv_len) / piv_len)
        # roof plane: perpendicular to the mean valve axis of this row
        w_head_guess = 6.0
        for _ in range(4):                                     # iterate head heights on the roof
            tilts = []
            for kind in ("in", "ex"):
                v = d[kind]
                v["tilt"] = math.degrees(math.atan2(v["u_tip"] - v["u_head"], tip_w - v.get("w_head", w_head_guess)))
                tilts.append(v["tilt"])
            roof_tilt = 0.5 * (tilts[0] + tilts[1])            # deg; + means the roof normal leans to +u
            # roof height at lateral position u: low edge where the roof normal points
            t = math.tan(math.radians(roof_tilt))
            edge = uc + math.copysign(P.bore / 2, roof_tilt)   # low edge
            roof_w = lambda u, t=t, edge=edge: P.roof_low_w + (edge - u) * t
            for kind in ("in", "ex"):
                d[kind]["w_head"] = roof_w(d[kind]["u_head"])
        d["roof_tilt"] = roof_tilt
        d["roof_edge_u"] = edge
        d["uc"] = uc
        for kind in ("in", "ex"):
            v = d[kind]
            v["length"] = math.hypot(v["u_tip"] - v["u_head"], tip_w - v["w_head"])
        # spark plug: electrode at the roof on the bore centre, well reaches the head centre plane at plug_top_w
        w0 = roof_w(uc)
        d["plug"] = dict(u0=uc, w0=w0, u1=0.0, w1=P.plug_top_w,
                         tilt=math.degrees(math.atan2(0.0 - uc, P.plug_top_w - w0)))
        out[row] = d
    return out


CHAMBER_CAD_FACTOR = 1.0725      # set so that the CAD-measured clearance volume gives CR 9.0 (see 06_ASSEMBLIES/cad_validation.json);
                                 # D-042: 1.0578 before - the 2.2 mm piston valve pockets (were 1.6) add 1.2 cm3; D-040: 1.0105 before - the D-039 chamber cut reaches the joint face over the whole bore (+3.7 cm3)
                                 # and the D-040 top-land relief adds 1.8 cm3 of crevice; D-038: 1.0022 before the D-034 head layout


def crevice_volume(crown_tilt_axis):
    """Top-land crevice (mm3): annulus between the bore and the turned-down top land (D-040), mean height = top land on
    the low side + the crown rise at the axis; plus 350 mm3 ring-groove clearances (EST)."""
    r_tl = P.bore / 2 - P.piston_clear_dia / 2 - P.piston_top_land_relief
    h = P.top_land + P.bore / 2 * math.tan(math.radians(crown_tilt_axis))
    return math.pi * ((P.bore / 2) ** 2 - r_tl ** 2) * h + 350.0


def finalize_geometry():
    """Solve the piston-crown tilt that gives the reference compression ratio and update the deck height.

    Clearance volume = head chamber (under the tilted roof plane) + gasket + wedge between the crown plane and
    the head joint face + ring-land crevice.  The crown is a plane rising from its low edge (where the deck
    clearance is defined) towards the high side of the roof by the angle kappa."""
    g = math.radians(0.5 * P.vr_angle)
    a_e = math.pi * (P.bore / 2) ** 2 / math.cos(g)             # bore footprint on the joint face (ellipse)
    r_u = P.bore / 2 / math.cos(g)
    a_g = math.pi * (P.gasket_bore / 2) ** 2 / math.cos(g)
    tilt_axis = getattr(P, "crown_tilt_axis", 0.5 * P.vr_angle + 7.0)
    for _ in range(6):
        lay = head_layout()
        tilt = 0.5 * (abs(lay["inner"]["roof_tilt"]) + abs(lay["outer"]["roof_tilt"]))
        v_head = CHAMBER_CAD_FACTOR * a_e * (P.roof_low_w + r_u * math.tan(math.radians(tilt))) + 900.0   # + plug/seat recesses (EST)
        v_c = P.v_clear_cc * 1000.0
        v_crev = crevice_volume(tilt_axis)                      # D-040 (600 mm3 EST before)
        tk = (v_head + a_e * P.deck_clearance + a_g * P.gasket_thk + v_crev - v_c) / (a_e * r_u)
        tk = max(tk, 0.0)
        tilt_axis = 0.5 * P.vr_angle + math.degrees(math.atan(tk))
        P.add("crown_rise_axis", r_u * tk, "mm", "CALC", "rise of the crown plane at the piston axis above its low edge")
        L.set_deck()
    P.add("crown_tilt", math.degrees(math.atan(tk)), "deg", "CALC",
          "tilt of the piston crown relative to the head joint face (towards the roof) giving CR 9.0")
    P.add("crown_tilt_axis", 0.5 * P.vr_angle + P.crown_tilt, "deg", "CALC", "crown tilt relative to the piston-axis normal")
    P.add("roof_tilt", tilt, "deg", "CALC", "combustion-chamber roof tilt relative to the head joint face")
    P.add("v_head_chamber_est_cc", v_head / 1000.0, "cm3", "CALC", "head chamber volume (analytic estimate)")
    return P.crown_tilt


def layout_clearances():
    """Transverse-plane clearance checks of the valve gear (plug well vs springs, cams, fingers)."""
    lay = head_layout()
    res = []
    r_well = P.plug_well_dia / 2 + 1.5                          # bore + minimum cast wall
    r_spring = P.spring_od / 2 + 1.0                            # spring + pocket clearance
    r_cam_core = 11.0
    for row, d in lay.items():
        pl = d["plug"]
        up = lambda w: pl["u0"] + (pl["u1"] - pl["u0"]) * (w - pl["w0"]) / (pl["w1"] - pl["w0"])
        for kind, dx in (("in", P.valve_dx_in), ("ex", P.valve_dx_ex)):
            v = d[kind]
            uv = lambda w, v=v: v["u_head"] + (v["u_tip"] - v["u_head"]) * (w - v["w_head"]) / (P.valve_tip_w - v["w_head"])
            worst = 1e9
            for w in np.linspace(62.0, P.valve_tip_w, 26):      # spring zone
                dist = math.hypot(up(w) - uv(w), dx) - r_well - r_spring
                worst = min(worst, dist)
            res.append((f"{row} row: plug well vs {kind} valve spring (min wall, mm)", worst))
            worst = 1e9
            for w in np.linspace(8.0, 60.0, 27):                # guide zone
                dist = math.hypot(up(w) - uv(w), dx) - r_well - (P.valve_guide_od / 2 + 1.5)
                worst = min(worst, dist)
            res.append((f"{row} row: plug well vs {kind} valve guide boss (min wall, mm)", worst))
        for cam_u, nm in ((-P.cam_u, "intake cam"), (P.cam_u, "exhaust cam")):
            # distance from the cam axis (a point in the u-w plane) to the plug-well axis line
            ax, aw = pl["u0"], pl["w0"]; bx, bw = pl["u1"], pl["w1"] + 30.0 * (pl["w1"] - pl["w0"]) / (pl["w1"] - pl["w0"])
            bx = pl["u0"] + (pl["u1"] - pl["u0"]) * (bw - pl["w0"]) / (pl["w1"] - pl["w0"])
            t = ((cam_u - ax) * (bx - ax) + (P.cam_w - aw) * (bw - aw)) / ((bx - ax) ** 2 + (bw - aw) ** 2)
            px, pw = ax + t * (bx - ax), aw + t * (bw - aw)
            res.append((f"{row} row: plug well vs {nm} core (clearance, mm)",
                        math.hypot(cam_u - px, P.cam_w - pw) - r_cam_core - P.plug_well_dia / 2 - 1.5))
    lobe_r = P.cam_base_r + max(P.valve_lift_in, P.valve_lift_ex) / min(rocker_ratio(True), rocker_ratio(False))
    res.append(("cam lobe tip circle to opposite cam lobe tip circle (mm)", 2 * P.cam_u - 2 * lobe_r))
    # finger-to-finger in the same x band: I finger [tip..pivot] and E finger [tip..pivot] must not overlap in u
    for row, d in lay.items():
        a = sorted((d["in"]["u_tip"], d["in"]["u_piv"]))
        b = sorted((d["ex"]["u_tip"], d["ex"]["u_piv"]))
        gap = max(b[0] - a[1], a[0] - b[1])
        res.append((f"{row} row: intake finger vs exhaust finger lateral gap (mm)", gap - 12.0))
    res += cross_clearances(lay)
    return res


def _seg_dist(a0, a1, b0, b1, n=80):
    A = np.linspace(a0, a1, n)
    B = np.linspace(b0, b1, n)
    return float(np.min(np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2)))


def cross_clearances(lay=None):
    """3-D clearance between the long (far-row) valve of a cylinder and the support element of its short (near-row)
    valve on the other camshaft.  Coordinates (x, u, w) relative to the bore centre in x.  This is the check whose
    absence let the conflict of D-031 through the 2-D layout study."""
    lay = lay or head_layout()
    out = []
    r_spring = P.spring_od / 2
    for row, d in lay.items():
        far_k = "in" if d["in"]["far"] else "ex"
        near_k = "ex" if far_k == "in" else "in"
        vf, vn = d[far_k], d[near_k]
        dx_f = P.valve_dx_in if far_k == "in" else P.valve_dx_ex
        dx_n = P.valve_dx_in if near_k == "in" else P.valve_dx_ex
        Tf = np.array([dx_f, vf["u_tip"], P.valve_tip_w])
        Hf = np.array([dx_f, vf["u_head"], vf["w_head"]])
        a = (Tf - Hf) / np.linalg.norm(Tf - Hf)
        S = Tf - a * P.spring_seat_drop                           # spring seat
        boss = (np.array([dx_n, vn["u_piv"], P.hla_boss_w0]), np.array([dx_n, vn["u_piv"], 106.0]))
        body = (np.array([dx_n, vn["u_piv"], 84.0]), np.array([dx_n, vn["u_piv"], 110.0]))
        out.append((f"{row} row: long {far_k} valve spring vs short {near_k} valve support-element boss (mm)",
                    _seg_dist(S, Tf - a * 3.0, *boss) - r_spring - 8.0))
        out.append((f"{row} row: long {far_k} valve spring vs short {near_k} valve support element (mm)",
                    _seg_dist(S, Tf - a * 3.0, *body) - r_spring - 6.0))
        out.append((f"{row} row: long {far_k} valve stem vs short {near_k} valve support-element boss (mm)",
                    _seg_dist(Hf, Tf, *boss) - P.valve_stem_dia / 2 - 8.0))
        pl = d["plug"]
        p0, p1 = np.array([0.0, pl["u0"], pl["w0"]]), np.array([0.0, pl["u1"], pl["w1"]])
        out.append((f"{row} row: plug well vs short {near_k} valve support-element bore (wall, mm)",
                    _seg_dist(p0, p1, *body) - P.plug_well_dia / 2 - 6.0))
    return out


def rocker_ratio(far=None):
    """Valve lift / cam lift of the far-row (far=True) or near-row (far=False) finger; None -> near-row."""
    if far:
        return (P.finger_tip_far + P.finger_piv_far) / P.finger_piv_far
    return (P.finger_tip_near + P.finger_piv_near) / P.finger_piv_near


# ------------------------------------------------------------------ piston-to-valve clearance
def piston_valve_clearance():
    """Minimum vertical clearance between each valve head rim and the piston crown over the cycle (mm).

    theta: deg ATDC gas-exchange TDC.  The crown plane is tilted by crown_tilt to the joint face, so the clearance is
    taken at 72 points round the valve rim, each against the crown height under that point.  D-042: the crown height was
    taken under the valve centre before; for the long valves the lowest rim point lies ~15 mm nearer the crown's low
    edge, where the crown is ~2.15 mm lower, so the old value was ~2 mm too pessimistic (CAD: true minimum distance)."""
    lay = head_layout()
    th = np.arange(-360.0, 360.0, 0.5)
    (li, _, _), (le, _, _) = valve_lifts(th)
    phi = np.linspace(0.0, 2 * math.pi, 73)[:-1]
    out = {}
    for row in ("inner", "outer"):
        c = L.CYL[2] if row == "inner" else L.CYL[1]
        # gas-exchange TDC is 360 deg after firing TDC
        x = L.piston_x_from_tdc(c, th + c.fire + 360.0)
        crown_low = -(x + P.deck_clearance + P.gasket_thk)      # crown low-edge height relative to the head joint face
        d_row = lay[row]
        tk = math.tan(math.radians(getattr(P, "crown_tilt", 0.0)))
        for kind, lift, dia in (("in", li, P.valve_in_dia), ("ex", le, P.valve_ex_dia)):
            v = lay[row][kind]
            au, aw = v["u_tip"] - v["u_head"], P.valve_tip_w - v["w_head"]
            na = math.hypot(au, aw)
            au, aw = au / na, aw / na                              # valve axis (u, w), towards the tip
            r = dia / 2
            u_rim = v["u_head"] - lift[:, None] * au + r * np.sin(phi)[None, :] * aw
            w_rim = v["w_head"] - lift[:, None] * aw - r * np.sin(phi)[None, :] * au
            crown_w = crown_low[:, None] + np.abs(d_row["roof_edge_u"] - u_rim) * tk    # tilted crown under each rim point
            pocket = P.piston_valve_pocket_depth if v["far"] else 0.0   # the long (far-row) valves run over the crown pockets
            cl = (w_rim - crown_w).min(axis=1) + pocket
            i = int(np.argmin(cl))
            out[(row, kind)] = dict(min_clear=float(cl[i]), at_theta=float(th[i]), lift_there=float(lift[i]), pocket_depth=pocket,
                                    required=1.5 if kind == "in" else 2.0)
    return out


# ------------------------------------------------------------------ spring requirement
def spring_requirement(rpm=None, m_valve_in=0.048, m_valve_ex=0.044, m_retainer=0.008, m_spring=0.038, J_finger_equiv=0.022):
    """Spring force needed to keep the follower on the cam at the nose (cam speed = rpm/2).

    Effective reciprocating mass at the valve = valve + retainer/cotters + 1/3 spring + finger equivalent mass.
    Returns dict for intake and exhaust.  Masses are EST until taken from CAD.
    """
    rpm = rpm or P.rpm_overspeed
    w_crank = rpm * 6.0                                          # deg/s
    th = np.arange(-360.0, 360.0, 0.1)
    out = {}
    for kind, (to, tc, lm, mv) in dict(
            intake=(TIMING["ivo"], TIMING["ivc"], P.valve_lift_in, m_valve_in),
            exhaust=(TIMING["evo"], TIMING["evc"], P.valve_lift_ex, m_valve_ex)).items():
        lift, vel, acc = lift_curve(th, to, tc, lm)
        a_ms2 = acc * 1e-3 * w_crank ** 2                         # m/s^2 (mm/deg^2 * (deg/s)^2)
        m_eff = mv + m_retainer + m_spring / 3 + J_finger_equiv
        f_nose = -m_eff * a_ms2.min()                             # N required at the nose
        i = int(np.argmin(a_ms2))
        f_req = 1.25 * f_nose                                     # 25 % margin against separation
        # choose spring: seat load to hold the valve shut against boost / exhaust back-pressure + rate
        seat_area = math.pi / 4 * ((P.valve_in_dia if kind == "intake" else P.valve_ex_dia) * 1e-3) ** 2
        dp = 2.2e5 if kind == "intake" else 3.4e5                 # Pa: boost behind intake valve / exhaust back-pressure pulse
        f_seat_min = dp * seat_area * 1.3 + 40.0
        rate = max((f_req - f_seat_min) / (lift[i] * 1e-3), 12e3)  # N/m
        f_seat = max(f_seat_min, f_req - rate * lift[i] * 1e-3)
        out[kind] = dict(m_eff=m_eff, a_nose=float(a_ms2.min()), a_flank=float(a_ms2.max()), f_nose=float(f_nose),
                         f_required=float(f_req), f_seat=float(f_seat), rate_n_mm=float(rate / 1e3),
                         f_open=float(f_seat + rate * lm * 1e-3), v_seat_mm_deg=float(np.abs(vel).max()),
                         v_max_ms=float(np.abs(vel).max() * 1e-3 * w_crank))
    return out


def mach_index(rpm=None):
    """Inlet Mach index Z (Taylor) - should stay below ~0.6 for good breathing."""
    rpm = rpm or P.rpm_rated
    sp = 2 * P.stroke * 1e-3 * rpm / 60
    a = math.sqrt(1.4 * 287 * 325.0)
    ci = 0.38                                                    # mean inlet flow coefficient (EST)
    return (P.bore / P.valve_in_dia) ** 2 / 2 * sp / (ci * a)
