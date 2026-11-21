"""0-D engine cycle + turbocharger matching model (single-zone, Wiebe heat release, Woschni heat transfer).

This is a first-principles sizing model, NOT a calibrated engine simulation.  All sub-model
constants are standard textbook values (Heywood) and are listed in ASSUMPTIONS at the top so
that they can be reviewed.  Results are compared with the published Chiron figures in
`validate_against_reference()`.
"""
from __future__ import annotations
import math
import numpy as np

from ..params import P
from .. import layout as L

# ------------------------------------------------------------------ assumptions (all EST unless noted)
A = dict(
    R_air=287.0, cp_air=1005.0, gam_air=1.40,
    cp_exh=1250.0, gam_exh=1.30, R_exh=290.0,
    LHV=42.5e6,            # J/kg, premium gasoline
    AFR_st=14.2,           # stoichiometric air/fuel ratio (E5 premium)
    wiebe_a=6.908, wiebe_m=2.0,
    ivc_deg=-130.0,        # intake valve closing, deg relative to firing TDC (50 deg ABDC)
    evo_deg=128.0,         # exhaust valve opening (52 deg BBDC)
    T_wall_head=500.0, T_wall_piston=560.0, T_wall_liner=420.0,   # K, mean gas-side wall temperatures
    resid_frac=0.04, T_resid=950.0, dT_charge_heating=18.0,
    h_fg_fuel=350e3, evap_frac_port=0.5,      # charge cooling by fuel evaporation before IVC

    eta_comp=0.72, eta_turb=0.68, eta_mech=0.97,
    ic_effectiveness=0.86, T_lt_coolant=313.0,
    dp_filter_rated=2.5e3, dp_cac_rated=12e3, dp_throttle=1.5e3, dp_exh_rated=32e3,   # Pa at rated flow
    mdot_rated_ref=1.22,   # kg/s, flow at which the rated pressure losses apply
    T3_limit=P.t_exh_valve_ref_c + 273.15,       # K, turbine-inlet limit = published valve rating (PUB)
    lam_min=0.72, lam_max_fullload=0.95,
    exh_manifold_heat_loss=0.06,
    woschni_scale=2.0,     # multiplier on the Woschni coefficient (EST, D-045): the only value of 1.0 / 1.5 / 2.0 that comes close
                           # to the published 3-5 % of fuel energy into the piston (2.8 % of the burned fuel energy at rated
                           # power, heat-consistent) and keeps T3 at the published limit (1.0 / 1.5 run 48 / 24 K over it at
                           # lambda_min); uncertainty band 1.0-2.0 - tools/piston_heat_input_study.py, report section 8.2
)


def ve(rpm):
    """Volumetric efficiency referred to manifold density (EST table)."""
    return float(np.interp(rpm, [1000, 2000, 3000, 4000, 5500, 6700, 7300], [0.86, 0.90, 0.93, 0.95, 0.95, 0.925, 0.90]))


def ca50(rpm):
    """Knock-limited combustion phasing at full load, deg ATDC (EST)."""
    return float(np.interp(rpm, [1000, 2000, 4000, 6700], [30.0, 26.0, 20.0, 17.0]))


def burn_duration(rpm):
    """0-100 % burn duration in deg CA (EST)."""
    return float(np.interp(rpm, [1000, 6700], [52.0, 66.0]))


def eta_comb(lam):
    """Combustion efficiency vs lambda.

    Rich mixtures are oxygen-limited: every mole of missing O2 leaves ~2 mol of CO/H2 (~530 kJ) unburned,
    while complete oxidation of gasoline releases ~402 kJ per mole of O2 consumed.  Hence the released
    fraction of the fuel energy is 1 - (530/402)(1 - lambda) for lambda < 1 (times 0.98 for crevice/HC losses)."""
    lam = min(lam, 1.0)
    return max(0.5, 0.98 * (1.0 - 530.0 / 402.0 * (1.0 - lam)))


def torque_target(rpm):
    """Published torque curve: 1,600 N m from 2,000-6,000 rpm, 1,103 kW at 6,700 rpm."""
    t_rated = P.power_rated_kw * 1e3 / (P.rpm_rated * math.pi / 30.0)
    return float(np.interp(rpm, [1000, P.rpm_torque_lo, P.rpm_torque_hi, P.rpm_rated, 7300],
                           [P.torque_max_nm, P.torque_max_nm, P.torque_max_nm, t_rated, 0.80 * t_rated]))


