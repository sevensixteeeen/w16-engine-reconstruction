"""Run every analytical model and write the engineering calculation package.

    python -m w16.reports

Outputs: 08_SIMULATIONS/analytical/*.md|png, results.json; 03_REFERENCE_SPECIFICATIONS/REFERENCE_SPEC.md and
MASTER_PARAMETERS.md.  Every number in the generated documents comes from the code that ran.
"""
from __future__ import annotations
import json
import math
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .params import P, MATERIALS
from . import layout as L
from .analysis import cycle, dynamics, valvetrain, thermal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "08_SIMULATIONS", "analytical")
SPEC = os.path.join(ROOT, "03_REFERENCE_SPECIFICATIONS")
plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 130, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)


def _tab(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        out.append("| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in r) + " |")
    return "\n".join(out)


def _w(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return None if o.size > 64 else o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return float(o)
    return o


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SPEC, exist_ok=True)
    R = {}

    # ================================================================= 1. performance / turbo matching
    A_t = cycle.size_turbine()
    curve, _ = cycle.full_load_curve(A_turb=A_t)
    comp = cycle.compressor_sizing(curve)
    checks = cycle.validate_against_reference(curve)
    rated = min(curve, key=lambda r: abs(r["rpm"] - P.rpm_rated))
    R["curve"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in curve]
    R["A_turb_cm2"] = A_t * 1e4
    R["compressor"] = comp
    rp = np.array([r["rpm"] for r in curve])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(rp, [r["torque"] for r in curve], "o-", label="model torque")
    ax[0].plot([2000, 6000], [1600, 1600], "k--", lw=1, label="published 1,600 N m, 2,000-6,000 rpm")
    ax[0].set_xlabel("rpm"); ax[0].set_ylabel("torque [N m]"); ax[0].legend(loc="lower right")
    a2 = ax[0].twinx(); a2.plot(rp, [r["power_kw"] for r in curve], "s-", color="C3"); a2.plot([6700], [1103], "k*", ms=12)
    a2.set_ylabel("power [kW]  (* = published 1,103 kW)"); a2.grid(False)
    ax[1].plot(rp, [r["boost_bar"] for r in curve], "o-", label="boost [bar gauge]")
    ax[1].plot(rp, [r["lam"] for r in curve], "s-", label="lambda")
    ax[1].plot(rp, [r["wg_frac"] for r in curve], "^-", label="waste-gate fraction")
    ax[1].plot(rp, [r["T3_c"] / 1000 for r in curve], "d-", label="T3 [1000 degC]")
    ax[1].axvline(P.rpm_turbo_switch, color="k", ls=":", lw=1); ax[1].set_xlabel("rpm"); ax[1].legend()
    _save(fig, "perf_full_load.png")

    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    md = np.array([r["mdot_per_turbo"] for r in curve]); pr = np.array([r["pr_comp"] for r in curve])
    two = np.array([r["n_active"] == 2 for r in curve])
    ax.plot(md[two], pr[two], "o-", label="2 turbos active (< 3,800 rpm)")
    ax.plot(md[~two], pr[~two], "s-", label="4 turbos active")
    prs = np.linspace(1.0, 3.3, 30)
    m_ch = comp["mdot_design"] * 1.08
    ax.plot(0.40 * m_ch * ((prs - 1) / (comp["pr_design"] - 1)) ** 0.85, prs, "k--", lw=1, label="surge line (representative, EST)")
    ax.plot(m_ch * np.sqrt(np.clip(1 - ((prs - 1) / 2.6) ** 4, 0, 1)), prs, "k:", lw=1, label="choke line (representative, EST)")
    for r in curve:
        ax.annotate(f"{r['rpm']:.0f}", (r["mdot_per_turbo"], r["pr_comp"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("air mass flow per turbocharger [kg/s]"); ax.set_ylabel("compressor pressure ratio"); ax.legend(fontsize=7)
    ax.set_title("Compressor operating line - sequential (register) charging")
    _save(fig, "turbo_compressor_operating_line.png")

    c = rated["_cyc"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(c["th"], c["p"] / 1e5); ax[0].set_xlabel("crank angle [deg ATDC firing]"); ax[0].set_ylabel("cylinder pressure [bar]")
    ax[0].set_title(f"Rated power: p_max {rated['p_max_bar']:.0f} bar at {rated['th_pmax']:.0f} deg")
    ax[1].loglog(c["V"] * 1e6, c["p"] / 1e5); ax[1].set_xlabel("volume [cm3]"); ax[1].set_ylabel("pressure [bar]"); ax[1].set_title("p-V (closed cycle)")
    _save(fig, "cycle_pressure_rated.png")

    cols = ["rpm", "torque", "power_kw", "bmep_bar", "boost_bar", "pr_comp", "T2_c", "T_man_c", "mdot_air", "lam", "bsfc_g_kwh",
            "p_max_bar", "T3_c", "p3_bar", "er_turb", "wg_frac", "n_active"]
    md_perf = f"""# Performance and turbocharger matching (0-D cycle model)

Generated by `python -m w16.reports`. Model: single-zone closed cycle (Wiebe heat release, Woschni heat transfer
x {cycle.A['woschni_scale']}, Chen-Flynn friction), rectangular pumping loop, turbocharger power balance with a fixed
turbine flow area and a waste-gate. It is a **sizing model, not a calibrated simulation**.

## Assumptions (all EST unless tagged)

{_tab([(k, v) for k, v in cycle.A.items()], ["constant", "value"])}

Volumetric efficiency, CA50 and burn duration are speed tables in `src/w16/analysis/cycle.py`.
The torque target is the published curve (1,600 N m from 2,000 to 6,000 rpm, 1,103 kW at 6,700 rpm); the model
solves the manifold pressure needed to reach it and reports whether the turbochargers can supply it.

## Full-load results

{_tab([[r[k] for k in cols] + ["yes" if r["boost_limited"] else ""] for r in curve], cols + ["turbine-limited"])}

![full load](perf_full_load.png)

## Comparison with published figures

{_tab([(n, v, ref, tag, f"{(v - ref) / ref * 100:+.1f} %") for n, v, ref, tag in checks], ["quantity", "model", "reference", "source", "deviation"])}

Notes
- Rated power and plateau torque are *targets*; the informative results are the boost, air flow, temperatures and
  the fact that the turbocharger balance closes.
- Rated-power boost: **{rated['boost_bar']:.2f} bar gauge** ({rated['p_man_bar']:.2f} bar abs). Secondary sources quote about
  1.85 bar for the Chiron; no manufacturer figure was found.
- The turbine-inlet limit ({P.t_exh_valve_ref_c:.0f} degC, the published rating of the exhaust switching valve) is held by
  enrichment; the model needs lambda = {rated['lam']:.2f} at rated power, i.e. BSFC {rated['bsfc_g_kwh']:.0f} g/kWh and
  {rated['mdot_fuel'] / 0.745 * 3600:.0f} L/h of fuel. This is consistent in magnitude with the widely quoted statement that
  a 100 L tank lasts roughly nine minutes at full load, but the enrichment level is a model result, not a measured value.
- Below {curve[4]['rpm']:.0f} rpm the torque is limited by turbine power (waste-gates shut).

## Sequential turbocharging - sizing logic

- Turbine effective flow area per turbocharger: **{A_t * 1e4:.2f} cm2** (CALC). Binding design point: just above the
  change-over ({P.rpm_turbo_switch:.0f} rpm, four turbochargers) the flow per turbine is at its minimum for full torque, so the
  waste-gates must be just closed there. With two turbochargers the same flow per turbine occurs near half that speed,
  which is why full torque is available from about 2,000 rpm - the published torque plateau and change-over speed are
  mutually consistent with four equal-size turbochargers.
- Provisional compressor: design flow {comp['mdot_design']:.3f} kg/s per turbocharger at PR {comp['pr_design']:.2f};
  tip speed {comp['U2']:.0f} m/s; impeller exducer **{comp['D2_comp']:.0f} mm**, inducer {comp['D1_comp']:.0f} mm; speed
  {comp['n_rpm']:.0f} rpm; shaft power {comp['P_shaft_kw']:.0f} kW. Turbine wheel {comp['D_turb']:.0f} mm inducer /
  {comp['D_turb_exd']:.0f} mm exducer (EST ratios). These are sizing values, not an aerodynamic design.

![compressor](turbo_compressor_operating_line.png)

The surge and choke lines are representative shapes for a compressor of this size, drawn only to show why two
turbochargers must carry the engine at low speed (with four in parallel the low-speed points would lie left of the
surge line). They are **not** a measured map.

## Control strategy derived from the model

| Regime | Active turbos | Boost control | Protection |
|---|---|---|---|
| < ~2,000 rpm | 2 (A-turbos) | waste-gates shut, exhaust valves to B-turbines shut, B-compressors isolated by check valves | spark retard on knock (ion current) |
| 2,000 - 3,800 rpm | 2 | waste-gate closed-loop on manifold pressure (bypass {curve[5]['wg_frac'] * 100:.0f}-{curve[8]['wg_frac'] * 100:.0f} %) | compressor outlet temperature, turbo speed model |
| ~3,600 - 3,800 rpm | 2 -> 4 | B-turbine valves opened progressively to pre-spin B-turbos; B-compressor recirculation open until its outlet pressure reaches manifold pressure, then check valve opens | surge margin of the B-compressors, torque smoothing by spark/throttle |
| > 3,800 rpm | 4 | all waste-gates closed-loop (bypass {curve[9]['wg_frac'] * 100:.0f}-{rated['wg_frac'] * 100:.0f} %) | T3 <= {P.t_exh_valve_ref_c:.0f} degC by enrichment, over-speed limit, boost reduction on knock/misfire |

![cycle](cycle_pressure_rated.png)
"""
    _w(os.path.join(OUT, "01_performance_turbocharging.md"), md_perf)

    # ================================================================= 2. crank-train dynamics
    loads = {n: dynamics.run(n, next((r for r in curve if r["rpm"] == n), None), A_turb=A_t) for n in (2000, 3000, 3750, 5000, 6000, 6700)}
    d = loads[6700]; d2 = loads[2000]
    ino = dynamics.inertia_only(P.rpm_overspeed)
    in_r = dynamics.inertia_only(P.rpm_rated)
    # torsional model with the CAD throw inertia (D-050): counterweights designed exactly as in the CAD assembly
    from .cad import cranktrain as CT
    cw_t, _ = CT.design_counterweights({k: v * 1e3 for k, v in d["mr_cw"].items()}, d["cw_angle"])
    J_cad = CT.throw_inertia(cw_t)
    f_t, modes, K, J, kk, tinfo = dynamics.torsional_modes(J_cad)
    tors, _, _ = dynamics.torsional_forced(loads, J_cad=J_cad)
    crit = {o: f_t[1] * 60 / o for o in (8, 4, 2.5)}                 # first-mode critical speeds of the listed orders
    n25 = crit[2.5]
    res25 = (f"**The order-2.5 resonance at about {n25:,.0f} rpm lies inside the operating range** (up to {P.rpm_max:,.0f} rpm, rated "
             f"{P.rpm_rated:,.0f} rpm): the viscous damper at the free end must address it." if n25 <= P.rpm_max else
             f"The order-2.5 resonance at about {n25:,.0f} rpm is above the governed speed ({P.rpm_max:,.0f} rpm).")
    hm_rod = dynamics.short_bearing_hmin(d2["be_peak"], P.pin_dia, d2["w_eff_rod"], 2000)
    hm_main = dynamics.short_bearing_hmin(d["main_peak"], P.main_dia, d["w_eff_main"], 6700)
    m_rec, m_rot = dynamics.masses()
    F_design = P.p_max_design_bar * 1e5 * math.pi / 4 * (P.bore * 1e-3) ** 2
    R["dynamics"] = dict(rod_peak_comp=max(v["rod_peak_comp"] for v in loads.values()), rod_peak_tens_overspeed=ino["F_tension"],
                         side_peak=max(v["side_peak"] for v in loads.values()), main_peak=max(v["main_peak"] for v in loads.values()),
                         be_peak=max(v["be_peak"] for v in loads.values()), mr_cw=d["mr_cw"], cw_angle=d["cw_angle"],
                         F_design_gas=F_design, torsional_f=f_t[:4].tolist(), m_rec=m_rec, m_rod_rot=m_rot,
                         main_peak_vec=max(d["mains"].values(), key=lambda m: m["peak"])["peak_vec"],
                         T_max=d["T_max"], T_min=d["T_min"], a_tdc_overspeed=ino["a_tdc"], tors=tinfo,
                         torsional_crit_rpm={str(o): n for o, n in crit.items()}, J_throw_cad={k: v for k, v in J_cad[0].items()}, J_main_cad=J_cad[1],
                         F_free_peak=d["F_free_peak"], M_free_peak=d["M_free_peak"])
    c1, c2 = L.CYL[1], L.CYL[2]
    al = dynamics.AL
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for cc, lab in ((c1, "cyl 1 (outer row)"), (c2, "cyl 2 (inner row)")):
        th = (al - cc.fire + 360) % 720 - 360
        o = np.argsort(th)
        ax[0].plot(th[o], L.piston_x_from_tdc(cc, al)[o], label=lab)
        ax[1].plot(th[o], d["cf"][cc.no]["v"][o], label=lab)
        ax[2].plot(th[o], d["cf"][cc.no]["a"][o] / 1e3, label=lab)
    ax[0].set_ylabel("piston travel from TDC [mm]"); ax[1].set_ylabel("piston speed [m/s] @6,700"); ax[2].set_ylabel("acceleration [1000 m/s2] @6,700")
    for a in ax: a.set_xlabel("crank angle [deg ATDC firing]"); a.legend(fontsize=7)
    _save(fig, "kinematics.png")
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for n in (2000, 6700):
        ax[0].plot(al, loads[n]["T"], label=f"{n} rpm (mean {loads[n]['T_mean']:.0f} N m)")
    ax[0].set_xlabel("crank angle [deg]"); ax[0].set_ylabel("indicated crank torque [N m]"); ax[0].legend(); ax[0].set_xlim(0, 180)
    ax[0].set_title("Torque ripple, 16 firings / 720 deg (first 180 deg shown)")
    mj = max(d["mains"], key=lambda j: d["mains"][j]["peak"])
    for j in (1, mj, 5):
        F = d["mains"][j]["F"] / 1e3
        ax[1].plot(F[:, 0], F[:, 1], lw=0.8, label=f"main {j} (peak {d['mains'][j]['peak'] / 1e3:.1f} kN)")
    ax[1].set_aspect("equal"); ax[1].set_xlabel("F_y [kN]"); ax[1].set_ylabel("F_z [kN]"); ax[1].legend(fontsize=7); ax[1].set_title("Main-bearing load loci at 6,700 rpm")
    _save(fig, "torque_and_bearing_loads.png")

    rows_l = [(n, v["rod_peak_comp"] / 1e3, v["rod_peak_tens"] / 1e3, v["side_peak"] / 1e3, v["be_peak"] / 1e3, v["be_spec_load_mpa"],
               v["main_peak"] / 1e3, v["main_spec_load_mpa"], v["se_spec_load_mpa"], v["T_mean"], v["T_max"], v["T_min"]) for n, v in loads.items()]
    md_dyn = f"""# Crank-train kinematics, balance, bearing loads and torsional vibration

Generated by `python -m w16.reports`. Rigid-body model; bearing loads from a statically determinate bay model
(each throw carried by its two neighbouring main bearings).

## Geometry (CALC from the master parameters)

| Item | Value |
|---|---|
| Stroke / crank throw | {P.stroke:.3f} mm / {P.throw:.4f} mm (offset bores: stroke > 2r) |
| Rod length / ratio r/l | {P.rod_length:.1f} mm / {P.throw / P.rod_length:.4f} |
| Row offset | {P.row_offset:.1f} mm |
| Max rod angularity | {in_r['rod_angle_max']:.2f} deg |
| Mean / max piston speed at {P.rpm_rated:.0f} rpm | {in_r['v_mean']:.2f} / {in_r['v_max']:.2f} m/s |
| Piston acceleration at TDC / BDC at {P.rpm_rated:.0f} rpm | {in_r['a_tdc']:.0f} / {in_r['a_bdc']:.0f} m/s2 |
| Same at mechanical overspeed {P.rpm_overspeed:.0f} rpm | {ino['a_tdc']:.0f} / {ino['a_bdc']:.0f} m/s2 |
| Firing intervals (numerically located TDCs) | min {L.firing_check().min():.3f} deg, max {L.firing_check().max():.3f} deg |
| Crankpin phases, pins 1-8 | {", ".join(f"{L.PIN_PHASE[k]:.2f}" for k in range(1, 9))} deg |

Masses used (EST until replaced by CAD mass properties): piston {P.m_piston} kg, pin {P.m_pin} kg, rings {P.m_rings} kg,
rod {P.m_rod} kg (CG at {P.rod_cg_frac:.0%} of the length from the big end) -> reciprocating {m_rec:.3f} kg per cylinder,
rotating rod mass {m_rot:.3f} kg.

![kinematics](kinematics.png)

## Balance

Each crankpin carries one cylinder of each bank, 90 deg apart, so the first-order reciprocating forces of a pair form
a vector rotating with the crank; it is cancelled together with the rotating rod mass by the counterweights of that
throw. Because of the VR offsets the required counterweight vector is not exactly opposite the pin; it was solved
per throw:

| Throw | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| m*r required [kg mm] | {" | ".join(f"{d['mr_cw'][k] * 1e3:.2f}" for k in range(1, 9))} |
| angle from pin [deg] | {" | ".join(f"{d['cw_angle'][k]:.2f}" for k in range(1, 9))} |

(the crankpin's own unbalance is added in CAD.) Residual free forces and moments at {d['rpm']} rpm:

| Quantity | Peak | Dominant orders (amplitude) |
|---|---|---|
| Free force | {d['F_free_peak']:.0f} N | 4th: {d['F_free_orders_z'][4]:.0f} N vertical, {d['F_free_orders_y'][4]:.0f} N lateral |
| Free moment | {d['M_free_peak']:.0f} N m | 1st: {d['M_y_orders'][1]:.1f}; 3rd: {d['M_y_orders'][3]:.1f}; 4th: {d['M_y_orders'][4]:.1f} N m (pitch) |

For scale: the unbalanced reciprocating force of a single cylinder at this speed is {m_rec * P.throw * 1e-3 * (d['rpm'] * math.pi / 30) ** 2 / 1e3:.1f} kN.
The W16 with this crank is therefore free of first- and second-order forces and moments; only small higher-order
residuals remain. No balance shafts are needed (the VW W8 needs two, the W12 and W16 none).

## Loads (full load)

{_tab(rows_l, ["rpm", "rod compression [kN]", "rod tension [kN]", "piston side force [kN]", "big-end bearing [kN]", "big-end spec. load [MPa]", "main bearing peak [kN]", "main spec. load [MPa]", "small-end spec. load [MPa]", "mean torque [N m]", "max torque", "min torque"])}

- Mean indicated torque from the force model vs. cycle model at 6,700 rpm: {d['T_mean']:.0f} vs {d['T_ind_expected']:.0f} N m
  ({(d['T_mean'] / d['T_ind_expected'] - 1) * 100:+.1f} %, consistency check between two independent calculations).
- Rod tension at gas-exchange TDC, overspeed {P.rpm_overspeed:.0f} rpm, no gas load: **{ino['F_tension'] / 1e3:.1f} kN**.
- Design gas force at the design peak pressure {P.p_max_design_bar:.0f} bar: **{F_design / 1e3:.1f} kN** (used for the FE load cases).
- Bearing projected widths used: big end {d['w_eff_rod']:.2f} mm x dia {P.pin_dia} mm; main {d['w_eff_main']:.1f} mm x dia {P.main_dia} mm.
  Typical capability of sputter (AlSn20 on bronze) bearings: 100+ MPa; bimetal: ~60 MPa. Both journals are inside this.
- Quasi-static short-bearing (Ocvirk) minimum film at peak load: big end {hm_rod[1]:.2f} um (2,000 rpm), main {hm_main[1]:.2f} um
  (6,700 rpm). This estimate ignores squeeze-film support and is conservative; an elasto-hydrodynamic orbit
  calculation is required before release (listed under limitations).

![loads](torque_and_bearing_loads.png)

## Torsional vibration (lumped model: damper - 8 throws - flywheel)

Throw stiffness from Carter's formula: {tinfo['k_throw'] / 1e3:.0f} kN m/rad; throw inertia {tinfo['J_throw'] * 1e3:.2f} g m2 (crank part
{tinfo['J_throw_crank'] * 1e3:.2f} g m2 from the CAD - pin, webs, counterweights and one main journal (D-050; the earlier EST was
{P.J_throw_fixed * 1e3:.1f} g m2) - plus {tinfo['J_throw_rods'] * 1e3:.2f} g m2 of rods and pistons);
damper {P.J_damper * 1e3:.0f} g m2; flywheel side {P.J_flywheel * 1e3:.0f} g m2.

Natural frequencies: {", ".join(f"{x:.0f} Hz" for x in f_t[1:5])}.
First mode ({f_t[1]:.0f} Hz) is excited by order 8 at {crit[8]:,.0f} rpm, order 4 at {crit[4]:,.0f} rpm and
order 2.5 at {crit[2.5]:,.0f} rpm. {res25}

{_tab([(o['rpm'], float(o['sec_torque'].max()), o['worst_order'], o['worst_amp']) for o in tors], ["rpm", "vibratory torque, worst section [N m, RSS of orders]", "largest single order", "its amplitude [N m]"])}

Nominal torsional shear stress in the crankpin (dia {P.pin_dia} mm) for mean + vibratory torque at 6,700 rpm:
{16 * (d['T_mean'] + float(tors[-1]['sec_torque'].max())) / (math.pi * (P.pin_dia * 1e-3) ** 3) / 1e6:.0f} MPa (before stress concentration).
A viscous damper is required at the free end; its tuning needs measured crank stiffness - listed under limitations.
The table is the root-sum-square of the orders. The crank fillet check (final report section 8.3, D-050) uses the harmonic synthesis of
IACS UR M53 (larger), and D-050 sets the damper requirement on it: the alternating torque at the most loaded section must stay <= 1,968 N m.
"""
    _w(os.path.join(OUT, "02_cranktrain_dynamics.md"), md_dyn)

    # ================================================================= 3. valve train
    lay = valvetrain.head_layout()
    clr = valvetrain.layout_clearances()
    pvc = valvetrain.piston_valve_clearance()
    spr = valvetrain.spring_requirement()
    th = np.arange(-360.0, 360.0, 0.5)
    (li, vi, ai), (le, ve_, ae) = valvetrain.valve_lifts(th)
    T = valvetrain.TIMING
    R["valvetrain"] = dict(layout=lay, clearances=clr, piston_valve={f"{k[0]}_{k[1]}": v for k, v in pvc.items()}, springs=spr,
                           timing=T, mach_index=valvetrain.mach_index(), rocker_ratio=dict(short=valvetrain.rocker_ratio(False), long=valvetrain.rocker_ratio(True)))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].plot(th, li, label="intake valve"); ax[0].plot(th, le, label="exhaust valve")
    x = L.piston_x_from_tdc(c1, th + c1.fire + 360.0)
    ax[0].plot(th, x / 10, "k:", label="piston travel / 10")
    ax[0].set_xlabel("crank angle [deg ATDC gas-exchange TDC]"); ax[0].set_ylabel("lift [mm]"); ax[0].legend(fontsize=7); ax[0].set_title("Valve lift and piston motion")
    # transverse layout sketch
    a = ax[1]
    col = {"in": "C0", "ex": "C3"}
    for row, dct in lay.items():
        for kind in ("in", "ex"):
            v = dct[kind]
            a.plot([v["u_head"], v["u_tip"]], [v["w_head"], P.valve_tip_w], color=col[kind], lw=2, ls="-" if row == "inner" else "--")
            a.plot([v["u_tip"], v["u_piv"]], [P.valve_tip_w + 3, P.valve_tip_w + 3], color="k", lw=3, alpha=0.5)
            a.plot(v["u_piv"], P.valve_tip_w - 3, "ks", ms=4)
        pl = dct["plug"]
        a.plot([pl["u0"], pl["u1"]], [pl["w0"], pl["w1"]], color="C2", lw=1.5, ls="-" if row == "inner" else "--")
        uc = dct["uc"]
        a.plot([uc - 43, uc + 43], [0, 0], "k", lw=1)
        e0 = dct["roof_edge_u"]; e1 = 2 * uc - e0
        a.plot([e0, e1], [P.roof_low_w, P.roof_low_w + abs(e1 - e0) * math.tan(math.radians(abs(dct["roof_tilt"])))], "k", lw=1)
    for cu in (-P.cam_u, P.cam_u):
        a.add_patch(plt.Circle((cu, P.cam_w), P.cam_base_r, fill=False))
        a.add_patch(plt.Circle((cu, P.cam_w), P.cam_base_r + P.valve_lift_in / valvetrain.rocker_ratio(True), fill=False, ls=":"))
    a.set_aspect("equal"); a.set_xlabel("u [mm]  (valley <-   -> outboard)"); a.set_ylabel("w above head face [mm]")
    a.set_title("Head transverse layout: solid = inner-row cylinder, dashed = outer-row\nblue intake, red exhaust, green plug well, circles = cams", fontsize=7)
    _save(fig, "valvetrain.png")
    md_vt = f"""# Valve train - layout, timing, clearances, spring loads

Generated by `python -m w16.reports`. Architecture per decision D-020 (two camshafts per head, roller finger followers
on hydraulic support elements, short and long valves). Dimensions are an engineering proposal (EST).

## Transverse layout (head-local u, w in mm)

{_tab([(row, kind, v['u_head'], v['w_head'], v['u_tip'], P.valve_tip_w, v['tilt'], v['length'], v['u_piv'], v['cam_u']) for row, dct in lay.items() for kind, v in ((k, dct[k]) for k in ('in', 'ex'))],
      ["row", "valve", "head u", "head w", "tip u", "tip w", "stem tilt [deg]", "head-to-tip length", "support element u", "cam u"])}

- Camshafts at u = -/+{P.cam_u:.0f} mm, w = {P.cam_w:.0f} mm; base circle radius {P.cam_base_r:.0f} mm.
- Two finger types (D-034): short valves {P.finger_tip_near:.0f} mm tip arm / {P.finger_piv_near:.0f} mm pivot arm, ratio {valvetrain.rocker_ratio(False):.2f}
  (cam lift {P.valve_lift_in / valvetrain.rocker_ratio(False):.2f} mm for {P.valve_lift_in:.1f} mm valve lift); long valves {P.finger_tip_far:.0f} / {P.finger_piv_far:.0f} mm,
  ratio {valvetrain.rocker_ratio(True):.2f} (cam lift {P.valve_lift_in / valvetrain.rocker_ratio(True):.2f} mm). The short pivot arm puts the short valve's support element
  {P.cam_u - P.finger_piv_near:.0f} mm from the head centre plane, clear of the long valve's spring; that element's boss hangs from the plug tower
  (lower end w = {P.hla_boss_w0:.0f} mm). A ratio of {valvetrain.rocker_ratio(False):.1f} is high for a finger follower: finger stiffness and roller contact
  stress must be checked in detail design.
- Valve springs: beehive, {P.spring_od:.0f} mm largest coil, installed height {P.spring_seat_drop - 4:.0f} mm (seat {P.spring_seat_drop:.0f} mm below the tip).
- Each camshaft serves the nearer row with short valves ({lay['inner']['in']['length']:.0f} mm head-to-tip, {abs(lay['inner']['in']['tilt']):.1f} deg) and the farther row with
  long valves ({lay['inner']['ex']['length']:.0f} mm, {abs(lay['inner']['ex']['tilt']):.1f} deg).
- Chamber roof tilt {P.roof_tilt:.2f} deg; piston crown tilted {P.crown_tilt:.2f} deg to the head face ({P.crown_tilt_axis:.2f} deg to the piston
  axis normal) to give CR {P.compression_ratio}:1 with an analytic head-chamber volume of {P.v_head_chamber_est_cc:.1f} cm3 (clearance volume
  {P.v_clear_cc:.2f} cm3). The CAD-measured compression ratio is reported in the CAD validation.
- Spark-plug wells tilt {abs(lay['inner']['plug']['tilt']):.1f} deg and meet the head centre plane at w = {P.plug_top_w:.0f} mm: one row of eight coils per head.

### Clearance study (transverse plane, positive = clear)

{_tab(clr, ["check", "margin [mm]"])}

## Timing (EST, phaser mid-position)

| Event | Crank angle |
|---|---|
| IVO | {-T['ivo']:.0f} deg BTDC |
| IVC | {T['ivc'] - 180:.0f} deg ABDC |
| EVO | {-(T['evo'] + 180):.0f} deg BBDC |
| EVC | {T['evc']:.0f} deg ATDC |
| Overlap | {T['evc'] - T['ivo']:.0f} deg |
| Intake / exhaust duration | {T['ivc'] - T['ivo']:.0f} / {T['evc'] - T['evo']:.0f} deg |
| Phaser authority (VW W-family values) | intake {T['intake_phaser_range']:.0f} deg, exhaust {T['exhaust_phaser_range']:.0f} deg crank |

Lift law: half-sine acceleration flanks ({T['flank_frac']:.0%} of the event each) with a half-sine nose. Inlet Mach index at
{P.rpm_rated:.0f} rpm: Z = {valvetrain.mach_index():.2f} (should stay below about 0.6).

## Piston-to-valve clearance (minimum over the cycle, tilted crown included)

{_tab([(k[0], k[1], v['min_clear'], v['at_theta'], v['lift_there']) for k, v in pvc.items()], ["row", "valve", "min clearance [mm]", "at crank angle [deg]", "valve lift there [mm]"])}

Criterion used: >= 1.5 mm intake, >= 2.0 mm exhaust. Shallow valve pockets are added in the piston CAD for the
far-side valves to raise the smallest values.

## Spring requirement at mechanical overspeed ({P.rpm_overspeed:.0f} rpm)

{_tab([(k, v['m_eff'] * 1e3, v['a_nose'], v['a_flank'], v['f_nose'], v['f_required'], v['f_seat'], v['rate_n_mm'], v['f_open'], v['v_max_ms']) for k, v in spr.items()],
      ["valve", "effective mass [g]", "nose decel. [m/s2]", "flank accel. [m/s2]", "inertia force at nose [N]", "required (x1.25) [N]", "seat load [N]", "rate [N/mm]", "load at full lift [N]", "max valve speed [m/s]"])}

Effective masses are EST (valve, retainer, one third of the spring, follower equivalent). No valve-train
dynamic (multi-body) simulation was run; spring surge is not assessed.

![valvetrain](valvetrain.png)
"""
    _w(os.path.join(OUT, "03_valvetrain.md"), md_vt)

    # ================================================================= 4. thermal, CAC, lubrication, fuel, ducts
    op_sw = min(curve, key=lambda r: abs(r["rpm"] - 3750))
    eb = thermal.energy_balance(rated)
    cool = thermal.coolant_ht(eb)
    wall = thermal.liner_wall_temps(rated, cool)
    cac = thermal.charge_air_cooler(rated)
    lub = thermal.lubrication(eb)
    fuel = thermal.fuel_system(rated)
    duct = thermal.duct_sizing(rated, op_sw)
    net = thermal.coolant_network()
    man = thermal.manifold_distribution(rated)
    R.update(energy=eb, coolant=cool, wall=wall, cac={k: v for k, v in cac.items()}, lube=lub, fuel=fuel, ducts=duct, coolant_net=net, manifold=man)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    items = [("brake power", eb["p_brake"]), ("HT coolant", eb["q_coolant_ht"]), ("oil", eb["q_oil"]), ("exhaust sensible", eb["q_exhaust_sensible"]),
             ("unburned (rich mixture)", eb["q_unburned"])]
    ax.barh([i[0] for i in items], [i[1] for i in items], color=["C2", "C0", "C1", "C3", "C7"])
    for i, (n, v) in enumerate(items):
        ax.text(v, i, f" {v:.0f} kW ({v / eb['q_fuel'] * 100:.0f} %)", va="center", fontsize=8)
    ax.set_xlabel("kW"); ax.set_title(f"Fuel energy split at rated power (fuel power {eb['q_fuel']:.0f} kW)"); ax.set_xlim(0, max(i[1] for i in items) * 1.35)
    _save(fig, "energy_balance.png")
    md_th = f"""# Thermal management, charge-air cooling, lubrication, fuel and duct sizing

Generated by `python -m w16.reports`. Analytical / 1-D steady-state calculations at rated power
({rated['rpm']:.0f} rpm, {rated['power_kw']:.0f} kW) unless stated. Not CFD.

## Energy balance at rated power

{_tab([(k, v, f"{v / eb['q_fuel'] * 100:.1f} %") for k, v in (("Fuel power", eb['q_fuel']), ("Brake power", eb['p_brake']), ("Heat to HT coolant", eb['q_coolant_ht']), ("Heat to oil", eb['q_oil']), ("Exhaust sensible enthalpy (after turbine) + radiation", eb['q_exhaust_sensible']), ("Unburned chemical energy (enrichment)", eb['q_unburned']))], ["item", "kW", "share"])}

Charge-air heat rejected to the LT circuit: {eb['q_cac_lt']:.0f} kW (this is compressor work, recirculated inside the balance).
Total heat leaving the engine other than shaft power: {(eb['q_fuel'] - eb['p_brake']) / 0.7355:.0f} PS equivalent, of which
{(eb['q_fuel'] - eb['p_brake'] - eb['q_unburned']) / 0.7355:.0f} PS is sensible heat. Published statement: "more than 3,000 hp" of heat.

In-cylinder wall heat (Woschni x {cycle.A['woschni_scale']}): head {eb['wall_parts'][0]:.0f} kW, piston {eb['wall_parts'][1]:.0f} kW, liner {eb['wall_parts'][2]:.0f} kW.
Split assumptions (EST): 55 % of piston heat and 55 % of friction heat to oil; 60 % of exhaust-port heat to coolant.

![energy](energy_balance.png)

## High-temperature coolant circuit

| Item | Value |
|---|---|
| Pump flow (PUB) | {cool['flow_lpm']:.0f} L/min = {cool['mdot']:.1f} kg/s |
| Coolant temperature rise across the engine | {cool['dT']:.1f} K |
| Circulation time of the {P.ht_volume_l:.0f} L fill (PUB: about 3 s) | {cool['circulation_time_s']:.1f} s |
| Mean jacket velocity / Reynolds number | {cool['v_jacket']:.1f} m/s / {cool['re']:.0f} |
| Jacket heat-transfer coefficient (Dittus-Boelter) | {cool['h_jacket']:.0f} W/m2K |
| Liner top zone heat flux | {wall['q_liner_top_wm2'] / 1e6:.2f} MW/m2 |
| Liner wall temperature, coolant side / gas side | {wall['T_liner_coolant_side_c']:.0f} / {wall['T_liner_gas_side_c']:.0f} degC |
| Fire-deck heat flux | {wall['q_deck_wm2'] / 1e6:.2f} MW/m2 |
| Fire-deck temperature, coolant side / gas side (mean, 1-D) | {wall['T_deck_coolant_side_c']:.0f} / {wall['T_deck_gas_side_c']:.0f} degC |

Coolant-side wall temperatures above about 130 degC imply sub-cooled nucleate boiling at 1.4-2 bar system pressure,
which is normal in exhaust-side head passages. Local hot spots (exhaust valve bridge) are assessed by FE in
`08_SIMULATIONS/fea/`.

### Flow distribution (1-D ladder network, one bank)

Inlet rail and outlet rail dia {net['d_rail_mm']:.0f} mm, eight cylinder branches (jacket + gasket metering + head passages, K = {net['k_branch']}).
Flow per cylinder station [L/min]: {", ".join(f"{q:.1f}" for q in net['q_station_lpm'])} -> maldistribution {net['maldistribution_pct']:.2f} %.
Engine pressure drop {net['dp_engine_bar']:.2f} bar, circuit total {net['dp_total_bar']:.2f} bar (external 0.9 bar EST) -> pump hydraulic power
{net['pump_hydraulic_kw']:.1f} kW, shaft power {net['pump_shaft_kw']:.1f} kW at 62 % efficiency.

## Charge-air cooler (water-to-air, one per bank)

Core (EST): {cac['core']['core_w'] * 1e3:.0f} x {cac['core']['core_h'] * 1e3:.0f} mm face, {cac['core']['core_d'] * 1e3:.0f} mm deep, {cac['n_layers']} layers,
fin pitch {cac['core']['fin_pitch'] * 1e3:.1f} mm, fin height {cac['core']['fin_h'] * 1e3:.0f} mm. LT coolant {cac['lt_flow_total_lpm']:.0f} L/min total at {cycle.A['T_lt_coolant'] - 273.15:.0f} degC.

| Item | Value |
|---|---|
| Air flow per cooler | {cac['mdot_air']:.3f} kg/s |
| Air in / out | {cac['T_air_in_c']:.0f} / {cac['T_air_out_c']:.0f} degC |
| Temperature drop (PUB: "as much as 130 K") | {cac['dT_air']:.0f} K |
| Effectiveness (e-NTU, cross-flow) / NTU | {cac['effectiveness']:.3f} / {cac['ntu']:.2f} |
| Heat rejected, both coolers | {cac['q_total_kw']:.0f} kW |
| Air-side pressure drop of the core | {cac['dp_air_kpa']:.2f} kPa |
| LT coolant temperature rise | {cac['water_dT']:.1f} K |
| Air-side / water-side h | {cac['h_air']:.0f} / {cac['h_water']:.0f} W/m2K |

The cycle model uses a deliberately lower effectiveness of {cac['assumed_eps_in_cycle']} (fouling, maldistribution, hot LT coolant).

## Lubrication (dry sump)

| Consumer | Flow [L/min] at {lub['p_gallery_bar']:.0f} bar gallery pressure, hot |
|---|---|
| 9 main bearings | {lub['q_main_lpm']:.1f} |
| 16 big-end bearings | {lub['q_rod_lpm']:.1f} |
| 16 piston cooling jets (dia {lub['jet_dia_mm']:.1f} mm) | {lub['q_jets_lpm']:.1f} |
| 20 camshaft bearings | {lub['q_cam_lpm']:.1f} |
| 64 hydraulic elements + finger spray | {lub['q_hla_lpm']:.1f} |
| 4 cam phasers | {lub['q_phaser_lpm']:.1f} |
| 4 turbochargers | {lub['q_turbo_lpm']:.1f} |
| chain tensioners + chain spray | {lub['q_chain_lpm']:.1f} |
| **Total engine demand** | **{lub['q_total_lpm']:.0f}** |
| Pressure pump delivery (x1.25) | {lub['q_pump_lpm']:.0f} |
| Scavenge capacity (x{lub['scav_ratio']:.0f}, aerated) | {lub['q_scavenge_lpm']:.0f} |

Oil heat load {lub['q_oil_kw']:.0f} kW -> oil temperature rise {lub['oil_dT']:.0f} K. Two main galleries dia {lub['d_gallery_design_mm']:.0f} mm
(required {lub['d_gallery_required_mm']:.1f} mm for 3.5 m/s) -> {lub['v_gallery_design']:.1f} m/s. Tank volume >= {lub['tank_volume_l']:.0f} L (12 s dwell).
Pump drive power about {lub['pump_power_kw']:.1f} kW. Bearing flows use the pressure-fed side-leakage formula at an
eccentricity ratio of 0.6 and are approximate.

## Fuel system (duplex port injection, 32 injectors)

Fuel flow at rated power {fuel['mdot_fuel_kg_s'] * 1e3:.0f} g/s = {fuel['fuel_lph']:.0f} L/h (lambda {fuel['lam_rated']:.2f}); per cylinder {fuel['per_cyl_g_s']:.2f} g/s.
Two injectors per cylinder at {fuel['duty_at_rated']:.0%} duty -> static flow {fuel['injector_static_cc_min']:.0f} cm3/min each; selected size
{fuel['injector_selected_cc_min']} cm3/min at {fuel['rail_dp_bar']:.0f} bar differential. Supply pumps {fuel['pump_flow_lph']:.0f} L/h (x1.35).

## Duct sizing (velocity / Mach limits, EST)

{_tab([(k, v) for k, v in duct.items()], ["item", "value [mm unless named]"])}

## Charge-air distribution

A quasi-steady 1-D model of an **end-fed log plenum** (rejected concept) gives relative runner flows of
{", ".join(f"{q:.2f}" for q in man['q_rel'])} along the bank, a spread of {man['spread_pct']:.0f} %, because the dynamic head in a
slim plenum exceeds the runner loss. Design consequence (decision D-021): the water-to-air cooler sits directly on
the plenum and discharges into it over its full length, so the plenum sees no axial through-flow; distribution is
then governed by the cooler inlet tank. That flow is three-dimensional and was **not** simulated (no CFD available).
"""
    _w(os.path.join(OUT, "04_thermal_lube_fuel.md"), md_th)

    # ================================================================= reference spec + parameter table
    disp = P.displacement_cc
    md_ref = f"""# Reference specification

Generated by `python -m w16.reports` from `src/w16/params.py`. Tags: PUB published, SEC secondary/unconfirmed,
CALC calculated here, EST engineering estimate. Sources: `01_RESEARCH/RESEARCH_LOG.md`.

## 1. Fixed baseline (from the brief, checked against sources)

{_tab([(k, v, u, t, n) for k, v, u, t, n in P.table(("PUB", "SEC"))], ["parameter", "value", "unit", "tag", "note"])}

## 2. Displacement check

16 x pi/4 x {P.bore}^2 x {P.stroke} mm3 = **{disp:.2f} cm3**; published {P.displacement_ref_cc:.0f} cm3; deviation {(disp / P.displacement_ref_cc - 1) * 100:+.4f} %.
Per cylinder {P.disp_cyl_cc:.2f} cm3. The commonly reported 86 x 86 mm is therefore consistent and is adopted.
Because the VR bores are offset from the crank axis by {P.row_offset} mm, a stroke of exactly {P.stroke} mm needs a crank
throw of {P.throw:.4f} mm rather than {P.stroke / 2:.1f} mm.

## 3. Derived performance figures

| Quantity | Value |
|---|---|
| BMEP at 1,600 N m | {P.torque_max_nm * 4 * math.pi / (disp * 1e-6) / 1e5:.2f} bar |
| BMEP at rated power | {P.power_rated_kw * 1e3 * 2 / (disp * 1e-6 * P.rpm_rated / 60) / 1e5:.2f} bar |
| Torque at rated power | {P.power_rated_kw * 1e3 / (P.rpm_rated * math.pi / 30):.0f} N m |
| Specific power | {P.power_rated_kw / disp * 1000:.1f} kW/L |
| Mean piston speed at {P.rpm_rated:.0f} rpm | {2 * P.stroke * 1e-3 * P.rpm_rated / 60:.2f} m/s |

## 4. Firing order and crank phasing (kinematic consistency test)

Firing order (SEC): {"-".join(str(c) for c in P.firing_order)}; 45 deg between firings.
Assumption: cylinders k (bank 1) and k+8 (bank 2) share crankpin k, bank 2 reaches TDC 90 deg after bank 1.

{_tab([(c.no, c.bank, c.row, c.pin, c.x, c.theta, L.tdc_phi(c), c.fire) for c in L.CYLS], ["cyl", "bank", "row", "crankpin", "x [mm]", "axis angle [deg]", "pin angle at TDC [deg]", "fires at [deg crank]"])}

Result: the two cylinders on every pin require the same pin phase (largest mismatch {L.PIN_PHASE_ERR:.1e} deg) and all 16
firing intervals found numerically are {L.firing_check().min():.3f}-{L.firing_check().max():.3f} deg. The published order is therefore
exactly reproducible with one rod of each bank on each of eight crankpins. Pin phases (deg, pins 1-8):
{", ".join(f"{L.PIN_PHASE[k]:.3f}" for k in range(1, 9))}; relative to pin 1: {", ".join(f"{(L.PIN_PHASE[k] - L.PIN_PHASE[1]) % 360:.2f}" for k in range(1, 9))}.
The {(L.PIN_PHASE[2] - L.PIN_PHASE[1]) % 360 - 180:.2f} deg stagger between odd and even pins is the VR correction (the VW W12 has 21.833 deg, SSP 248).

## 5. Derived architecture dimensions (CALC)

{_tab([(k, v, u, t, n) for k, v, u, t, n in P.table(("CALC",))], ["parameter", "value", "unit", "tag", "note"])}

## 6. Not publicly available - provisional values used

See `MASTER_PARAMETERS.md` (all `EST` rows) and `00_PROJECT_CONTROL/DECISIONS.md`.
"""
    _w(os.path.join(SPEC, "REFERENCE_SPEC.md"), md_ref)
    _w(os.path.join(SPEC, "MASTER_PARAMETERS.md"),
       "# Master parameter table\n\nGenerated from `src/w16/params.py` - the single source of truth for CAD, calculations and documents.\n\n"
       + P.markdown() + "\n\n## Materials\n\n"
       + _tab([(k, v["rho"], v["E"], v["nu"], v["alpha"] * 1e6, v["k"], v["yield_"], v["uts"], v["fatigue"], v["use"]) for k, v in MATERIALS.items()],
              ["material", "density [kg/m3]", "E [GPa]", "nu", "alpha [1e-6/K]", "k [W/mK]", "yield [MPa]", "UTS [MPa]", "fatigue limit [MPa] (EST)", "use"]) + "\n")

    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(jsonable(R), fh, indent=1)
    np.savez_compressed(os.path.join(OUT, "pressure_trace_rated.npz"), th=c["th"], p=c["p"], V=c["V"], T=c["T"])
    print("analytical package written to", OUT)
    for n, v, ref, tag in checks:
        print(f"  {n}: {v:.1f} (ref {ref})")
    return R


if __name__ == "__main__":
    main()
