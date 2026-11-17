# W16 engine — valve-train and piston work: progress report

_Date: 2026-11-17 · Branch `bugatti-w16-engine` · Backup: commit `56f4d67`, tag `pre-D041`_

Concept-level engineering package (estimated values, not manufacturer data). Decisions referred to below are in
`00_PROJECT_CONTROL/DECISIONS.md`; the resume file is `00_PROJECT_CONTROL/PROGRESS.md`.

## 1. Status at a glance

| Area | Status |
|---|---|
| Valve-train clashes | Fixed. The D-039 rebuild cleared all but three small contacts; D-041 fixes those in the source and the targeted check finds no overlap. The full interference run on the D-041 geometry is **not done yet**. |
| Piston design | Fixed and verified (D-035 to D-040): solid ring belt, cooling gallery, boss and slot geometry, land reliefs, CR 9.00, FE re-run. |
| Piston FE | Done on the D-040 geometry: fatigue factor 2.09, top land keeps a hot clearance. |
| Full regeneration | Done for the D-040 state. D-041 is applied in `head.py` only; exports, interference report, drawings, BOM and final report are **still the D-040 state**. |
| Fails a criterion | **Piston to valve at full intake advance: 1.34 mm vs 1.5 mm required** (see section 3.1). |

## 2. What we did

### 2.1 Valve train

- **D-034 — layout fix.** The long valve's spring ran through the short valve's support element in 32 places (D-031). Two
  finger types (short valves ratio 2.7, long valves 1.65), exhaust valves moved to x = ±19 mm, the short valve's
  support-element boss hangs from the spark-plug tower, beehive springs (20 mm), installed height 38 mm.
- **D-039 — clashes found by the first 3-D interference run after D-034** (61 static / 33 kinematic pairs). Root causes found
  with direct boolean checks, then fixed:
  1. Chamber cut started 1 mm below the joint face on a 7.5° leaning axis, leaving a 3.9 cm³ wedge of head material over each
     bore. The opening long valves (up to 455 mm³) and the piston crown at TDC (212 mm³) ran into it. Cut now starts 10 mm below.
  2. The head chamber was centred on the bore axis at the deck, not at the head joint face (0.13 mm off). The crown scraped
     the chamber wall (60 mm³). Now centred at the joint face (`u_bore_head`).
  3. Camshaft exits at the drive end were missing: each shaft ran through 959 mm³ of head end wall and 639 mm³ of cam cover.
     Now 32 mm seal bores; the cam covers are now per bank (W16-02-003 bank 1, new W16-02-008 bank 2).
  4. Retainers ran 2 mm into the camshaft bearing webs (springs 1.5 mm). Webs now have spring / retainer pockets.
  5. The exhaust valve's back cone sat in the seat-insert throat corner. The throat was widened.
  6. Flat finger pad: the tilted valve tip cut 3–19 mm³ into it. Now a crowned pad (R 12 mm) solved for tangency, with a
     raised underside.
  7. Cam lobes assumed a roller moving straight at the cam. They are now generated from the real roller path, so the rollers
     stay in contact all round (gap ≤ 0.001 mm).
  8. Port fuse failure after the 0.13 mm layout shift. Fixed with joint spheres 0.05 mm smaller than the cylinders they join.
  9. Checker artefact: springs were not compressed in the kinematic sweep. Now compressed to the lift at each crank angle.
- **D-041 — the three small contacts left after D-039** (approved 2026-11-17):
  - Seat-insert pocket cut 3.5 mm below the seat plane on every valve (was 1.5 mm). Between about 1.6 and 2.8 mm lift the
    valve margin was shaving the pocket lip, on both intake types.
  - Long-valve finger (W16-06-013): the corner on the pivot side of the roller is chamfered (top edge 14.0 → 11.5 mm). The
    intake lobe flank had clipped it by 0.4 mm.

### 2.2 Piston

- **D-035 / D-036 — cooling and ring belt.** Solid ring belt with an oil cooling gallery. The gallery follows the slanted crown;
  crown 11 mm. The cooling jet is bent so the rod no longer strikes it.
- **D-037 — pin boss and slot geometry.** The D-036 cavity change had left a 1.75 mm sliver notch, where the 219 MPa peak sat.
  Fixes: bosses carried out to the cavity wall, R3 fillet, 4 mm pin-end land.
- **D-038 — CR recalibration after D-034.** The roof-tilt change had left the CAD at CR 8.92; recalibrated back to 9.00.
- **D-040 — land reliefs and CR after D-039.**
  - The FE showed 0.35 mm radial growth at the crown edge against only 0.03 mm cold clearance. The top land is now turned
    down 0.40 mm and the second land 0.25 mm.
  - The D-039 chamber added 3.7 cm³ and the reliefs 1.8 cm³ of crevice. Recalibrated to CR 9.0007: chamber factor 1.0578,
    crown tilt 15.76°.
  - The steeper crown pushed the oil-ring groove into the pin bore. Compression height raised to 40.0 mm (piston height 61.0)
    to restore a 0.97 mm land.
  - Piston mass is now 0.446 kg.

