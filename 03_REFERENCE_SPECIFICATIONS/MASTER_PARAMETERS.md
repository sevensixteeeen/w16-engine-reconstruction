# Master parameter table

Generated from `src/w16/params.py` - the single source of truth for CAD, calculations and documents.

| Parameter | Value | Unit | Tag | Note |
|---|---|---|---|---|
| `n_cyl` | 16 | - | PUB | 16 cylinders, W configuration |
| `displacement_ref_cc` | 7993 | cm3 | PUB | Bugatti technical data |
| `bore` | 86 | mm | SEC | commonly reported; verified against displacement |
| `stroke` | 86 | mm | SEC | commonly reported; verified against displacement |
| `bank_angle` | 90 | deg | PUB | angle between the two VR8 banks |
| `vr_angle` | 15 | deg | PUB | included angle between the two rows of one VR bank (VW W family) |
| `cyl_pitch` | 73 | mm | PUB | cylinder pitch along the crank, carried over Veyron->Chiron |
| `compression_ratio` | 9 | - | SEC | widely quoted, Veyron origin |
| `power_rated_kw` | 1103 | kW | PUB | 1,500 PS |
| `rpm_rated` | 6700 | 1/min | PUB |  |
| `torque_max_nm` | 1600 | N m | PUB |  |
| `rpm_torque_lo` | 2000 | 1/min | PUB | start of torque plateau |
| `rpm_torque_hi` | 6000 | 1/min | PUB | end of torque plateau |
| `rpm_turbo_switch` | 3800 | 1/min | PUB | second turbocharger pair cuts in |
| `firing_order` | (1, 14, 9, 4, 7, 12, 15, 6, 13, 8, 3, 16, 11, 2, 5, 10) | - | SEC | two independent secondary sources; kinematically consistent |
| `n_valves` | 64 | - | PUB | 4 per cylinder |
| `n_injectors` | 32 | - | PUB | duplex injection, 2 per cylinder |
| `n_turbos` | 4 | - | PUB | 2 per VR8 bank, sequential |
| `mass_ref_kg` | 400 | kg | PUB | plausibility reference only |
| `length_ref` | 710 | mm | SEC | published engine length (Veyron) |
| `coolant_flow_ref_lpm` | 800 | L/min | PUB | HT circuit pump flow at full load |
| `air_flow_ref_lpm` | 6e+04 | L/min | PUB | 'more than 60,000 L/min' |
| `cac_delta_t_ref` | 130 | K | PUB | 'cooled by as much as 130 degrees' |
| `t_exh_valve_ref_c` | 980 | degC | PUB | exhaust switching-valve temperature rating |
| `ht_volume_l` | 37 | L | PUB | HT coolant volume (37-40 L) |
| `lt_volume_l` | 12 | L | PUB | LT coolant volume (12-15 L) |
| `rod_length` | 164 | mm | EST | inferred from the VW W12 (SSP 248 pin stagger 21.833 deg -> l ~ 163-165 mm); assumed carried over |
| `row_offset` | 12.5 | mm | EST | lateral offset of each row axis from the bank centre plane at crank-centre height (VR 'desaxe'); 12.5 mm is the documented VW W8/W12 value (SSP 248), assumed for the W16 |
| `n_main` | 9 | - | EST | one main bearing between every pair of adjacent throws |
| `main_dia` | 68 | mm | EST | main journal diameter |
| `main_width` | 18 | mm | EST | main journal axial length |
| `pin_dia` | 56 | mm | EST | crankpin diameter |
| `pin_width` | 36 | mm | EST | crankpin axial length, two rods side by side |
| `web_thk` | 9.5 | mm | EST | crank web thickness; main + 2 webs + pin = cylinder pitch |
| `rod_be_width` | 17.75 | mm | EST | big-end width |
| `rod_side_clear` | 0.25 | mm | EST | total axial float of the rod pair on the pin |
| `cw_radius` | 90 | mm | EST | counterweight outer radius (limited by the piston skirt at BDC) |
| `pin_bore` | 28 | mm | EST | lightening bore through each crankpin |
| `deck_clearance` | 0.8 | mm | EST | piston crown to block deck at TDC |
| `gasket_thk` | 1 | mm | EST | compressed MLS head-gasket thickness |
| `gasket_bore` | 87.5 | mm | EST | head-gasket fire-ring bore |
| `comp_height` | 40 | mm | EST | pin centre to crown plane on the cylinder axis (ring pack must clear the pin bore on the low side of the tilted crown; 38.5 before D-040 - the steeper crown of D-040 moves the ring pack down) |
| `piston_height` | 61 | mm | EST | crown to skirt foot on the axis (59.5 before D-040; raised with comp_height, skirt foot unchanged) |
| `pin_dia_piston` | 24 | mm | EST | gudgeon pin outer diameter |
| `pin_bore_id` | 14 | mm | EST | gudgeon pin inner diameter |
| `pin_length` | 60 | mm | EST |  |
| `ring1_h` | 1.2 | mm | EST | top compression ring axial height |
| `ring2_h` | 1.2 | mm | EST | second ring axial height |
| `ring3_h` | 2 | mm | EST | oil-control ring axial height |
| `ring_radial` | 3.1 | mm | EST | ring radial wall |
| `top_land` | 5 | mm | EST | crown edge to top ring groove (measured on the low side of the slanted crown) |
| `piston_clear_dia` | 0.06 | mm | EST | diametral skirt clearance, cold |
| `piston_top_land_relief` | 0.4 | mm | EST | radial turn-down of the top land below the skirt diameter (D-040: none before; the gas + thermal FE gives 0.35 mm radial growth at the crown edge) |
| `piston_second_land_relief` | 0.25 | mm | EST | radial turn-down of the second land (D-040) |
| `piston_crown_thk` | 11 | mm | EST | crown thickness over the under-crown cavity (was 7.5; 9.0 in D-035; 11.0 in D-036) |
| `piston_uc_r` | 22 | mm | EST | under-crown cavity radius inside the ring belt (ring belt is solid outside it; D-035, 26 -> 22 in D-036) |
| `piston_skirt_wall` | 4.6 | mm | EST | slipper-skirt wall below the ring belt |
| `piston_boss_fillet_r` | 3 | mm | EST | fillet between the pin-boss side faces and the underside of the ring-belt step (D-037) |
| `piston_valve_pocket_depth` | 2.2 | mm | EST | depth of the two crown pockets under the long valves, normal to the crown plane (D-042: 1.6 before; gives >= 1.8 mm piston-to-valve at full intake advance) |
| `piston_pin_end_land` | 4 | mm | EST | land left under the oil-ring groove where the slipper skirt is cut away at the pin ends (1.5 mm before D-037) |
| `gallery_r_in` | 25 | mm | EST | oil cooling gallery inner radius (29 -> 25 in D-036: closer to the crown centre) |
| `gallery_r_out` | 35.8 | mm | EST | oil cooling gallery outer radius (>= 3.5 mm wall to the ring-groove roots) |
| `gallery_top_gap` | 5.5 | mm | EST | gallery roof below the crown plane, measured normal to the crown (the gallery follows the slanted crown; D-036 - the flat gallery of D-035 lay 14-23 mm under the high side) |
| `gallery_h` | 8 | mm | EST | gallery height normal to the crown |
| `gallery_inlet_dia` | 7 | mm | EST | gallery inlet (jet side) diameter |
| `gallery_outlet_dia` | 5 | mm | EST | gallery outlet diameter |
| `jet_inlet_y` | 32 | mm | EST | gallery inlet position on the piston +Y side (rod plane) |
| `jet_tip_lateral` | 35 | mm | EST | piston-cooling jet nozzle exit: lateral offset from the bore axis (D-036: bent jet; the straight jet of D-035 at 34.5 mm was struck by the rod) |
| `jet_tip_height` | 95 | mm | EST | nozzle exit along the bore from the cylinder's crank-plane point q3 (below the skirt at BDC) |
| `rod_se_width` | 20 | mm | EST | small-end width at the loaded (lower) side; trapezoidal eye, 14 mm at the top |
| `rod_se_od` | 38 | mm | EST | small-end outer diameter |
| `rod_be_od` | 68 | mm | EST | big-end outer diameter across the eye |
| `rod_bolt_dia` | 8 | mm | EST | M8x1 rod bolts |
| `bearing_shell_thk` | 1.8 | mm | EST | rod bearing shell wall |
| `main_shell_thk` | 2.5 | mm | EST | main bearing shell wall |
| `liner_wall` | 5 | mm | EST | minimum cylinder wall to water jacket |
| `jacket_width` | 7 | mm | EST | water-jacket radial width |
| `jacket_depth` | 78 | mm | EST | water-jacket depth below deck |
| `deck_thk` | 9 | mm | EST | closed-deck plate thickness above the jacket |
| `head_bolt_dia` | 11 | mm | EST | M11 head bolts |
| `main_bolt_dia` | 12 | mm | EST | M12 main bolts |
| `oil_gallery_dia` | 18 | mm | EST | main oil galleries (two, one per bank) |
| `block_wall` | 6 | mm | EST | general cast wall |
| `valve_in_dia` | 32 | mm | EST | intake valve head |
| `valve_ex_dia` | 27 | mm | EST | exhaust valve head |
| `valve_stem_dia` | 6 | mm | EST |  |
| `valve_lift_in` | 10 | mm | EST |  |
| `valve_lift_ex` | 9.5 | mm | EST |  |
| `valve_dx_in` | 19 | mm | EST | intake valve offset along crank axis from bore centre |
| `valve_dx_ex` | 19 | mm | EST | exhaust valve offset along crank axis from bore centre (= intake; D-034) |
| `valve_du_in` | 17.5 | mm | EST | intake valve-head lateral offset from bore centre (towards the valley) |
| `valve_du_ex` | 17.5 | mm | EST | exhaust valve-head lateral offset from bore centre (outboard) |
| `cam_u` | 27 | mm | EST | camshaft axes at u = -/+ cam_u from the head centre plane (intake cam on the valley side) |
| `cam_w` | 141 | mm | EST | camshaft axis height above the head joint face |
| `valve_tip_w` | 112 | mm | EST | valve-tip height above the head joint face (closed) |
| `finger_tip_near` | 17 | mm | EST | near-row finger (valves on the far side of their camshaft from the head centre): valve tip to roller axis |
| `finger_piv_near` | 10 | mm | EST | near-row finger: roller axis to support element (short arm keeps the element clear of the far-row spring; D-034) |
| `finger_tip_far` | 11 | mm | EST | far-row finger (long valves): valve tip to roller axis (short arm moves the long stem away; D-034) |
| `finger_piv_far` | 17 | mm | EST | far-row finger: roller axis to support element |
| `finger_pad_r` | 12 | mm | EST | crown radius of the finger's valve pad; the pad touches the tip centre at half lift (D-039: flat pad before) |
| `hla_boss_w0` | 82 | mm | EST | lower end of the near-row support-element boss (hangs from the plug tower; D-034) |
| `roller_dia` | 17 | mm | EST | finger-follower roller |
| `plug_top_w` | 150 | mm | EST | height at which the spark-plug wells reach the head centre plane |
| `plug_well_dia` | 19 | mm | EST | spark-plug well bore (M10 plug, 12 mm bi-hex) |
| `roof_low_w` | 1 | mm | EST | height of the chamber roof at its low edge above the head joint face |
| `head_height` | 141 | mm | EST | head joint face to cam-cover joint (= camshaft centre line) |
| `fire_deck_thk` | 9 | mm | EST |  |
| `plug_thread` | 10 | mm | EST | M10x1 spark plug |
| `cam_base_r` | 14 | mm | EST | cam base-circle radius |
| `cam_journal_dia` | 26 | mm | EST |  |
| `spring_od` | 20 | mm | EST | valve spring outer diameter (beehive, largest coil; reduced from 22 for clearance, D-034) |
| `spring_seat_drop` | 42 | mm | EST | spring seat below the closed valve tip along the stem (installed height 38 mm; was 40 / 36 mm with ~0.1 mm coil-bind margin at full lift) |
| `valve_guide_od` | 11 | mm | EST |  |
| `rpm_max` | 6800 | 1/min | EST | governed speed |
| `rpm_overspeed` | 7300 | 1/min | EST | mechanical design overspeed |
| `p_max_design_bar` | 135 | bar | EST | design peak cylinder pressure (about 1.3 x the highest cycle-model value) |
| `t_amb_k` | 298.1 | K | EST | ISO reference ambient |
| `p_amb_bar` | 1.013 | bar | EST | ISO reference ambient |
| `m_piston` | 0.444 | kg | CALC | bare piston, CAD mass of the gallery-cooled design (D-042: 0.4436 - deeper valve pockets; 0.4457 in D-040, 0.4348 in D-038, 0.4341 in D-037, 0.430 in D-036, 0.427 in D-035, 0.365 EST before) |
| `m_pin` | 0.141 | kg | CALC | gudgeon pin, CAD mass (dia 24 / 14 x 60) |
| `m_rings` | 0.027 | kg | CALC | ring pack + circlips, CAD mass |
| `m_rod` | 0.43 | kg | EST | titanium rod incl. bolts and shells |
| `rod_cg_frac` | 0.3 | - | EST | rod centre of gravity from big-end centre / rod length |
| `J_damper` | 0.022 | kg m2 | EST | viscous damper ring + hub + pulley |
| `J_flywheel` | 0.11 | kg m2 | EST | flex plate + dual-clutch input mass |
| `J_throw_fixed` | 0.0042 | kg m2 | EST | webs + pin + counterweights of one throw; replaced by CAD value |
| `p_crankcase_bar` | 0.85 | bar | EST | dry-sump crankcase depression (abs) |
| `throw` | 42.87 | mm | CALC | crank radius giving 86.000 mm stroke with offset bores (< stroke/2) |
| `s_tdc` | 204.9 | mm | CALC | piston-pin distance along the cylinder axis from the axis foot point at TDC |
| `s_bdc` | 118.9 | mm | CALC | same at BDC |
| `bank_offset` | 18 | mm | CALC | axial offset bank 2 vs bank 1 (one rod width) |
| `disp_cyl_cc` | 499.6 | cm3 | CALC | swept volume per cylinder |
| `displacement_cc` | 7993 | cm3 | CALC | total swept volume |
| `v_clear_cc` | 62.44 | cm3 | CALC | clearance volume per cylinder for CR 9.0 |
| `deck_height` | 237.1 | mm | CALC | block deck plane height along the bank centre line from the crank axis |
| `s_deck` | 239.1 | mm | CALC | axis coordinate s where a row axis pierces the deck |
| `u_bore_deck` | 43.71 | mm | CALC | lateral distance of a bore centre from the bank centre plane at the deck |
| `s_bore_foot` | 105.9 | mm | CALC | bore foot; skirt protrudes 8 mm (EST) below it at BDC |
| `web_bore_foot` | 3.998 | mm | CALC | solid web between adjacent zig-zag bores at the bore foot |
| `web_bore_deck` | 27.89 | mm | CALC | solid web between adjacent zig-zag bores at the deck |
| `bore_length` | 133.3 | mm | CALC | machined bore length on the axis |
| `head_face_height` | 238.1 | mm | CALC | cylinder-head joint face height (v) |
| `u_bore_head` | 43.84 | mm | CALC | lateral distance of a bore centre from the bank centre plane at the head joint face |
| `crown_rise_axis` | 6.491 | mm | CALC | rise of the crown plane at the piston axis above its low edge |
| `crown_tilt` | 8.512 | deg | CALC | tilt of the piston crown relative to the head joint face (towards the roof) giving CR 9.0 |
| `crown_tilt_axis` | 16.01 | deg | CALC | crown tilt relative to the piston-axis normal |
| `roof_tilt` | 16.4 | deg | CALC | combustion-chamber roof tilt relative to the head joint face |
| `v_head_chamber_est_cc` | 87.37 | cm3 | CALC | head chamber volume (analytic estimate) |