_CY = L.CYL[1]
_TH = np.arange(-180.0, 180.0001, 0.5)                        # deg relative to firing TDC
_X = L.piston_x_from_tdc(_CY, _TH + _CY.fire)                  # mm from TDC
_AP = math.pi / 4 * (P.bore * 1e-3) ** 2
_VD = P.disp_cyl_cc * 1e-6
_VC = P.v_clear_cc * 1e-6
_V = _VC + _AP * _X * 1e-3


def gamma_mix(T, xb):
    gu = 1.36 - 7.5e-5 * (T - 300.0)             # fuel-air mixture
    gb = 1.27 - 3.5e-5 * (T - 1500.0)            # rich combustion products incl. dissociation trend
    return (1 - xb) * np.clip(gu, 1.28, 1.37) + xb * np.clip(gb, 1.21, 1.30)


def closed_cycle(rpm, p_man, T_man, lam, p_exh, ca50_deg=None, dur=None):
    """Single-cylinder closed cycle.  Pressures in Pa.  Returns dict with traces and integrals."""
    ca50_deg = ca50(rpm) if ca50_deg is None else ca50_deg
    dur = burn_duration(rpm) if dur is None else dur
    th, V = _TH, _V
    n = len(th)
    i_ivc = int(np.searchsorted(th, A["ivc_deg"]))
    i_evo = int(np.searchsorted(th, A["evo_deg"]))
    m_air = ve(rpm) * p_man * _VD / (A["R_air"] * T_man)
    m_fuel = m_air / (lam * A["AFR_st"])
    m_fresh = m_air + m_fuel
    xr = A["resid_frac"]
    m = m_fresh / (1 - xr)
    dT_evap = A["evap_frac_port"] * A["h_fg_fuel"] * (m_fuel / m_air) / A["cp_air"]
    T_ivc = (1 - xr) * (T_man + A["dT_charge_heating"] - dT_evap) + xr * A["T_resid"]
    R = A["R_air"]
    p_ivc = m * R * T_ivc / V[i_ivc]
    Q_tot = m_fuel * A["LHV"] * eta_comb(lam)
    th0 = ca50_deg - dur * (math.log(2) / A["wiebe_a"]) ** (1 / (A["wiebe_m"] + 1))
    xb = np.where(th > th0, 1 - np.exp(-A["wiebe_a"] * np.clip((th - th0) / dur, 0, None) ** (A["wiebe_m"] + 1)), 0.0)
    xb = np.clip(xb, 0, 1)

    p = np.empty(n); T = np.empty(n)
    p[:i_ivc + 1] = p_ivc
    T[:i_ivc + 1] = T_ivc
    Sp = 2 * P.stroke * 1e-3 * rpm / 60.0
    dt = (th[1] - th[0]) / (6.0 * rpm)
    B = P.bore * 1e-3
    Qw = 0.0
    qw_parts = np.zeros(3)
    for i in range(i_ivc, n - 1):
        Ti, pi, Vi = T[i], p[i], V[i]
        g = float(gamma_mix(Ti, xb[i]))
        cv = R / (g - 1)
        p_mot = p_ivc * (V[i_ivc] / Vi) ** 1.33
        C2 = 3.24e-3 if th[i] > th0 else 0.0
        w = 2.28 * Sp + C2 * _VD * T_ivc / (p_ivc * V[i_ivc]) * max(pi - p_mot, 0.0)
        h = A["woschni_scale"] * 3.26 * B ** -0.2 * (pi * 1e-3) ** 0.8 * Ti ** -0.55 * w ** 0.8
        a_head = 1.15 * _AP; a_pist = 1.10 * _AP; a_lin = math.pi * B * _X[i] * 1e-3
        dq = h * np.array([a_head * (Ti - A["T_wall_head"]), a_pist * (Ti - A["T_wall_piston"]),
                           a_lin * (Ti - A["T_wall_liner"])]) * dt
        dQc = Q_tot * (xb[i + 1] - xb[i])
        dV = V[i + 1] - Vi
        dT = (dQc - dq.sum() - pi * dV) / (m * cv)
        # predictor-corrector on pressure for the p dV term
        Tn = Ti + dT
        pn = m * R * Tn / V[i + 1]
        dT = (dQc - dq.sum() - 0.5 * (pi + pn) * dV) / (m * cv)
        T[i + 1] = Ti + dT
        p[i + 1] = m * R * T[i + 1] / V[i + 1]
        if i < i_evo:
            Qw += dq.sum(); qw_parts += dq
    # blow-down: linear pressure decay from EVO to BDC down to exhaust manifold pressure
    p_evo, T_evo = p[i_evo], T[i_evo]
    k = np.arange(i_evo, n)
    frac = (k - i_evo) / max(n - 1 - i_evo, 1)
    p[i_evo:] = p_evo + (p_exh - p_evo) * frac
    W_gross = float(np.trapezoid(p, V))                                   # J, compression + expansion
    imep_g = W_gross / _VD
    pmep = 0.92 * (p_man - p_exh)                                         # 4-stroke pumping loop (rectangular approx.)
    p_max = float(p.max())
    fmep = (0.4 + 0.005 * p_max * 1e-5 + 0.09 * Sp + 0.0009 * Sp ** 2) * 1e5   # Chen-Flynn, Pa
    bmep = imep_g + pmep - fmep
    ge = A["gam_exh"]
    T_exh = T_evo * (1 - (ge - 1) / ge * (1 - min(p_exh / p_evo, 1.0)))   # mean temperature after blow-down
    T3 = T_exh * (1 - A["exh_manifold_heat_loss"])
    return dict(th=th, p=p, T=T, V=V, xb=xb, m_air=m_air, m_fuel=m_fuel, imep_g=imep_g, pmep=pmep, fmep=fmep,
                bmep=bmep, p_max=p_max, th_pmax=float(th[int(np.argmax(p))]), T_max=float(T[i_ivc:i_evo].max()),
                T_evo=float(T_evo), p_evo=float(p_evo), T3=float(T3), Q_wall=float(Qw), Q_wall_parts=qw_parts,
                Q_fuel=m_fuel * A["LHV"], Q_released=Q_tot, T_ivc=T_ivc, p_ivc=p_ivc)


