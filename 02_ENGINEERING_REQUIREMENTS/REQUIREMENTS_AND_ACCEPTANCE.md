# Engineering requirements and traceability

Requirements are taken from the project brief (section numbers in brackets). "Where" points to the deliverable that answers it.

| ID | Requirement (brief section) | Where | Status |
|---|---|---|---|
| R-01 | Reference specifications with sources and confidence levels [2, 3] | `01_RESEARCH/RESEARCH_LOG.md`, `03_REFERENCE_SPECIFICATIONS/` | done |
| R-02 | Verify bore/stroke against displacement [2] | `03_REFERENCE_SPECIFICATIONS/REFERENCE_SPEC.md` section 2 | done |
| R-03 | Architecture: banks, numbering, crank, envelope, master assembly, 8 views [4] | `src/w16/layout.py`, `06_ASSEMBLIES/views/`, `07_ENGINEERING_DRAWINGS/` | done |
| R-04 | Block/crankcase with real jackets and galleries; loads analysed [5] | `05_COMPONENT_CAD/01_*`, `08_SIMULATIONS/fea/` | done (slice FE) |
| R-05 | Pistons, rods, crank; balance, bearing loads, torsional vibration; animation [6] | `08_SIMULATIONS/analytical/02_cranktrain_dynamics.md`, `09_ANIMATIONS/02_*` | done |
| R-06 | Heads, 64 valves, cams, timing drive; timing model; animation [7] | `08_SIMULATIONS/analytical/03_valvetrain.md`, `09_ANIMATIONS/04_*` | done (2 head castings, see D-003) |
| R-07 | Four turbochargers, sequential strategy, derived sizing, system diagram [8] | `08_SIMULATIONS/analytical/01_performance_turbocharging.md`, `06_ASSEMBLIES/system_diagrams/01_*` | done (1-D) |
| R-08 | Intake and water-to-air charge cooling with calculations [9] | `08_SIMULATIONS/analytical/04_thermal_lube_fuel.md` | done (1-D) |
| R-09 | Duplex injection (32), ignition, sensors, EMS concept [10] | `06_ASSEMBLIES/system_diagrams/04_*`, CAD group 11 | done (concept, no calibration) |
| R-10 | Dry-sump lubrication with flows and diagram [11] | same report, `system_diagrams/03_*` | done (1-D) |
| R-11 | Cooling circuits, thermal results, hot spots [12] | same report, `08_SIMULATIONS/fea/` thermal cases | done (1-D + FE slices) |
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

| Criterion | Result | Evidence |
|---|---|---|
| All sixteen cylinders are represented | PASS | 16 bores in the block CAD; pistons x16 |
| Four cylinder banks (rows) correctly organised | PASS | two VR8 banks at 90 deg, each with two rows at 15 deg; firing intervals 45.000 deg (layout check) |
| Engine architecture mechanically coherent | PARTIAL - packaging overlaps listed | interference check: 35 static and 1 kinematic clash pairs remain (listed in the report) |
| Displacement consistent with bore and stroke | PASS | 7992.92 cm3 vs 7,993 cm3 published |
| All sixteen piston assemblies modelled | PASS | pistons 16, pins 16, rings 48 |
| Shared crankshaft modelled | PASS | one-piece crank, 8 pins, 9 mains, distributed counterweights |
| All connecting rods represented | PASS | rods x16 with caps, shells, bushes, bolts |
| Cylinder heads and the 64-valve system modelled | PASS | 64 valves, 64 springs/retainers/followers/support elements, 4 camshafts; **two head castings serve the four rows** (documented architecture, decision D-003) |
| Four turbochargers modelled | PASS | 2 RH + 2 LH units with housings, wheels, bearing housing, actuator |
| Sequential turbocharging flow architecture documented | PASS | diagram + animation + matching calculation |
| Intake and exhaust systems connected | PASS | manifolds, coolers, charge pipes, logs, cross-over, down-pipes modelled per bank |
| Fuel injection and ignition represented | PASS | 32 injectors, 4 rails, 16 plugs, 16 coils; EMS architecture diagram |
| Lubrication and cooling circuits modelled | PASS | galleries and jackets are real passages in block/heads; external circuit parts and 1-D flow calculations |
| Major mechanical interfaces validated | PARTIAL | CAD interference check (static all-pairs + 12 crank angles); CAD compression ratio 9.00, 9.00 |
| Parametric CAD files editable | PASS | geometry is generated from `src/w16/params.py`; BREP per part in `05_COMPONENT_CAD/` |
| STEP exports generated | PASS | 166 component STEP files; master assembly 186.33 MB; 15 sub-assemblies |
| STL and 3MF exports generated where supported | PASS | 166 STL, 159 3MF component files |
| Exploded assembly documentation complete | PASS | exploded views + hierarchy |
| Engineering drawings available | PASS | 9 sheets (PDF/SVG/PNG) |
| Simulation evidence documented | PASS | FE cases run: block, crank, head, insert, piston, rod; not run: none; 0-D/1-D models in `08_SIMULATIONS/analytical`. No 3-D CFD. |
| BOM complete | PASS | 151 part numbers (modelled content only) |
| Final technical report produced | see file | `12_FINAL_REPORT/` (Markdown + PDF) |
| Deliverables organised in the structured directory | PASS | folders 01-14 + 00_PROJECT_CONTROL + src |
| Piston at operating temperature: hot fatigue (engineering check added 2026-11-20, not in brief section 21) | NOT ASSESSABLE - OPEN | **hot fatigue NOT ASSESSABLE with available public data** (the method fails even production-range temperatures: with Woschni x 1.0 the crown runs at 272 degC, inside the 270-310 degC range of production gasoline pistons, and the factors are still 0.23-0.51); crown 376 degC (heat-consistent, Woschni x 2.0) is above the typical 270-310 degC range - **OPEN: cooling upgrade + hot-strength piston alloy with manufacturer data**; factor 0.10-0.28 with 4032-T6 strength after 10,000 h at temperature (section 8.1); the room-temperature factor 2.05 is not an acceptance measure |
