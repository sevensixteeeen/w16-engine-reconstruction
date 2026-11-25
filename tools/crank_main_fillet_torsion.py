"""Main-journal fillet: combined bending + torsion, hand calculation (D-050, 2026-11-25).  Light calc, no FE.

Bending: the official main-fillet peak of the crank FE convergence (zero-size extrapolation, 08_SIMULATIONS/fea/
crank_groove_convergence.json): von Mises peak at the design gas force (135 bar), pulsating load -> alternating = mean =
half the peak (project convention).
Torsion: nominal shear in the main journal tau_N = M / W_P, W_P = pi D_G^3 / 16 (solid journal), times the torsion stress
concentration factor of the journal fillet of IACS UR M53 Rev.4 (2019) section M53.3.3 / 3.2 (p. 19):
    beta_T = 0.8 f(r,s) f(b) f(w),  f(r,s) = r^(-0.322 + 0.1015 (1 - s)),  f(b) = 7.8955 - 10.654 b + 5.3482 b^2 - 0.857 b^3,
    f(w) = w^(-0.145),  with r = R_G / D_G (journal fillet over journal diameter, crankpin and journal differ), s = S / D
    (pin overlap over crankpin diameter), w = W / D (web thickness), b = B / D (web width).
M53's validity ranges are 0.03 <= r <= 0.13, 0.2 <= w <= 0.8, 1.1 <= b <= 2.2, s <= 0.5 (p. 18); this crank has r = 0.024
and w = 0.17, outside them: the factor is evaluated both at the range limits and extrapolated, and the larger is used.
The web width B is taken at the pin boss (the narrower width, larger f(b)).
Torques: mean = the engine mean torque at full load (the section next to the flywheel carries all of it); vibratory =
harmonic synthesis over orders 0.5-12 (M53 2.2.2) of the forced response of the lumped torsional model with the CAD throw
inertia (dynamics, D-050; damper and damping EST), M_TN = (M_max - M_min) / 2 per section, at the most loaded section,
scanned in speed across the first-mode order-2.5 resonance and at rated speed; the largest is used.
Combination (M53 5.2, journal fillet, p. 22): sigma_v = sqrt(sigma_B,a^2 + 3 tau_a^2), bending and torsion peaks assumed in
phase at the same point (conservative: the bending peak of throw 3 at the design gas force with the torque of the most
loaded section).  Factor = fatigue strength / sigma_v - the project convention (alternating stresses, target 1.5); M53
asks Q >= 1.15 (p. 23).  Mean stresses are in no project factor; their effect is given as a Goodman sensitivity on the
von Mises equivalents (sigma_m from the pulsating bending and the mean torque).  M53's own fatigue-strength formula
(p. 22, no credit for nitriding, R_G taken as 2 mm) is given for comparison.  Decision of the user (D-050, 2026-11-25):
option (c) is kept and the viscous damper must hold the alternating torque at the most loaded section to the value that
gives the 1.5 target (damper_requirement).

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\crank_main_fillet_torsion.py

Output: 08_SIMULATIONS/analytical/crank_main_fillet_torsion.json
"""
from __future__ import annotations
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
CONV = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_groove_convergence.json")
ORDERS_H = range(1, 25)          # h cycles per 720 deg -> orders 0.5 ... 12 (M53 2.2.2, 4-stroke)


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