# ------------------------------------------------------------------ turbocharger side
def n_active(rpm):
    return 2 if rpm < P.rpm_turbo_switch else 4


def turbine_flow_param(er):
    """Swallowing function of a nozzle (choked above the critical ratio)."""
    g = A["gam_exh"]
    crit = ((g + 1) / 2) ** (g / (g - 1))
    r = min(er, crit)
    return math.sqrt(2 * g / (g - 1) * (r ** (-2 / g) - r ** (-(g + 1) / g)))


def turbine_capacity(A_turb, nt, er, p4, T3):
    """Mass flow (kg/s) through nt turbines of effective area A_turb at expansion ratio er."""
    return nt * A_turb * (er * p4) / math.sqrt(A["R_exh"] * T3) * turbine_flow_param(er)


def turbine_balance(P_c, md_e, T3, p4, rpm, A_turb, wg_nominal=0.0):
    """Expansion ratio, waste-gate fraction and power deficit (fraction of P_c) for the active turbines."""
    kk = (A["gam_exh"] - 1) / A["gam_exh"]
    eta = A["eta_mech"] * A["eta_turb"]
    pw = lambda md, er: eta * md * A["cp_exh"] * T3 * (1 - er ** (-kk))
    if A_turb is None:
        x = P_c / (eta * (1 - wg_nominal) * md_e * A["cp_exh"] * T3)
        return (1 - min(x, 0.9)) ** (-1 / kk), wg_nominal, 0.0
    nt = n_active(rpm)
    lo, hi = 1.0001, 10.0
    for _ in range(48):                                  # ER at which the wheels swallow the whole flow (gate shut)
        mid = 0.5 * (lo + hi)
        if turbine_capacity(A_turb, nt, mid, p4, T3) > md_e:
            hi = mid
        else:
            lo = mid
    er_flow = hi
    if pw(md_e, er_flow) < P_c:
        return er_flow, 0.0, (P_c - pw(md_e, er_flow)) / P_c
    lo, hi = 1.0001, er_flow
    for _ in range(48):                                  # gate open: ER at which the wheel flow delivers P_c
        mid = 0.5 * (lo + hi)
        if pw(turbine_capacity(A_turb, nt, mid, p4, T3), mid) > P_c:
            hi = mid
        else:
            lo = mid
    return hi, 1 - turbine_capacity(A_turb, nt, hi, p4, T3) / md_e, 0.0