### 2.3 Analysis and tooling fixes

- **Piston FE support model (D-037).** Every "held pin bore" support restrained the bosses' thermal growth and gave false
  peaks of 1,190–1,550 MPa. The model now uses gas pressure on all chamber-side faces, a cosine pin-bearing load balanced to
  the gas load, and a 3-2-1 point support.
- **Bearing-selection bug (mine).** The pin load was being applied on bore-exit faces beyond the pin ends (|x| > 30 mm),
  giving a false 611 MPa. Fixed.
- **Head FE meshing.** The 0.05 mm port-bend steps (D-039 item 8) produced zero-volume elements and NaN temperatures. The
  mesher now drops elements with γ ≤ 1e-6 (25 in the head slice; none in any other case). I tried two other port-joint
  variants first; both broke either the mesh or the casting build, so I reverted them.
- **FE runner.** A stale `<case>_FAILED.json` is now removed after a successful run.
- **Report text.** The report now gives the real crank-angle count of the sweep (12, not 24).

### 2.4 Regeneration on the D-039 / D-040 geometry (all verified)

| Stage | Result |
|---|---|
| CAD | 151 part numbers, 1,599 instances, 344.5 kg; every part a single valid solid |
| Exports | 166 STEP / BREP / STL, 159 3MF; master STEP 186.6 MB |
| CR (CAD) | 9.0007 (V_tdc 62.44 cm³) |
| FE rod | 592 / 489 MPa at overspeed; yield factor 1.80, fatigue factor 1.18 |
| FE piston | gas 182 / 105 MPa; gas + thermal 285 / 138 MPa; crown 380 °C mean / 431 °C max; groove 268 °C; fatigue factor 2.09; top-land growth 0.33 mm vs 0.43 mm clearance |
| FE crank / bearing cover | 155 / 126 MPa, factor 8.27 / 89 / 75 MPa, factor 4.97 |
| FE block / head | bore out-of-round 511 µm / valve bridge 220 °C max (218 °C with D-041) |
| Interference | static 35 clash pairs (61 before), none in the valve train or pistons; kinematic 4 pairs (33 before): the 3 small valve-train contacts fixed by D-041, plus rod bearing shells on the crankpin (26.5 mm³) |
| Views, animations, drawings, diagrams, BOM, report | regenerated 18:04–18:27 |

### 2.5 D-041 targeted verification

Both banks; cylinder positions 1 and 2 (covering every valve type, every camshaft and both finger types); 2° crank steps
across each lift window; mid phaser and intake ±26° / exhaust ±11°.

| Check | Result |
|---|---|
| Valve face + margin vs head, while opening | old pocket: both intake types overlapped (0.67 mm³); new: no overlap, min 1.70 mm (short intake 1.19 mm at full lift) |
| Head vs every valve type, whole lift window | no overlap; min 1.02 mm intake / 1.40 mm exhaust (closed valve, behind the seat insert) |
| Camshaft vs long-valve finger body | 1.49 mm intake / 1.57 mm exhaust (was −0.4 mm) |
| Camshaft vs short-valve finger body | 0.29 mm intake / 0.51 mm exhaust (not changed by D-041) |
| Rollers on lobes | in contact, gap 0–0.001 mm |
| CR | 9.0007 by the CAD-validation method (unchanged); 8.9993 if the extra 10.7 mm³ per cylinder is counted (not recalibrated) |
| Walls | pocket to jacket 1.23 / 1.49 mm (unchanged); pocket to other port 7.65 / 8.67 mm; valve bridge 2.60 / 3.41 mm |
| Finger corner section | two 1.7 mm walls, 11.8 mm high (14.3 before); roller, pad and finger motion unchanged |
| Head FE | 35 zero-volume elements dropped (25 before); heat balance 0.0 % |
| Piston to valve | see 3.1 |

## 3. What fails / is open

### 3.1 Fails a criterion

- **Piston to valve at full intake advance.** The outer-row long intake comes within **1.34 mm** of the piston (CAD) at 26°
  advance, 8.5° after gas-exchange TDC, 3.6 mm lift. The criterion is 1.5 mm; the analytic method gives −0.63 mm. Mid phaser
  gives 3.73 mm, and 1.5 mm is met up to 24° advance. D-041 did not cause this: the phaser extremes had never been checked.
  The exhaust at 11° retard passes (4.20 mm CAD).

### 3.2 Not yet regenerated (D-041)