## Materials

| material | density [kg/m3] | E [GPa] | nu | alpha [1e-6/K] | k [W/mK] | yield [MPa] | UTS [MPa] | fatigue limit [MPa] (EST) | use |
|---|---|---|---|---|---|---|---|---|---|
| AlSi7Mg0.3-T6 (A356) | 2680 | 72 | 0.33 | 21.5 | 150 | 230 | 290 | 90 | cylinder block, heads, bedplate (low-pressure / sand cast, HIP) |
| AlSi12CuMgNi (forged 4032-T6) | 2700 | 79 | 0.33 | 19.5 | 140 | 315 | 380 | 110 | pistons (forged) |
| 42CrMo4 QT + nitrided | 7850 | 210 | 0.3 | 12 | 42 | 900 | 1100 | 520 | crankshaft (die forged), camshafts |
| Ti-6Al-4V | 4430 | 114 | 0.34 | 8.6 | 6.7 | 880 | 950 | 500 | connecting rods, exhaust system |
| Inconel 713C | 7910 | 206 | 0.3 | 13 | 11 | 740 | 850 | 300 | turbine wheels, exhaust switching valve |
| D5S Ni-resist / 1.4849 cast steel | 7700 | 190 | 0.3 | 16 | 15 | 250 | 450 | 150 | turbine housings, exhaust manifolds |
| 16MnCr5 case hardened | 7850 | 210 | 0.3 | 12 | 45 | 600 | 900 | 450 | gudgeon pins, sprockets |
| CFRP (prepreg, quasi-iso) | 1550 | 55 | 0.3 | 3 | 5 | 500 | 600 | 250 | intake tubes, plenums, chain cover |
| Steel (generic fastener 10.9/12.9) | 7850 | 210 | 0.3 | 12 | 45 | 940 | 1040 | 400 | fasteners, valves (X45CrSi9-3 / NiCr20TiAl grouped here for mass) |
| Elastomer / polymer | 1200 | 2 | 0.4 | 80 | 0.3 | 40 | 50 | 10 | hoses, seals, connectors |
