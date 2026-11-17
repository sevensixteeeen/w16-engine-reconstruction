"""Master parameter set — the single source of truth for the W16 reconstruction.

Every value carries a provenance tag:
    PUB  publicly documented by the manufacturer / VW Group literature
    SEC  secondary sources only (unconfirmed)
    CALC calculated in this project
    EST  engineering estimate / provisional design value

Units: mm, deg, kg, s, N, MPa, K unless the name says otherwise.
Do not type a master dimension anywhere else in the code base.
"""
from __future__ import annotations


class Params:
    def __init__(self):
        self._meta: dict[str, tuple[str, str, str]] = {}

    def add(self, name, value, unit, tag, note=""):
        assert tag in ("PUB", "SEC", "CALC", "EST"), tag
        if name in self._meta and self._meta[name][1] != "CALC":
            raise ValueError(f"parameter {name} defined twice")
        setattr(self, name, value)
        self._meta[name] = (unit, tag, note)

    def table(self, tags=None):
        rows = []
        for k, (unit, tag, note) in self._meta.items():
            if tags and tag not in tags:
                continue
            rows.append((k, getattr(self, k), unit, tag, note))
        return rows

    def markdown(self, tags=None):
        out = ["| Parameter | Value | Unit | Tag | Note |", "|---|---|---|---|---|"]
        for k, v, unit, tag, note in self.table(tags):
            if isinstance(v, float):
                v = f"{v:.4g}"
            out.append(f"| `{k}` | {v} | {unit} | {tag} | {note} |")
        return "\n".join(out)


P = Params()
a = P.add

# ---------------------------------------------------------------- reference (fixed baseline)
a("n_cyl", 16, "-", "PUB", "16 cylinders, W configuration")
a("displacement_ref_cc", 7993.0, "cm3", "PUB", "Bugatti technical data")
a("bore", 86.0, "mm", "SEC", "commonly reported; verified against displacement")
a("stroke", 86.0, "mm", "SEC", "commonly reported; verified against displacement")
a("bank_angle", 90.0, "deg", "PUB", "angle between the two VR8 banks")
a("vr_angle", 15.0, "deg", "PUB", "included angle between the two rows of one VR bank (VW W family)")
a("cyl_pitch", 73.0, "mm", "PUB", "cylinder pitch along the crank, carried over Veyron->Chiron")
a("compression_ratio", 9.0, "-", "SEC", "widely quoted, Veyron origin")
a("power_rated_kw", 1103.0, "kW", "PUB", "1,500 PS")
a("rpm_rated", 6700.0, "1/min", "PUB", "")
a("torque_max_nm", 1600.0, "N m", "PUB", "")
a("rpm_torque_lo", 2000.0, "1/min", "PUB", "start of torque plateau")
a("rpm_torque_hi", 6000.0, "1/min", "PUB", "end of torque plateau")
a("rpm_turbo_switch", 3800.0, "1/min", "PUB", "second turbocharger pair cuts in")
a("firing_order", (1, 14, 9, 4, 7, 12, 15, 6, 13, 8, 3, 16, 11, 2, 5, 10), "-", "SEC",
  "two independent secondary sources; kinematically consistent")
a("n_valves", 64, "-", "PUB", "4 per cylinder")
a("n_injectors", 32, "-", "PUB", "duplex injection, 2 per cylinder")
a("n_turbos", 4, "-", "PUB", "2 per VR8 bank, sequential")
a("mass_ref_kg", 400.0, "kg", "PUB", "plausibility reference only")
a("length_ref", 710.0, "mm", "SEC", "published engine length (Veyron)")
a("coolant_flow_ref_lpm", 800.0, "L/min", "PUB", "HT circuit pump flow at full load")
a("air_flow_ref_lpm", 60000.0, "L/min", "PUB", "'more than 60,000 L/min'")
a("cac_delta_t_ref", 130.0, "K", "PUB", "'cooled by as much as 130 degrees'")
a("t_exh_valve_ref_c", 980.0, "degC", "PUB", "exhaust switching-valve temperature rating")
a("ht_volume_l", 37.0, "L", "PUB", "HT coolant volume (37-40 L)")
a("lt_volume_l", 12.0, "L", "PUB", "LT coolant volume (12-15 L)")

# ---------------------------------------------------------------- crank train (provisional)
a("rod_length", 164.0, "mm", "EST", "inferred from the VW W12 (SSP 248 pin stagger 21.833 deg -> l ~ 163-165 mm); assumed carried over")
a("row_offset", 12.5, "mm", "EST",
  "lateral offset of each row axis from the bank centre plane at crank-centre height (VR 'desaxe'); "
  "12.5 mm is the documented VW W8/W12 value (SSP 248), assumed for the W16")
