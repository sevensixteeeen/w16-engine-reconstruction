"""Main-journal fillet: combined bending + torsion, hand calculation (D-050, 2026-11-25).  Light calc, no FE.

Bending: the official main-fillet peak of the crank FE convergence (zero-size extrapolation, 08_SIMULATIONS/fea/
crank_groove_convergence.json): von Mises peak at the design gas force (135 bar), pulsating load -> alternating = mean =
half the peak (project convention).
Torsion: nominal shear in the main journal tau_N = M / W_P, W_P = pi D_G^3 / 16 (solid journal), times the torsion stress
concentration factor of the journal fillet of IACS UR M53 Rev.4 (2019) section M53.3.3 / 3.2 (p. 19):
    beta_T = 0.8 f(r,s) f(b) f(w),  f(r,s) = r^(-0.322 + 0.1015 (1 - s)),  f(b) = 7.8955 - 10.654 b + 5.3482 b^2 - 0.857 b^3,
    f(w) = w^(-0.145),  with r = R_G / D_G (journal fillet over journal diameter, crankpin and journal differ), s = S / D
    (pin overlap over crankpin diameter), w = W / D (web thickness), b = B / D (web width).
M53's validity ranges are 0.03 <= r <= 0.13, 0.2 <= w <= 0.8, 1.1 <= b <= 2.2, s <= 0.5 (p. 18); outside them the factor is
evaluated both at the range limits and extrapolated, and the larger is used.  The web width B is taken at the pin boss (the
narrower width, larger f(b)).
Torques: mean = the engine mean torque at full load (the section next to the flywheel carries all of it); vibratory =
harmonic synthesis over orders 0.5-12 (M53 2.2.2) of the forced response of the lumped torsional model with the CAD throw
inertia (dynamics, D-050; damper and damping EST), M_TN = (M_max - M_min) / 2 per section, at the most loaded section,
scanned in speed across the first-mode order-2.5 resonance and at rated speed; the largest is used.
Combination (M53 5.2, journal fillet, p. 22): sigma_v = sqrt(sigma_B,a^2 + 3 tau_a^2), bending and torsion peaks assumed in
phase at the same point (conservative: the bending peak of throw 3 at the design gas force with the torque of the most
loaded section).  Factor = fatigue strength / sigma_v - the project convention (alternating stresses, target 1.5); M53
asks Q >= 1.15 (p. 23).  Mean stresses are in no other project factor; their effect is given as a Goodman value on the
von Mises equivalents (sigma_m from the pulsating bending and the mean torque).  M53's own fatigue-strength formula
(p. 22, no credit for nitriding, R_G taken as not less than 2 mm) is given for comparison.  The alternating torque that
would give the 1.5 target with the same bending, SCF and combination is reported (`torque_limit_for_target`) - a
number for the decision, not a requirement.

--compare (2026-11-25, at the user's request, the basis of the D-050 decision for option (b)): option (c) (R1.6, 16 mm
shells with 1.0 mm chamfers, 14 mm land; its FE convergence is kept as `semicircle_r16_option_c`) against option (b) (R2.5
on the journal, unchamfered shells narrowed to fit: the largest width in 0.1 mm steps that keeps the same axial allowance,
`cranktrain.main_fillet_fit`).  The bending peak of
(b) is the official (c) peak scaled by the ratio of the M53 journal-fillet bending factors, which differ only in
f_B(r) = 0.1908 r^(-0.5568), r = R_G / D (M53.3.3, p. 19): (2.5 / 1.6)^(-0.5568) = 0.780 - the nominal web bending stress
does not change with the fillet radius.  Main bearing per option: land width, specific load at the model peak and the
quasi-static Ocvirk film at 6,700 rpm (the method of the dynamics report).

The default mode evaluates the modelled fillet (P.main_fillet_r) on its own convergence record (key `semicircle`) and stops
if that record is for another radius; with an unconverged main-fillet peak it writes 'not converged' and no factor.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\crank_main_fillet_torsion.py [--compare]

Output: 08_SIMULATIONS/analytical/crank_main_fillet_torsion.json (default) or crank_main_fillet_options.json (--compare).
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from w16.params import P, MATERIALS  # noqa: E402
from w16 import layout as L  # noqa: E402
from w16.analysis import cycle, dynamics as D  # noqa: E402
from w16.cad import cranktrain as CT  # noqa: E402
from w16.cad.assembly import _cw  # noqa: E402
from w16.cad.common import MAT  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "crank_main_fillet_torsion.json")
OUT_OPT = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "crank_main_fillet_options.json")
CONV = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_groove_convergence.json")
ORDERS_H = range(1, 25)          # h cycles per 720 deg -> orders 0.5 ... 12 (M53 2.2.2, 4-stroke)
TARGET = 1.5
R_B = 2.5                        # option (b) main fillet radius


def beta_T(r, s, w, b):
    f_rs = r ** (-0.322 + 0.1015 * (1 - s))
    f_b = 7.8955 - 10.654 * b + 5.3482 * b ** 2 - 0.857 * b ** 3
    f_w = w ** (-0.145)
    return 0.8 * f_rs * f_b * f_w, dict(f_rs=f_rs, f_b=f_b, f_w=f_w)


def section_torques(res, J_cad, damping_ratio=0.02, c_damper=14.0):
    """Harmonic synthesis of the section torques (as dynamics.torsional_forced, with phases kept): returns the alternating
    torque M_TN = (max - min) / 2 per section, the order-2.5 amplitude per section and the mean torque per section."""
    f, modes, K, J, k, info = D.torsional_modes(J_cad)
    om = res["rpm"] * math.pi / 30
    Tk = np.zeros((len(J), D.N_AL))
    for c in L.CYLS:
        Tk[c.pin] += res["cf"][c.no]["torque"]
    X = np.fft.rfft(Tk, axis=1) / D.N_AL * 2
    n = np.arange(D.N_AL)
    sig = np.zeros((len(k), D.N_AL))
    a25 = np.zeros(len(k))
    for h in ORDERS_H:
        w = 0.5 * h * om
        Z = (K * (1 + 2j * damping_ratio) - w ** 2 * np.diag(J)).astype(complex)
        Z[0, 0] += 1j * w * c_damper
        th = np.linalg.solve(Z, X[:, h])
        A = np.diff(th) * k                                         # complex section-torque amplitude, order h/2
        sig += np.real(A[:, None] * np.exp(2j * math.pi * h * n / D.N_AL)[None, :])
        if h == 5:
            a25 = np.abs(A)
    mtn = 0.5 * (sig.max(1) - sig.min(1))
    mean = np.cumsum(Tk.mean(1))[:-1]                               # section i (mass i -> i + 1) carries the throws up to i
    return mtn, a25, mean, f


def torque_scan():
    cw, _ = _cw()
    J_cad = CT.throw_inertia(cw)
    f = D.torsional_modes(J_cad)[0]
    n25 = f[1] * 60 / 2.5
    A_t = cycle.size_turbine()
    speeds = sorted({round(x) for x in np.arange(n25 - 300, n25 + 301, 50) if x <= P.rpm_max} | {round(n25), round(P.rpm_rated)})
    scan, main_peak_rated = [], None
    for rpm in speeds:
        res = D.run(float(rpm), A_turb=A_t)
        if rpm == round(P.rpm_rated):
            main_peak_rated = float(res["main_peak"])
        mtn, a25, mean, _ = section_torques(res, J_cad)
        i = int(np.argmax(mtn))
        scan.append(dict(rpm=rpm, M_TN_max_Nm=float(mtn[i]), section=i, order25_amp_at_section_Nm=float(a25[i]),
                         order25_amp_max_Nm=float(a25.max()), T_mean_engine_Nm=float(res["T_mean"]), mean_at_section_Nm=float(abs(mean[i]))))
        print(f"{rpm:5d} rpm: M_TN max {mtn[i]:7.1f} N m (section {i}), order 2.5 there {a25[i]:6.1f} (max {a25.max():6.1f}), "
              f"mean torque {res['T_mean']:.0f} N m", flush=True)
    return dict(first_mode_Hz=float(f[1]), order25_resonance_rpm=n25, scan=scan, governing=max(scan, key=lambda x: x["M_TN_max_Nm"]),
                T_mean_Nm=max(x["T_mean_engine_Nm"] for x in scan), main_peak_rated_N=main_peak_rated,
                damper="EST: 22 g m2, 14 N m s/rad; structural damping ratio 0.02 (dynamics.torsional_forced)")


def evaluate(R, s_peak, tq):
    """Combined bending + torsion at a main fillet of radius R (mm) with the bending peak s_peak (MPa, von Mises)."""
    mt = MATERIALS[MAT["steel_qt"]]
    fat, uts = mt["fatigue"], mt["uts"]
    sb_a = sb_m = 0.5 * s_peak
    D_pin, D_G, W = P.pin_dia, P.main_dia, P.web_thk
    S = (D_pin + D_G) / 2 - P.throw                                 # pin overlap
    B = 2 * CT.R_PIN_WEB                                            # web width at the pin boss (narrower -> larger f(b))
    geo = dict(r=R / D_G, s=S / D_pin, w=W / D_pin, b=B / D_pin)
    bt_ext, f_ext = beta_T(**geo)
    clamp = dict(r=max(geo["r"], 0.03), s=min(geo["s"], 0.5), w=max(geo["w"], 0.2), b=min(max(geo["b"], 1.1), 2.2))
    bt_clamp, f_clamp = beta_T(**clamp)
    bT = max(bt_ext, bt_clamp)
    W_P = math.pi * D_G ** 3 / 16
    g = tq["governing"]
    tauN_a, tauN_m = g["M_TN_max_Nm"] * 1e3 / W_P, tq["T_mean_Nm"] * 1e3 / W_P
    tau_a, tau_m = bT * tauN_a, bT * tauN_m
    sv_a = math.sqrt(sb_a ** 2 + 3 * tau_a ** 2)
    sv_m = math.sqrt(sb_m ** 2 + 3 * tau_m ** 2)
    R_x = max(R, 2.0)
    s_dw = 1.05 * (0.42 * uts + 39.3) * (0.264 + 1.073 * D_G ** -0.2 + (785 - uts) / 4900 + 196 / uts * math.sqrt(1 / R_x))
    tau_req = math.sqrt(max((fat / TARGET) ** 2 - sb_a ** 2, 0.0) / 3)
    M_req = tau_req / bT * W_P / 1e3
    return dict(
        main_fillet_r_mm=R,
        bending=dict(peak_MPa=s_peak, alternating_MPa=sb_a, mean_MPa=sb_m, factor_bending_only=fat / sb_a),
        torsion_scf=dict(geometry=geo, beta_T_extrapolated=bt_ext, sub_extrapolated=f_ext, at_range_limits=clamp, beta_T_range_limits=bt_clamp,
                         sub_range_limits=f_clamp, beta_T_used=bT, web_width_B_mm=B, pin_overlap_S_mm=S,
                         validity="M53: 0.03 <= r <= 0.13, 0.2 <= w <= 0.8, 1.1 <= b <= 2.2, s <= 0.5"),
        stresses=dict(W_P_mm3=W_P, tau_N_alt_MPa=tauN_a, tau_N_mean_MPa=tauN_m, tau_alt_MPa=tau_a, tau_mean_MPa=tau_m,
                      sigma_v_alt_MPa=sv_a, sigma_v_mean_MPa=sv_m),
        factors=dict(fatigue_strength_MPa=fat, uts_MPa=uts, combined_alternating=fat / sv_a, combined_goodman_with_mean=1 / (sv_a / fat + sv_m / uts),
                     bending_only=fat / sb_a, target=TARGET, meets_target_combined=bool(fat / sv_a >= TARGET),
                     m53_sigma_DW_MPa=s_dw, m53_Q=s_dw / sv_a, m53_Q_min=1.15,
                     m53_sigma_DW_note="M53.6 (p. 22), drop-forged K = 1.05, sigma_B = UTS, R_G taken as not less than 2 mm, no credit for nitriding"),
        torque_limit_for_target=dict(M_TN_max_Nm=M_req, reduction_pct=100 * (1 - M_req / g["M_TN_max_Nm"]),
                                     note="alternating torque at the most loaded section that would give the 1.5 target - information for "
                                          "the decision, not a requirement"))


def bearing(land, main_peak_N, rpm=6700.0):
    eps, h = D.short_bearing_hmin(main_peak_N, P.main_dia, land, rpm)
    return dict(land_mm=land, specific_load_MPa=main_peak_N / (P.main_dia * land), ocvirk_eps=eps, ocvirk_hmin_um=h,
                note=f"model main peak {main_peak_N / 1e3:.2f} kN at {rpm:.0f} rpm, quasi-static short bearing (as the dynamics report)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="reproduce the option comparison of D-050 (crank_main_fillet_options.json)")
    a = ap.parse_args()
    t0 = time.time()
    allc = json.load(open(CONV, encoding="utf-8"))
    if a.compare:
        compare(allc, t0)
        return
    rec = allc.get("semicircle", {})
    R = P.main_fillet_r
    if abs(rec.get("main_fillet_r_mm", -1.0) - R) > 1e-9:
        raise SystemExit(f"the convergence record 'semicircle' is for a main fillet R{rec.get('main_fillet_r_mm')}, the model has R{R}: run "
                         f"tools/crank_groove_convergence.py first")
    mf = rec.get("verdict", {}).get("main_fillet", {})
    base = dict(note=__doc__.split("\n\n")[0].replace("\n", " "), date=time.strftime("%Y-%m-%d"), main_fillet_r_mm=R,
                shell_width_mm=P.main_shell_width, chamfer_mm=P.main_shell_chamfer,
                source_scf="IACS UR M53 Rev.4 (2019), M53.3.2 / M53.3.3 (p. 19), ranges p. 18; equivalent stress M53.5.2 (p. 22); Q >= 1.15 M53.7")
    if not mf.get("converged") or "official" not in mf:
        out = dict(base, status="main-fillet peak not converged - no combined factor", converged=False, series=mf.get("series"))
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(out["status"]); print("written", OUT)
        return
    off = mf["official"]
    tq = torque_scan()
    m = evaluate(R, off["peak_MPa"], tq)
    ok = m["factors"]["meets_target_combined"]
    out = dict(base, converged=True,
               status="meets the 1.5 combined criterion" if ok else "does not meet the 1.5 combined criterion; open",
               bending=dict(official_peak_MPa=off["peak_MPa"], basis=off["basis"], alternating_MPa=m["bending"]["alternating_MPa"],
                            mean_MPa=m["bending"]["mean_MPa"], factor_bending_only=m["bending"]["factor_bending_only"]),
               torsion_scf=m["torsion_scf"], torque=tq, stresses=m["stresses"], factors=m["factors"],
               torque_limit_for_target=m["torque_limit_for_target"], minutes=(time.time() - t0) / 60)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(dict(R=R, status=out["status"], stresses=m["stresses"], factors=m["factors"]), indent=1))
    print("written", OUT)


# option (c) as evaluated for the D-050 decision (2026-11-25): its FE convergence is kept under this key
OPT_C = dict(R=1.6, shell_width=16.0, chamfer=1.0, conv_key="semicircle_r16_option_c")


def compare(allc, t0):
    """The option comparison of D-050 (decision basis): (c) on its own FE convergence, (b) scaled from it (M53 bending factor)."""
    rec_c = allc[OPT_C["conv_key"]]
    assert abs(rec_c["main_fillet_r_mm"] - OPT_C["R"]) < 1e-9
    off = rec_c["verdict"]["main_fillet"]["official"]
    tq = torque_scan()
    c = evaluate(OPT_C["R"], off["peak_MPa"], tq)
    fit_c = CT.main_fillet_fit(R=OPT_C["R"], shell_width=OPT_C["shell_width"], chamfer=OPT_C["chamfer"])
    fit_b = CT.main_fillet_fit(R=R_B, shell_width=None, chamfer=0.0)
    land_c = OPT_C["shell_width"] - 2 * OPT_C["chamfer"]
    land_b = fit_b["shell_width_max_mm"]
    fit_b = CT.main_fillet_fit(R=R_B, shell_width=land_b, chamfer=0.0)
    ratio = (R_B / OPT_C["R"]) ** (-0.5568)
    b = evaluate(R_B, off["peak_MPa"] * ratio, tq)
    mp = tq["main_peak_rated_N"]
    opt = dict(
        note=__doc__.split("\n\n")[2].replace("\n", " "), date=time.strftime("%Y-%m-%d"),
        source="IACS UR M53 Rev.4 (2019): bending factor of the journal fillet M53.3.3 (p. 19), f_B(r) = 0.1908 r^(-0.5568), r = R_G / D; "
               "torsion factor M53.3.3 / 3.2; equivalent stress M53.5.2",
        bending_scaling=dict(r_c=OPT_C["R"] / P.pin_dia, r_b=R_B / P.pin_dia, ratio_b_over_c=ratio,
                             note="r_c = 0.029 is just below M53's 0.03; r_b = 0.045 is inside the range"),
        axial_allowance_mm=fit_c["allowance_mm"],
        options={
            "c": dict(description=f"R{OPT_C['R']:.1f} on the journal, {OPT_C['shell_width']:.0f} mm shells with {OPT_C['chamfer']:.1f} x 45 deg chamfers",
                      shell_width_mm=OPT_C["shell_width"], chamfer_mm=OPT_C["chamfer"], axial_gap_nominal_mm=fit_c["axial_gap_nominal_mm"],
                      **c, bearing=bearing(land_c, mp)),
            "b": dict(description=f"R{R_B:.1f} on the journal, unchamfered shells narrowed to fit (land in 0.1 mm steps, same axial allowance)",
                      shell_width_mm=land_b, chamfer_mm=0.0, axial_gap_nominal_mm=fit_b["axial_gap_nominal_mm"], **b, bearing=bearing(land_b, mp))},
        reference_16mm=bearing(16.0, mp), minutes=(time.time() - t0) / 60)
    with open(OUT_OPT, "w", encoding="utf-8") as fh:
        json.dump(opt, fh, indent=1)
    for k in ("c", "b"):
        o = opt["options"][k]
        print(f"({k}) R{o['main_fillet_r_mm']:.1f}: bending peak {o['bending']['peak_MPa']:.0f} MPa (factor {o['factors']['bending_only']:.2f}), "
              f"beta_T {o['torsion_scf']['beta_T_used']:.2f}, sigma_v {o['stresses']['sigma_v_alt_MPa']:.0f} MPa -> combined "
              f"{o['factors']['combined_alternating']:.2f}, Goodman {o['factors']['combined_goodman_with_mean']:.2f}, M53 Q {o['factors']['m53_Q']:.2f}; "
              f"land {o['bearing']['land_mm']:.1f} mm, {o['bearing']['specific_load_MPa']:.1f} MPa, film {o['bearing']['ocvirk_hmin_um']:.2f} um", flush=True)
    r = opt["reference_16mm"]
    print(f"reference 16 mm land: {r['specific_load_MPa']:.1f} MPa, film {r['ocvirk_hmin_um']:.2f} um")
    print("written", OUT_OPT)


if __name__ == "__main__":
    main()