def evaluate(rpm, p_man, lam, A_turb, state, wg_nominal=0.0):
    """Engine + turbocharger boundary conditions for a given manifold pressure (fixed point on p3 and T_man)."""
    p0, T0 = P.p_amb_bar * 1e5, P.t_amb_k
    ga, cpa = A["gam_air"], A["cp_air"]
    p_exh = state.get("p_exh", 1.1 * p_man)
    T_man = state.get("T_man", 325.0)
    res = None
    for _ in range(8):
        cyc = closed_cycle(rpm, p_man, T_man, lam, p_exh)
        md_a = cyc["m_air"] * 16 * rpm / 120.0
        md_f = cyc["m_fuel"] * 16 * rpm / 120.0
        md_e = md_a + md_f
        fr = (md_a / A["mdot_rated_ref"]) ** 2
        p1 = p0 - A["dp_filter_rated"] * fr
        p2 = p_man + A["dp_throttle"] + A["dp_cac_rated"] * fr * (2.6e5 / max(p_man, 1e5))
        pr = max(p2 / p1, 1.0)
        T2 = T0 * (1 + (pr ** ((ga - 1) / ga) - 1) / A["eta_comp"])
        T_man_new = T2 - A["ic_effectiveness"] * (T2 - A["T_lt_coolant"]) if T2 > A["T_lt_coolant"] else T2
        P_c = md_a * cpa * (T2 - T0)
        p4 = p0 + A["dp_exh_rated"] * (md_e / A["mdot_rated_ref"]) ** 2
        er, wg, deficit = turbine_balance(P_c, md_e, cyc["T3"], p4, rpm, A_turb, wg_nominal)
        p_exh_new = er * p4
        res = dict(cyc=cyc, md_a=md_a, md_f=md_f, md_e=md_e, p1=p1, p2=p2, pr=pr, T2=T2, T_man=T_man_new,
                   P_c=P_c, p4=p4, T3=cyc["T3"], er=er, p3=p_exh_new, wg=wg, deficit=deficit, p_man=p_man, lam=lam)
        if abs(p_exh_new - p_exh) < 300 and abs(T_man_new - T_man) < 0.3:
            break
        p_exh = 0.4 * p_exh + 0.6 * p_exh_new
        T_man = T_man_new
    state["p_exh"], state["T_man"] = p_exh, T_man
    return res


def solve_pman(rpm, bmep_target, lam, A_turb, state, wg_nominal=0.0):
    """Secant solve of the manifold pressure that gives the BMEP target."""
    pa = state.get("p_man", 1e5 * (0.25 + bmep_target / 1e5 / 11.0))
    ra = evaluate(rpm, pa, lam, A_turb, state, wg_nominal)
    pb = pa * (1.06 if ra["cyc"]["bmep"] < bmep_target else 0.94)
    rb = evaluate(rpm, pb, lam, A_turb, state, wg_nominal)
    for _ in range(10):
        fa, fb = ra["cyc"]["bmep"] - bmep_target, rb["cyc"]["bmep"] - bmep_target
        if abs(fb) < 1500.0 or abs(fb - fa) < 1e-6:
            break
        pn = min(max(pb - fb * (pb - pa) / (fb - fa), 0.45e5), 4.8e5)
        pa, ra = pb, rb
        pb = pn
        rb = evaluate(rpm, pb, lam, A_turb, state, wg_nominal)
    state["p_man"] = pb
    return rb


