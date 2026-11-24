"""Crank-train dynamics: gas + inertia forces, free forces/moments, bearing loads, torque ripple, torsional vibration.

Rigid-body, quasi-static bearing model (statically determinate bay model).  See report for limitations.
"""
from __future__ import annotations
import math
import numpy as np

from ..params import P
from .. import layout as L
from . import cycle

N_AL = 2880                                    # samples per 720 deg (0.25 deg)
AL = np.arange(N_AL) * 720.0 / N_AL


def masses():
    m_rod_rec = P.m_rod * P.rod_cg_frac
    m_rod_rot = P.m_rod - m_rod_rec
    m_rec = P.m_piston + P.m_pin + P.m_rings + m_rod_rec
    return m_rec, m_rod_rot


def pressure_720(cyc, p_man, p_exh):
    """Cylinder pressure over the 720 deg cycle, theta relative to firing TDC in [-360, 360)."""
    th = np.arange(N_AL) * 720.0 / N_AL - 360.0
    p = np.interp(th, cyc["th"], cyc["p"])
    p = np.where(th < -180.0, p_man, p)        # intake stroke
    p = np.where(th >= 180.0, p_exh, p)        # exhaust stroke
    return th, p


def cylinder_forces(c, rpm, th_p, p_trace):
    """Forces of one cylinder vs crank angle alpha (0..720).  Returns dict of arrays (N, N m)."""
    om = rpm * math.pi / 30.0
    dal = math.radians(AL[1] - AL[0])
    s = L.piston_s(c, AL) * 1e-3
    sd = (np.roll(s, -1) - np.roll(s, 1)) / (2 * dal) * om
    sdd = (np.roll(s, -1) - 2 * s + np.roll(s, 1)) / dal ** 2 * om ** 2
    m_rec, m_rod_rot = masses()
    theta = (AL - c.fire + 360.0) % 720.0 - 360.0
    p = np.interp(theta, th_p, p_trace)
    Fg = (p - P.p_crankcase_bar * 1e5) * math.pi / 4 * (P.bore * 1e-3) ** 2
    pp = L.piston_pin_pos(c, AL)
    cp = L.pin_pos(c.pin, AL)
    er = (pp - cp) / P.rod_length
    d = c.d
    n = np.array([d[1], -d[0]])
    R = (m_rec * sdd + Fg) / (er @ d)                       # rod force, + = compression
    N = -R * (er @ n)                                        # piston side force
    F_pin = -R[:, None] * er                                 # rod force on the crankpin (y, z)
    cpm = cp * 1e-3
    torque = cpm[:, 0] * F_pin[:, 1] - cpm[:, 1] * F_pin[:, 0]
    F_rec_block = -(m_rec * sdd)[:, None] * d[None, :]       # inertia reaction of the reciprocating mass
    return dict(s=s, v=sd, a=sdd, p=p, Fg=Fg, R=R, N=N, F_pin=F_pin, torque=torque, F_rec=F_rec_block, theta=theta)


def orders(x):
    """Amplitude of selected engine orders of a 720-deg periodic signal."""
    X = np.fft.rfft(x) / len(x) * 2
    return {o: float(abs(X[int(round(2 * o))])) for o in (0.5, 1, 1.5, 2, 3, 4, 6, 8)}