a("n_main", 9, "-", "EST", "one main bearing between every pair of adjacent throws")
a("main_dia", 68.0, "mm", "EST", "main journal diameter")
a("main_width", 18.0, "mm", "EST", "main journal axial length")
a("pin_dia", 56.0, "mm", "EST", "crankpin diameter")
a("pin_width", 36.0, "mm", "EST", "crankpin axial length, two rods side by side")
a("web_thk", 9.5, "mm", "EST", "crank web thickness; main + 2 webs + pin = cylinder pitch")
a("rod_be_width", 17.75, "mm", "EST", "big-end width")
a("rod_side_clear", 0.25, "mm", "EST", "total axial float of the rod pair on the pin")
a("cw_radius", 90.0, "mm", "EST", "counterweight outer radius (limited by the piston skirt at BDC)")
a("pin_bore", 28.0, "mm", "EST", "lightening bore through each crankpin")
a("deck_clearance", 0.8, "mm", "EST", "piston crown to block deck at TDC")
a("gasket_thk", 1.0, "mm", "EST", "compressed MLS head-gasket thickness")
a("gasket_bore", 87.5, "mm", "EST", "head-gasket fire-ring bore")

# piston
a("comp_height", 40.0, "mm", "EST", "pin centre to crown plane on the cylinder axis (ring pack must clear the pin bore on the low side of the tilted crown; 38.5 before D-040 - the steeper crown of D-040 moves the ring pack down)")
a("piston_height", 61.0, "mm", "EST", "crown to skirt foot on the axis (59.5 before D-040; raised with comp_height, skirt foot unchanged)")
a("pin_dia_piston", 24.0, "mm", "EST", "gudgeon pin outer diameter")
a("pin_bore_id", 14.0, "mm", "EST", "gudgeon pin inner diameter")
a("pin_length", 60.0, "mm", "EST", "")
a("ring1_h", 1.2, "mm", "EST", "top compression ring axial height")
a("ring2_h", 1.2, "mm", "EST", "second ring axial height")
a("ring3_h", 2.0, "mm", "EST", "oil-control ring axial height")
a("ring_radial", 3.1, "mm", "EST", "ring radial wall")
a("top_land", 5.0, "mm", "EST", "crown edge to top ring groove (measured on the low side of the slanted crown)")
a("piston_clear_dia", 0.06, "mm", "EST", "diametral skirt clearance, cold")
a("piston_top_land_relief", 0.40, "mm", "EST", "radial turn-down of the top land below the skirt diameter (D-040: none before; the gas + thermal FE "
  "gives 0.35 mm radial growth at the crown edge)")
a("piston_second_land_relief", 0.25, "mm", "EST", "radial turn-down of the second land (D-040)")
a("piston_crown_thk", 11.0, "mm", "EST", "crown thickness over the under-crown cavity (was 7.5; 9.0 in D-035; 11.0 in D-036)")
a("piston_uc_r", 22.0, "mm", "EST", "under-crown cavity radius inside the ring belt (ring belt is solid outside it; D-035, 26 -> 22 in D-036)")
a("piston_skirt_wall", 4.6, "mm", "EST", "slipper-skirt wall below the ring belt")
a("piston_boss_fillet_r", 3.0, "mm", "EST", "fillet between the pin-boss side faces and the underside of the ring-belt step (D-037)")
a("piston_valve_pocket_depth", 2.2, "mm", "EST", "depth of the two crown pockets under the long valves, normal to the crown plane (D-042: 1.6 before; gives >= 1.8 mm piston-to-valve at full intake advance)")
a("piston_pin_end_land", 4.0, "mm", "EST", "land left under the oil-ring groove where the slipper skirt is cut away at the pin ends (1.5 mm before D-037)")
a("gallery_r_in", 25.0, "mm", "EST", "oil cooling gallery inner radius (29 -> 25 in D-036: closer to the crown centre)")
a("gallery_r_out", 35.8, "mm", "EST", "oil cooling gallery outer radius (>= 3.5 mm wall to the ring-groove roots)")
a("gallery_top_gap", 5.5, "mm", "EST", "gallery roof below the crown plane, measured normal to the crown (the gallery follows the slanted "
  "crown; D-036 - the flat gallery of D-035 lay 14-23 mm under the high side)")
a("gallery_h", 8.0, "mm", "EST", "gallery height normal to the crown")
a("gallery_inlet_dia", 7.0, "mm", "EST", "gallery inlet (jet side) diameter")
a("gallery_outlet_dia", 5.0, "mm", "EST", "gallery outlet diameter")
a("jet_inlet_y", 32.0, "mm", "EST", "gallery inlet position on the piston +Y side (rod plane)")
a("jet_tip_lateral", 35.0, "mm", "EST", "piston-cooling jet nozzle exit: lateral offset from the bore axis (D-036: bent jet; the straight "
  "jet of D-035 at 34.5 mm was struck by the rod)")