def operating_point(rpm, bmep_target, A_turb=None, wg_nominal=0.0):
    """Full-load operating point: manifold pressure for the BMEP target, enrichment for the T3 limit and the
    turbocharger power balance.  `deficit` > 0 means the turbines cannot supply the compressor power."""
    state = {}
    lam = A["lam_max_fullload"]
    r = solve_pman(rpm, bmep_target, lam, A_turb, state, wg_nominal)
    if r["T3"] > A["T3_limit"]:
        la, ra = lam, r
        lb = max(A["lam_min"], lam - 0.07)
        rb = solve_pman(rpm, bmep_target, lb, A_turb, state, wg_nominal)
        for _ in range(4):
            if abs(rb["T3"] - A["T3_limit"]) < 3.0 or lb <= A["lam_min"] + 1e-9 and rb["T3"] > A["T3_limit"]:
                break
            if abs(rb["T3"] - ra["T3"]) < 1e-6:
                break
            ln = lb - (rb["T3"] - A["T3_limit"]) * (lb - la) / (rb["T3"] - ra["T3"])
            ln = min(max(ln, A["lam_min"]), A["lam_max_fullload"])
            la, ra = lb, rb
            lb = ln
            rb = solve_pman(rpm, bmep_target, lb, A_turb, state, wg_nominal)
        r, lam = rb, lb
    c = r["cyc"]
    om = rpm * math.pi / 30
    vd_tot = P.displacement_cc * 1e-6
    torque = c["bmep"] * vd_tot / (4 * math.pi)
    power = torque * om
    out = dict(rpm=rpm, torque=torque, power_kw=power / 1e3, bmep_bar=c["bmep"] / 1e5, imep_g_bar=c["imep_g"] / 1e5,
               pmep_bar=c["pmep"] / 1e5, fmep_bar=c["fmep"] / 1e5, p_man_bar=r["p_man"] / 1e5,
               boost_bar=(r["p_man"] - P.p_amb_bar * 1e5) / 1e5, pr_comp=r["pr"], T2_c=r["T2"] - 273.15,
               T_man_c=r["T_man"] - 273.15, cac_dT=r["T2"] - r["T_man"], mdot_air=r["md_a"], mdot_fuel=r["md_f"],
               lam=lam, bsfc_g_kwh=r["md_f"] * 3600e3 / (power / 1e3) if power > 0 else float("nan"),
               eta_brake=power / (r["md_f"] * A["LHV"]), p_max_bar=c["p_max"] / 1e5, th_pmax=c["th_pmax"],
               T_max_k=c["T_max"], T3_c=r["T3"] - 273.15, p3_bar=r["p3"] / 1e5, p4_bar=r["p4"] / 1e5, er_turb=r["er"],
               wg_frac=r["wg"], deficit=r["deficit"], P_comp_kw=r["P_c"] / 1e3, n_active=n_active(rpm),
               mdot_per_turbo=r["md_a"] / n_active(rpm), ca50=ca50(rpm),
               air_lpm=r["md_a"] / (P.p_amb_bar * 1e5 / (A["R_air"] * P.t_amb_k)) * 60e3,
               Q_wall_kw=c["Q_wall"] * 16 * rpm / 120 / 1e3, Q_fuel_kw=r["md_f"] * A["LHV"] / 1e3,
               Q_cac_kw=r["md_a"] * A["cp_air"] * (r["T2"] - r["T_man"]) / 1e3,
               Q_exh_kw=r["md_e"] * A["cp_exh"] * (r["T3"] - P.t_amb_k) / 1e3,
               P_fric_kw=c["fmep"] * vd_tot * rpm / 120 / 1e3,
               Q_wall_parts_kw=(c["Q_wall_parts"] * 16 * rpm / 120 / 1e3).tolist())
    out["_cyc"] = c
    return out


_A_TURB = None


def size_turbine(rpm_design=None):
    """Effective turbine flow area per turbocharger (m2).

    Binding design point: immediately after the change-over (rpm_turbo_switch, four turbochargers active) the
    exhaust flow per turbine is at its minimum for full torque, so the waste-gates must be just closed there.
    With two turbochargers active the same flow per turbine is reached at about half that speed."""
    global _A_TURB
    if _A_TURB is not None and rpm_design is None:
        return _A_TURB
    n = rpm_design or P.rpm_turbo_switch
    bt = torque_target(n) * 4 * math.pi / (P.displacement_cc * 1e-6)
    r = operating_point(n, bt, A_turb=None, wg_nominal=0.0)
    md_e = r["mdot_air"] + r["mdot_fuel"]
    T3 = r["T3_c"] + 273.15
    a = md_e / (n_active(n) * r["p3_bar"] * 1e5 / math.sqrt(A["R_exh"] * T3) * turbine_flow_param(r["er_turb"]))
    if rpm_design is None:
        _A_TURB = a
    return a


