# Materials and manufacturing specification

Scope: concept-level manufacturing definition for the reconstructed W16. Tolerances are given as **classes** to show
which features need precision manufacturing; they are provisional and must be confirmed by tolerance-stack and
functional analysis before release. Operating temperatures and loads refer to the calculations in `08_SIMULATIONS/`.

## 1. Component specification

| Component | Proposed material | Manufacturing process | Critical dimensions | Tolerance class (provisional) | Surface finish | Operating temperature | Expected loading | Inspection |
|---|---|---|---|---|---|---|---|---|
| Crankcase upper section | AlSi7Mg0.3-T6 (alternative: hypereutectic AlSi17CuMg as VW W12, or AlSi9Cu3 with coated bores) | low-pressure sand casting with core package (water jacket, crank chamber), HIP, T6; 5-axis machining; bore coating (plasma / PEO) or iron-coated pistons on Alusil | bore dia 86 H5-class, cylindricity; main bore line dia 73; deck height 238.2; bore positions (zig-zag, +/-43.86 at deck) | bores IT5, positions +/-0.03, deck flatness 0.03 (classes, provisional) | bore plateau honed Rpk<0.2; deck Rz 6 | coolant 95-110 degC; liner top ~150-170 degC (calc.) | 135 bar design gas pressure; main bearing 37 kN; head bolt clamp | CT scan, pressure tests, CMM, bore form |
| Crankcase lower section (bearing support) | AlSi7Mg0.3-T6 with cast-in EN-GJS-600 bearing covers | sand casting around pre-machined iron inserts; line boring assembled with the upper section | main bore line; joint face; insert position | main bore IT6, coaxiality 0.02 (class) | joint Rz 6 | oil 100-140 degC | main bearing loads 37 kN peak, 4 bolts per bearing | X-ray of insert bond, CMM |
| Cylinder heads | AlSi7Mg0.3-T6 (+Cu variant for hot strength) | low-pressure sand casting, HIP, T6; valve seats and guides shrink-fitted; cam line bored with caps | chamber volume (CR), valve seat run-out to guide, cam bore line, port positions | seat run-out 0.03, cam bores IT6, joint flatness 0.03 (classes) | ports as cast + CNC blended throats; joint Rz 6 | roof ~230 degC mean gas side (1-D), coolant 95-110 degC | 135 bar on roof, bolt clamp, thermal gradient | CT scan, leak test, CMM, flow bench |
| Crankshaft | 42CrMo4 (alternative 34CrNiMo6), QT, nitrided | closed-die forging (twisted or as-forged throws), rough machining, QT, finish turning, drilling, nitriding, grinding, lapping, balancing | journal diameters 68/56, throw 42.868, pin phasing (non-uniform, see table), main fillets R2.5 (main shells 12.2 mm, unchamfered), pin relief grooves R2.5 x 2.5 deep, solid pins, dia 5 oil drilling per rod | journals IT5, phasing +/-0.05 deg, run-out 0.02 (classes) | journals Ra 0.1 | oil 100-150 degC | bending from 78 kN design rod force, torsion mean 1.6 kN m + vibratory ~1.2 kN m | MPI, CMM, hardness depth, balance |
| Connecting rods | Ti-6Al-4V (forged, STA) | die forging, machining, shot peening, anti-galling coating on thrust faces (CrN/MoS2) | centre distance 164, bores, width 17.75, weight | bores IT6, parallelism 0.02/100 (classes) | peened; bores honed | ~150 degC | 78 kN compression (design), 23 kN tension at overspeed | FPI, CMM, weight split |
| Pistons | AlSi12CuMgNi forged (4032) or 2618 for higher strength | forging, CNC turning with oval/barrel skirt, pin-bore profiling, anodising, skirt coating | skirt profile and clearance, compression height 40.0, ring grooves, crown tilt | skirt profile +/-0.005, grooves IT6 (classes) | pin bore Ra 0.2 | crown up to 433 degC (mean 380), top ring groove 267 degC at rated power (FE, section 8 of the report; crown above the ~350 degC guide - open item); hot fatigue **NOT ASSESSABLE with public data** (method fails even production-range crown temperatures) with 4032-T6 lower-bound strength (factor 0.10-0.28) - **piston material / cooling OPEN** (report section 8.1) | 135 bar gas, 31,700 m/s2 at overspeed | CMM, ultrasonic, groove gauges |
| Valves | intake X45CrSi9-3 / titanium option; exhaust NiCr20TiAl (Nimonic 80A), hollow sodium-filled | forging / friction welding, grinding, nitriding or chrome stem | stem dia 6, seat angle, length (short/long types) | stem IT5-class, seat run-out 0.02 | stem Ra 0.2 | exhaust head 750-850 degC (typical; not simulated) | seating force, 5,300 m/s2 nose deceleration | eddy current, X-ray of sodium fill |
| Valve springs | CrSiV super-clean wire (OTEVA 90 class) | coiling, stress relief, shot peening, presetting | rate ~33 N/mm, seat load ~270 N, open load ~600 N (calc.) | load +/-4 % | peened | 120-150 degC | see spring table (valve-train report) | load test 100 %, fatigue sampling |
| Camshafts | assembled (steel tube + 100Cr6 lobes) or forged 16MnCr5, induction/case hardened | lobe grinding to conjugate profile for dia 17 roller | lobe profile, phase angles per cylinder, journals dia 26 | profile +/-0.02, phase +/-0.2 deg cam (classes) | lobes Ra 0.2 | 120-150 degC | roller contact (Hertz), chain drive torque | cam-form measurement, MPI |
| Turbocharger housings | turbine: austenitic cast steel 1.4849 / Ni-resist D5S; compressor: AlSi7Mg | investment / sand casting, machining | wheel contours (tip clearance), flange faces | contour +/-0.05, flatness 0.05 (classes) | as cast flow surfaces | turbine housing up to 980 degC gas | thermal cycling, gas pressure 3 bar | X-ray, leak test |
| Turbocharger rotating group | turbine wheel Inconel 713C (or TiAl), shaft 42CrMo4 EB-welded; compressor wheel forged 2618 milled | investment casting, EB/friction welding, 5-axis milling, high-speed balancing | wheel profiles, journal dia 11, balance | balance G0.4 class, journals IT5 | journals Ra 0.1 | turbine 980 degC, compressor 173 degC outlet | tip speed ~470 m/s at ~107,000 rpm (calc.) | spin test, FPI, balancing |
| Intake manifolds, plenums, charge pipes, air ducts, chain housing, cam covers | CFRP prepreg (as published for intake tube, charge-air system and chain housing) with bonded metal inserts | autoclave lay-up on tooling, bonding of flanges | flange positions, sealing faces | flange position +/-0.2 | sealing faces machined | charge air up to 175 degC before cooler, 60 degC after | 2.9 bar abs boost + pulsation | leak / burst test, ultrasonic |
| Exhaust manifolds and cross-over | investment-cast 1.4849 (or fabricated Inconel 625 sheet) | casting / hydroforming and welding, bellows in cross-over | flange flatness, port alignment | flatness 0.1 (class) | - | up to 980 degC | thermal expansion ~4 mm over manifold length, gas pulsation | X-ray of welds, leak test |
| Down-pipes, pre-catalyst shells | titanium grade 2 / Ti-6242 (published: titanium exhaust) | tube bending, TIG welding under shield gas | joint positions | +/-1.0 | - | up to ~850 degC after turbine (calc.) | thermal, vibration | leak test, weld inspection |
| Oil and coolant connections | AlMgSi tube, stainless braided PTFE hose, FKM seals | bending, brazing, crimping | port threads and sealing faces | per fitting standard | - | oil 150 degC, coolant 120 degC | oil 8 bar, coolant 2 bar | pressure test |
| Fasteners | 10.9 / 12.9 steel; MP35N or Ti-6Al-4V where justified (rod bolts, flywheel) | cold forming, rolled threads after heat treatment | thread, under-head fillet | 6g/6H, torque+angle tightening | - | up to 150 degC (manifold studs 700 degC: Inconel) | preload 75-90 % of yield | batch tensile tests, MPI |
| Bearings | main / big end: steel-backed bronze with sputter AlSn20 overlay; small end: bronze bush; turbo: floating bronze bushes | strip sintering/casting, sputtering, boring | wall thickness, crush height | wall +/-0.003 | bore Ra 0.2 | 150 degC | specific load 45-55 MPa (calc.) | wall-thickness gauging, bond test |

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
