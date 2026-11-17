"""Thermal management, charge-air cooling, lubrication, fuel and exhaust sizing (analytical / 1-D).

All correlations are textbook steady-state relations.  Every function returns a dict of inputs and
results so that the report generator can print assumptions next to results.
"""
from __future__ import annotations
import math
import numpy as np

from ..params import P
from .. import layout as L
from . import cycle

# fluid properties (EST, typical values at operating temperature)
COOLANT = dict(rho=1030.0, cp=3600.0, mu=0.75e-3, k=0.42, name="50/50 water-glycol at ~95 degC")
COOLANT_LT = dict(rho=1055.0, cp=3450.0, mu=1.9e-3, k=0.40, name="50/50 water-glycol at ~45 degC")
OIL = dict(rho=820.0, cp=2150.0, mu=0.0055, k=0.13, name="10W-60 class oil at ~130 degC")
AIR_HOT = dict(cp=1012.0, mu=2.4e-5, k=0.034, pr=0.70)


# ------------------------------------------------------------------ energy balance
def energy_balance(op):
    """Split of the fuel energy at one operating point (kW)."""
    qw_head, qw_piston, qw_liner = op["Q_wall_parts_kw"]
    q_fuel = op["Q_fuel_kw"]
    p_brake = op["power_kw"]
    p_fric = op["P_fric_kw"]
    q_exh_gross = op["Q_exh_kw"]
    q_port = 0.04 * (q_exh_gross / 0.96)                       # exhaust port/manifold loss assumed in the cycle model
    piston_to_oil = 0.55 * qw_piston                            # share removed by the cooling jets (EST)
    fric_to_oil = 0.55 * p_fric
    turbo_to_oil = 4 * 3.0 if op["n_active"] == 4 else 2 * 3.0
    q_oil = piston_to_oil + fric_to_oil + turbo_to_oil
    q_cool = qw_head + qw_liner + (qw_piston - piston_to_oil) + 0.6 * q_port + (p_fric - fric_to_oil) + op["n_active"] * 2.0
    q_cac = op["Q_cac_kw"]
    unburned = q_fuel * (1 - cycle.eta_comb(op["lam"]))
    q_exh = q_fuel - p_brake - q_cool - q_oil - q_cac * 0.0 - unburned   # sensible exhaust enthalpy after turbine + radiation
    return dict(q_fuel=q_fuel, p_brake=p_brake, q_coolant_ht=q_cool, q_oil=q_oil, q_cac_lt=q_cac,
                q_unburned=unburned, q_exhaust_sensible=q_exh, p_friction=p_fric,
                q_total_rejected=q_fuel - p_brake + q_cac,
                q_total_rejected_hp=(q_fuel - p_brake + q_cac) / 0.7355,
                eta_brake=p_brake / q_fuel, wall_parts=(qw_head, qw_piston, qw_liner),
                piston_to_oil=piston_to_oil, fric_to_oil=fric_to_oil, turbo_to_oil=turbo_to_oil)


# ------------------------------------------------------------------ HT coolant circuit
def coolant_ht(eb, flow_lpm=None):
    flow_lpm = flow_lpm or P.coolant_flow_ref_lpm
    md = flow_lpm / 60e3 * COOLANT["rho"]
    dT = eb["q_coolant_ht"] * 1e3 / (md * COOLANT["cp"])
    # jacket: flow per bank split over the bore-surrounding jacket cross-section
    a_jacket = 2 * P.jacket_width * 1e-3 * P.jacket_depth * 1e-3          # two flow sides around a bore
    v_jacket = (md / 2 / COOLANT["rho"]) / (a_jacket * 2.0)                # two parallel lanes per bank (inner/outer row side)
    dh = 2 * P.jacket_width * 1e-3
    re = COOLANT["rho"] * v_jacket * dh / COOLANT["mu"]
    pr = COOLANT["cp"] * COOLANT["mu"] / COOLANT["k"]
    nu = 0.023 * re ** 0.8 * pr ** 0.4
    h = nu * COOLANT["k"] / dh
    return dict(flow_lpm=flow_lpm, mdot=md, dT=dT, v_jacket=v_jacket, re=re, h_jacket=h,
                circulation_time_s=P.ht_volume_l / flow_lpm * 60.0)