def full_load_curve(rpms=None, A_turb=None):
    rpms = rpms if rpms is not None else [1000, 1250, 1500, 1750, 2000, 2500, 3000, 3500, 3750, 3850, 4000, 4500,
                                          5000, 5500, 6000, 6400, 6700, 6800]
    A_turb = A_turb or size_turbine()
    vd = P.displacement_cc * 1e-6
    rows = []
    for n in rpms:
        bt = torque_target(n) * 4 * math.pi / vd
        r = operating_point(n, bt, A_turb=A_turb)
        limited = False
        if r["deficit"] > 2e-3:
            # turbine-limited: scan downwards for the highest target the turbochargers can sustain, then refine
            hi, lo = bt, None
            for frac in np.linspace(0.95, 0.25, 15):
                r = operating_point(n, frac * bt, A_turb=A_turb)
                if r["deficit"] <= 2e-3:
                    lo = frac * bt
                    break
                hi = frac * bt
            lo = lo if lo is not None else 0.25 * bt
            for _ in range(6):
                mid = 0.5 * (lo + hi)
                r = operating_point(n, mid, A_turb=A_turb)
                if r["deficit"] > 2e-3:
                    hi = mid
                else:
                    lo = mid
            r = operating_point(n, lo, A_turb=A_turb)
            limited = True
        r["boost_limited"] = limited
        rows.append(r)
    return rows, A_turb


def compressor_sizing(curve):
    """Provisional compressor/turbine wheel sizing from the worst-case per-turbo operating points."""
    ga, cpa = A["gam_air"], A["cp_air"]
    hi = max(curve, key=lambda r: r["mdot_per_turbo"] * math.sqrt(1.0))
    pr = max(r["pr_comp"] for r in curve)
    md = hi["mdot_per_turbo"]
    dh = cpa * P.t_amb_k * (pr ** ((ga - 1) / ga) - 1) / A["eta_comp"]
    mu = 0.68                                   # work coefficient (backswept impeller, slip included)
    U2 = math.sqrt(dh / mu)
    rho1 = P.p_amb_bar * 1e5 / (A["R_air"] * P.t_amb_k)
    phi = 0.095                                 # design flow coefficient mdot/(rho U2 D2^2)
    D2 = math.sqrt(md * 1.08 / (rho1 * phi * U2))   # 8 % choke margin
    n_rpm = U2 / (math.pi * D2) * 60
    return dict(mdot_design=md, pr_design=pr, dh_kj=dh / 1e3, U2=U2, D2_comp=D2 * 1e3, D1_comp=0.72 * D2 * 1e3,
                n_rpm=n_rpm, D_turb=0.92 * D2 * 1e3, D_turb_exd=0.92 * 0.86 * D2 * 1e3,
                P_shaft_kw=max(r["P_comp_kw"] / r["n_active"] for r in curve))


def validate_against_reference(curve):
    rated = min(curve, key=lambda r: abs(r["rpm"] - P.rpm_rated))
    plateau = [r for r in curve if P.rpm_torque_lo <= r["rpm"] <= P.rpm_torque_hi]
    checks = [
        ("Rated power [kW]", rated["power_kw"], P.power_rated_kw, "PUB"),
        ("Torque on plateau, min [N m]", min(r["torque"] for r in plateau), P.torque_max_nm, "PUB"),
        ("Air flow at rated [L/min, ISO ambient]", rated["air_lpm"], P.air_flow_ref_lpm, "PUB (>60,000)"),
        ("Charge-air temperature drop at rated [K]", rated["cac_dT"], P.cac_delta_t_ref, "PUB (as much as 130)"),
        ("Power-equivalent air supply per turbo [PS]", rated["power_kw"] / 4 / 0.7355, 380.0, "PUB (approx. 380)"),
        ("Turbine inlet temperature at rated [degC]", rated["T3_c"], P.t_exh_valve_ref_c, "PUB valve rating (limit)"),
    ]
    return checks