def main():
    t0 = time.time()
    mt = MATERIALS[MAT["steel_qt"]]
    conv = json.load(open(CONV, encoding="utf-8"))["semicircle"]["verdict"]["main_fillet"]
    off = conv["official"]
    s_peak = off["peak_MPa"]
    sb_a = sb_m = 0.5 * s_peak
    # torsion SCF (M53)
    D_pin, D_G, W = P.pin_dia, P.main_dia, P.web_thk
    S = (D_pin + D_G) / 2 - P.throw                                 # pin overlap
    B = 2 * CT.R_PIN_WEB                                            # web width at the pin boss (narrower -> larger f(b))
    geo = dict(r=P.main_fillet_r / D_G, s=S / D_pin, w=W / D_pin, b=B / D_pin)
    bt_ext, f_ext = beta_T(**geo)
    clamp = dict(r=max(geo["r"], 0.03), s=min(geo["s"], 0.5), w=max(geo["w"], 0.2), b=min(max(geo["b"], 1.1), 2.2))
    bt_clamp, f_clamp = beta_T(**clamp)
    bT = max(bt_ext, bt_clamp)
    W_P = math.pi * D_G ** 3 / 16                                   # mm3, solid journal
    # torques
    cw, _ = _cw()
    J_cad = CT.throw_inertia(cw)
    f = D.torsional_modes(J_cad)[0]
    n25 = f[1] * 60 / 2.5
    A_t = cycle.size_turbine()
    speeds = sorted({round(x) for x in np.arange(n25 - 300, n25 + 301, 50) if x <= P.rpm_max} | {round(n25), round(P.rpm_rated)})
    scan = []
    for rpm in speeds:
        res = D.run(float(rpm), A_turb=A_t)
        mtn, a25, mean, _ = section_torques(res, J_cad)
        i = int(np.argmax(mtn))
        scan.append(dict(rpm=rpm, M_TN_max_Nm=float(mtn[i]), section=i, order25_amp_at_section_Nm=float(a25[i]),
                         order25_amp_max_Nm=float(a25.max()), T_mean_engine_Nm=float(res["T_mean"]), mean_at_section_Nm=float(abs(mean[i]))))
        print(f"{rpm:5d} rpm: M_TN max {mtn[i]:7.1f} N m (section {i}), order 2.5 there {a25[i]:6.1f} (max {a25.max():6.1f}), "
              f"mean torque {res['T_mean']:.0f} N m", flush=True)
    g = max(scan, key=lambda x: x["M_TN_max_Nm"])
    T_m = max(x["T_mean_engine_Nm"] for x in scan)                  # full engine mean torque (flywheel-side section)
    tauN_a = g["M_TN_max_Nm"] * 1e3 / W_P
    tauN_m = T_m * 1e3 / W_P
    tau_a, tau_m = bT * tauN_a, bT * tauN_m
    sv_a = math.sqrt(sb_a ** 2 + 3 * tau_a ** 2)
    sv_m = math.sqrt(sb_m ** 2 + 3 * tau_m ** 2)
    fat, uts = mt["fatigue"], mt["uts"]
    # D-050 decision of the user (2026-11-25): keep option (c); the viscous damper must hold the alternating torque at the most
    # loaded section to the value that gives the target factor 1.5 with the same bending, SCF and combination
    TARGET = 1.5
    tau_req = math.sqrt(max((fat / TARGET) ** 2 - sb_a ** 2, 0.0) / 3)
    M_req = tau_req / bT * W_P / 1e3
    R_x = max(P.main_fillet_r, 2.0)
    sB = uts
    s_dw = 1.05 * (0.42 * sB + 39.3) * (0.264 + 1.073 * D_G ** -0.2 + (785 - sB) / 4900 + 196 / sB * math.sqrt(1 / R_x))
    out = dict(
        note=__doc__.split("\n\n")[0].replace("\n", " "), date=time.strftime("%Y-%m-%d"),
        source_scf="IACS UR M53 Rev.4 (2019), M53.3.2 / M53.3.3 (p. 19), ranges p. 18; equivalent stress M53.5.2 (p. 22); Q >= 1.15 M53.7",
        bending=dict(official_peak_MPa=s_peak, basis=off["basis"], alternating_MPa=sb_a, mean_MPa=sb_m, factor_bending_only=fat / sb_a),
        torsion_scf=dict(geometry=geo, beta_T_extrapolated=bt_ext, sub_extrapolated=f_ext, at_range_limits=clamp, beta_T_range_limits=bt_clamp,
                         sub_range_limits=f_clamp, beta_T_used=bT, web_width_B_mm=B, pin_overlap_S_mm=S,
                         validity="M53: 0.03 <= r <= 0.13, 0.2 <= w <= 0.8, 1.1 <= b <= 2.2, s <= 0.5 - r and w are outside"),
        torque=dict(first_mode_Hz=float(f[1]), order25_resonance_rpm=n25, scan=scan, governing=g, T_mean_Nm=T_m,
                    damper="EST: 22 g m2, 14 N m s/rad; structural damping ratio 0.02 (dynamics.torsional_forced)"),
        stresses=dict(W_P_mm3=W_P, tau_N_alt_MPa=tauN_a, tau_N_mean_MPa=tauN_m, tau_alt_MPa=tau_a, tau_mean_MPa=tau_m,
                      sigma_v_alt_MPa=sv_a, sigma_v_mean_MPa=sv_m),
        factors=dict(fatigue_strength_MPa=fat, uts_MPa=uts,
                     combined_alternating=fat / sv_a, combined_goodman_with_mean=1 / (sv_a / fat + sv_m / uts),
                     bending_only=fat / sb_a, target=1.5,
                     m53_sigma_DW_MPa=s_dw, m53_Q=s_dw / sv_a, m53_Q_min=1.15,
                     m53_sigma_DW_note="M53.6 (p. 22), drop-forged K = 1.05, sigma_B = UTS, R_G taken as 2 mm, no credit for nitriding"),
        damper_requirement=dict(M_TN_max_Nm=M_req, reduction_pct=100 * (1 - M_req / g["M_TN_max_Nm"]), target_factor=TARGET,
                                decision="D-050, user 2026-11-25: option (c) kept; the viscous damper must hold the alternating torque at the "
                                         "most loaded crank section (harmonic synthesis, orders 0.5-12, whole speed range) to this value"),
        minutes=(time.time() - t0) / 60)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(dict(beta_T=dict(extrapolated=bt_ext, range_limits=bt_clamp), governing=g, stresses=out["stresses"], factors=out["factors"]), indent=1))
    print("written", OUT)


if __name__ == "__main__":
    main()