a("jet_tip_height", 95.0, "mm", "EST", "nozzle exit along the bore from the cylinder's crank-plane point q3 (below the skirt at BDC)")

# rod
a("rod_se_width", 20.0, "mm", "EST", "small-end width at the loaded (lower) side; trapezoidal eye, 14 mm at the top")
a("rod_se_od", 38.0, "mm", "EST", "small-end outer diameter")
a("rod_be_od", 68.0, "mm", "EST", "big-end outer diameter across the eye")
a("rod_bolt_dia", 8.0, "mm", "EST", "M8x1 rod bolts")
a("bearing_shell_thk", 1.8, "mm", "EST", "rod bearing shell wall")
a("main_shell_thk", 2.5, "mm", "EST", "main bearing shell wall")

# ---------------------------------------------------------------- block
a("liner_wall", 5.0, "mm", "EST", "minimum cylinder wall to water jacket")
a("jacket_width", 7.0, "mm", "EST", "water-jacket radial width")
a("jacket_depth", 78.0, "mm", "EST", "water-jacket depth below deck")
a("deck_thk", 9.0, "mm", "EST", "closed-deck plate thickness above the jacket")
a("head_bolt_dia", 11.0, "mm", "EST", "M11 head bolts")
a("main_bolt_dia", 12.0, "mm", "EST", "M12 main bolts")
a("oil_gallery_dia", 18.0, "mm", "EST", "main oil galleries (two, one per bank)")
a("block_wall", 6.0, "mm", "EST", "general cast wall")

# ---------------------------------------------------------------- head / valvetrain
a("valve_in_dia", 32.0, "mm", "EST", "intake valve head")
a("valve_ex_dia", 27.0, "mm", "EST", "exhaust valve head")
a("valve_stem_dia", 6.0, "mm", "EST", "")
a("valve_lift_in", 10.0, "mm", "EST", "")
a("valve_lift_ex", 9.5, "mm", "EST", "")
a("valve_dx_in", 19.0, "mm", "EST", "intake valve offset along crank axis from bore centre")
a("valve_dx_ex", 19.0, "mm", "EST", "exhaust valve offset along crank axis from bore centre (= intake; D-034)")
a("valve_du_in", 17.5, "mm", "EST", "intake valve-head lateral offset from bore centre (towards the valley)")
a("valve_du_ex", 17.5, "mm", "EST", "exhaust valve-head lateral offset from bore centre (outboard)")
a("cam_u", 27.0, "mm", "EST", "camshaft axes at u = -/+ cam_u from the head centre plane (intake cam on the valley side)")
a("cam_w", 141.0, "mm", "EST", "camshaft axis height above the head joint face")
a("valve_tip_w", 112.0, "mm", "EST", "valve-tip height above the head joint face (closed)")
a("finger_tip_near", 17.0, "mm", "EST", "near-row finger (valves on the far side of their camshaft from the head centre): valve tip to roller axis")
a("finger_piv_near", 10.0, "mm", "EST", "near-row finger: roller axis to support element (short arm keeps the element clear of the far-row spring; D-034)")
a("finger_tip_far", 11.0, "mm", "EST", "far-row finger (long valves): valve tip to roller axis (short arm moves the long stem away; D-034)")
a("finger_piv_far", 17.0, "mm", "EST", "far-row finger: roller axis to support element")
a("finger_pad_r", 12.0, "mm", "EST", "crown radius of the finger's valve pad; the pad touches the tip centre at half lift (D-039: flat pad before)")
a("hla_boss_w0", 82.0, "mm", "EST", "lower end of the near-row support-element boss (hangs from the plug tower; D-034)")
a("roller_dia", 17.0, "mm", "EST", "finger-follower roller")
a("plug_top_w", 150.0, "mm", "EST", "height at which the spark-plug wells reach the head centre plane")
a("plug_well_dia", 19.0, "mm", "EST", "spark-plug well bore (M10 plug, 12 mm bi-hex)")
a("roof_low_w", 1.0, "mm", "EST", "height of the chamber roof at its low edge above the head joint face")
a("head_height", 141.0, "mm", "EST", "head joint face to cam-cover joint (= camshaft centre line)")
a("fire_deck_thk", 9.0, "mm", "EST", "")
a("plug_thread", 10.0, "mm", "EST", "M10x1 spark plug")
a("cam_base_r", 14.0, "mm", "EST", "cam base-circle radius")
a("cam_journal_dia", 26.0, "mm", "EST", "")
a("spring_od", 20.0, "mm", "EST", "valve spring outer diameter (beehive, largest coil; reduced from 22 for clearance, D-034)")
a("spring_seat_drop", 42.0, "mm", "EST", "spring seat below the closed valve tip along the stem (installed height 38 mm; was 40 / 36 mm "
  "with ~0.1 mm coil-bind margin at full lift)")