def liner_wall_temps(op, cool):
    """1-D wall temperature at the top of the liner and in the fire deck (steady, cycle-mean)."""
    mat_k = 150.0                                               # W/mK aluminium alloy
    qw_head, qw_piston, qw_liner = [q * 1e3 / 16 for q in op["Q_wall_parts_kw"]]
    a_liner_top = math.pi * P.bore * 1e-3 * 0.030               # top 30 mm takes most of the liner heat
    q_liner = 0.65 * qw_liner / a_liner_top + 0.30 * 0.45 * qw_piston / a_liner_top   # + ring/skirt heat path
    a_deck = 1.15 * math.pi / 4 * (P.bore * 1e-3) ** 2
    q_deck = qw_head / a_deck
    T_c = 273.15 + 95.0
    h = cool["h_jacket"]
    h_head = 1.6 * h                                            # higher velocity / nucleate boiling margin in head passages (EST)
    T_liner_cool = T_c + q_liner / h
    T_liner_gas = T_liner_cool + q_liner * P.liner_wall * 1e-3 / mat_k
    T_deck_cool = T_c + 8.0 + q_deck / h_head
    T_deck_gas = T_deck_cool + q_deck * P.fire_deck_thk * 1e-3 / mat_k
    return dict(q_liner_top_wm2=q_liner, q_deck_wm2=q_deck, T_liner_coolant_side_c=T_liner_cool - 273.15,
                T_liner_gas_side_c=T_liner_gas - 273.15, T_deck_coolant_side_c=T_deck_cool - 273.15,
                T_deck_gas_side_c=T_deck_gas - 273.15, h_jacket=h, h_head=h_head)


# ------------------------------------------------------------------ charge-air cooler (water-to-air, one per bank)
CAC = dict(core_w=0.420, core_h=0.130, core_d=0.180,           # m: air face width x height, depth in flow direction
           fin_pitch=1.6e-3, fin_h=6.0e-3, fin_t=0.10e-3, tube_h=2.4e-3, plate_t=0.4e-3, water_ch=1.8e-3,
           n_cores=2, lt_flow_lpm=240.0)


