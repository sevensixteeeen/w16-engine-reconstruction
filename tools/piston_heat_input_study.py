"""Piston heat-input study (2026-11-21): Woschni multiplier 1.0 / 1.5 / 2.0 at the rated point.

For each multiplier: the rated operating point is re-solved with the turbine area of the baseline (same hardware, same
torque target), the piston wall heat per cylinder is taken from the cycle model, and the piston FE is run in
thermal-only mode with that heat input (scratch copy of results.json; no committed output is touched).  Two variants:
  - "cycle wall": the cycle model's piston wall temperature (T_wall_piston = 560 K) as in the committed piston FE;
  - "consistent": T_wall_piston iterated to the FE crown mean (heat in and crown temperature consistent, < 0.5 K).
At the governing elements of the hot-fatigue evaluation (08_SIMULATIONS/fea/piston_section_fatigue.json) the metal
temperature of each case gives the hot-fatigue factor with the same lower-bound strength data, to show whether the
method can separate a hot crown from a production-range one.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\piston_heat_input_study.py

Output: 08_SIMULATIONS/analytical/piston_heat_input_study.json
"""
from __future__ import annotations
import copy
import json
import math
import os
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from w16.params import P  # noqa: E402
from w16.analysis import cycle as CY, thermal as TH  # noqa: E402
from w16.sim import fea as F  # noqa: E402

OUT = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "piston_heat_input_study.json")
HOT = os.path.join(ROOT, "08_SIMULATIONS", "fea", "piston_section_fatigue.json")
SCALES = (1.0, 1.5, 2.0)
PROD_RANGE_C = (270.0, 310.0)          # crown centre, port-injected gasoline engines (DieselNet / MAHLE, see SOURCES)
SOURCES = [
    dict(id="DN", ref="H. Jaaskelainen, 'Piston Cooling', DieselNet Technology Guide (rev. 2017.09), citing MAHLE data",
         url="https://dieselnet.com/tech/combustion_piston-cool.php",
         used="3-5 % of the fuel energy to the piston (quiescent chambers); typical crown-centre temperature 270-310 degC for "
              "port-injected gasoline engines and 200-280 degC top ring groove with cooling gallery (1990s engines); "
              "1.0 MW/m2 of power per piston area ~ 10 kW/L for bore/stroke ~ 1"),
    dict(id="SAE930217", ref="SAE 930217, 'Combustion Chamber Temperature and Instantaneous Local Heat Flux Measurements in a Spark "
                             "Ignition Engine' (1993)", url="https://www.sae.org/publications/technical-papers/content/930217/",
         used="peak surface heat flux 1.2-5.0 MW/m2 at wide-open throttle (2.2 L SI engine)"),
    dict(id="MIT", ref="MIT 2.61 Internal Combustion Engines, lecture 18 'Engine heat transfer'",
         url="https://web.mit.edu/2.61/www/Lecture%20notes/Lec.%2018%20Heat%20transf.pdf",
         used="SI engine peak heat flux of order 1-3 MW/m2"),
    dict(id="REV", ref="Review: 'Thermal modelling of modern engines: a review of empirical correlations to estimate the in-cylinder "
                       "heat transfer coefficient'",
         url="https://www.researchgate.net/publication/238186418",
         used="Woschni-type correlations need a calibration multiplier per engine / operating point"),
]


def operating(ws, twp, A_t, bt):
    CY.A["woschni_scale"], CY.A["T_wall_piston"] = ws, twp
    op = CY.operating_point(P.rpm_rated, bt, A_turb=A_t)
    return op, TH.energy_balance(op)


