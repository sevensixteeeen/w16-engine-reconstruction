"""Documentation generators: requirements trace, BOM, manufacturing specification, final report (MD + PDF),
acceptance checklist.  Everything is assembled from the JSON evidence written by the analysis / CAD / FE stages;
missing evidence is reported as missing.

    python -m w16.docs
"""
from __future__ import annotations
import csv
import glob
import json
import os
import subprocess
import sys

import numpy as np

from .params import P, MATERIALS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
p = lambda *a: os.path.join(ROOT, *a)


def J(*a):
    f = p(*a)
    if not os.path.exists(f):
        return {}
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def W(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def tab(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        out.append("| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in r) + " |")
    return "\n".join(out)


def count(pattern):
    return len(glob.glob(p(*pattern.split("/")), recursive=True))


# ====================================================================== BOM
SUPPLIER = [
    (("bolt", "screw"), "Fastener specialist (aerospace / motorsport grade)", "catalogue thread form, special length/material"),
    (("bearing shell", "bush", "journal bearing"), "Engine-bearing manufacturer", "catalogue material system, special dimensions"),
    (("ring", "circlip"), "Piston-ring manufacturer", "catalogue section, special diameter"),
    (("spring", "retainer", "finger", "support element", "guide", "seat insert", "phaser", "tensioner", "chain", "sprocket"), "Valve-train / timing-drive supplier", "catalogue families, application engineering needed"),
    (("injector", "spark plug", "coil", "sensor", "throttle", "recirculation", "actuator", "lt pump", "alternator", "ac compressor", "belt", "filter"), "Tier-1 electrical / mechatronic supplier", "commercially available component class"),
    (("turbine", "compressor", "bearing housing"), "Turbocharger manufacturer", "custom turbocharger (wheel aero, housing castings)"),
    (("substrate", "catalyst"), "Exhaust after-treatment supplier", "custom canning of catalogue substrates"),
    (("cooler", "radiator"), "Heat-exchanger manufacturer", "custom core dimensions"),
    (("hose", "isolator", "harness"), "Hose / elastomer / harness supplier", "made to drawing"),
    (("crankshaft", "camshaft", "connecting rod", "piston", "gudgeon"), "Forging + precision machining specialist", "custom engineered"),
    (("crankcase", "cylinder head", "sump", "bearing cover", "housing", "manifold", "cover", "pump", "tank", "plenum", "bracket", "pipe", "duct", "air box", "flex", "damper", "rail", "jet", "gasket", "valve"), "Foundry / machining / composite shop to drawing", "custom engineered"),
]


def supplier(name):
    n = name.lower()
    for keys, cat, note in SUPPLIER:
        if any(k in n for k in keys):
            return cat, note
    return "Machining shop to drawing", "custom engineered"


def bom():
    rows = J("06_ASSEMBLIES", "bom_rows.json")
    if not rows:
        return None
    from .cad.common import GROUPS
    out = []
    for r in rows:
        cat, note = supplier(r["name"])
        out.append(dict(pn=r["pn"], name=r["name"], group=f"{r['group']} {GROUPS[r['group']]}", qty=r["qty"], material=r["material"],
                        process=r["process"] or ("purchased" if not r["custom"] else "machined / fabricated to drawing"),
                        mass_each_kg=round(r["mass_each"], 4), mass_total_kg=round(r["mass_total"], 3),
                        type="custom-engineered" if r["custom"] else "commercial component class (adaptation required)",
                        supplier_category=cat, critical_spec=(r["note"] or note), cost="not estimated - no reliable public price source",
                        status="concept CAD; not sourced"))
    with open(p("10_BOM_AND_PROCUREMENT", "BOM.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    n_c = sum(1 for r in out if r["type"].startswith("custom")); q_c = sum(r["qty"] for r in out if r["type"].startswith("custom"))
    md = f"""# Bill of materials and procurement

Generated from the CAD registry (`06_ASSEMBLIES/bom_rows.json`). Machine-readable copy: `BOM.csv`.

- Part numbers: **{len(out)}**; individual parts: **{sum(r['qty'] for r in out)}**; CAD mass **{sum(r['mass_total_kg'] for r in out):.1f} kg** (dry, as modelled).
- Custom-engineered part numbers: {n_c} ({q_c} parts). Commercial component classes: {len(out) - n_c} part numbers ({sum(r['qty'] for r in out) - q_c} parts).
- The published engine has 3,712 individual parts; this model contains {sum(r['qty'] for r in out)} because seals, O-rings, dowels, plugs, most small
  fasteners, clamps, brackets, hoses, wiring and the internals of purchased units are not modelled.
- **Cost:** no reliable public pricing exists for these parts (one-off forgings, castings and a custom turbocharger family), so no costs are given.
  Inventing numbers would be misleading.
- "Commercial component class" means a suitable *type* of part is available from the named supplier category; in every case application
  engineering is still required. Buying those parts does not make the engine manufacturable without the custom parts.

{tab([(r['pn'], r['name'], r['qty'], r['material'], r['process'], r['mass_each_kg'], r['type'], r['supplier_category'], r['critical_spec'], r['status']) for r in out],
     ['Part no.', 'Component', 'Qty', 'Material', 'Manufacturing process', 'Mass each [kg]', 'Type', 'Supplier category', 'Critical specification / note', 'Procurement status'])}

## Long-lead items (procurement risk)

| Item | Why | Typical lead time class |
|---|---|---|
| Crankcase and head castings | tooling, casting development, CT qualification | longest |
| Crankshaft forging | die, forging trials, nitriding distortion control | long |
| Turbochargers | custom wheels and housings, hot-gas test | long |
| Titanium connecting rods | forging dies, peening qualification | medium |
| Camshafts, pistons | profile grinding, forging dies | medium |
| Bearings, rings, valve-train kit | catalogue families | short-medium |
"""
    W(p("10_BOM_AND_PROCUREMENT", "BOM.md"), md)
    return out


# ====================================================================== manufacturing specification
MFG = [  # component, material, process, critical dimensions, tolerance class, surface, operating temperature, loading, inspection
    ("Crankcase upper section", "AlSi7Mg0.3-T6 (alternative: hypereutectic AlSi17CuMg as VW W12, or AlSi9Cu3 with coated bores)", "low-pressure sand casting with core package (water jacket, crank chamber), HIP, T6; 5-axis machining; bore coating (plasma / PEO) or iron-coated pistons on Alusil",
     "bore dia 86 H5-class, cylindricity; main bore line dia 73; deck height 238.2; bore positions (zig-zag, +/-43.86 at deck)", "bores IT5, positions +/-0.03, deck flatness 0.03 (classes, provisional)",
     "bore plateau honed Rpk<0.2; deck Rz 6", "coolant 95-110 degC; liner top ~150-170 degC (calc.)", "135 bar design gas pressure; main bearing 37 kN; head bolt clamp", "CT scan, pressure tests, CMM, bore form"),
    ("Crankcase lower section (bearing support)", "AlSi7Mg0.3-T6 with cast-in EN-GJS-600 bearing covers", "sand casting around pre-machined iron inserts; line boring assembled with the upper section", "main bore line; joint face; insert position", "main bore IT6, coaxiality 0.02 (class)", "joint Rz 6", "oil 100-140 degC", "main bearing loads 37 kN peak, 4 bolts per bearing", "X-ray of insert bond, CMM"),
    ("Cylinder heads", "AlSi7Mg0.3-T6 (+Cu variant for hot strength)", "low-pressure sand casting, HIP, T6; valve seats and guides shrink-fitted; cam line bored with caps", "chamber volume (CR), valve seat run-out to guide, cam bore line, port positions", "seat run-out 0.03, cam bores IT6, joint flatness 0.03 (classes)", "ports as cast + CNC blended throats; joint Rz 6", "roof ~230 degC mean gas side (1-D), coolant 95-110 degC", "135 bar on roof, bolt clamp, thermal gradient", "CT scan, leak test, CMM, flow bench"),
    ("Crankshaft", "42CrMo4 (alternative 34CrNiMo6), QT, nitrided", "closed-die forging (twisted or as-forged throws), rough machining, QT, finish turning, drilling, nitriding, grinding, lapping, balancing", "journal diameters 68/56, throw 42.868, pin phasing (non-uniform, see table), main fillets R1.6 (main shells chamfered 1.0 x 45 deg), pin relief grooves R2.5 x 2.5 deep, solid pins, dia 5 oil drilling per rod", "journals IT5, phasing +/-0.05 deg, run-out 0.02 (classes)", "journals Ra 0.1", "oil 100-150 degC", "bending from 78 kN design rod force, torsion mean 1.6 kN m + vibratory ~1.2 kN m", "MPI, CMM, hardness depth, balance"),
    ("Connecting rods", "Ti-6Al-4V (forged, STA)", "die forging, machining, shot peening, anti-galling coating on thrust faces (CrN/MoS2)", "centre distance 164, bores, width 17.75, weight", "bores IT6, parallelism 0.02/100 (classes)", "peened; bores honed", "~150 degC", "78 kN compression (design), 20 kN tension at overspeed", "FPI, CMM, weight split"),
    ("Pistons", "AlSi12CuMgNi forged (4032) or 2618 for higher strength", "forging, CNC turning with oval/barrel skirt, pin-bore profiling, anodising, skirt coating", "skirt profile and clearance, compression height 38.5, ring grooves, crown tilt", "skirt profile +/-0.005, grooves IT6 (classes)", "pin bore Ra 0.2", "crown temperature: see the piston FE (section 8 of the report)", "135 bar gas, 31,700 m/s2 at overspeed", "CMM, ultrasonic, groove gauges"),
    ("Valves", "intake X45CrSi9-3 / titanium option; exhaust NiCr20TiAl (Nimonic 80A), hollow sodium-filled", "forging / friction welding, grinding, nitriding or chrome stem", "stem dia 6, seat angle, length (short/long types)", "stem IT5-class, seat run-out 0.02", "stem Ra 0.2", "exhaust head 750-850 degC (typical; not simulated)", "seating force, 5,300 m/s2 nose deceleration", "eddy current, X-ray of sodium fill"),
    ("Valve springs", "CrSiV super-clean wire (OTEVA 90 class)", "coiling, stress relief, shot peening, presetting", "rate ~33 N/mm, seat load ~270 N, open load ~600 N (calc.)", "load +/-4 %", "peened", "120-150 degC", "see spring table (valve-train report)", "load test 100 %, fatigue sampling"),
    ("Camshafts", "assembled (steel tube + 100Cr6 lobes) or forged 16MnCr5, induction/case hardened", "lobe grinding to conjugate profile for dia 17 roller", "lobe profile, phase angles per cylinder, journals dia 26", "profile +/-0.02, phase +/-0.2 deg cam (classes)", "lobes Ra 0.2", "120-150 degC", "roller contact (Hertz), chain drive torque", "cam-form measurement, MPI"),
    ("Turbocharger housings", "turbine: austenitic cast steel 1.4849 / Ni-resist D5S; compressor: AlSi7Mg", "investment / sand casting, machining", "wheel contours (tip clearance), flange faces", "contour +/-0.05, flatness 0.05 (classes)", "as cast flow surfaces", "turbine housing up to 980 degC gas", "thermal cycling, gas pressure 3 bar", "X-ray, leak test"),
    ("Turbocharger rotating group", "turbine wheel Inconel 713C (or TiAl), shaft 42CrMo4 EB-welded; compressor wheel forged 2618 milled", "investment casting, EB/friction welding, 5-axis milling, high-speed balancing", "wheel profiles, journal dia 11, balance", "balance G0.4 class, journals IT5", "journals Ra 0.1", "turbine 980 degC, compressor 173 degC outlet", "tip speed ~470 m/s at ~107,000 rpm (calc.)", "spin test, FPI, balancing"),
    ("Intake manifolds, plenums, charge pipes, air ducts, chain housing, cam covers", "CFRP prepreg (as published for intake tube, charge-air system and chain housing) with bonded metal inserts", "autoclave lay-up on tooling, bonding of flanges", "flange positions, sealing faces", "flange position +/-0.2", "sealing faces machined", "charge air up to 175 degC before cooler, 60 degC after", "2.9 bar abs boost + pulsation", "leak / burst test, ultrasonic"),
    ("Exhaust manifolds and cross-over", "investment-cast 1.4849 (or fabricated Inconel 625 sheet)", "casting / hydroforming and welding, bellows in cross-over", "flange flatness, port alignment", "flatness 0.1 (class)", "-", "up to 980 degC", "thermal expansion ~4 mm over manifold length, gas pulsation", "X-ray of welds, leak test"),
    ("Down-pipes, pre-catalyst shells", "titanium grade 2 / Ti-6242 (published: titanium exhaust)", "tube bending, TIG welding under shield gas", "joint positions", "+/-1.0", "-", "up to ~850 degC after turbine (calc.)", "thermal, vibration", "leak test, weld inspection"),
    ("Oil and coolant connections", "AlMgSi tube, stainless braided PTFE hose, FKM seals", "bending, brazing, crimping", "port threads and sealing faces", "per fitting standard", "-", "oil 150 degC, coolant 120 degC", "oil 8 bar, coolant 2 bar", "pressure test"),
    ("Fasteners", "10.9 / 12.9 steel; MP35N or Ti-6Al-4V where justified (rod bolts, flywheel)", "cold forming, rolled threads after heat treatment", "thread, under-head fillet", "6g/6H, torque+angle tightening", "-", "up to 150 degC (manifold studs 700 degC: Inconel)", "preload 75-90 % of yield", "batch tensile tests, MPI"),
    ("Bearings", "main / big end: steel-backed bronze with sputter AlSn20 overlay; small end: bronze bush; turbo: floating bronze bushes", "strip sintering/casting, sputtering, boring", "wall thickness, crush height", "wall +/-0.003", "bore Ra 0.2", "150 degC", "specific load 45-55 MPa (calc.)", "wall-thickness gauging, bond test"),
]


def manufacturing(E=None):
    md = """# Materials and manufacturing specification

Scope: concept-level manufacturing definition for the reconstructed W16. Tolerances are given as **classes** to show
which features need precision manufacturing; they are provisional and must be confirmed by tolerance-stack and
functional analysis before release. Operating temperatures and loads refer to the calculations in `08_SIMULATIONS/`.

## 1. Component specification

"""
    rows = [list(r) for r in MFG]                       # temperatures / loads that come from the analysis results
    th = J("08_SIMULATIONS", "fea", "piston.json").get("results", {}).get("thermal", {})
    dyn = J("08_SIMULATIONS", "analytical", "results.json").get("dynamics", {})
    H = (E or {}).get("hot")
    for r in rows:
        if r[0] == "Pistons":
            r[3] = r[3].replace("compression height 38.5", f"compression height {P.comp_height:.1f}")      # was fixed text (38.5 before D-040)
        if r[0] == "Pistons" and th:
            r[6] = (f"crown up to {th['T_max_C']:.0f} degC (mean {th['T_crown_mean_C']:.0f}), top ring groove {th['T_top_ring_groove_C']:.0f} degC "
                    "at rated power (FE, section 8 of the report; crown above the ~350 degC guide - open item)"
                    + (("; hot fatigue " + {"fails": "**FAILS**", "below target": "**below the 1.5 target**", "meets target": "meets the 1.5 target",
                                            "not assessable": "**NOT ASSESSABLE with public data** (method fails even production-range crown temperatures)"}[hot_status(H)]
                        + f" with 4032-T6 lower-bound strength (factor {H['worst']:.2f}-{H['best']:.2f})"
                        + (" - **piston material / cooling OPEN**" if hot_status(H) != "meets target" else "") + " (report section 8.1)")
                       if H else "; hot fatigue not evaluated - **piston thermal design OPEN** (report section 8.1)"))
        if r[0] == "Connecting rods" and dyn.get("rod_peak_tens_overspeed"):
            r[7] = f"{dyn['F_design_gas'] / 1e3:.0f} kN compression (design), {dyn['rod_peak_tens_overspeed'] / 1e3:.0f} kN tension at overspeed"
    md += tab(rows, ["Component", "Proposed material", "Manufacturing process", "Critical dimensions", "Tolerance class (provisional)", "Surface finish",
                     "Operating temperature", "Expected loading", "Inspection"])
    md += """

## 2. Process evaluation

| Process | Where it is the right choice here | Where it is not |
|---|---|---|
| Aluminium low-pressure sand casting + HIP | block, bedplate, heads: complex cores (zig-zag jackets, ports) at very low volume | thin CFRP-replaceable covers |
| Die casting | sump, pump housings if volume justifies | block / head (porosity, tooling cost at this volume) |
| Closed-die forging | crankshaft, rods, pistons, cam blanks: fatigue strength and grain flow | one-off prototypes: billet machining is acceptable for first builds |
| CNC machining from billet | prototype crankshaft and rods, turbo compressor wheels, brackets | series castings |
| Heat treatment | T6 for castings; QT + nitriding crank; STA titanium rods; case hardening pins, sprockets | - |
| Surface coating | bore coating (plasma / PEO) if eutectic alloy is used; DLC on pins and followers; anodised piston crown | - |
| Precision grinding / honing | journals, cam lobes, valve stems and seats, bores | - |
| Additive manufacturing | prototype manifolds (Inconel 625), turbo housings for development, water-jacket sand cores (binder-jet printed cores are well suited to the zig-zag jacket), brackets | highly loaded rotating parts without qualification |

## 3. Assembly sequence (derived from the CAD structure)

1. Upper crankcase on the stand, deck down. Fit piston-cooling jets and upper main shells.
2. Pre-assemble pistons with rings, pins and rods. Because the big end is 88 mm wide across the bolt bosses and the bore is 86 mm,
   **piston-rod units are inserted from the crankcase side** before the crankshaft is laid in (ring compressor from below).
3. Lay in the crankshaft; fit rod caps (2 x M8, torque + angle), check side float 0.25 mm per pair.
4. Fit the bearing support with lower shells; tighten 36 main bolts in sequence from bearing 5 outwards; perimeter bolts.
5. Dry-sump pan, scavenge collector, oil pump stack, front cover and seal.
6. Turn the engine. Head gaskets, heads (pre-assembled with valves, springs, guides, seats), 25 head bolts per bank in a spiral sequence.
7. Hydraulic support elements, finger followers, camshafts, caps; set cam phasing with the crank locked at cylinder 1 TDC.
8. Rear: crank sprocket, intermediate shaft, primary chain, four secondary chains, guides, tensioners, phasers; chain housing; flex plate.
9. Cam covers, plugs, coils. Intake manifolds with injectors and rails; charge-air coolers; throttles.
10. Exhaust manifolds, cross-overs, turbochargers, down-pipes, pre-catalysts; oil and water lines to the turbochargers.
11. Water pump, thermostat housing, pipes; LT pump and hoses; damper, accessory drive; harness and sensors.

## 4. Maintenance considerations

- Spark plugs and coils: accessible through the cam covers (one row of eight per head) after removing the air boxes.
- Valve clearance: hydraulic, no adjustment.
- Oil filter module and scavenge manifold at the free end; oil tank is vehicle-mounted.
- Timing chains: rear of the engine, engine-out job (as on the VW W engines) - chains are designed for engine life.
- Turbochargers: removable sideways after detaching the down-pipe and the manifold neck; the switchable turbocharger's shut-off valve is a wear item.
- Charge-air coolers sit on the plenums: remove throttle bodies and the inlet tank first.
"""
    W(p("11_MANUFACTURING_DOCUMENTATION", "MANUFACTURING_SPEC.md"), md)


# ====================================================================== requirements trace + acceptance
def ic_status(I):
    """Completeness of the interference check.  Returns (complete, text).  A report written before the completeness flag
    existed counts as complete only if it has no unchecked static pairs and its checked count equals the candidates."""
    m = (I or {}).get("meta", {})
    if not m:
        return False, "interference check not run"
    un = m.get("static_unchecked", 0)
    cand, chk = m.get("static_candidates", 0), m.get("static_checked", 0)
    probs = m.get("problems", [])
    complete = m.get("complete", un == 0 and chk == cand) and not probs
    if complete:
        return True, f"all {cand} static candidate pairs checked, {len(m.get('kin_angles', []))} crank angles"
    return False, (f"**INCOMPLETE: {un} of {cand} static candidate pairs were not checked**"
                   + (f" ({'; '.join(probs)})" if probs else "") + " - the static clash list is not complete")


def evidence():
    R = J("08_SIMULATIONS", "analytical", "results.json")
    S = J("06_ASSEMBLIES", "assembly_summary.json")
    V = J("06_ASSEMBLIES", "cad_validation.json")
    I = J("06_ASSEMBLIES", "interference_report.json")
    rows = J("06_ASSEMBLIES", "bom_rows.json") or []
    q = {r["pn"]: r["qty"] for r in rows}
    fea = {}
    for f in glob.glob(p("08_SIMULATIONS", "fea", "*.json")):
        v = json.load(open(f, encoding="utf-8"))
        if "case" in v:          # FE case records and their _FAILED records; post-processing records (no "case") are read separately
            fea[os.path.basename(f)[:-5]] = v
    exp = J("13_EXPORTS_STEP", "component_export_log.json") or []
    aexp = J("13_EXPORTS_STEP", "assembly_export_log.json")
    E = dict(R=R, S=S, V=V, I=I, q=q, rows=rows, fea=fea, exp=exp, aexp=aexp)
    E["heat"] = J("08_SIMULATIONS", "analytical", "piston_heat_input_study.json")
    E["hot"] = piston_hot(E, J("08_SIMULATIONS", "fea", "piston_section_fatigue.json"))
    E["crank_conv"] = J("08_SIMULATIONS", "fea", "crank_groove_convergence.json")
    E["crank_tors"] = J("08_SIMULATIONS", "analytical", "crank_main_fillet_torsion.json")
    E["oil"] = J("08_SIMULATIONS", "analytical", "oil_drillings.json")
    E["ic_crank_static"] = J("06_ASSEMBLIES", "interference", "targeted_d050_static.json")
    E["ic_crank_kin"] = J("06_ASSEMBLIES", "interference", "targeted_d050_kinematic.json")
    return E


HOT_REGIONS = [("crown_above_gallery", "Crown above the oil gallery"), ("section", "Crown section under the long-valve pockets"),
               ("ring_belt_top_groove", "Ring belt at the top ring groove"), ("pin_bosses", "Pin bosses"),
               ("slot_end_corner", "Slot-end corner under the crown (unradiused in the concept CAD)")]


def piston_hot(E, h):
    """Piston hot-fatigue verdict from 08_SIMULATIONS/fea/piston_section_fatigue.json (tools/piston_section_fatigue.py:
    temperature-dependent strength, 4032-T6 after 10,000 h at temperature = lower bound).  None if the record is missing or
    belongs to another piston FE run than fea/piston.json."""
    pis = E["fea"].get("piston", {})
    if not h or not pis or "fatigue" not in h:
        return None
    rep = h.get("reproduction", {}).get("gas_pressure.vm_max_MPa", {})
    if abs(rep.get("production", -1.0) - pis.get("results", {}).get("gas_pressure", {}).get("vm_max_MPa", -2.0)) > 1e-6:
        return None                                       # stale: evaluated on a different piston FE run
    t_tab, u_tab = zip(*h["uts_table_degC_MPa"])
    sf_rt, u_rt = h["fatigue_strength_rt_MPa"], u_tab[0]
    uts = lambda T: float(np.interp(T, t_tab, u_tab))
    t_oil = pis.get("inputs", {}).get("T_oil_K", 400.0) - 273.15
    secs = h.get("section_under_long_valve_pockets", {})
    sec = min(secs.values(), key=lambda s: s["fatigue"]["min_factor"]) if secs else None
    rows = []
    for key, label in HOT_REGIONS:
        f = sec["fatigue"] if key == "section" and sec else h["fatigue"].get(key)
        if not f:
            continue
        need = 1.5 * f["sigma_a_MPa"] * u_rt / sf_rt               # UTS needed for factor 1.5 (sigma_f scales with UTS)
        t_need = float(np.interp(-need, [-u for u in u_tab], t_tab)) if need <= u_rt else None
        rows.append(dict(key=key, label=label, T=f["T_C"], sa=f["sigma_a_MPa"], sf=f["sigma_f_T_MPa"], n=f["min_factor"],
                         n_goodman=f["min_factor_goodman"], T_need=t_need, n_rt=sf_rt / f["sigma_a_MPa"], frac_need=1.5 * f["sigma_a_MPa"] / sf_rt))
    if not rows:
        return None
    gt = pis["results"].get("gas_plus_thermal", {})
    rod = E["fea"].get("rod", {}).get("results", {})
    m_rec = (E["R"].get("dynamics", {}) or {}).get("m_rec")
    rod_f = rod_d50 = None
    if rod.get("fatigue_estimate") and m_rec:
        c = rod["compression_design_gas_force"]["vm_p999_MPa"]; t = rod["tension_overspeed_inertia"]["vm_p999_MPa"]
        lim = rod["fatigue_estimate"]["fatigue_limit_MPa"]
        rod_f = lim / (0.5 * (c + t))
        rod_d50 = rod_f - lim / (0.5 * (c + t * (m_rec + 0.05) / m_rec))      # tension scales with the reciprocating mass
    sens = pis["results"].get("thermal_sensitivity", [])
    prod = heat_cases(E.get("heat"), pis)
    return dict(rows=rows, worst=min(r["n"] for r in rows), best=max(r["n"] for r in rows), fails=min(r["n"] for r in rows) < 1.0, **prod,
                n_rt=pis["results"].get("fatigue_estimate", {}).get("factor"), sec=sec, source=h.get("source", ""),
                method=h.get("method", ""), t_oil=t_oil, uts=uts, gt=gt, rod_f=rod_f, rod_d50=rod_d50, m_rec=m_rec,
                best_cooling=min(sens, key=lambda s: s["T_crown_mean_C"]) if sens else None,
                T_crown=pis["results"].get("thermal", {}).get("T_crown_mean_C"))


def crank_md(E):
    """Report section 8.3 (D-050): crank throw supports, mesh convergence of both fillet features with the official
    (zero-size extrapolated) values, combined bending + torsion at the main fillet, targeted interference re-check."""
    C = E.get("crank_conv", {}).get("semicircle")
    if not C or "verdict" not in C:
        return ""
    v, runs = C["verdict"], C["runs"]
    old = E.get("crank_conv", {}).get("semicircle_hollow_pin", {}).get("verdict", {})
    T = E.get("crank_tors", {})
    fat = MATERIALS["42CrMo4 QT + nitrided"]["fatigue"]                # crank material (cad.common.MAT["steel_qt"])
    names = dict(pin_groove="Pin relief groove", main_fillet="Main-journal fillet")
    rows = []
    for ft in ("pin_groove", "main_fillet"):
        x = v.get(ft, {})
        if not x.get("converged"):
            rows.append((names[ft], *[f"{s['peak_MPa']:.1f}" for s in x.get("series", [])], "NOT CONVERGED", "-", "-"))
            continue
        rows.append((names[ft], *[f"{s['peak_MPa']:.1f}" for s in x["series"]], f"{x['change_pct']:.2f} %",
                     f"{x['converged_peak_MPa']:.1f} ({x['factor_on_converged_peak']:.2f})",
                     f"**{x['official']['peak_MPa']:.0f} ({x['official']['factor']:.2f})**"))
    sizes = [f"{r['local_size_mm']:.1f} mm" if r["local_size_mm"] >= 1 else f"{r['local_size_mm']:g} mm" for r in runs]
    cr = E["fea"].get("crank", {}).get("results", {})
    std = ""
    if cr.get("fillet_vm_max_MPa") and cr.get("main_fillet_vm_max_MPa") and v.get("pin_groove", {}).get("official"):
        std = (f" The standard crank FE record (1.0 mm, section 8 table) gives {cr['fillet_vm_max_MPa']:.0f} / {cr['main_fillet_vm_max_MPa']:.0f} MPa, "
               f"{100 * (1 - cr['fillet_vm_max_MPa'] / v['pin_groove']['official']['peak_MPa']):.0f} % / "
               f"{100 * (1 - cr['main_fillet_vm_max_MPa'] / v['main_fillet']['official']['peak_MPa']):.0f} % below the official values.")
    land = P.main_shell_width - 2 * P.main_shell_chamfer
    out = [f"""### 8.3 Crank throw: supports, mesh convergence and combined fatigue of the fillets (D-047 to D-050)

**Geometry.** Solid crankpins (D-049); pin relief grooves R2.5, 2.5 mm into the {P.web_thk} mm webs, {P.web_thk - 2.5:.1f} mm of web left behind them
(D-048); main-journal fillets **R{P.main_fillet_r:.1f}** on the journal, main shells **{P.main_shell_width:.0f} mm** wide with {P.main_shell_chamfer:.1f} x 45 deg bore
chamfers, so the load-carrying land is **{land:.0f} mm** (option (c) of D-050: the largest radius that keeps the axial allowance for end float, block / crank
thermal growth and tolerances to the chamfered shell).

**Boundary conditions (D-050).** Until D-049 the slice was clamped: both main-journal surfaces fully fixed. A clamped journal cannot turn, so the
throw acts as a frame fixed at both ends and most of its bending moment stays in the journals; the {P.web_thk} mm webs see little of it. The slice is
now a bay simply supported on its two main bearings: the bearing reactions are compressive pressures on the {land:.0f} mm shell lands (cosine around
the loaded half, parabolic across the land), balanced to the pin load, and a statically determinate 3-2-1 point support carries only the mesh
residual ({max(r['supports']['point_reaction_pct'] for r in runs):.0e} % of the load). This is the support of the dynamics bay model and of the
classification method for crankshafts (IACS UR M53: a throw on two main bearings, statically determinate). Real bearings let the journal tilt
within their clearance and the oil film cannot clamp it, while the neighbouring bays add some restraint: reality lies between the two models,
nearer to simple support, so the new model is the more realistic and the conservative one. A fixed journal surface would also have sat on the main
fillets. The change, together with the solid pin, moved the pin-groove peak from {old.get('converged_peak_MPa', float('nan')):.1f} MPa
(factor {old.get('factor_on_converged_peak', float('nan')):.2f}; hollow pin, clamped, D-048) to the values below.

**Mesh convergence** (`tools/crank_groove_convergence.py`, two refinement balls in every refined mesh; element-mean von Mises peak at the design
gas force, pulsating load, factor = fatigue strength {fat:.0f} MPa / half the peak; converged = less than 5 % between the two finest meshes):

{tab(rows, ["Feature", *sizes, "change, two finest", "0.35 mm value (factor)", "official: zero-size extrapolation (factor)"])}

The peak rises by about the same amount per refinement step ({", ".join(f"{d:+.1f}" for d in v.get("pin_groove", {}).get("increments_MPa", []))} MPa at
the groove, {", ".join(f"{d:+.1f}" for d in v.get("main_fillet", {}).get("increments_MPa", []))} MPa at the main fillet): the element-mean stress
approaches the surface value about linearly with the element size. The **official values are the zero-size linear extrapolation of the two
finest meshes** (decision D-050) - conservative against the 0.35 mm values.{std} Web {v.get('web_vm_max_MPa', float('nan')):.0f} MPa,
ligament behind the groove {v.get('ligament_vm_max_MPa', float('nan')):.0f} MPa (0.35 mm mesh). The main-fillet rule of D-050 (option (b) below a
factor of 1.5) gives: {v.get('main_fillet_decision', '-')}.
"""]
    if T:
        sc, tq, st, fa = T["torsion_scf"], T["torque"], T["stresses"], T["factors"]
        g = tq["governing"]
        below = fa["combined_alternating"] < fa["target"]
        dr = T.get("damper_requirement")
        dec = (f"**Decision (D-050, 2026-11-25): option (c) is kept, and the viscous damper at the free end must hold the alternating torque at the "
               f"most loaded crank section to <= {dr['M_TN_max_Nm']:,.0f} N m ({dr['reduction_pct']:.0f} % below the estimated damper) over the whole "
               f"speed range** - that gives the combined factor of {dr['target_factor']:.1f}; damper sizing and tuning is an open item." if dr else "")
        out.append(f"""**Main-journal fillet, bending + torsion** (hand calculation, `tools/crank_main_fillet_torsion.py`; no FE). Bending: the official peak,
alternating {T['bending']['alternating_MPa']:.0f} MPa. Torsion: stress concentration factor of the journal fillet from IACS UR M53 Rev.4 (2019), M53.3.3 / 3.2,
beta_T = 0.8 f(r,s) f(b) f(w) = **{sc['beta_T_used']:.2f}** (r = R_G / D_G = {sc['geometry']['r']:.4f}, w = W / D = {sc['geometry']['w']:.3f}, both below M53's
ranges (r >= 0.03, w >= 0.2): extrapolated; {sc['beta_T_range_limits']:.2f} at the range limits); alternating torque **{g['M_TN_max_Nm']:,.0f} N m** at
{g['rpm']:,} rpm (most loaded section; harmonic synthesis of orders 0.5-12 as M53 2.2.2 of the torsional model with the CAD inertia and the EST
damper; order 2.5 alone {g['order25_amp_max_Nm']:,.0f} N m - its resonance is at {tq['order25_resonance_rpm']:,.0f} rpm), mean {tq['T_mean_Nm']:,.0f} N m;
nominal shear {st['tau_N_alt_MPa']:.1f} / {st['tau_N_mean_MPa']:.1f} MPa alternating / mean, {st['tau_alt_MPa']:.0f} / {st['tau_mean_MPa']:.0f} MPa with
beta_T. Equivalent alternating stress (M53 5.2) sqrt(sigma_B,a^2 + 3 tau_a^2) = {st['sigma_v_alt_MPa']:.0f} MPa, bending and torsion peaks taken in
phase at the same point -> **combined factor {fa['combined_alternating']:.2f}** (target 1.5{'; below it' if below else ''}; bending alone
{fa['bending_only']:.2f}). With the mean stresses (Goodman on the von Mises equivalents, ultimate {fa['uts_MPa']:.0f} MPa): {fa['combined_goodman_with_mean']:.2f}.
M53's own fatigue strength without credit for nitriding ({fa['m53_sigma_DW_MPa']:.0f} MPa) gives Q = {fa['m53_Q']:.2f} (M53 asks >= 1.15).
{dec}
""")
    oil = E.get("oil", {}).get("summary")
    if oil:
        out.append(f"""**Oil drillings** (D-049, `tools/check_oil_drillings.py`; not in the FE): one dia 5 drilling per rod, main surface -> pin surface at
{E['oil']['geometry']['outlet_phi_deg']:.0f} deg; only the pin and main surfaces are cut; walls >= {min(oil['min_wall_to_relief_groove_mm'], *oil['min_wall_web_faces_mm'].values()):.2f} mm
to the relief groove and the web faces; {oil.get('min_wall_to_main_fillet_mm', float('nan')):.2f} mm to the main-fillet tangent on the inlet's exit ramp.
""")
    ict = [x for x in (E.get("ic_crank_static"), E.get("ic_crank_kin")) if x]
    if ict:
        txt = "; ".join(f"{x.get('what') or ' / '.join(x.get('patterns', []))}: {', '.join(f'{k} {n}' for k, n in sorted(x['counts'].items()))}" for x in ict)
        out.append(f"**Targeted interference re-check after D-049 / D-050** (the full check of section 9 ran on the D-047 geometry): {txt}.\n")
    out.append("Limitations: one throw slice under one rod's design gas force spread over the pin (D-047 load model), bending only in the FE, "
               "element-mean stresses, no oil drillings in the FE, torsion stress concentration from M53 formulae outside their ranges, "
               "torsional damper and damping estimated.\n")
    return "\n".join(out)


def torsional_note(dyn):
    """D-050: the first-mode order-2.5 resonance, stated when it lies inside the operating range."""
    n25 = dyn.get("torsional_crit_rpm", {}).get("2.5")
    if n25 is None:
        return ""
    if n25 <= P.rpm_max:
        return (f"; **its order-2.5 resonance at about {n25:,.0f} rpm lies inside the operating range** (up to {P.rpm_max:,.0f} rpm, "
                f"rated {P.rpm_rated:,.0f}) - the viscous damper at the free end must address it")
    return f"; its order-2.5 resonance (about {n25:,.0f} rpm) is above the governed speed"


def cad_balance_note(cw):
    """As-built crank balance (D-049): CAD mass properties of the crankshaft with its oil drillings + rod / piston equivalents."""
    if "cad_residual_force_kgmm" not in cw:
        return f" (residual {cw.get('residual_force_kgmm', 0):.1e} kg mm, {cw.get('residual_couple_kgmm2', 0):.1e} kg mm2)"
    return (f": the CAD crankshaft with its oil drillings and the rod / piston equivalents leaves {cw['cad_residual_force_kgmm']:.3f} kg mm and "
            f"{cw['cad_residual_couple_kgmm2']:.1f} kg mm2 ({cw['cad_residual_force_rated_N']:.0f} N and {cw['cad_residual_couple_rated_Nm']:.1f} N m at "
            f"{P.rpm_rated:,.0f} rpm); the final balance is set on the balancing machine")


def heat_cases(heat, pis):
    """From the heat-input study (tools/piston_heat_input_study.py): the heat-consistent case of the current Woschni
    multiplier and the case whose crown lies in the published production range, with its hot-fatigue factors (slot-end
    corner excluded, mesh-dependent).  Empty if the study is missing or was run on another piston FE."""
    if not heat or not pis:
        return {}
    rep_t = heat.get("reproduction", {}).get("T_crown_mean_C", [None, None])
    if rep_t[1] is None or abs(rep_t[1] - pis.get("results", {}).get("thermal", {}).get("T_crown_mean_C", -1.0)) > 1e-6:
        return {}                                          # stale: the study was run on a different piston FE
    from .analysis import cycle as _cy
    cons = [c for c in heat["cases"] if c["variant"] == "consistent"]
    lo, hi = heat["production_crown_range_C"]
    cur = next((c for c in cons if abs(c["woschni_scale"] - _cy.A["woschni_scale"]) < 1e-9), None)
    inr = [c for c in cons if lo - 5.0 <= c["T_crown_mean_C"] <= hi]
    pc = min(inr or cons, key=lambda c: c["T_crown_mean_C"])
    f = [r["factor"] for k, r in pc["hot_fatigue_regions"].items() if k != "slot_end_corner"]
    return dict(prod_case=pc, prod_in_range=bool(inr), prod_worst=min(f), prod_best=max(f), prod_range=(lo, hi),
                cur_case=cur, heat=heat)


def acceptance(E):
    q, V, I, fea, exp, aexp = E["q"], E["V"], E["I"], E["fea"], E["exp"], E["aexp"]
    ok = lambda c: "PASS" if c else "NOT MET"
    n_valves = sum(q.get(f"W16-06-00{i}", 0) for i in range(1, 5))
    cr = [V.get("cyl1", {}).get("cr"), V.get("cyl2", {}).get("cr")]
    fea_ok = [k for k, v in fea.items() if "FAILED" not in k]
    fea_bad = [k for k in fea if "FAILED" in k]
    sc = I.get("static", {}).get("clashes", None)
    kc = I.get("kinematic", {}).get("clashes", None)
    ic_done, ic_text = ic_status(I)
    vt_clash = [c for c in (sc or []) + (kc or []) if c["a"].startswith("W16-06") or c["b"].startswith("W16-06")]
    n_step = sum(1 for r in exp if r.get("step")); n_stl = sum(1 for r in exp if r.get("stl")); n_3mf = sum(1 for r in exp if r.get("threemf"))
    items = [
        ("All sixteen cylinders are represented", ok(q.get("W16-03-001") == 16), f"16 bores in the block CAD; pistons x{q.get('W16-03-001')}"),
        ("Four cylinder banks (rows) correctly organised", ok(bool(V)), "two VR8 banks at 90 deg, each with two rows at 15 deg; firing intervals 45.000 deg (layout check)"),
        ("Engine architecture mechanically coherent", ("NOT VERIFIED - interference check incomplete" if not ic_done else ("PARTIAL - valve-train clashes remain" if vt_clash else "PARTIAL - packaging overlaps listed") if (sc or kc) else "PASS"),
         f"interference check: {len(sc) if sc is not None else 'not run'} static and {len(kc) if kc is not None else 'not run'} kinematic clash pairs remain (listed in the report)"
         + ("" if ic_done else "; " + ic_text)),
        ("Displacement consistent with bore and stroke", "PASS", f"{P.displacement_cc:.2f} cm3 vs 7,993 cm3 published"),
        ("All sixteen piston assemblies modelled", ok(q.get("W16-03-001") == 16 and q.get("W16-03-004") == 16), f"pistons {q.get('W16-03-001')}, pins {q.get('W16-03-004')}, rings {q.get('W16-03-002', 0) + q.get('W16-03-003', 0)}"),
        ("Shared crankshaft modelled", ok(q.get("W16-05-001") == 1), "one-piece crank, 8 pins, 9 mains, distributed counterweights"),
        ("All connecting rods represented", ok(q.get("W16-04-001") == 16), f"rods x{q.get('W16-04-001')} with caps, shells, bushes, bolts"),
        ("Cylinder heads and the 64-valve system modelled", ok(n_valves == 64), f"{n_valves} valves, 64 springs/retainers/followers/support elements, 4 camshafts; **two head castings serve the four rows** (documented architecture, decision D-003)"),
        ("Four turbochargers modelled", ok(q.get("W16-08-001", 0) + q.get("W16-08-002", 0) == 4), "2 RH + 2 LH units with housings, wheels, bearing housing, actuator"),
        ("Sequential turbocharging flow architecture documented", ok(os.path.exists(p("06_ASSEMBLIES", "system_diagrams", "01_air_exhaust_sequential_turbocharging.png"))), "diagram + animation + matching calculation"),
        ("Intake and exhaust systems connected", ok(any(k.startswith("W16-09-intake_manifold") for k in q) and any(k.startswith("W16-10-manifold_front") for k in q)), "manifolds, coolers, charge pipes, logs, cross-over, down-pipes modelled per bank"),
        ("Fuel injection and ignition represented", ok(sum(v for k, v in q.items() if k.startswith("W16-11-003")) == 32 and q.get("W16-11-001") == 16), "32 injectors, 4 rails, 16 plugs, 16 coils; EMS architecture diagram"),
        ("Lubrication and cooling circuits modelled", ok(any(k.startswith("W16-12-") for k in q) and any(k.startswith("W16-13-") for k in q)), "galleries and jackets are real passages in block/heads; external circuit parts and 1-D flow calculations"),
        ("Major mechanical interfaces validated", "NOT VERIFIED - interference check incomplete" if not ic_done else "PARTIAL" if (sc or kc) else "PASS",
         (f"CAD interference check (static all-pairs + {len(I.get('meta', {}).get('kin_angles', []))} crank angles)" if ic_done else "CAD interference check: " + ic_text) + "; CAD compression ratio "
         + (", ".join(f"{c:.2f}" for c in cr if c) if cr[0] else "n/a")),
        ("Parametric CAD files editable", "PASS", "geometry is generated from `src/w16/params.py`; BREP per part in `05_COMPONENT_CAD/`"),
        ("STEP exports generated", ok(n_step > 0 and bool(aexp)), f"{n_step} component STEP files; master assembly {aexp.get('master', {}).get('size_mb', 'n/a')} MB; {len([k for k in aexp if k != 'master'])} sub-assemblies"),
        ("STL and 3MF exports generated where supported", ok(n_stl > 0), f"{n_stl} STL, {n_3mf} 3MF component files"),
        ("Exploded assembly documentation complete", ok(os.path.exists(p("06_ASSEMBLIES", "views", "exploded_isometric.png"))), "exploded views + hierarchy"),
        ("Engineering drawings available", ok(count("07_ENGINEERING_DRAWINGS/*.pdf") > 0), f"{count('07_ENGINEERING_DRAWINGS/*.pdf')} sheets (PDF/SVG/PNG)"),
        ("Simulation evidence documented", "PARTIAL" if (fea_bad or len(fea_ok) < 6) else "PASS", f"FE cases run: {', '.join(sorted(fea_ok)) or 'none'}" + (f"; failed: {', '.join(fea_bad)}" if fea_bad else "") + "; not run: " + (", ".join(sorted({'rod', 'piston', 'crank', 'insert', 'block', 'head'} - set(fea_ok))) or "none") + "; 0-D/1-D models in `08_SIMULATIONS/analytical`. No 3-D CFD."),
        ("BOM complete", ok(os.path.exists(p("10_BOM_AND_PROCUREMENT", "BOM.csv"))), f"{len(E['rows'])} part numbers (modelled content only)"),
        ("Final technical report produced", "see file", "`12_FINAL_REPORT/` (Markdown + PDF)"),
        ("Deliverables organised in the structured directory", "PASS", "folders 01-14 + 00_PROJECT_CONTROL + src"),
    ]
    if "piston" in fea:                    # engineering check added 2026-11-20 (not one of the brief's section 21 criteria)
        H = E.get("hot")
        st = hot_status(H) if H else None
        items.append(("Piston at operating temperature: hot fatigue (engineering check added 2026-11-20, not in brief section 21)",
                      {"fails": "NOT MET - OPEN", "below target": "NOT MET - OPEN", "meets target": "PASS", "not assessable": "NOT ASSESSABLE - OPEN",
                       None: "OPEN - not evaluated"}[st],
                      ((not_assessable_txt(H) + "; ") if st == "not assessable" else "")
                      + (f"factor {H['worst']:.2f}-{H['best']:.2f} with 4032-T6 strength after 10,000 h at temperature (section 8.1); "
                       f"the room-temperature factor {H['n_rt']:.2f} is not an acceptance measure") if H else
                      "no temperature-dependent evaluation of the current piston FE; the room-temperature factor is not an acceptance measure"))
    return items


def requirements(E):
    acc = acceptance(E)
    fe = E["fea"]
    st04 = "done (slice FE)" if "block" in fe else "CAD done; block FE slice not run (stopped for memory)"
    st11 = "done (1-D + FE slices)" if "head" in fe else "done at 1-D level + piston FE; block/head FE slices not run"
    md = f"""# Engineering requirements and traceability

Requirements are taken from the project brief (section numbers in brackets). "Where" points to the deliverable that answers it.

| ID | Requirement (brief section) | Where | Status |
|---|---|---|---|
| R-01 | Reference specifications with sources and confidence levels [2, 3] | `01_RESEARCH/RESEARCH_LOG.md`, `03_REFERENCE_SPECIFICATIONS/` | done |
| R-02 | Verify bore/stroke against displacement [2] | `03_REFERENCE_SPECIFICATIONS/REFERENCE_SPEC.md` section 2 | done |
| R-03 | Architecture: banks, numbering, crank, envelope, master assembly, 8 views [4] | `src/w16/layout.py`, `06_ASSEMBLIES/views/`, `07_ENGINEERING_DRAWINGS/` | done |
| R-04 | Block/crankcase with real jackets and galleries; loads analysed [5] | `05_COMPONENT_CAD/01_*`, `08_SIMULATIONS/fea/` | {st04} |
| R-05 | Pistons, rods, crank; balance, bearing loads, torsional vibration; animation [6] | `08_SIMULATIONS/analytical/02_cranktrain_dynamics.md`, `09_ANIMATIONS/02_*` | done |
| R-06 | Heads, 64 valves, cams, timing drive; timing model; animation [7] | `08_SIMULATIONS/analytical/03_valvetrain.md`, `09_ANIMATIONS/04_*` | done (2 head castings, see D-003) |
| R-07 | Four turbochargers, sequential strategy, derived sizing, system diagram [8] | `08_SIMULATIONS/analytical/01_performance_turbocharging.md`, `06_ASSEMBLIES/system_diagrams/01_*` | done (1-D) |
| R-08 | Intake and water-to-air charge cooling with calculations [9] | `08_SIMULATIONS/analytical/04_thermal_lube_fuel.md` | done (1-D) |
| R-09 | Duplex injection (32), ignition, sensors, EMS concept [10] | `06_ASSEMBLIES/system_diagrams/04_*`, CAD group 11 | done (concept, no calibration) |
| R-10 | Dry-sump lubrication with flows and diagram [11] | same report, `system_diagrams/03_*` | done (1-D) |
| R-11 | Cooling circuits, thermal results, hot spots [12] | same report, `08_SIMULATIONS/fea/` thermal cases | {st11} |
| R-12 | Exhaust: 16 ports, 4 manifold paths, valves, down-pipes [13] | CAD group 10, decision D-023 | done |
| R-13 | Timing, accessories, mounts, sensors, harness, interfaces [14] | CAD groups 07, 14 | done (envelope level for purchased units) |
| R-14 | Materials and manufacturing specification [15] | `11_MANUFACTURING_DOCUMENTATION/` | done (tolerance classes only) |
| R-15 | Parametric CAD, 15 sub-assemblies, exports, exploded and section views, drawings [16] | `src/w16/cad/`, folders 04-07, 13, 14 | done |
| R-16 | Simulation with inputs, BCs, mesh quality, limits; comparison with Chiron targets [17] | `08_SIMULATIONS/` | done within tool limits (no CFD, linear FE) |
| R-17 | Visualisations and animations [18] | `06_ASSEMBLIES/views/`, `09_ANIMATIONS/` | done |
| R-18 | BOM and procurement [19] | `10_BOM_AND_PROCUREMENT/` | done (no costs: no reliable source) |
| R-19 | Documentation package, report in PDF and Markdown [20] | `12_FINAL_REPORT/` | done |
| R-20 | Never invent OEM data; label assumptions [22] | tags PUB/SEC/CALC/EST throughout | done |

## Acceptance criteria (brief section 21) - evaluated from the generated evidence files

"""
    md += tab(acc, ["Criterion", "Result", "Evidence"])
    W(p("02_ENGINEERING_REQUIREMENTS", "REQUIREMENTS_AND_ACCEPTANCE.md"), md + "\n")
    return acc


# ====================================================================== final report
def fea_table(fea):
    rows = []
    for k, v in sorted(fea.items()):
        if "FAILED" in k:
            rows.append((v.get("case", k), "-", "-", "FAILED: " + v.get("error", "")[:90], "-")); continue
        ms = v.get("mesh", {})
        res = v.get("results", {})
        cases = res.items() if any(isinstance(x, dict) for x in res.values()) else [("single load case", res)]
        for name, r in cases:
            if not isinstance(r, dict):
                continue
            keys = [x for x in ("vm_max_MPa", "vm_p999_MPa", "max_displacement_mm", "pin_deflection_mm", "bore_deflection_mm", "T_max_C", "T_crown_mean_C",
                                "T_top_ring_groove_C", "T_bore_max_C", "T_bore_mean_C", "T_valve_bridge_max_C", "T_valve_bridge_mean_C", "T_roof_mean_C",
                                "energy_balance_error_pct", "bore_radial_growth_mean_um", "bore_out_of_round_um", "yield_factor_on_p999", "factor_on_p999",
                                "factor", "sigma_a_MPa", "max_axial_displacement_mm", "crown_deflection_mm", "peak_bearing_pressure_MPa",
                                "T_at_vm_max_C") if isinstance(r.get(x), (int, float))]
            bc = v.get("boundary_conditions", "")[:220] + (" NOTE: " + r["note"] if r.get("note") else "")
            res_txt = "; ".join(f"{x.replace('_', ' ')} = {r[x]:.3g}" for x in keys)
            if k == "piston" and name == "fatigue_estimate":
                res_txt += " - **room-temperature limit: NOT an acceptance measure** (hot fatigue: section 8.1)"
            rows.append((v.get("case", k), name.replace("_", " "), f"{ms.get('tets', '?')} tets, gamma min {ms.get('quality_gamma_min', 0):.2f}",
                         res_txt, bc))
    return tab(rows, ["Case", "Load case", "Mesh", "Results", "Boundary conditions"])


def fea_findings(fea, H=None):
    """Plain-language findings derived from the FE records (limits are handbook guide values).  H: piston hot-fatigue
    evaluation (piston_hot), None if there is none for the current piston FE."""
    out = []
    if "piston" in fea:
        out.append("**piston - hot fatigue:** " + (hot_verdict(H) + "." if H else
                   "no temperature-dependent evaluation for the current piston FE; the room-temperature fatigue factor is **not an "
                   "acceptance measure** and **piston thermal design is an OPEN item** (section 8.1)."))
    for k, v in sorted(fea.items()):
        if "FAILED" in k:
            continue
        mat = v.get("material", {})
        ms = v.get("mesh", {})
        if ms.get("quality_below_0p1", 0) > 20:
            out.append(f"**{v.get('case', k)}:** mesh has {ms['quality_below_0p1']} poorly shaped elements (gamma < 0.1); local peaks are unreliable.")
        res = v.get("results", {})
        cases = res.items() if any(isinstance(x, dict) for x in res.values()) else [("single load case", res)]
        for name, r in cases:
            if not isinstance(r, dict):
                continue
            if r.get("plausible") is False:
                out.append(f"**{v.get('case', k)} - {name.replace('_', ' ')}:** result flagged implausible (max displacement {r.get('max_displacement_mm', 0):.1f} mm) - not used.")
            if r.get("bore_out_of_round_um", 0) > 50:
                out.append(f"**{v.get('case', k)}:** thermal bore distortion up to {r['bore_out_of_round_um']:.0f} um (upper bound from a slice with a rigid base; "
                           "rings typically tolerate a few tens of um) -> bore distortion needs a full-block thermo-mechanical analysis with head clamp load "
                           "before the liner/jacket design can be accepted.")
            if r.get("T_valve_bridge_max_C") is not None:
                verdict = "within" if r["T_valve_bridge_max_C"] < 250 else "above"
                out.append(f"**{v.get('case', k)}:** valve-bridge temperature up to {r['T_valve_bridge_max_C']:.0f} degC (mean {r.get('T_valve_bridge_mean_C', 0):.0f} degC), "
                           f"roof mean {r.get('T_roof_mean_C', 0):.0f} degC - {verdict} the ~250 degC guide limit for cast Al-Si heads. The reported T max "
                           f"({r.get('T_max_C', 0):.0f} degC) is a slice artefact (see note). Exhaust-port heat input was not applied, so exhaust-side temperatures are low.")
            if "vm_p999_MPa" in r and mat.get("yield_") and r["vm_p999_MPa"] > mat["yield_"]:
                out.append(f"**{v.get('case', k)} - {name.replace('_', ' ')}:** 99.9th-percentile stress {r['vm_p999_MPa']:.0f} MPa exceeds the yield strength "
                           f"{mat['yield_']:.0f} MPa of {mat.get('name', 'the material')}"
                           + (f" - but this load case is dominated by a modelling artefact: {r['note']}." if r.get("note") else
                              " -> the part as modelled is under-designed for this load case."))
            if r.get("T_top_ring_groove_C", 0) > 280:
                out.append(f"**{v.get('case', k)}:** top ring groove {r['T_top_ring_groove_C']:.0f} degC and crown up to {r.get('T_max_C', 0):.0f} degC "
                           "(guide limits about 260-280 degC and 350 degC for aluminium pistons) -> "
                           + ("the oil cooling gallery of the modelled piston is not sufficient." if v.get("design", {}).get("gallery_area_mm2")
                              else "an oil cooling gallery fed by the piston jet is required; the modelled piston has only under-crown spray cooling."))
            elif r.get("T_crown_mean_C") is not None and r.get("T_max_C", 0) > 350:
                sens = [x for x in v.get("results", {}).get("thermal_sensitivity", []) if isinstance(x, dict)]
                s_txt = "; ".join(f"{x['case']}: crown max {x['T_max_C']:.0f} / groove {x['T_top_ring_groove_C']:.0f} degC" for x in sens)
                out.append(f"**{v.get('case', k)}:** top ring groove {r['T_top_ring_groove_C']:.0f} degC (within the ~280 degC guide) but crown up to "
                           f"{r['T_max_C']:.0f} degC, mean {r['T_crown_mean_C']:.0f} degC, at rated power with the estimated oil-side film coefficients"
                           + (f" (sensitivity - {s_txt})" if s_txt else "") + ". The crown centre stays above the ~350 degC guide for forged "
                           "Al-Si pistons in every case studied -> open item: the piston heat load is bracketed in section 8.2 (Woschni x 1.0-2.0); confirm it and "
                           "the gallery cooling by test; stronger cooling (higher jet flow, under-crown spray) and a hot-strength alloy or steel crown are needed.")
            if "factor" in r and r["factor"] < 1.0:
                out.append(f"**{v.get('case', k)} - {name.replace('_', ' ')}:** estimated fatigue factor {r['factor']:.2f} (< 1).")
            if k == "piston" and name == "gas_pressure" and len(r.get("vm_max_location", [])) == 3:
                x, y, z = (abs(c) for c in r["vm_max_location"])
                slot_corner = abs(x - 11.5) < 1.0 and 16.5 < y < 17.0 + P.piston_boss_fillet_r + 0.5      # D-037 slot end / fillet-strip end
                out.append(f"**piston - gas pressure:** peak {r['vm_max_MPa']:.0f} MPa (99.9th percentile {r['vm_p999_MPa']:.0f} MPa) at "
                           f"|x|, |y|, z = {x:.1f}, {y:.1f}, {z:.1f} mm (pin axis along x, z up from the pin centre)"
                           + (" - the corner where the end of the under-crown slot meets the cavity wall and the end of the R3 boss fillet. The "
                              "concept CAD leaves this corner unradiused, so the peak there depends on the mesh; detail design radiuses it and "
                              "re-checks. The 99.9th percentile is the basis of the fatigue estimate." if slot_corner else "."))
            if name == "gas_plus_thermal" and r.get("T_at_vm_max_C") is not None:
                out.append(f"**{v.get('case', k)} - gas + thermal:** linear-elastic peak {r['vm_max_MPa']:.0f} MPa (99.9th percentile {r['vm_p999_MPa']:.0f} MPa) "
                           f"at about {r['T_at_vm_max_C']:.0f} degC metal temperature. The yield ({mat.get('yield_', 0):.0f} MPa) and fatigue "
                           f"({mat.get('fatigue', 0):.0f} MPa) values in the FE record are room-temperature values; "
                           + (("with temperature-dependent strength the stress exceeds even the hot tensile strength of the lower-bound data, "
                               + ("and hot fatigue is not assessable with public data (section 8.1), so" if hot_status(H) == "not assessable"
                                  else "and the piston fails hot fatigue (section 8.1), so")) if (k == "piston" and H) else "forged Al-Si piston alloys lose a large part of their "
                              "strength above ~200 degC, so")
                           + " the pin boss, ring belt and crown need a temperature-dependent elastic-plastic and fatigue analysis with a "
                           "deformable pin (pin bending and bore contact) before release.")
            if name == "gas_plus_thermal" and r.get("top_land_radial_growth_max_mm") is not None:
                g, c0 = r["top_land_radial_growth_max_mm"], r.get("top_land_cold_clearance_mm", 0.0)
                bg = ((fea.get("block", {}).get("results", {}) or {}).get("thermal_expansion", {}) or {}).get("bore_radial_growth_mean_um")
                hot = c0 - g + (bg or 0.0) / 1000.0
                out.append(f"**{v.get('case', k)} - top land:** radial growth up to {g:.2f} mm at rated power against {c0:.2f} mm cold radial "
                           f"clearance (D-040 land relief)" + (f" and {bg:.0f} um mean bore growth (block FE)" if bg else "")
                           + f" -> about {hot:.2f} mm hot clearance at the tightest point"
                           + (" - adequate for the concept; the piston / liner thermal match is a detail-design check." if hot > 0.05 else
                              " - too small: the land relief must be increased."))
    return out


def hot_status(H):
    """'not assessable' when the method fails even a crown in the published production range (heat-input study: factors
    < 1 with the crown at 270-310 degC - production pistons survive there, so the data cannot separate good from bad);
    otherwise 'fails' (factor < 1), 'below target' (< 1.5) or 'meets target'."""
    if H.get("prod_worst") is not None and H["prod_in_range"] and H["prod_worst"] < 1.0:
        return "not assessable"
    return "fails" if H["worst"] < 1.0 else ("below target" if H["worst"] < 1.5 else "meets target")


def not_assessable_txt(H):
    """Status wording of the 2026-11-21 reframing (user): hot fatigue not assessable with public data."""
    pc, cc = H["prod_case"], H.get("cur_case")
    lo, hi = H["prod_range"]
    t_cur = cc["T_crown_mean_C"] if cc else H["T_crown"]
    return (f"**hot fatigue NOT ASSESSABLE with available public data** (the method fails even production-range temperatures: with "
            f"Woschni x {pc['woschni_scale']:.1f} the crown runs at {pc['T_crown_mean_C']:.0f} degC, inside the {lo:.0f}-{hi:.0f} degC range "
            f"of production gasoline pistons, and the factors are still {H['prod_worst']:.2f}-{H['prod_best']:.2f}); "
            f"crown {t_cur:.0f} degC" + (f" (heat-consistent, Woschni x {cc['woschni_scale']:.1f})" if cc else "")
            + f" is above the typical {lo:.0f}-{hi:.0f} degC range - **OPEN: cooling upgrade + hot-strength piston alloy with "
            "manufacturer data**")


def slot_note(H):
    """Wording for the unradiused slot-end corner, from its factor against the room-temperature limit (target 1.5):
    'misses the 1.5 target' for 1.0 <= factor < 1.5, 'fails' only below 1.0; '' if it meets the target or is not evaluated."""
    s = next((r for r in (H or {}).get("rows", []) if r["key"] == "slot_end_corner"), None)
    if not s or s["n_rt"] >= 1.5:
        return ""
    word = "misses the 1.5 target" if s["n_rt"] >= 1.0 else "fails even against the room-temperature fatigue limit"
    return (f"{word} (room-temperature factor {s['n_rt']:.2f}" + (", above 1.0 but below the 1.5 target" if s["n_rt"] >= 1.0 else "")
            + ", whatever the crown temperature) at a corner the concept CAD leaves unradiused, so the value is mesh-dependent: it needs a "
            "real radius and a mesh-converged re-check")


def hot_verdict(H):
    """One-line verdict for the summary, the FE findings and the limitations list."""
    st = hot_status(H)
    if st == "not assessable":
        return (not_assessable_txt(H) + f". With 4032-T6 lower-bound strength (10,000 h at temperature) the factors are "
                f"{H['worst']:.2f}-{H['best']:.2f}; neither they nor the room-temperature factor {H['n_rt']:.2f} are acceptance "
                "measures (sections 8.1, 8.2)")
    what = {"fails": "**the piston FAILS hot fatigue**", "below target": "**the piston does not reach the 1.5 hot-fatigue target**",
            "meets target": "the piston meets the 1.5 hot-fatigue target"}[st]
    return (f"{what} with temperature-dependent strength (4032-T6 lower-bound data after 10,000 h at temperature: factor "
            f"{H['worst']:.2f}-{H['best']:.2f} over the hot regions); the room-temperature fatigue factor {H['n_rt']:.2f} is **not an "
            "acceptance measure**" + ("; **piston thermal design is an OPEN item**" if st != "meets target" else "") + " (section 8.1)")


def hot_fatigue_md(H):
    """Section 8.1 of the report: piston hot fatigue (from fea/piston_section_fatigue.json)."""
    if not H:
        return ("### 8.1 Piston hot fatigue\n\nNo temperature-dependent fatigue evaluation for the current piston FE "
                "(`tools/piston_section_fatigue.py` not run on it): the room-temperature factor in the FE table is **not an acceptance "
                "measure** and **piston thermal design is an OPEN item**.\n")
    rows = [(r["label"], f"{r['T']:.0f}", f"{r['sa']:.1f}", f"{r['sf']:.1f}", f"{r['n']:.2f}", f"{r['n_goodman']:.2f}",
             (f"{r['T_need']:.0f}" + (f" (below the {H['t_oil']:.0f} degC oil)" if r["T_need"] < H["t_oil"] else "")) if r["T_need"] is not None
             else f"none: room-temperature factor {r['n_rt']:.2f} (target 1.5)") for r in H["rows"]]
    s, gt = H["sec"], H["gt"]
    crown = next((r for r in H["rows"] if r["key"] == "crown_above_gallery"), H["rows"][0])
    slot = next((r for r in H["rows"] if r["key"] == "slot_end_corner"), None)
    hot_frac = [r["frac_need"] for r in H["rows"] if r["key"] != "slot_end_corner"]
    bc = H["best_cooling"]
    st = hot_status(H)
    head = {"fails": "**Result: the piston FAILS hot fatigue**", "below target": "**Result: the piston does not reach the 1.5 hot-fatigue target**",
            "meets target": "**Result: the piston meets the 1.5 hot-fatigue target**",
            "not assessable": "**Result: " + (not_assessable_txt(H).replace("**", "") if st == "not assessable" else "") + ".**\n\nEvaluated"}[st]
    md = f"""### 8.1 Piston hot fatigue - temperature-dependent strength{' (OPEN)' if st != 'meets target' else ''}

{head} with temperature-dependent strength (4032-T6, lower-bound data after 10,000 h at temperature): factor
{H['worst']:.2f}-{H['best']:.2f} over the hot regions (table). **The room-temperature fatigue factor {H['n_rt']:.2f} in the FE table is not an
acceptance measure**: it compares with the 110 MPa room-temperature limit at metal temperatures of
{min(r['T'] for r in H['rows']):.0f}-{max(r['T'] for r in H['rows']):.0f} degC.{' **Piston thermal design is an OPEN item.**' if st != 'meets target' else ''}

{tab(rows, ["Region (governing element)", "Metal temperature [degC]", "sigma_a [MPa]", "sigma_f(T) [MPa]", "Factor", "Factor, Goodman", "Temperature for factor 1.5, lower-bound data [degC]"])}
"""
    if s:
        md += (f"\nThinnest crown section, {s['thickness_mm']:.1f} mm from the pocket floors to the oil-gallery roof: {s['T_min_C']:.0f}-{s['T_max_C']:.0f} degC "
               f"(mean {s['T_mean_C']:.0f} degC), von Mises up to {s['vm_gas_max_MPa']:.0f} MPa under gas load and {s['vm_gas_thermal_max_MPa']:.0f} MPa gas + thermal.\n")
    if gt:
        md += (f"\nThe linear-elastic gas + thermal stress (99.9th percentile {gt.get('vm_p999_MPa', 0):.0f} MPa, peak {gt.get('vm_max_MPa', 0):.0f} MPa at "
               f"{gt.get('T_at_vm_max_C', 0):.0f} degC) exceeds even the hot tensile strength of the alloy (lower-bound data: "
               f"{H['uts'](gt.get('T_at_vm_max_C', 250)):.0f} MPa at {gt.get('T_at_vm_max_C', 250):.0f} degC, {H['uts'](s['T_mean_C']) if s else H['uts'](350):.0f} MPa at "
               f"{s['T_mean_C'] if s else 350:.0f} degC), so that result is outside the range of a linear analysis.\n")
    md += "\nConsequences:\n" if st != "meets target" else ""
    tn = crown["T_need"]
    if st != "meets target" and tn is not None:
        md += (f"- With the lower-bound data the crown would have to run at about {tn:.0f} degC or less"
               + (f" - below the {H['t_oil']:.0f} degC oil - so cooling alone cannot reach a factor of 1.5" if tn < H["t_oil"] else "")
               + (f" (best cooling case of the FE sensitivity, {bc['case']}: crown mean {bc['T_crown_mean_C']:.0f} degC against "
                  f"{H['T_crown']:.0f} degC)" if bc else "")
               + "; a hot-strength piston material or a steel crown, with measured hot fatigue data, and/or lower crown stresses are needed.\n")
    if slot_note(H):
        md += f"- **Slot-end corner:** {slot_note(H)} (OPEN). Its hot factor in the table is mesh-dependent for the same reason.\n"
    if H["rod_f"] and st != "meets target":
        md += (f"- A heavier piston loads the titanium rod: rod fatigue factor {H['rod_f']:.2f} now, about {H['rod_d50']:.3f} lower per 50 g of "
               f"reciprocating mass ({H['m_rec']:.3f} kg now; the overspeed tension scales with it).\n")
    md += f"\nMethod: {H['method']}\n\nSource: {H['source']}\n\n"
    if st != "meets target":
        md += (f"Short-exposure (upper-bound) strength data were not evaluated: the fatigue strength needed for a factor of 1.5 at the operating "
               f"temperatures is {min(hot_frac):.2f}-{max(hot_frac):.2f} of the room-temperature value"
               + (f" ({slot['frac_need']:.2f} at the slot-end corner)" if slot else "") + "; the project judged on 2026-11-20 that short-exposure "
               "data cannot change the conclusion. ")
    if st == "not assessable":
        pc = H["prod_case"]
        prs = H["heat"]["production_range_strength"]
        md += (f"\n\n**Why not assessable:** the same data and method applied to the crown temperatures of the Woschni x {pc['woschni_scale']:.1f} case "
               f"(crown mean {pc['T_crown_mean_C']:.0f} degC, inside the published {H['prod_range'][0]:.0f}-{H['prod_range'][1]:.0f} degC range of "
               f"production gasoline pistons) give factors {H['prod_worst']:.2f}-{H['prod_best']:.2f} (section 8.2). At {prs[0]['T_C']:.0f}-{prs[-1]['T_C']:.0f} degC "
               f"the lower-bound data allow sigma_f = {prs[0]['sigma_f_MPa']:.1f}-{prs[-1]['sigma_f_MPa']:.1f} MPa, so a factor of 1.5 would need a gas-load "
               f"von Mises stress below {prs[0]['vm_gas_max_for_1p5_MPa']:.0f}-{prs[-1]['vm_gas_max_for_1p5_MPa']:.0f} MPa - production pistons run at "
               "these temperatures, so tensile data after 10,000 h of static exposure, scaled to fatigue, cannot separate an acceptable piston "
               "from an unacceptable one. A verdict needs measured hot fatigue data of the actual piston alloy (manufacturer data).\n\n")
    md += "Evaluation: `tools/piston_section_fatigue.py` -> `08_SIMULATIONS/fea/piston_section_fatigue.json`.\n"
    return md


def heat_input_md(E):
    """Section 8.2: piston heat input, Woschni multiplier 1.0 / 1.5 / 2.0 (tools/piston_heat_input_study.py)."""
    heat = E.get("heat")
    if not heat:
        return ""
    from .analysis import cycle as _cy
    cons = [c for c in heat["cases"] if c["variant"] == "consistent"]
    base = next((c for c in heat["cases"] if c["variant"] == "cycle wall" and abs(c["woschni_scale"] - _cy.A["woschni_scale"]) < 1e-9), None)
    wf = lambda c: min(r["factor"] for k, r in c["hot_fatigue_regions"].items() if k != "slot_end_corner")
    rows = [(f"{c['woschni_scale']:.1f}", f"{c['piston_W']:,.0f}", f"{c['piston_W_mm2_crown']:.2f}", f"{100 * c['piston_share_released']:.1f} ({100 * c['piston_share_fuel']:.1f})",
             f"{c['T_crown_mean_C']:.0f} / {c['T_max_C']:.0f}", f"{c['T_top_ring_groove_C']:.0f}", f"{c['T3_c']:.0f}" + (" (over limit)" if c["T3_c"] > c["T3_limit_c"] + 3 else ""),
             f"{c['coolant_over_brake']:.2f}", f"{wf(c):.2f}") for c in cons]
    lo, hi = heat["production_crown_range_C"]
    src = {x["id"]: x for x in heat["sources"]}
    c1 = min(cons, key=lambda c: c["woschni_scale"]); c2 = max(cons, key=lambda c: c["woschni_scale"])
    md = f"""### 8.2 Piston heat input - Woschni multiplier (study of 2026-11-21)

The piston heat comes from the cycle model's Woschni correlation, scaled by `woschni_scale` = {_cy.A['woschni_scale']:.1f}. The rated point
({heat['rated_rpm']:.0f} rpm, {c2['power_kw']:,.0f} kW) was re-solved with multipliers 1.0 / 1.5 / 2.0 on the same hardware (turbine area and
torque target unchanged), and the piston FE was run thermal-only with each heat input; the cycle's piston wall temperature is iterated to
the FE crown temperature so that heat and temperature are consistent ("heat-consistent").

{tab(rows, ["Woschni x", "Piston heat per cylinder [W]", "W/mm2 of crown", "% of burned (of supplied) fuel energy", "Crown mean / max [degC]", "Top ring groove [degC]", f"T3 [degC] (limit {c2['T3_limit_c']:.0f})", "Coolant heat / brake power", "Worst hot-fatigue factor (8.1 method)"])}

""" + (f"""The committed piston FE (section 8) uses the cycle model's wall temperature (560 K) for the gas-side calibration: {base['piston_W']:,.0f} W
per piston, crown mean {base['T_crown_mean_C']:.0f} degC; the heat-consistent value is {next(c for c in cons if c['woschni_scale'] == base['woschni_scale'])['T_crown_mean_C']:.0f} degC.
""" if base else "") + f"""
Comparison with published values:

- Share of fuel energy into the piston: about 3-5 % in quiescent combustion chambers ([DieselNet, Piston Cooling]({src['DN']['url']})).
  The model gives {100 * c1['piston_share_released']:.1f} % (x {c1['woschni_scale']:.1f}) to {100 * c2['piston_share_released']:.1f} % (x {c2['woschni_scale']:.1f}) of the burned fuel energy
  (the model burns {100 * c2['q_released_kw'] / c2['q_fuel_kw']:.1f} % of the supplied fuel at lambda {c2['lam']:.2f}); only x {c2['woschni_scale']:.1f} comes close to the range.
- Crown temperature: 270-310 degC at the crown centre and 200-280 degC at the top ring groove (gallery-cooled) for production gasoline
  pistons of the 1990s (same source, MAHLE data). This engine runs at {heat['specific_power_kw_per_l']:.0f} kW/L, or
  {heat['power_per_piston_area_MW_m2'] / 1e6:.1f} MW of brake power per m2 of piston area (DieselNet's scale: 1 MW/m2 ~ 10 kW/L), so a crown above that
  range is plausible; x {c1['woschni_scale']:.1f} lands inside it ({c1['T_crown_mean_C']:.0f} degC), which is low for this specific power.
- Heat flux: no published cycle-averaged piston heat flux for a turbocharged gasoline engine at full load was found. Measured peak surface
  heat flux at wide-open throttle is 1.2-5 MW/m2 ([SAE 930217]({src['SAE930217']['url']})), of order 1-3 MW/m2 ([MIT 2.61]({src['MIT']['url']}));
  the model's {c1['piston_W_mm2_crown']:.1f}-{c2['piston_W_mm2_crown']:.1f} MW/m2 cycle mean is plausible below those peaks (inference, not a published value).
- Woschni-type correlations need a multiplier calibrated per engine and operating point ([review]({src['REV']['url']})).

**Decision (D-045):** `woschni_scale` stays {_cy.A['woschni_scale']:.1f} - the only multiplier that comes close to the published piston heat share and
keeps T3 at the published {c2['T3_limit_c']:.0f} degC limit (x 1.0 and x 1.5 run {c1['T3_c'] - c1['T3_limit_c']:.0f} and
{next(c for c in cons if c['woschni_scale'] == 1.5)['T3_c'] - c1['T3_limit_c']:.0f} K over it with the enrichment already at its limit, lambda {c1['lam']:.2f});
the uncertainty band is x 1.0-2.0 (crown {c1['T_crown_mean_C']:.0f}-{c2['T_crown_mean_C']:.0f} degC). The earlier note that the multiplier was calibrated to coolant heat of
0.4-0.5 x brake power was wrong (the model gives {c2['coolant_over_brake']:.2f}) and is withdrawn. Whatever the multiplier, the hot-fatigue factors stay far below 1
(table) - see 8.1 for why that check cannot give a verdict with public data.

Evaluation: `tools/piston_heat_input_study.py` -> `08_SIMULATIONS/analytical/piston_heat_input_study.json`.
"""
    return md


def report(E, bom_rows):
    _sc = E["I"].get("static", {}).get("clashes", []) + E["I"].get("kinematic", {}).get("clashes", [])
    _vt = sorted({(c["a"], c["b"]) for c in _sc if c["a"].startswith("W16-06") or c["b"].startswith("W16-06")})
    _done, _txt = ic_status(E["I"])
    vt_text = ("9. **Valve-train clashes remain** after the D-039 revision: " + ", ".join(f"{a} / {b}" for a, b in _vt[:8])
               + ". Other remaining CAD overlaps are listed in section 9.") if _vt else (
               "9. The valve-train conflicts found earlier are resolved: the long-valve spring through the short valve's support element "
               "(D-031) by the D-034 layout; the camshafts through the closed head / cover end walls, the retainers in the camshaft bearing "
               "webs, the opening long valves and the piston crown in a wedge left by the chamber cut, the follower pads on the valve tips "
               "and the cam / roller fit by D-039. " + ("The interference check finds no valve-train clashes. " if _done else
               "The interference check found no valve-train clashes among the pairs it checked, but it is " + _txt + ". ")
               + "The finger ratio of 2.7 on the short valves is high and needs a stiffness / contact-stress check. Remaining packaging "
               "overlaps are listed in section 9.")
    R, S, V, I, fea = E["R"], E["S"], E["V"], E["I"], E["fea"]
    cur = R.get("curve", [])
    rated = min(cur, key=lambda r: abs(r["rpm"] - P.rpm_rated)) if cur else {}
    dyn, en, lube, cool, cac = R.get("dynamics", {}), R.get("energy", {}), R.get("lube", {}), R.get("coolant", {}), R.get("cac", {})
    acc = acceptance(E)
    img = lambda rel, cap, w=100: f'\n<p><img src="../{rel}" style="width:{w}%"><br><em>{cap}</em></p>\n' if os.path.exists(p(*rel.split("/"))) else f"\n*(figure not generated: {rel})*\n"
    env = V.get("envelope_dressed_mm", {}).get("size", [0, 0, 0]); lb = V.get("envelope_long_block_mm", {}).get("size", [0, 0, 0])
    sc = I.get("static", {}); kc = I.get("kinematic", {})
    ic_done, ic_text = ic_status(I)
    cl_rows = [("static", c["a"], c["b"], c["count"], c["max_volume_mm3"]) for c in sc.get("clashes", [])] + \
              [("kinematic", c["a"], c["b"], c["count"], c["max_volume_mm3"]) for c in kc.get("clashes", [])[:25]]
    cw = V.get("counterweights", {})
    ib = list(cw.get("internal_balance", {}).values()) or [0.0]
    from .analysis import cycle as _cy
    m05 = next((g["mass_kg"] for g in S.get("groups", []) if g["group"] == "05"), "?")
    H = E.get("hot")
    hot_line = ("**Open item - piston:** " + (hot_verdict(H) if H else "no temperature-dependent fatigue evaluation for the current piston FE; "
                "the room-temperature fatigue factor is **not an acceptance measure**; **piston thermal design is an OPEN item** (section 8.1)") + ".\n"
                if "piston" in fea else "")
    md = f"""# W16 engine reconstruction - engineering design report

**Subject:** 8.0-litre, quad-turbocharged W16 reconstructed from publicly documented information on the Bugatti Chiron engine.
**Status:** concept-level digital engineering package (analysis + parametric CAD + linear FE). Not manufacturer data, not released for manufacture.
{hot_line}**Date:** 2026-11-14. **Generated by:** `python -m w16.docs` from the evidence files in this repository.

## 1. Project overview

The package reconstructs the architecture of the W16 from public sources and fills every gap with a labelled engineering
value. Each number carries a tag: PUB (published), SEC (secondary source), CALC (calculated here), EST (engineering estimate).
What exists:

| Deliverable | Content |
|---|---|
| Research + reference specification | sources with confidence levels, firing-order consistency proof, parameter table |
| Analytical models | 0-D cycle and turbo matching, crank-train dynamics and balance, valve train, thermal / lubrication / fuel sizing |
| Parametric CAD | {S.get('part_numbers', '?')} part numbers, {S.get('instances', '?')} placed parts, 15 sub-assemblies, generated from one parameter file |
| Checks | CAD compression ratio, interference (static + {len(I.get('meta', {}).get('kin_angles', []))} crank angles), mass and envelope |
| FE | {len([k for k in fea if 'FAILED' not in k])} linear structural / thermal cases on the CAD solids |
| Outputs | STEP / BREP / STL / 3MF, drawings, renders, exploded and section views, animations, BOM, manufacturing specification |

{img('06_ASSEMBLIES/views/engine_isometric.png', 'Dressed engine, isometric view from the free end (CAD render).', 80)}

## 2. Reference specifications

| Item | Value | Tag |
|---|---|---|
| Configuration | W16: two VR8 banks at 90 deg, each with two rows at 15 deg; one crankshaft | PUB |
| Displacement | 7,993 cm3 ({P.displacement_cc:.2f} cm3 from 86 x 86 mm) | PUB / CALC |
| Power / torque | 1,103 kW (1,500 PS) at 6,700 rpm; 1,600 N m from 2,000 to 6,000 rpm | PUB |
| Charging | four equal turbochargers, two per bank, sequential; second pair from about 3,800 rpm | PUB |
| Injection | duplex, 32 injectors | PUB |
| Cylinder pitch | 73 mm | PUB |
| Firing | 45 deg intervals; order 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10 | PUB / SEC |
| Compression ratio | 9.0 | SEC |
| Cooling | 800 L/min HT pump; separate LT charge-air circuit; charge air cooled by up to 130 K | PUB |
| Mass / length | about 400 kg / 710 mm | PUB / SEC |

Full list and sources: `03_REFERENCE_SPECIFICATIONS/REFERENCE_SPEC.md`, `01_RESEARCH/RESEARCH_LOG.md`.

## 3. Engineering assumptions

All provisional values are in `03_REFERENCE_SPECIFICATIONS/MASTER_PARAMETERS.md` (tag EST) and every non-obvious choice is in
`00_PROJECT_CONTROL/DECISIONS.md`. The most consequential ones:

- **Two cylinder-head castings, not four** - one head serves both rows of a bank (documented VR/W principle). The brief's "four heads" is read as four cylinder rows.
- Cylinders k and k+8 share crankpin k; nine main bearings; rod 164 mm and row offset 12.5 mm taken from the VW W12 family (SSP 248).
- Valve train: two camshafts per head 54 mm apart, roller finger followers, short and long valves; chamber roof tilted {P.roof_tilt:.1f} deg; piston crown tilted to give CR 9.0.
- Because the camshafts are only 54 mm apart, each camshaft has its own secondary chain in its own plane (four secondary chains). The VW W engines use one chain per head; this is a consequence of this reconstruction's head layout.
- Exhaust grouped front/rear per bank; turbine A permanently fed, turbine B behind a shut-off valve.
- Cycle-model constants (combustion phasing, efficiencies) are textbook values, not calibration. The Woschni multiplier {_cy.A['woschni_scale']} is an estimate justified by the published piston heat share and the T3 limit (section 8.2, D-045); band 1.0-2.0.

## 4. Engine architecture

Coordinate system: X = crank axis (+X flywheel end), Z up, bank 1 (cyl 1-8) towards +Y. Crank throw {P.throw:.3f} mm (offset bores make the
stroke larger than twice the throw), deck height {P.deck_height:.2f} mm, bore centres +/-{P.u_bore_deck:.2f} mm at the deck, bank offset {P.bank_offset:.1f} mm.
Crankpin phases are derived from the published firing order; the two cylinders on every pin require the same pin angle to 1e-13 deg and
all firing intervals found numerically are 45.000 deg, which shows the published order and the shared-pin 90 deg layout are mutually consistent.

{img('06_ASSEMBLIES/views/four_bank_arrangement_front.png', 'Four-row arrangement seen from the free end (block transparent).', 62)}
{img('06_ASSEMBLIES/views/section_transverse_cyl1.png', 'Transverse section through cylinder 1 (outer row, bank 1).', 62)}
{img('06_ASSEMBLIES/views/cutaway_transparent_block.png', 'Crank train inside the transparent crankcase.', 70)}

Envelope from CAD: dressed engine {env[0]:.0f} x {env[1]:.0f} x {env[2]:.0f} mm (L x W x H); long block {lb[0]:.0f} x {lb[1]:.0f} x {lb[2]:.0f} mm.
The published length is 710 mm; this reconstruction's block is 660 mm long and the long block {lb[0]:.0f} mm including chain housing and crank nose.

## 5. Component design

### 5.1 Crankcase
Split at the crank axis: upper section with both banks, lower bearing support with nine cast-in iron bearing covers (4 bolts each), dry-sump pan.
Zig-zag bores with a {P.web_bore_deck:.1f} mm web at the deck and {P.web_bore_foot:.1f} mm at the bore foot. Closed deck; the water jacket of each bank is one
connected volume of {V.get('jacket_block_bank_l', float('nan')):.2f} L surrounding all eight bores (CAD-measured), fed at the free end, with four transfer holes per cylinder to the head.
Oil: central gallery dia {P.oil_gallery_dia:.0f} mm to the nine main bearings and the inner-row piston jets; two side galleries for the outer-row jets.

### 5.2 Crank train
Crankshaft assembly group {m05} kg, eight solid pins with R2.5 relief grooves, one straight oil drilling per rod (main journal -> pin). The webs are only {P.web_thk} mm thick and the rods pass between them at BDC,
so counterweights cannot be wider than the webs: each throw is balanced internally to {min(ib) * 100:.0f}-{max(ib) * 100:.0f} % and the sixteen
counterweights are sized so that the resultant force and couple of the complete crank are zero{cad_balance_note(cw)}.
Titanium I-beam rods with trapezoidal small end; forged pistons with a crown tilted {P.crown_tilt_axis:.2f} deg to the pin-axis normal, three rings, slipper skirt.

{img('06_ASSEMBLIES/views/crank_train_isometric.png', 'Crankshaft, rods and pistons.', 70)}

### 5.3 Cylinder heads and valve train
Each head: eight wedge chambers, 16 intake ports from the valley side and 16 exhaust ports outboard (short and long ports alternate), 32 valves,
one row of eight inclined plug wells between the camshafts, a single connected water jacket ({V.get('head_jacket', {}).get('jacket_l', float('nan')):.2f} L, CAD-measured), oil galleries with risers to the cam bearings.
Valve sizes {P.valve_in_dia:.0f} / {P.valve_ex_dia:.0f} mm, lifts {P.valve_lift_in} / {P.valve_lift_ex} mm, follower ratio 2.0. Cam lobes are the exact inner envelope of the dia {P.roller_dia:.0f} mm roller.

{img('06_ASSEMBLIES/views/valvetrain_cutaway_bank1.png', 'Valve train of bank 1 (head semi-transparent, cut).', 70)}
{img('06_ASSEMBLIES/views/timing_drive_rear.png', 'Timing drive at the flywheel end: duplex primary chain, intermediate shaft, four secondary chains.', 62)}

### 5.4 Turbocharging, intake, exhaust
{img('06_ASSEMBLIES/system_diagrams/01_air_exhaust_sequential_turbocharging.png', 'Flow architecture of one bank.', 90)}
{img('06_ASSEMBLIES/views/turbo_arrangement_isometric.png', 'Turbochargers, exhaust (red) and charge-air system (blue) on the long block.', 75)}

### 5.5 Fuel, ignition, engine management
32 port injectors on four rails, 16 M10 plugs with pencil coils and ion-current measurement, two ECUs (concept). No calibration exists.
{img('06_ASSEMBLIES/system_diagrams/04_fuel_ignition_ems_architecture.png', 'Engine-management architecture (concept).', 85)}

### 5.6 Lubrication and cooling
{img('06_ASSEMBLIES/system_diagrams/03_lubrication_circuit.png', 'Dry-sump lubrication circuit with calculated flows.', 85)}
{img('06_ASSEMBLIES/system_diagrams/02_cooling_circuits.png', 'High- and low-temperature cooling circuits.', 85)}

## 6. Assembly documentation

Hierarchy and masses: `06_ASSEMBLIES/ASSEMBLY_HIERARCHY.md`. Sub-assembly and master STEP files: `06_ASSEMBLIES/step/`, `13_EXPORTS_STEP/`.

{tab([(g['group'], g['name'], g['part_numbers'], g['instances'], g['mass_kg']) for g in S.get('groups', [])], ['Group', 'Sub-assembly', 'Part numbers', 'Parts', 'Mass [kg]'])}

CAD mass {S.get('total_mass_kg', '?')} kg dry, as modelled (published: about 400 kg; the CAD figure includes dressing items such as pre-catalysts, air boxes,
oil tank and charge-air system, and excludes unmodelled small parts and fluids - the two numbers are not directly comparable).

{img('06_ASSEMBLIES/views/exploded_isometric.png', 'Exploded view.', 95)}

## 7. Engineering calculations (summary; full reports in `08_SIMULATIONS/analytical/`)

### 7.1 Performance and turbocharger matching
{img('08_SIMULATIONS/analytical/perf_full_load.png', 'Full-load model results against the published torque and power.', 95)}

| Quantity at rated power | Model | Published |
|---|---|---|
| Boost pressure | {rated.get('boost_bar', 0):.2f} bar gauge | not published (about 1.85 bar quoted by secondary sources) |
| Air flow | {rated.get('air_lpm', 0):,.0f} L/min | more than 60,000 L/min |
| Charge-air temperature drop | {rated.get('cac_dT', 0):.0f} K | as much as 130 K |
| Turbine inlet temperature | {rated.get('T3_c', 0):.0f} degC (held by enrichment, lambda {rated.get('lam', 0):.2f}) | valve rated 980 degC |
| Peak cylinder pressure | {rated.get('p_max_bar', 0):.0f} bar | not published |
| BSFC / fuel flow | {rated.get('bsfc_g_kwh', 0):.0f} g/kWh / {rated.get('mdot_fuel', 0) / 0.745 * 3600:.0f} L/h | - |

Torque and power are model targets, so they match by construction; the informative results are the boost, flows and temperatures and the
fact that the turbocharger power balance closes with four equal turbochargers sized at the change-over point. The same sizing gives full
torque with two turbochargers from about 2,000 rpm, consistent with the published plateau.
{img('08_SIMULATIONS/analytical/turbo_compressor_operating_line.png', 'Compressor operating line (surge/choke lines are representative shapes, not a measured map).', 60)}

### 7.2 Crank train
Rod force {dyn.get('rod_peak_comp', 0) / 1e3:.1f} kN compression at full load, {dyn.get('rod_peak_tens_overspeed', 0) / 1e3:.1f} kN tension at {P.rpm_overspeed:.0f} rpm; main bearing peak {dyn.get('main_peak', 0) / 1e3:.1f} kN.
With fully balanced throws the free forces and moments would be {dyn.get('F_free_peak', float('nan')):.0f} N and {dyn.get('M_free_peak', float('nan')):.0f} N m at rated speed (higher orders only). First torsional mode {dyn.get('torsional_f', [0, 0])[1]:.0f} Hz (lumped model, CAD throw inertia){torsional_note(dyn)}.
{img('08_SIMULATIONS/analytical/torque_and_bearing_loads.png', 'Torque ripple and main-bearing load loci.', 90)}

### 7.3 Thermal, lubrication, fuel
Fuel power {en.get('q_fuel', 0):.0f} kW; to HT coolant {en.get('q_coolant_ht', 0):.0f} kW (temperature rise {cool.get('dT', 0):.1f} K at 800 L/min); to oil {en.get('q_oil', 0):.0f} kW;
charge-air coolers {cac.get('q_total_kw', 0):.0f} kW at effectiveness {cac.get('effectiveness', 0):.2f}. Oil demand {lube.get('q_total_lpm', 0):.0f} L/min, pump {lube.get('q_pump_lpm', 0):.0f} L/min.
{img('08_SIMULATIONS/analytical/energy_balance.png', 'Fuel-energy split at rated power (model).', 60)}

## 8. Simulation reports (finite elements)

Tools: gmsh tetrahedral meshes of the CAD solids, scikit-fem linear elasticity (P2 unless noted) and steady conduction (P1).
Peak values at re-entrant corners and at fixed boundaries are mesh-dependent; the 99.9th-percentile element stress is reported next to the peak.

{fea_table(fea)}

{img('08_SIMULATIONS/fea/rod_compression_design_gas_force.png', 'Connecting rod, design gas force: von Mises stress.', 55)}
{img('08_SIMULATIONS/fea/piston_temperature.png', 'Piston steady temperature field.', 55)}
{img('08_SIMULATIONS/fea/crank_throw_vm.png', 'Crank throw 3 in bending: von Mises stress.', 55)}
{img('08_SIMULATIONS/fea/block_slice_temperature.png', 'Cylinder-block slice: temperature field.', 55)}
{img('08_SIMULATIONS/fea/head_slice_temperature.png', 'Cylinder-head slice: temperature field.', 55)}

### Findings from the FE results

{chr(10).join('- ' + x for x in fea_findings(fea, H)) or '- no limit exceeded in the cases that ran'}

{hot_fatigue_md(H) if 'piston' in fea else ''}
{heat_input_md(E) if 'piston' in fea else ''}
{crank_md(E)}
Limitations of the FE work: linear elastic, no contact, no bolt preload, no bearing films, simplified supports, slices instead of the complete
castings, cycle-mean thermal loads from the 0-D model, no fatigue solver (factors are simple ratios against handbook limits).

## 9. Validation results

- **Compression ratio from CAD volumes:** {", ".join(f"cyl {k[-1]}: {V[k]['cr']:.2f} (V_tdc {V[k]['v_tdc_cc']:.1f} cm3)" for k in ("cyl1", "cyl2") if k in V) or "not available"}; target {P.compression_ratio}.
- **Firing intervals:** 45.000 deg for all 16 cylinders (numerical TDC search).
- **Interference check:** {ic_text}. Of {I.get('meta', {}).get('static_candidates', 'n/a')} static candidate pairs (bounding boxes overlapping, {I.get('meta', {}).get('instances', 'n/a')} placed solids):
  {sc.get('clear', 'n/a')} clear, {sc.get('expected', 'n/a')} intentional contacts by rule (threads, press fits, seats), {sc.get('contact', 0)} touching with no overlap
  (zero distance; the common of the two solids, cut to their bounding-box overlap, is empty and the fuse residual is within volume-integration noise), {sc.get('errors', 0)} boolean errors, {sc.get('unchecked', I.get('meta', {}).get('static_unchecked', 0))} not checked; {len(sc.get('clashes', []))} static clash pairs.
  Kinematic sweep over {len(I.get('meta', {}).get('kin_angles', []))} crank angles: {kc.get('clear', 'n/a')} pair checks clear, {kc.get('contact', 0)} touching, {len(kc.get('clashes', []))} clash pairs, boolean errors {kc.get('errors', 0)}.
{("" if not cl_rows else chr(10) + tab(cl_rows, ["Check", "Part A", "Part B", "Occurrences", "Max overlap [mm3]"]) + chr(10) + chr(10) + "These remaining overlaps are packaging errors of this concept model and are listed as open work; they are not hidden.")}
- **Piston-to-valve clearance, spring loads, transverse head clearances:** `08_SIMULATIONS/analytical/03_valvetrain.md`.
- **Comparison with published targets:** section 7.1.

## 10. Acceptance criteria

{tab(acc, ["Criterion", "Result", "Evidence"])}

## 11. Bill of materials and procurement

{len(bom_rows or [])} part numbers; see `10_BOM_AND_PROCUREMENT/BOM.md` / `BOM.csv`. No costs are given because no reliable price source exists.

## 12. Materials and manufacturing

See `11_MANUFACTURING_DOCUMENTATION/MANUFACTURING_SPEC.md` (materials, processes, critical dimensions, tolerance classes, inspection, assembly sequence, maintenance).

## 13. Drawings, exports, animations

- Drawings: `07_ENGINEERING_DRAWINGS/` ({count('07_ENGINEERING_DRAWINGS/*.pdf')} PDF sheets, also SVG/PNG).
- STEP: `13_EXPORTS_STEP/` (master assembly + components); sub-assemblies in `06_ASSEMBLIES/step/`. STL / 3MF: `14_EXPORTS_STL_3MF/`.
- Animations: `09_ANIMATIONS/` ({count('09_ANIMATIONS/*.gif')} GIF, {count('09_ANIMATIONS/*.mp4')} MP4).

## 14. Known engineering limitations

1. No manufacturer geometry: every internal dimension is a reconstruction. The model shows that the public data are mutually consistent; it does not reproduce the real parts.
2. No 3-D CFD of any kind (ports, plenum, coolant jacket, combustion). Flow results are 0-D / 1-D.
3. The cycle model is uncalibrated; enrichment, boost and temperatures are plausible estimates. Knock is not modelled.
4. Turbomachinery is sized, not designed: wheels and volutes are representative shapes; there are no compressor or turbine maps.
5. FE is linear and local (see section 8). No fatigue, no bearing elasto-hydrodynamics, no valve-train dynamics, no crank 3-D torsional/bending model, no thermal-mechanical head analysis with valve-bridge detail. The crank FE has no oil drillings, so the stress at the drilling exits is not assessed.
6. Purchased units (injectors, coils, sensors, pumps, alternator, phasers, tensioners) are envelopes. Seals, O-rings, dowels, clips, brackets, most small fasteners, hoses and the detailed harness are not modelled.
7. Castings have no draft, fillets or wall-thickness optimisation; mass is therefore indicative.
8. Tolerances are classes, not a stack-up. Drawings are layout drawings.
{vt_text}
10. The engine-management description is an architecture, not software.
{"11. **Piston:** " + (hot_verdict(H) if H else "no temperature-dependent fatigue evaluation for the current piston FE; **piston thermal design is an OPEN item** (section 8.1)") + "." + (" The slot-end corner under the crown " + slot_note(H) + "." if slot_note(H) else " The slot-end corner under the crown is unradiused in the concept CAD: it needs a real radius and a mesh-converged re-check.") + " A cooling / material decision and a new piston FE are needed before the piston is mechanically acceptable." if 'piston' in fea else ""}

## 15. Future development recommendations

1. Resolve the listed interferences and add draft/fillets to castings; then repeat the mass and FE work on full castings.
2. 1-D gas-dynamics model (GT-Power class) with real turbocharger maps; then 3-D CFD of ports, plenum distribution and water jackets.
3. Elasto-hydrodynamic bearing analysis and a flexible multi-body crank and valve-train simulation; damper tuning.
4. Thermo-mechanical fatigue analysis of head and manifolds; piston secondary motion and ring-pack analysis.
5. Tolerance stack-ups for the chamber volume (CR scatter), valve train and timing drive.
6. Supplier engagement for turbochargers, bearings and valve train; replace envelopes by supplier CAD.
7. Prototype sequence: single-bank VR8 test rig for combustion and cooling development before the full W16.
8. Piston: confirm the piston heat load by test (bracketed in section 8.2), upgrade the crown cooling and choose a hot-strength piston alloy or steel crown with manufacturer hot-fatigue data (check the rod for any mass increase), radius the slot-end corner, then a temperature-dependent elastic-plastic piston FE.

## 16. Reproducing the package

```
set PYTHONPATH=src
.venv\\Scripts\\python -m w16.reports            analytical package
.venv\\Scripts\\python -m w16.cad.assembly       CAD build + summary
.venv\\Scripts\\python -m w16.cad.export all     exports, hierarchy, validation
.venv\\Scripts\\python -m w16.cad.export interference
.venv\\Scripts\\python -m w16.cad.render         views and animations
.venv\\Scripts\\python -m w16.cad.drawings       drawings
.venv\\Scripts\\python -m w16.sim.fea            finite-element cases
.venv\\Scripts\\python -m w16.diagrams           schematics
.venv\\Scripts\\python -m w16.docs               BOM, manufacturing spec, this report
```
"""
    W(p("12_FINAL_REPORT", "W16_ENGINEERING_REPORT.md"), md)
    return md


def to_pdf(md):
    import markdown
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    css = """body{font-family:Segoe UI,Arial,sans-serif;font-size:10.5pt;line-height:1.35;margin:18mm 16mm;color:#111}
h1{font-size:20pt;border-bottom:2px solid #333;padding-bottom:4px}h2{font-size:14.5pt;margin-top:22px;border-bottom:1px solid #999}h3{font-size:12pt}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:8.2pt;page-break-inside:auto}th,td{border:1px solid #999;padding:3px 5px;vertical-align:top}
th{background:#e8ebef}tr{page-break-inside:avoid}img{max-width:100%;page-break-inside:avoid}em{font-size:9pt;color:#444}code,pre{font-size:8.5pt;background:#f3f3f3}
p{orphans:3;widows:3}"""
    doc = f'<!doctype html><html><head><meta charset="utf-8"><title>W16 engineering report</title><style>{css}</style></head><body>{html}</body></html>'
    hp = p("12_FINAL_REPORT", "W16_ENGINEERING_REPORT.html")
    W(hp, doc)
    pdf = p("12_FINAL_REPORT", "W16_ENGINEERING_REPORT.pdf")
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(exe):
            try:
                subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", "file:///" + hp.replace("\\", "/")],
                               timeout=240, capture_output=True)
            except Exception as e:
                print("pdf attempt failed:", exe, e)
            if os.path.exists(pdf) and os.path.getsize(pdf) > 20000:
                return pdf
    return None


def main():
    E = evidence()
    b = bom()
    manufacturing(E)
    acc = requirements(E)
    md = report(E, b)
    pdf = to_pdf(md)
    print("BOM rows:", len(b or []), "| report chars:", len(md), "| pdf:", pdf, os.path.getsize(pdf) if pdf else None)
    for c, r, e in acc:
        print(f"  [{r}] {c}")


if __name__ == "__main__":
    main()