def charge_air_cooler(op, core=None):
    """epsilon-NTU sizing of one water-to-air cooler (bar-and-plate, louvred/offset fins on the air side)."""
    c = dict(CAC, **(core or {}))
    md_air = op["mdot_air"] / c["n_cores"]
    T_in = op["T2_c"] + 273.15
    T_w = cycle.A["T_lt_coolant"]
    p = op["p_man_bar"] * 1e5
    rho = p / (287.0 * 0.5 * (T_in + op["T_man_c"] + 273.15))
    layer = c["fin_h"] + 2 * c["plate_t"] + c["water_ch"]
    n_layers = int(c["core_h"] / layer)
    a_face = c["core_w"] * c["core_h"]
    sigma = (c["fin_h"] * (1 - c["fin_t"] / c["fin_pitch"])) / layer          # free-flow fraction
    a_free = a_face * sigma
    g = md_air / a_free
    dh = 4 * (c["fin_pitch"] - c["fin_t"]) * c["fin_h"] / (2 * (c["fin_pitch"] - c["fin_t"]) + 2 * c["fin_h"])
    re = g * dh / AIR_HOT["mu"]
    j = 0.53 * re ** -0.5 if re < 3500 else 0.04 * re ** -0.2               # offset-strip-fin Colburn factor (Kays & London trend)
    f = 9.6 * re ** -0.74 * 0.25 + 0.012 if re < 3500 else 0.05 * re ** -0.15
    h_air = j * g * AIR_HOT["cp"] * AIR_HOT["pr"] ** (-2 / 3)
    # air-side area per unit volume of the fin passage
    beta = 2 * (c["fin_h"] + c["fin_pitch"]) / (c["fin_pitch"] * c["fin_h"])
    a_air = beta * (n_layers * c["fin_h"] * c["core_w"] * c["core_d"])
    m_fin = math.sqrt(2 * h_air / (180.0 * c["fin_t"]))
    eta_fin = math.tanh(m_fin * c["fin_h"] / 2) / (m_fin * c["fin_h"] / 2)
    eta_o = 1 - (1 - eta_fin) * 0.85
    # water side
    md_w = c["lt_flow_lpm"] / c["n_cores"] / 60e3 * COOLANT_LT["rho"]
    a_w_flow = n_layers * c["water_ch"] * c["core_d"]
    v_w = md_w / COOLANT_LT["rho"] / a_w_flow
    dh_w = 2 * c["water_ch"]
    re_w = COOLANT_LT["rho"] * v_w * dh_w / COOLANT_LT["mu"]
    pr_w = COOLANT_LT["cp"] * COOLANT_LT["mu"] / COOLANT_LT["k"]
    nu_w = 7.5 if re_w < 2300 else 0.023 * re_w ** 0.8 * pr_w ** 0.4
    nu_w *= 1.8                                                  # turbulators in the water channels (EST)
    h_w = nu_w * COOLANT_LT["k"] / dh_w
    a_w = 2 * n_layers * c["core_w"] * c["core_d"]
    ua = 1 / (1 / (eta_o * h_air * a_air) + 1 / (h_w * a_w))
    c_air = md_air * AIR_HOT["cp"]
    c_w = md_w * COOLANT_LT["cp"]
    cmin, cmax = min(c_air, c_w), max(c_air, c_w)
    ntu = ua / cmin
    cr = cmin / cmax
    eps = 1 - math.exp(ntu ** 0.22 / cr * (math.exp(-cr * ntu ** 0.78) - 1))   # cross-flow, both unmixed
    q = eps * cmin * (T_in - T_w)
    T_out = T_in - q / c_air
    dp_air = 4 * f * (c["core_d"] / dh) * g ** 2 / (2 * rho) + 1.5 * g ** 2 / (2 * rho)   # core friction + entry/exit
    return dict(core=c, n_layers=n_layers, mdot_air=md_air, T_air_in_c=T_in - 273.15, T_air_out_c=T_out - 273.15,
                dT_air=T_in - T_out, effectiveness=eps, ntu=ntu, ua=ua, h_air=h_air, h_water=h_w, re_air=re,
                re_water=re_w, q_kw=q / 1e3, q_total_kw=q * c["n_cores"] / 1e3, dp_air_kpa=dp_air / 1e3,
                water_dT=q / c_w, v_water=v_w, eta_fin=eta_fin, a_air=a_air,
                lt_flow_total_lpm=c["lt_flow_lpm"], assumed_eps_in_cycle=cycle.A["ic_effectiveness"])


# ------------------------------------------------------------------ lubrication
def bearing_flow(dia_mm, width_mm, p_supply, clearance_ratio=0.0008, eps=0.6, groove_frac=0.5):
    """Pressure-fed side-leakage flow of a journal bearing with a partial circumferential groove (m3/s)."""
    D, Lw = dia_mm * 1e-3, width_mm * 1e-3
    c = clearance_ratio * D / 2
    land = max((Lw - 4e-3) / 2, 2e-3)                           # land each side of a 4 mm groove
    q = math.pi * D * c ** 3 * p_supply / (6 * OIL["mu"] * land) * (1 + 1.5 * eps ** 2) * groove_frac * 2
    return q