def run(rpm, op=None, A_turb=None):
    """Full crank-train force analysis at one full-load operating point."""
    if op is None:
        vd = P.displacement_cc * 1e-6
        op = cycle.operating_point(rpm, cycle.torque_target(rpm) * 4 * math.pi / vd, A_turb=A_turb or cycle.size_turbine())
    cyc = op["_cyc"]
    th_p, p_tr = pressure_720(cyc, op["p_man_bar"] * 1e5, op["p3_bar"] * 1e5)
    om = rpm * math.pi / 30.0
    m_rec, m_rod_rot = masses()
    cf = {c.no: cylinder_forces(c, rpm, th_p, p_tr) for c in L.CYLS}

    T = sum(cf[c.no]["torque"] for c in L.CYLS)
    T_ind_expected = (cyc["imep_g"] + cyc["pmep"]) * P.displacement_cc * 1e-6 / (4 * math.pi)

    # free forces and moments from the reciprocating masses
    F_rec = sum(cf[c.no]["F_rec"] for c in L.CYLS)                       # (n, 2) -> (y, z)
    M_y = sum(-c.x * 1e-3 * cf[c.no]["F_rec"][:, 1] for c in L.CYLS)     # N m
    M_z = sum(c.x * 1e-3 * cf[c.no]["F_rec"][:, 0] for c in L.CYLS)

    # rotating masses per throw and the counterweights that balance them
    r = P.throw * 1e-3
    throw = {}
    for k in range(1, 9):
        e_pin = L.vec(L.PIN_PHASE[k] - AL)
        e_q = L.vec(L.PIN_PHASE[k] - AL + 90.0)
        mr_rot = 2 * m_rod_rot * r                   # two rod big ends (crankpin itself is balanced in CAD)
        F_rot = mr_rot * om ** 2 * e_pin
        # Counterweight of this throw = minus the crank-fixed (co-rotating) part of all inertia forces of the
        # throw: rotating rod mass + the reciprocating masses of the 90-deg cylinder pair.  Because of the VR
        # offsets this vector is not exactly opposite the pin, so magnitude AND angle are solved per throw.
        F_in = F_rot + sum(cf[c.no]["F_rec"] for c in L.CYLS if c.pin == k)
        a_bar = float((F_in * e_pin).sum(1).mean())
        b_bar = float((F_in * e_q).sum(1).mean())
        F_cw = -(a_bar * e_pin + b_bar * e_q)
        mr_cw = math.hypot(a_bar, b_bar) / om ** 2
        cw_angle = math.degrees(math.atan2(-b_bar, -a_bar))      # angle of the counterweight vector from the pin, towards +phi
        rods = sum(cf[c.no]["F_pin"] for c in L.CYLS if c.pin == k)
        throw[k] = dict(F=rods + F_rot + F_cw, F_cw=F_cw, F_rot=F_rot, mr_cw=mr_cw, cw_angle=cw_angle)

    rot_net = {k: throw[k]["F_rot"] + throw[k]["F_cw"] for k in throw}
    F_free = F_rec + sum(rot_net.values())
    M_y_free = M_y + sum(-L.pin_x(k) * 1e-3 * rot_net[k][:, 1] for k in throw)
    M_z_free = M_z + sum(L.pin_x(k) * 1e-3 * rot_net[k][:, 0] for k in throw)

    # main bearing loads (each bay simply supported on its two neighbouring mains)
    mains = {}
    for j in range(1, P.n_main + 1):
        F = np.zeros((N_AL, 2))
        if j - 1 >= 1:
            F += 0.5 * throw[j - 1]["F"]
        if j <= 8:
            F += 0.5 * throw[j]["F"]
        mag = np.hypot(F[:, 0], F[:, 1])
        i = int(np.argmax(mag))
        mains[j] = dict(F=F, peak=float(mag.max()), mean=float(mag.mean()), peak_vec=F[i].tolist(), peak_alpha=float(AL[i]))
    w_eff_main = P.main_shell_width - 2 * P.main_shell_chamfer    # load-carrying land of the chamfered main shells (D-050; was 16 mm)
    w_eff_rod = P.rod_be_width - 1.5
    rod_peak_c = max(float(cf[c.no]["R"].max()) for c in L.CYLS)
    rod_peak_t = min(float(cf[c.no]["R"].min()) for c in L.CYLS)
    side_peak = max(float(np.abs(cf[c.no]["N"]).max()) for c in L.CYLS)
    e_pin1 = L.vec(L.PIN_PHASE[1] - AL)
    be = cf[1]["F_pin"] + m_rod_rot * r * om ** 2 * e_pin1
    be_mag = np.hypot(be[:, 0], be[:, 1])
    main_peak = max(m["peak"] for m in mains.values())
    return dict(rpm=rpm, op=op, cf=cf, T=T, T_mean=float(T.mean()), T_ind_expected=T_ind_expected,
                T_max=float(T.max()), T_min=float(T.min()), T_orders=orders(T),
                F_free=F_free, M_y_free=M_y_free, M_z_free=M_z_free,
                F_free_orders_y=orders(F_free[:, 0]), F_free_orders_z=orders(F_free[:, 1]),
                M_y_orders=orders(M_y_free), M_z_orders=orders(M_z_free),
                F_rec_peak=float(np.hypot(F_rec[:, 0], F_rec[:, 1]).max()),
                F_free_peak=float(np.hypot(F_free[:, 0], F_free[:, 1]).max()),
                M_free_peak=float(np.hypot(M_y_free, M_z_free).max()),
                mains=mains, throw=throw, main_peak=main_peak,
                main_spec_load_mpa=main_peak / (P.main_dia * w_eff_main),
                rod_peak_comp=rod_peak_c, rod_peak_tens=rod_peak_t, side_peak=side_peak,
                be_peak=float(be_mag.max()), be_mean=float(be_mag.mean()),
                be_spec_load_mpa=float(be_mag.max()) / (P.pin_dia * w_eff_rod),
                se_spec_load_mpa=rod_peak_c / (P.pin_dia_piston * P.rod_se_width),
                mr_cw={k: throw[k]["mr_cw"] for k in throw}, cw_angle={k: throw[k]["cw_angle"] for k in throw},
                w_eff_main=w_eff_main, w_eff_rod=w_eff_rod)