def fe_thermal(base, eb, tmp_dir):
    R = copy.deepcopy(base)
    R["energy"]["wall_parts"] = list(eb["wall_parts"])
    path = os.path.join(tmp_dir, "results.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(R, fh)
    F.ANA = path
    return F.case_piston(thermal_only=True)


def t_at(rec, pt):
    """Temperature (degC) of the tetrahedron containing a governing element centroid of the hot-fatigue record (P1 element
    mean = mean of its 4 vertices, as in the record); nearest element by centroid distance."""
    m, T = rec["_mesh"], rec["_T"]
    cen = m.p[:, m.t].mean(axis=1)
    e = int(np.argmin(((cen - np.reshape(pt, (3, 1))) ** 2).sum(0)))
    return float(T[m.t[:, e]].mean() - 273.15)


def main():
    with open(F.ANA, encoding="utf-8") as fh:
        base = json.load(fh)
    with open(HOT, encoding="utf-8") as fh:
        hot = json.load(fh)
    t_tab, u_tab = zip(*hot["uts_table_degC_MPa"])
    sf_rt, u_rt = hot["fatigue_strength_rt_MPa"], u_tab[0]
    sf = lambda T: sf_rt * float(np.interp(T, t_tab, u_tab)) / u_rt
    regions = {k: v for k, v in hot["fatigue"].items() if k != "whole_piston"}
    sec = min(hot["section_under_long_valve_pockets"].values(), key=lambda s: s["fatigue"]["min_factor"])["fatigue"]
    regions["section"] = sec
    A_t = base["A_turb_cm2"] * 1e-4
    bt = CY.torque_target(P.rpm_rated) * 4 * math.pi / (P.displacement_cc * 1e-6)
    a_bore = math.pi * (P.bore / 2) ** 2
    a_crown = a_bore / math.cos(math.radians(P.crown_tilt_axis))
    ws0, tw0 = CY.A["woschni_scale"], CY.A["T_wall_piston"]
    eta_c = CY.eta_comb
    tmp = tempfile.mkdtemp(prefix="w16_heat_")
    cases = []
    try:
        for ws in SCALES:
            for variant in ("cycle wall", "consistent"):
                twp = tw0
                hist = []
                for it in range(8):
                    op, eb = operating(ws, twp, A_t, bt)
                    rec = fe_thermal(base, eb, tmp)
                    th = rec["results"]["thermal"]
                    hist.append(round(th["T_crown_mean_C"], 2))
                    if variant == "cycle wall":
                        break
                    new = th["T_crown_mean_C"] + 273.15
                    if abs(new - twp) < 0.5:
                        break
                    twp = new
                q_p = eb["wall_parts"][1] * 1e3 / 16
                released = eb["q_fuel"] * eta_c(op["lam"])
                reg = {}
                for k, f in regions.items():
                    T = t_at(rec, f["at"])
                    reg[k] = dict(T_C=T, factor=sf(T) / f["sigma_a_MPa"], sigma_a_MPa=f["sigma_a_MPa"], T_record_C=f["T_C"])
                row = dict(woschni_scale=ws, variant=variant, T_wall_piston_K=twp, iterations=hist,
                           power_kw=op["power_kw"], lam=op["lam"], T3_c=op["T3_c"], T3_limit_c=CY.A["T3_limit"] - 273.15,
                           p_max_bar=op["p_max_bar"], q_fuel_kw=eb["q_fuel"], q_released_kw=released,
                           wall_kw=list(eb["wall_parts"]), q_coolant_kw=eb["q_coolant_ht"], coolant_over_brake=eb["q_coolant_ht"] / op["power_kw"],
                           piston_W=q_p, piston_W_mm2_crown=q_p / a_crown, piston_W_mm2_bore=q_p / a_bore,
                           piston_share_fuel=eb["wall_parts"][1] / eb["q_fuel"], piston_share_released=eb["wall_parts"][1] / released,
                           fe_heat_in_crown_W=rec["results"]["thermal"]["heat_in_crown_W"],
                           T_crown_mean_C=rec["results"]["thermal"]["T_crown_mean_C"], T_max_C=rec["results"]["thermal"]["T_max_C"],
                           T_top_ring_groove_C=rec["results"]["thermal"]["T_top_ring_groove_C"], hot_fatigue_regions=reg)
                cases.append(row)
                print(f"ws {ws} {variant:10s}: piston {q_p:5.0f} W ({q_p / a_crown:.3f} W/mm2 crown), {100 * row['piston_share_released']:.2f} % of released, "
                      f"crown {row['T_crown_mean_C']:.1f} / max {row['T_max_C']:.1f} / groove {row['T_top_ring_groove_C']:.1f} degC, "
                      f"T3 {row['T3_c']:.0f}, coolant/brake {row['coolant_over_brake']:.3f}, worst hot factor "
                      f"{min(r['factor'] for k, r in reg.items() if k != 'slot_end_corner'):.2f}", flush=True)
    finally:
        CY.A["woschni_scale"], CY.A["T_wall_piston"] = ws0, tw0
    # reproduction of the committed piston FE: ws 2.0, cycle wall
    base_case = next(c for c in cases if c["woschni_scale"] == 2.0 and c["variant"] == "cycle wall")
    with open(os.path.join(ROOT, "08_SIMULATIONS", "fea", "piston.json"), encoding="utf-8") as fh:
        pis = json.load(fh)
    rep = dict(T_crown_mean_C=(base_case["T_crown_mean_C"], pis["results"]["thermal"]["T_crown_mean_C"]),
               region_T_C={k: (r["T_C"], r["T_record_C"]) for k, r in base_case["hot_fatigue_regions"].items()})
    # what the lower-bound data allow at production-range crown temperatures (independent of this piston's stresses)
    prod = [dict(T_C=T, sigma_f_MPa=sf(T), sigma_a_max_for_1p5_MPa=sf(T) / 1.5, vm_gas_max_for_1p5_MPa=2 * sf(T) / 1.5) for T in PROD_RANGE_C]
    out = dict(date=time.strftime("%Y-%m-%d"), rated_rpm=P.rpm_rated, a_bore_mm2=a_bore, a_crown_mm2=a_crown,
               specific_power_kw_per_l=base_case["power_kw"] / (P.displacement_cc / 1000.0),
               power_per_piston_area_MW_m2=base_case["power_kw"] * 1e3 / 16 / (a_bore * 1e-6),
               production_crown_range_C=PROD_RANGE_C, production_range_strength=prod, reproduction=rep, cases=cases, sources=SOURCES,
               method=("rated point re-solved per Woschni multiplier with the baseline turbine area; piston heat = cycle-model piston wall heat / 16; "
                       "piston FE thermal-only with that heat (gas-side Robin condition calibrated to it at the cycle wall temperature, "
                       "oil-side coefficients unchanged); 'consistent' iterates the cycle piston wall temperature to the FE crown mean; "
                       "hot-fatigue factor = sigma_f(T) / sigma_a at the governing elements of piston_section_fatigue.json, same data and "
                       "scaling (sigma_a from the gas case, temperature-independent)"))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("written", OUT)


if __name__ == "__main__":
    main()