def lubrication(eb, rpm=None, p_gallery_bar=5.0):
    rpm = rpm or P.rpm_rated
    p = p_gallery_bar * 1e5
    lpm = lambda q: q * 60e3
    q_main = P.n_main * bearing_flow(P.main_dia, P.main_width, p)
    q_rod = 16 * bearing_flow(P.pin_dia, P.rod_be_width, 0.8 * p + 0.5 * OIL["rho"] * (rpm * math.pi / 30 * P.throw * 1e-3) ** 2,
                              groove_frac=0.35)
    d_jet = 2.2e-3
    q_jet = 16 * 0.80 * math.pi / 4 * d_jet ** 2 * math.sqrt(2 * (p - P.p_crankcase_bar * 1e5 * 0 - 0.3e5) / OIL["rho"])
    q_cam = 4 * 5 * bearing_flow(P.cam_journal_dia, 18.0, 0.6 * p, clearance_ratio=0.0016, groove_frac=0.3)
    q_hla = 64 * 0.05 / 60e3 + 4 * 1.0 / 60e3                    # HLA leak-down + finger spray rails
    q_phaser = 4 * 1.2 / 60e3
    q_turbo = 4 * 1.8 / 60e3
    q_chain = 3 * 0.8 / 60e3 + 2.0 / 60e3
    q_pumps = 1.5 / 60e3
    q_tot = q_main + q_rod + q_jet + q_cam + q_hla + q_phaser + q_turbo + q_chain + q_pumps
    q_pump = 1.25 * q_tot                                        # delivery margin for wear / hot idle
    md = q_tot * OIL["rho"]
    dT = eb["q_oil"] * 1e3 / (md * OIL["cp"])
    d_gallery = math.sqrt(4 * (q_tot * 0.8 / 2) / (math.pi * 3.5))   # 3.5 m/s limit, 80 % of the flow through two main galleries
    scav_ratio = 3.0
    pump_power = q_pump * (p + 2.0e5) / 0.65 + scav_ratio * q_pump * 0.6e5 / 0.5
    return dict(p_gallery_bar=p_gallery_bar, q_main_lpm=lpm(q_main), q_rod_lpm=lpm(q_rod), q_jets_lpm=lpm(q_jet),
                q_cam_lpm=lpm(q_cam), q_hla_lpm=lpm(q_hla), q_phaser_lpm=lpm(q_phaser), q_turbo_lpm=lpm(q_turbo),
                q_chain_lpm=lpm(q_chain), q_total_lpm=lpm(q_tot), q_pump_lpm=lpm(q_pump),
                q_scavenge_lpm=lpm(q_pump) * scav_ratio, scav_ratio=scav_ratio, jet_dia_mm=d_jet * 1e3,
                oil_dT=dT, q_oil_kw=eb["q_oil"], d_gallery_required_mm=d_gallery * 1e3, d_gallery_design_mm=P.oil_gallery_dia,
                v_gallery_design=q_tot * 0.8 / 2 / (math.pi / 4 * (P.oil_gallery_dia * 1e-3) ** 2),
                tank_volume_l=max(lpm(q_pump) * 12.0 / 60.0, 18.0), pump_power_kw=pump_power / 1e3,
                oil_mass_flow=md)


# ------------------------------------------------------------------ fuel system
def fuel_system(op_rated):
    md_f = op_rated["mdot_fuel"]
    rho_f = 745.0
    per_cyl = md_f / 16
    duty = 0.85
    q_inj_cc_min = per_cyl / 2 / duty / rho_f * 60e6            # each of two injectors at 85 % duty
    return dict(mdot_fuel_kg_s=md_f, fuel_lph=md_f / rho_f * 3600e3, per_cyl_g_s=per_cyl * 1e3,
                injector_static_cc_min=q_inj_cc_min, injector_selected_cc_min=math.ceil(q_inj_cc_min / 25) * 25 + 25,
                duty_at_rated=duty, rail_dp_bar=5.0, pump_flow_lph=md_f / rho_f * 3600e3 * 1.35,
                lam_rated=op_rated["lam"], bsfc=op_rated["bsfc_g_kwh"])