def inertia_only(rpm):
    """Kinematic extremes and rod tension at gas-exchange TDC with no gas load (overspeed case)."""
    om = rpm * math.pi / 30.0
    c = L.CYL[1]
    dal = math.radians(AL[1] - AL[0])
    s = L.piston_s(c, AL) * 1e-3
    sd = (np.roll(s, -1) - np.roll(s, 1)) / (2 * dal) * om
    sdd = (np.roll(s, -1) - 2 * s + np.roll(s, 1)) / dal ** 2 * om ** 2
    m_rec, _ = masses()
    return dict(a_tdc=float(sdd.min()), a_bdc=float(sdd.max()), F_tension=float(-(m_rec * sdd).min()),
                v_max=float(np.abs(sd).max()), v_mean=2 * P.stroke * 1e-3 * rpm / 60.0,
                rod_angle_max=float(np.abs(L.rod_angle(c, AL)).max()),
                rod_angle_max_inner=float(np.abs(L.rod_angle(L.CYL[2], AL)).max()))


# ------------------------------------------------------------------ bearing film estimate (short bearing, quasi-static)
def short_bearing_hmin(load_n, dia_mm, width_mm, rpm, clearance_ratio=0.0008, mu=0.0045):
    """Ocvirk short-bearing minimum film thickness for a steady load.

    mu: dynamic viscosity at bearing temperature (Pa s); 0.0045 ~ 10W-60 class oil at ~140 degC (EST).
    Returns (eccentricity ratio, h_min in micrometres).  Conservative for dynamically loaded engine
    bearings because squeeze-film support is ignored.
    """
    D, Lw = dia_mm * 1e-3, width_mm * 1e-3
    c = clearance_ratio * D / 2
    N = rpm / 60.0
    S = mu * N * D * Lw / load_n * (D / (2 * c)) ** 2
    So = S * (Lw / D) ** 2
    f = lambda e: (1 - e * e) ** 2 / (math.pi * e * math.sqrt(math.pi ** 2 * (1 - e * e) + 16 * e * e))
    lo, hi = 1e-4, 0.99999
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(mid) > So:
            lo = mid
        else:
            hi = mid
    eps = 0.5 * (lo + hi)
    return eps, c * (1 - eps) * 1e6