a("valve_guide_od", 11.0, "mm", "EST", "")

# ---------------------------------------------------------------- operating limits
a("rpm_max", 6800.0, "1/min", "EST", "governed speed")
a("rpm_overspeed", 7300.0, "1/min", "EST", "mechanical design overspeed")
a("p_max_design_bar", 135.0, "bar", "EST", "design peak cylinder pressure (about 1.3 x the highest cycle-model value)")
a("t_amb_k", 298.15, "K", "EST", "ISO reference ambient")
a("p_amb_bar", 1.01325, "bar", "EST", "ISO reference ambient")

# ---------------------------------------------------------------- masses / inertias (EST until replaced by CAD mass properties)
a("m_piston", 0.444, "kg", "CALC", "bare piston, CAD mass of the gallery-cooled design (D-042: 0.4436 - deeper valve pockets; 0.4457 in D-040, 0.4348 in D-038, 0.4341 in D-037, 0.430 in D-036, 0.427 in D-035, 0.365 EST before)")
a("m_pin", 0.141, "kg", "CALC", "gudgeon pin, CAD mass (dia 24 / 14 x 60)")
a("m_rings", 0.027, "kg", "CALC", "ring pack + circlips, CAD mass")
a("m_rod", 0.430, "kg", "EST", "titanium rod incl. bolts and shells")
a("rod_cg_frac", 0.30, "-", "EST", "rod centre of gravity from big-end centre / rod length")
a("J_damper", 0.022, "kg m2", "EST", "viscous damper ring + hub + pulley")
a("J_flywheel", 0.110, "kg m2", "EST", "flex plate + dual-clutch input mass")
a("J_throw_fixed", 0.0042, "kg m2", "EST", "webs + pin + counterweights of one throw; replaced by CAD value")
a("p_crankcase_bar", 0.85, "bar", "EST", "dry-sump crankcase depression (abs)")

# ---------------------------------------------------------------- materials (density kg/m3, E GPa, nu, alpha 1/K, k W/mK, yield MPa, fatigue MPa)
MATERIALS = {
    "AlSi7Mg0.3-T6 (A356)": dict(rho=2680, E=72, nu=0.33, alpha=21.5e-6, k=150, yield_=230, uts=290, fatigue=90,
                                 use="cylinder block, heads, bedplate (low-pressure / sand cast, HIP)"),
    "AlSi12CuMgNi (forged 4032-T6)": dict(rho=2700, E=79, nu=0.33, alpha=19.5e-6, k=140, yield_=315, uts=380, fatigue=110,
                                          use="pistons (forged)"),
    "42CrMo4 QT + nitrided": dict(rho=7850, E=210, nu=0.30, alpha=12.0e-6, k=42, yield_=900, uts=1100, fatigue=520,
                                  use="crankshaft (die forged), camshafts"),
    "Ti-6Al-4V": dict(rho=4430, E=114, nu=0.34, alpha=8.6e-6, k=6.7, yield_=880, uts=950, fatigue=500,
                      use="connecting rods, exhaust system"),
    "Inconel 713C": dict(rho=7910, E=206, nu=0.30, alpha=13.0e-6, k=11, yield_=740, uts=850, fatigue=300,
                         use="turbine wheels, exhaust switching valve"),
    "D5S Ni-resist / 1.4849 cast steel": dict(rho=7700, E=190, nu=0.30, alpha=16.0e-6, k=15, yield_=250, uts=450, fatigue=150,
                                              use="turbine housings, exhaust manifolds"),
    "16MnCr5 case hardened": dict(rho=7850, E=210, nu=0.30, alpha=12.0e-6, k=45, yield_=600, uts=900, fatigue=450,
                                  use="gudgeon pins, sprockets"),
    "CFRP (prepreg, quasi-iso)": dict(rho=1550, E=55, nu=0.30, alpha=3e-6, k=5, yield_=500, uts=600, fatigue=250,
                                      use="intake tubes, plenums, chain cover"),
    "Steel (generic fastener 10.9/12.9)": dict(rho=7850, E=210, nu=0.30, alpha=12e-6, k=45, yield_=940, uts=1040, fatigue=400,
                                               use="fasteners, valves (X45CrSi9-3 / NiCr20TiAl grouped here for mass)"),
    "Elastomer / polymer": dict(rho=1200, E=2, nu=0.4, alpha=80e-6, k=0.3, yield_=40, uts=50, fatigue=10,
                                use="hoses, seals, connectors"),
}