# ------------------------------------------------------------------ exhaust / intake pipe sizing
def duct_sizing(op_rated, op_switch):
    """Diameters from Mach/velocity limits (EST limits)."""
    out = {}
    # exhaust primary (one cylinder): peak blow-down flow ~ 3x mean cylinder flow
    md_e = op_rated["mdot_air"] + op_rated["mdot_fuel"]
    T3 = op_rated["T3_c"] + 273.15
    p3 = op_rated["p3_bar"] * 1e5
    rho3 = p3 / (cycle.A["R_exh"] * T3)
    a3 = math.sqrt(cycle.A["gam_exh"] * cycle.A["R_exh"] * T3)
    def dia(md, rho, v):
        return math.sqrt(4 * md / (rho * v * math.pi)) * 1e3
    out["exh_primary_id"] = dia(md_e / 16 * 3.0, rho3, 0.30 * a3)
    out["exh_collector_id"] = dia(md_e / 4 * 1.6, rho3, 0.30 * a3)          # 4-cylinder group
    out["turbine_inlet_id"] = dia(md_e / 4, rho3, 0.22 * a3)
    T4 = T3 * (1 - cycle.A["eta_turb"] * (1 - op_rated["er_turb"] ** (-(cycle.A["gam_exh"] - 1) / cycle.A["gam_exh"])))
    rho4 = op_rated["p4_bar"] * 1e5 / (cycle.A["R_exh"] * T4)
    out["T4_c"] = T4 - 273.15
    out["downpipe_id"] = dia(md_e / 4, rho4, 95.0)
    out["main_exhaust_id"] = dia(md_e / 2, rho4, 100.0)
    # intake
    rho1 = P.p_amb_bar * 1e5 / (287 * P.t_amb_k)
    out["comp_inlet_id"] = dia(op_rated["mdot_air"] / 4, rho1, 75.0)
    out["comp_inlet_id_2turbo"] = dia(op_switch["mdot_air"] / 2, rho1, 95.0)
    rho2 = op_rated["pr_comp"] * P.p_amb_bar * 1e5 / (287 * (op_rated["T2_c"] + 273.15))
    out["charge_pipe_id"] = dia(op_rated["mdot_air"] / 4, rho2, 45.0)
    rho_m = op_rated["p_man_bar"] * 1e5 / (287 * (op_rated["T_man_c"] + 273.15))
    out["throttle_id"] = dia(op_rated["mdot_air"] / 2, rho_m, 60.0)
    sp = 2 * P.stroke * 1e-3 * P.rpm_rated / 60
    out["runner_id"] = math.sqrt((P.bore ** 2) * sp / 62.0)                  # mean runner velocity ~62 m/s at rated
    out["plenum_volume_l_per_bank"] = 0.9 * P.displacement_cc / 2 / 1000     # ~0.9 x bank displacement
    return out