# ------------------------------------------------------------------ torsional vibration (lumped model)
def torsional_model(J_cad=None):
    """Lumped model damper - throw1 ... throw8 - flywheel.  Returns J (kg m2), k (N m/rad), info.
    J_cad: (dict throw -> kg m2 of pin + webs + counterweights, kg m2 of one main journal) from the CAD
    (cranktrain.throw_inertia; D-050).  Without it the EST `J_throw_fixed` is used (fallback only: it is less than half
    the CAD value)."""
    G = 80.0e3                                                    # MPa
    Dj, Lj, Lw, Lc, Dc, R = P.main_dia, P.main_width, P.web_thk, P.pin_width, P.pin_dia, P.throw
    W = 104.0                                                     # web width (mm, EST)
    inv = (Lj + 0.8 * Lw) / Dj ** 4 + 0.75 * Lc / (Dc ** 4 - P.pin_bore ** 4) + 1.5 * R / (Lw * W ** 3)   # Carter formula, mm^-3
    k_throw = G * math.pi / (32 * inv) * 1e-3                     # N m/rad
    m_rec, m_rod_rot = masses()
    r = P.throw * 1e-3
    J_rods = (2 * m_rod_rot + 0.5 * 2 * m_rec) * r ** 2
    if J_cad is not None:
        J_crank = {k: v + J_cad[1] for k, v in J_cad[0].items()}  # throw + one main journal
        src = "CAD (pin, webs, counterweights + one main journal)"
    else:
        J_crank = {k: P.J_throw_fixed for k in range(1, 9)}
        src = "EST J_throw_fixed"
    J_th = [J_crank[k] + J_rods for k in range(1, 9)]
    k_front = G * math.pi * 50.0 ** 4 / (32 * 75.0) * 1e-3        # nose Ø50 x 75 (EST)
    k_rear = G * math.pi * Dj ** 4 / (32 * 45.0) * 1e-3
    J = np.array([P.J_damper] + J_th + [P.J_flywheel])
    k = np.array([k_front] + [k_throw] * 7 + [k_rear])
    return J, k, dict(k_throw=k_throw, J_throw=float(np.mean(J_th)), J_throw_crank=float(np.mean(list(J_crank.values()))),
                      J_throw_rods=J_rods, J_source=src, k_front=k_front, k_rear=k_rear)


def torsional_modes(J_cad=None):
    J, k, info = torsional_model(J_cad)
    n = len(J)
    K = np.zeros((n, n))
    for i, ki in enumerate(k):
        K[i, i] += ki; K[i + 1, i + 1] += ki; K[i, i + 1] -= ki; K[i + 1, i] -= ki
    Jh = np.diag(1 / np.sqrt(J))
    w2, v = np.linalg.eigh(Jh @ K @ Jh)
    f = np.sqrt(np.clip(w2, 0, None)) / (2 * math.pi)
    return f, Jh @ v, K, J, k, info


def torsional_forced(loads, damping_ratio=0.02, c_damper=14.0, J_cad=None):
    """Forced response to the full-load torque harmonics of every throw.

    loads: {rpm: result of run(rpm)}.  Structural damping (loss factor 2*zeta) plus a viscous damper
    coefficient c_damper (N m s/rad, EST) acting on the free-end inertia.
    Returns list of dicts with the vibratory torque amplitude (root-sum-square over orders) per shaft section.
    """
    f, modes, K, J, k, info = torsional_modes(J_cad)
    out = []
    for rpm, res in sorted(loads.items()):
        om = rpm * math.pi / 30
        Tk = np.zeros((len(J), N_AL))
        for c in L.CYLS:
            Tk[c.pin] += res["cf"][c.no]["torque"]
        X = np.fft.rfft(Tk, axis=1) / N_AL * 2
        sec2 = np.zeros(len(k))
        worst = (0.0, 0.0)
        for h in range(1, 49):                                    # h cycles per 720 deg -> order h/2
            w = 0.5 * h * om
            Z = K * (1 + 2j * damping_ratio) - w ** 2 * np.diag(J)
            Z = Z.astype(complex)
            Z[0, 0] += 1j * w * c_damper
            th = np.linalg.solve(Z, X[:, h])
            amp = np.abs(np.diff(th)) * k
            sec2 += amp ** 2
            if amp.max() > worst[0]:
                worst = (float(amp.max()), 0.5 * h)
        out.append(dict(rpm=rpm, sec_torque=np.sqrt(sec2), worst_order=worst[1], worst_amp=worst[0]))
    return out, f, info