- CAD exports, `cad_validation.json`, `interference_report.json`, views, animations, drawings, BOM and the final report are the
  D-040 state. The final report therefore still lists the three small valve-train contacts and rates "mechanically coherent"
  as PARTIAL.
- The full interference sweep takes about 7 h. About 70 % of that time is the head / camshaft pairs (journals in their saddles
  at 0.03 mm clearance).

### 3.3 Tight or marginal (no overlap, but small)

| Item | Value |
|---|---|
| Short-valve finger vs camshafts (pivot-side corner) | 0.29 mm intake / 0.51 mm exhaust |
| Seat pocket to water jacket (at the insert shoulder) | 1.23 mm intake / 1.49 mm exhaust — thin for a press-fit insert in cast Al |
| Plug well vs cam core | 0.945 mm |
| Long-valve spring vs short-valve support-element boss | 1.175 mm |
| Piston-cooling jet vs rod | about 2.3 mm |
| Short-valve finger ratio | 2.7 (stiffness / contact stress to check) |
| Connecting rod at overspeed | fatigue factor 1.18, yield factor 1.80 |

### 3.4 Other open engineering items

- **Piston thermal.** Crown 380 °C mean / 431 °C max against the ~350 °C guide. Hot strength and fatigue of the boss and ring
  belt need a temperature-dependent analysis. The slot-end corner is unradiused in the concept CAD, so its peak is
  mesh-dependent. The FE gas load is 2 % low because the relieved top-land annulus is not loaded.
- **Block thermal distortion.** 511 µm bore out-of-round (upper bound from a slice) needs a full-block analysis.
- **Packaging overlaps outside the valve train.** 35 static pairs: ducts vs pipes, chain guides vs chain housing, turbo vs
  exhaust parts, coolant pipes, fuel rail vs head 0.12 cm³, engine mounts, injectors. Plus the rod bearing shells on the
  crankpin (26.5 mm³).
- **Exports.** Seven parts fail 3MF meshing; STL exists for all.
- **Head FE mesh.** About 1,000 poorly shaped elements (γ < 0.1); local peaks are unreliable.

### 3.5 Process failures during the work

- **Regeneration chain killed.** The first chain was killed when the session ended (during the piston FE).
- **Memory stop.** The resumed chain was stopped by Claude Code for low memory; the piston FE needs about 10 GB.
- **Leftover process.** A process I was not permitted to end finished the run unattended. All its outputs were checked.
- **Permission denials.** Ending that process and the first `git commit` were denied; the commit was then run by the user.
- **My own regression.** My first port-joint change broke the head FE mesh; it was found and fixed.
- **GitHub limit.** Two committed files exceed GitHub's 100 MB limit: the master STEP (186.6 MB) and the valve-train
  sub-assembly STEP (100.4 MB). Pushing needs Git LFS or leaving those exports out.

## 4. State of the files

| Current (D-041) | Still D-040 |
|---|---|
| `src/w16/cad/head.py`, `DECISIONS.md` (D-041), `PROGRESS.md`, `08_SIMULATIONS/fea/head.json`, `.cache/` head core and camshafts | `05_COMPONENT_CAD/`, `13_EXPORTS_STEP/`, `14_EXPORTS_STL_3MF/`, `06_ASSEMBLIES/` (incl. `cad_validation.json`, `interference_report.json`), `07_ENGINEERING_DRAWINGS/`, `09_ANIMATIONS/`, `10_`, `11_`, `12_FINAL_REPORT/` |

Backup of the D-040 state: commit `56f4d67` / tag `pre-D041`, and `_backup_pre-D041/` (interference report and CAD validation).

## 5. Decisions needed

1. **Piston to valve at full intake advance.** Options: limit the advance to 24°, deepen the outer-row piston valve pockets
   by about 0.2–0.3 mm, or accept 1.34 mm.
2. **Short-valve finger.** Whether to give W16-06-007 the same corner chamfer (0.29 / 0.51 mm today).
3. **Seat pocket to water jacket wall** (1.23 / 1.49 mm). Fix now, or leave it to detail design.
4. Then the regeneration: assembly, export, interference (about 7 h, faster with more kinematic workers), render, drawings,
   diagrams, docs.

## 6. Resume commands

```
python -m w16.cad.assembly
python -m w16.cad.export all
python -m w16.sim.fea head        # piston / rod / crank / insert / block are unaffected by D-041
python -c "from w16.cad import export as E; E.interference(2, 3)"
python -m w16.cad.render ; python -m w16.cad.drawings ; python -m w16.diagrams ; python -m w16.docs
```

Run from the project root with `PYTHONPATH=src` and `.venv\Scripts\python.exe`, one heavy job at a time (15.6 GB RAM).