# ------------------------------------------------------------------ 1-D coolant network (flow distribution)
def coolant_network(flow_lpm=None):
    """Flow split between the two banks and along each bank (8 cylinder stations in a ladder network).

    Model: pump -> block inlet rail (valley) -> per cylinder: jacket branch -> head branch -> outlet rail.
    Rails have friction between stations; branches are orifice-like (K-factor).  Solved by fixed-point
    iteration on rail pressures (quadratic branch law)."""
    flow_lpm = flow_lpm or P.coolant_flow_ref_lpm
    rho = COOLANT["rho"]
    q_bank = flow_lpm / 60e3 / 2
    n = 8
    d_rail_in, d_rail_out = 0.046, 0.046
    k_branch = 9.0                                              # jacket + gasket metering hole + head passages, referred to a 15 mm hole
    a_branch = math.pi / 4 * 0.015 ** 2
    a_in, a_out = math.pi / 4 * d_rail_in ** 2, math.pi / 4 * d_rail_out ** 2
    f = 0.022
    seg = P.cyl_pitch * 1e-3
    q = np.full(n, q_bank / n)
    for _ in range(200):
        # inlet rail flows (fed at station 0 end), outlet rail collects towards station n-1 end (Z flow) -> reverse return (U) option
        qin = np.array([q[i:].sum() for i in range(n)])          # flow in the inlet rail entering station i
        qout = np.array([q[:i + 1].sum() for i in range(n)])     # flow in the outlet rail leaving station i
        dp_in = f * seg / d_rail_in * rho / 2 * (qin / a_in) ** 2
        dp_out = f * seg / d_rail_out * rho / 2 * (qout / a_out) ** 2
        p_in = -np.cumsum(dp_in) + dp_in[0]                      # relative inlet-rail pressure at each station
        # outlet rail: pressure rises upstream; station i sees the sum of downstream losses
        p_out = np.array([dp_out[i:].sum() for i in range(n)])
        dp_b = p_in - p_out
        dp_b = dp_b - dp_b.min() + 1.0
        qn = a_branch * np.sqrt(2 * dp_b / (rho * k_branch))
        # scale: the common offset is unknown -> find offset so that sum(q) = q_bank
        lo, hi = 0.0, 5e5
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            qq = a_branch * np.sqrt(2 * (p_in - p_out - (p_in - p_out).min() + mid) / (rho * k_branch))
            if qq.sum() > q_bank:
                hi = mid
            else:
                lo = mid
        qn = a_branch * np.sqrt(2 * (p_in - p_out - (p_in - p_out).min() + lo) / (rho * k_branch))
        if np.abs(qn - q).max() < 1e-9:
            q = qn
            break
        q = 0.5 * (q + qn)
    dp_branch = rho * k_branch / 2 * (q / a_branch) ** 2
    dp_engine = float(dp_branch.max() + dp_in.sum() + dp_out.sum())
    dp_external = 0.9e5                                          # radiators, thermostat, pipes at 800 L/min (EST)
    hyd_power = (dp_engine + dp_external) * (flow_lpm / 60e3)
    return dict(flow_lpm=flow_lpm, q_station_lpm=(q * 60e3).tolist(), maldistribution_pct=float((q.max() - q.min()) / q.mean() * 100),
                dp_engine_bar=dp_engine / 1e5, dp_total_bar=(dp_engine + dp_external) / 1e5,
                pump_hydraulic_kw=hyd_power / 1e3, pump_shaft_kw=hyd_power / 0.62 / 1e3,
                v_rail=float(q_bank / a_in), k_branch=k_branch, d_rail_mm=d_rail_in * 1e3)


# ------------------------------------------------------------------ intake manifold distribution (quasi-steady)
def manifold_distribution(op_rated):
    """Cylinder-to-cylinder air distribution of one bank plenum fed from one end (log manifold, 8 runners)."""
    md_bank = op_rated["mdot_air"] / 2
    rho = op_rated["p_man_bar"] * 1e5 / (287 * (op_rated["T_man_c"] + 273.15))
    n = 8
    a_plenum = 0.0075                                            # m2 plenum cross-section (EST: 4 L / 0.53 m)
    d_run = 0.046
    a_run = math.pi / 4 * d_run ** 2
    k_run = 1.6                                                  # entry bell-mouth + runner friction + port
    q = np.full(n, md_bank / n)
    for _ in range(100):
        m_pl = np.array([q[i:].sum() for i in range(n)])
        v_pl = m_pl / (rho * a_plenum)
        # static pressure recovery along a dead-ended plenum (momentum) minus friction
        p_stat = 0.5 * rho * (v_pl[0] ** 2 - v_pl ** 2) * 0.8 - np.cumsum(0.02 * 0.073 / 0.098 * 0.5 * rho * v_pl ** 2)
        lo, hi = 0.0, 5e4
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            qq = rho * a_run * np.sqrt(2 * np.clip(p_stat - p_stat.min() + mid, 0, None) / (rho * k_run))
            if qq.sum() > md_bank:
                hi = mid
            else:
                lo = mid
        qn = rho * a_run * np.sqrt(2 * np.clip(p_stat - p_stat.min() + lo, 0, None) / (rho * k_run))
        if np.abs(qn - q).max() < 1e-9:
            break
        q = 0.5 * (q + qn)
    return dict(q_rel=(q / q.mean()).tolist(), spread_pct=float((q.max() - q.min()) / q.mean() * 100),
                v_plenum_inlet=float(md_bank / (rho * a_plenum)), v_runner=float(md_bank / n / (rho * a_run)) * 4.0,
                note="quasi-steady; runner velocity quoted as peak during the intake stroke (~4x mean)")
