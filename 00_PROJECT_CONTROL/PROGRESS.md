# Progress — resume from here

_Last updated: 2026-11-21_

Read `EXECUTION_STRATEGY.md` and `DECISIONS.md` (D-001…D-044) first. Run everything from the project root with
`PYTHONPATH=src` and `.venv\Scripts\python.exe`.

## 2026-11-21 — regeneration finished; interference check completed (D-044)

- `run_regeneration.cmd` ran 2026-11-20 21:28 to 2026-11-21 12:56, all 9 stages exit 0 (`regen_logs/summary.json`; interference
  with 2 static + 1 kinematic worker, 10.6 GB available; the kinematic sweep took 14.4 h).
- **The static interference result was incomplete**: worker 0 hit the old 2700 s default time budget (1550 of 3779 pairs) and
  exited 0 - 2229 of 7557 pairs unchecked. Fixed by D-044 (no default budget, worker / `interference()` exit 3, `meta.complete`,
  `recheck` command, clipped-solid check for touching pairs, report says INCOMPLETE / NOT VERIFIED). Rechecked only those pairs
  (not the kinematic sweep) and merged: **all 7557 static pairs checked, 35 static clash pairs (the same 35 as 2026-11-17),
  93 touching contacts (were "boolean errors"), 0 errors; kinematic 1 clash pair** (big-end shell / crankshaft). Run log:
  `06_ASSEMBLIES/interference_run.log`. Report regenerated (`python -m w16.docs`).
- Instances 1599 -> 1597: the exhaust secondary chains of both banks have 103 links instead of 104 - a rounding side effect of
  the D-042 deck change, odd link count; logged as an open item (DECISIONS), not changed.
- **Next study (unchanged, no geometry changes):** piston heat input / `woschni_scale` (see 2026-11-20 below).
- **Published** as its own public repository https://github.com/sevensixteeeen/w16-engine-reconstruction (no licence yet).
  Re-publish at milestones from the monorepo with `.venv\Scripts\python tools\publish_github.py --push` (split, strip, verify,
  push; it publishes committed history only). `01_RESEARCH/sources/` (VW SSP 248 copy and text extract) is git-ignored and
  stripped from the published history; SSP 248 is cited in `01_RESEARCH/RESEARCH_LOG.md` (S5). The report HTML no longer
  carries a local `<base href>`.

## D-041 + D-042 — applied in the source, verified by targeted checks; full regeneration approved 2026-11-20

**2026-11-20 — state before the regeneration (run by the user, not by Claude Code).**
- Regeneration approved: `run_regeneration.cmd` → `tools/regenerate_d042.py` (reports, assembly, export all, FE rod / crank /
  insert / block / head — **not the piston**, interference with 2 static + 3 kinematic workers if the measured build peak fits
  in RAM, else 2 / 1; render, drawings, diagrams, docs). Per-stage logs and peak RAM in `regen_logs/` (git-ignored, as is `regen_logs_console.log`); the chain stops at the
  first failing stage. The analytical stage gives the same rated-point piston heat as the committed piston FE (95.812 kW for
  16 pistons, checked 2026-11-20), so `fea/piston.json` stays consistent.
- `docs.py`: the report now states that the piston **fails hot fatigue** with the 10,000 h lower-bound data, that the
  room-temperature factor 2.05 is **not an acceptance measure**, and that **piston thermal design is OPEN** — status line under
  the title, FE table (fatigue row), FE findings, new section 8.1 (table per region, section values, hot tensile strength,
  consequences, method, source), limitations item 11, future work item 8, an added acceptance row (marked as not in the brief)
  and the manufacturing-spec piston row (also: compression height now from the parameter, was fixed text 38.5).
  `evidence()` reads only FE case records, so `piston_section_fatigue.json` is not counted as a seventh FE case. Tested
  end-to-end (MD / HTML / PDF) on a scratch copy of the evidence files, including a missing and a stale hot-fatigue record.
- Short-exposure strength data: dropped (decision of the user, 2026-11-20 — cannot change the conclusion).
- **Next study, after the regeneration (no geometry changes):** piston heat input — justify or correct `woschni_scale` 2.0;
  heat into the piston per cylinder (W and W/mm² of crown) against published ranges for high-output turbocharged SI engines,
  with sources; crown temperature at `woschni_scale` 1.0 / 1.5 / 2.0.

**Commits.** Backup of the D-040 state: commit `56f4d67`, tag `pre-D041` (branch `bugatti-w16-engine`), plus copies of
`interference_report.json` and `cad_validation.json` in `_backup_pre-D041/`. Everything since (D-041, D-042, records, head FE,
the untracking below) is in the commit that follows `56f4d67`. `13_EXPORTS_STEP/`, `14_EXPORTS_STL_3MF/` and `06_ASSEMBLIES/step/`
are git-ignored and no longer tracked (files stay on disk); they are still inside `56f4d67`, so a GitHub push needs that commit
rewritten first. Nothing has been pushed. Other staged items elsewhere in the repository were not committed.

**What changed.**
- **D-041** (`cad/head.py`): seat-insert pocket 3.5 mm deep (was 1.5); long-finger (W16-06-013) pivot-side corner chamfered.
- **D-042**: piston valve pockets 2.2 mm (`params.piston_valve_pocket_depth`, was 1.6), CR recalibrated (`CHAMBER_CAD_FACTOR`
  1.0725; crown tilt 16.01 deg, deck 0.19 mm lower), short-finger (W16-06-007) corner chamfered, analytic piston-to-valve
  formula corrected (crown taken under each rim point), piston 0.444 kg (CAD 0.4436).

**Verified on D-042** (targeted checks, both banks, mid phaser and intake ±26 / exhaust ±11 deg): CAD piston-to-valve ≥ 1.890 mm
(outer long intake at full advance; 1.342 before), inner long exhaust 4.738 mm at full retard; head vs valves no overlap (min
1.02 / 1.40 mm); finger bodies vs camshafts ≥ 1.49 mm (short finger 1.675 / 1.722, was 0.29 / 0.51); rollers in contact; CR
8.9998; head FE (`fea/head.json`): 9 zero-volume tets dropped, heat balance 0.0 %, valve bridge 220 / 159 degC.

**Piston FE on D-042 — VALID re-run of 2026-11-18 13:09** (user's terminal, log `08_SIMULATIONS/fea_piston_run.log`; log and
`piston.json` identical value for value; all D-043 guards passed: gas force −2.04 %, side force and point-support reactions ~1e-10 N
in both solved cases). Same mesh class as D-040 (81,483 tets, γ min 2.0e-5, none dropped). Solve 8,411 s (D-040 2,708 s —
probably paging, ~5 GB free afterwards). Against D-040:

| | D-042 | D-040 |
|---|---|---|
| Gas: peak / p99.9 | 171.2 / 107.2 MPa (slot-end corner (−11.8, −19.1, 10.6), 248 °C) | 181.8 / 105.4 (same corner) |
| Gas + thermal: peak / p99.9 | **277.2 / 138.9 MPa** (same corner, 248 °C) | 285.4 / 138.3 |
| Crown mean / max / top groove | 380.3 / 433.2 / 266.8 °C | 379.9 / 431.5 / 267.6 |
| Top-land radial growth vs cold clearance | **0.331 vs 0.430 mm → 0.10 mm hot** | 0.331 vs 0.430 |
| Crown deflection; bearing pressure | 0.093 mm; 85.3 MPa | 0.090; 85.3 |
| Fatigue factor, room-temperature limit (FE record) | 2.05 | 2.09 |

Thinnest crown section and temperature-dependent fatigue — `tools/piston_section_fatigue.py` →
`08_SIMULATIONS/fea/piston_section_fatigue.json`. The tool re-solves the same mesh with conjugate gradients (2 GB) and stops
unless it reproduces `piston.json`; worst difference 1.1e-10. Strength data: ASM Handbook Vol. 2 (1990), alloy 4032-T6 after
10,000 h at temperature (UTS 380 / 345 / 255 / 90 / 55 / 35 / 22 MPa and yield 315 / 305 / 230 / 60 / 35 / 20 / 14 MPa at
24 / 100 / 150 / 205 / 260 / 315 / 370 °C; fatigue 110 MPa at 5e8 cycles, room temperature); fatigue strength at temperature
scaled with UTS (EST — the source has no hot fatigue data for 4032).
- **Section under the long-valve pockets** (3.30 mm, pocket floor to gallery roof; both pockets): 319–378 °C, mean 354 °C;
  von Mises gas 110.6 / 116.2 MPa max, 53.8 mean; gas + thermal 125.2 / 126.8 max, 68 mean (max at 356 °C).
- **Fatigue (σa = ½ gas von Mises, against σf(T))**: section 0.13 (σa 58 MPa vs σf 7.3 MPa at 356 °C; Goodman 0.10); crown
  above the gallery 0.10 (388 °C; 0.1-percentile 0.14); slot-end corner 0.21 (248 °C); top ring groove 0.27 (301 °C); pin
  bosses 0.28 (267 °C). **With this data every hot region fails by a factor of 3–10.** The room-temperature factor 2.05 is not
  a valid acceptance measure.
- **Hot yield**: the gas + thermal stresses (139 MPa p99.9, 125 MPa in the section) are far above the hot yield of 4032-T6
  (41 MPa at 248 °C, 16 MPa at 355 °C): the linear-elastic gas + thermal result is beyond its range (plastic shake-down).
- Caveats: the 10,000-h data are the fully overaged lower bound, and scaling fatigue with UTS is an estimate. Real piston alloys
  hold more hot strength, but the margin is so large that the conclusion stands: at 355–430 °C the crown is above the usable
  range of a 4032-class alloy. The design needs a cooler crown (gallery / jet cooling — see the sensitivity: gallery 4,000 +
  under-crown 1,000 W/m²K gives 334 °C) and/or a hot-strength piston alloy or steel crown, with measured hot fatigue data.

**Piston FE (history) — the 23:21 run was INVALID; fixed by D-043.** The run of 2026-11-17 23:21
(`08_SIMULATIONS/fea/piston.json`, committed in `46a4cfe`) reported 640 / 143 MPa and a crown of 332 degC. Cause: the facet
band that selects the chamber side was a fixed 2.2 mm, and the D-042 pocket floors are exactly 2.2 mm deep. The floors (a third
of the crown) got no gas pressure and no gas-side heat: 58.4 kN + 5.27 kN sideways instead of 76.8 kN; the side load went into
the point support and produced the 640 MPa there; 3.7 instead of 5.4 kW into the crown. The run log was not written because the
run printed to the console. D-043 (approved 2026-11-18) ties the band to the pocket depth and adds guards that fail the case on a
wrong load or heat balance, a loaded-area change or a facet on a ring groove — before the solve and again after it. Verified
through the case code (thermal only): 76,817.3 N, no side force, heat applied 5,866 / 5,988 W (−2.04 %, the relieved top-land
annulus, as D-040), crown 380.3 degC mean / 433.2 max, groove 266.8 degC (D-040: 379.9 / 431.5 / 267.6); coarse-mesh smoke test
of the whole case passed.

**Piston FE run command (from `cmd`, nothing else running, ~10 GB):**
```
cd bugatti_w16_engine
set PYTHONPATH=src
.venv\Scripts\python.exe -m w16.sim.fea piston > 08_SIMULATIONS\fea_piston_run.log 2>&1
```
Then check: `piston checks` line at the top of the log; `checks` in `piston.json` (solved_gas / solved_gas_thermal reactions
~0); no `piston_FAILED.json`; peak location back at the slot-end corner.

**Geometric checks on D-042 (2026-11-18)** — `tools/check_piston_clearances.py`, result `08_SIMULATIONS/clearance/piston_clearances.json`
(exact CAD distances; cylinder positions 1 and 2 of both banks, both valves of each pair; crank angle swept ±90 deg around
gas-exchange TDC, refined to 0.05 deg; the spread over banks / valve pairs is ≤ 0.003 mm, so one value per case).

Piston to valve (θ = deg after gas-exchange TDC; criterion 1.5 mm intake / 2.0 mm exhaust):

| Valve | Phaser advanced | Mid | Phaser retarded | Closest features (valve / piston) |
|---|---|---|---|---|
| Long intake (outer row) | **1.887** (+8.6°, 3.65 mm lift) | 3.670 (+1.5°, 0.16) | 3.756 (0°, closed) | rim edge / pocket floor (adv.); rim edge / pocket rim edge (mid, ret.) |
| Short intake (inner row) | 7.822 (+8.9°, 3.69) | 10.741 (+2.5°, 0.20) | 10.889 (0°, closed) | rim edge / crown plane |
| Long exhaust (inner row) | 5.445 (0°, closed) | 5.372 (−1.5°, 0.09) | **4.737** (−6.0°, 1.02) | rim edge / pocket floor |
| Short exhaust (outer row) | 10.977 (0°, closed) | 10.902 (−1.5°, 0.09) | 10.240 (−6.3°, 1.05) | rim edge / crown plane |

Phaser: intake ±26, exhaust ±11 deg crank. Binding case: long intake at full advance, 1.887 mm (the D-042 record's 1.890 mm is
the bank-1 value; bank 2 is 0.003 mm lower).

Why deeper pockets stopped helping beyond 2.2 mm (long intake, full advance, crown as built, no CR refit): 1.6 / 2.2 / 2.4 mm →
1.290 / 1.890 / 2.090 mm, all rim edge to **pocket floor** at +8.55° (one for one with depth). From 2.6 mm on, 2.104 mm at
every depth (2.6 / 3.0 / 4.0): the closest point moves to the **pocket rim edge on the outer side of the pocket** (piston
(±33.6, −25.1), where the pocket runs out towards the crown edge) at +6.45°, 3.35 mm lift — the valve rim passes over the
pocket's edge, which depth does not move. The plateau is 2.10 mm; the D-042 search with the CR refit gave 2.07 / 2.06 mm at
2.4 / 2.6 because each refit raises the crown (≈0.07 mm per 0.2 mm of depth). Beyond ~2.4 mm only a wider pocket or a
smaller crown tilt helps.

Crown to head at firing TDC (all four checked cylinders identical; D-040 baseline from the `pre-D041` source):

| | D-040 | D-042 |
|---|---|---|
| Minimum, whole piston top | 0.430 | 0.430 — crown edge / top land vs the bore cylinder of the chamber cut in the head (radial: r 42.57 vs 43.0; same as in the liner, not changed by the crown / deck change) |
| Crown faces vs chamber surfaces (without that wall and the joint face) | 2.766 | 2.770 — crown plane vs the roof / chamber-wall corner at the roof's low edge |
| Crown plane to roof plane, axial, minimum | 2.943 | 2.949 — at the crown's low edge (the deck clearance is set there, so the tilt change pivots about it) |
| Crown top above the head joint face | 10.855 | 11.247 (+0.39 at the high edge) |
| Nearest head part: outer intake seat insert vs pocket rim | 1.873 | 1.822 |
| Inner exhaust seat insert | 3.522 | 3.798 |
| Spark plug | 8.34 | 8.16 |

The 0.19 mm change raises the high side of the crown 0.39 mm further into the head but does not reduce the crown-to-roof
clearance (minimum at the low edge); the tightest head part is the intake seat insert, 1.82 mm, against the pocket rim.

**Not regenerated** (still the D-040 state): CAD exports, `cad_validation.json`, `interference_report.json`, views, animations,
drawings, BOM and final report. To finish, after approval: verify the piston FE; assembly; export all; FE rod (piston mass),
crank, insert, block (deck moved); interference (~7 h, faster with `E.interference(2, 3)`); render; drawings; diagrams; docs.

**Open items from D-041 / D-042.**
- **Piston hot fatigue fails** with temperature-dependent strength (factors 0.10–0.28, above) — the main open piston item; needs
  a cooling / material decision before the design is mechanically acceptable.
- Oil-ring land over the pin-bore exit 0.97 → 0.77 mm — logged as a detail-design open item (DECISIONS.md, 2026-11-18);
  crown under the pockets to the oil gallery 3.9 → 3.3 mm.
- Finger corner walls 1.7 mm (short finger W16-06-007, long finger W16-06-013) — logged as a detail-design open item.
- Outer-intake piston-to-valve at mid phaser 3.725 → 3.670 mm; the corrected analytic formula reads 1 mm high at mid phaser —
  use the CAD check for acceptance.
- Seat-insert pocket to water-jacket wall 1.23 / 1.49 mm — open detail-design item, deliberately not changed (see 1a below).

## Status — D-039 / D-040 regeneration complete (2026-11-17)

Every stage was re-run on the D-039 (valve train, head, piston / head) and D-040 (piston land reliefs, CR recalibration,
compression height 40 mm) geometry and its output checked.

| Stage | Done | Evidence |
|---|---|---|
| Analytical models | 00:57 | `08_SIMULATIONS/analytical/` — 1102.8 kW, 1600.2 N·m; piston-to-valve min 2.01 mm intake / 3.03 mm exhaust (criteria 1.5 / 2.0) |
| CAD, 15 sub-assemblies | 01:08 | `06_ASSEMBLIES/assembly_summary.json` — 151 part numbers, 1,599 instances, 344.5 kg; every part a single valid solid |
| CAD validation, exports | 01:13 | `06_ASSEMBLIES/cad_validation.json` — CR 9.0007 (V_tdc 62.44 cm³); envelope 976 × 900 × 832 mm; 166 STEP / BREP / STL, 159 3MF; master STEP 186.6 MB |
| FE (6 cases) | 01:14–11:57 | `08_SIMULATIONS/fea/` — rod 592 / 489 MPa, fatigue factor 1.18; piston gas 182 / 105 MPa, gas + thermal 285 / 138 MPa, crown 380 °C mean / 431 °C max, groove 268 °C, fatigue factor 2.09, top land 0.33 mm growth vs 0.43 mm clearance; crank factor 8.27; bearing cover yield factor 4.97; block bore out-of-round 511 µm; head valve bridge 220 °C |
| Interference check | 18:02 | `06_ASSEMBLIES/interference_report.json` — static: 4,850 clear, 2,500 intentional, 35 clash pairs (none in the valve train / pistons), 94 boolean errors; kinematic (12 angles): 11,853 clear, 4 clash pairs, 0 errors |
| Views, animations | 18:14 | `06_ASSEMBLIES/views/` (24), `09_ANIMATIONS/` (7 × GIF + MP4) |
| Drawings | 18:19 | `07_ENGINEERING_DRAWINGS/` (9 sheets × PDF / SVG / PNG) |
| System diagrams | 18:20 | `06_ASSEMBLIES/system_diagrams/` (4) |
| BOM, manufacturing spec, requirements, final report | 18:27 | `10_`, `11_`, `02_`, `12_FINAL_REPORT/` (MD + HTML + PDF) |

## Open engineering items (not hidden — listed in the report)

1. **Three small valve-train contacts** (kinematic check, D-039): intake camshaft vs long-valve finger 0.72 / 1.26 mm³ and
   head vs short intake valve 0.67 mm³. **Fixed in the source by D-041** (approved 2026-11-17) and verified by targeted
   checks (no overlap; long finger 1.49 / 1.57 mm, valve margin 1.70 mm while open); the full interference run on the D-041
   geometry is still to do.
1a. **Detail design — seat-insert pocket to water-jacket wall** (logged 2026-11-17; not changed, by decision): 1.23 mm intake /
   1.49 mm exhaust of cast metal at the pocket shoulder where the insert seats. Thin for a press-fit insert in cast Al-Si.
   Resolve in detail design (jacket keep-out around the pocket shoulder or a smaller insert OD), then re-check the head FE.
1b. **Piston-to-valve at the phaser extremes** (D-042): CAD 1.890 mm at full intake advance after the deeper pockets; the
   corrected analytic formula is optimistic at mid phaser (4.70 vs CAD 3.67 mm) — use the CAD check for acceptance.
2. **Piston thermal:** crown 380 °C mean / 431 °C max at rated power with the estimated oil-side coefficients (guide
   ~350 °C); hot strength / fatigue of boss and ring belt need a temperature-dependent analysis; the slot-end corner under
   the crown is unradiused in the concept CAD (mesh-dependent peak). The piston FE gas load is 2 % low (the relieved
   top-land annulus is not loaded).
2a. **Detail design — piston oil-ring land over the pin-bore exit 0.77 mm** (D-042; 0.97 mm in D-040; logged 2026-11-18):
   thin forged land next to the boss and the drain holes; local stress / temperature to be read from the valid D-042 piston FE;
   options and knock-on checks in DECISIONS.md (open items).
2b. **Detail design — piston slot-end corner: misses the 1.5 target; needs a real radius and a mesh-converged re-check**
   (logged 2026-11-20): unradiused in the concept CAD, carries the gas-case peak (171 MPa, mesh-dependent); room-temperature
   fatigue factor 1.29 — above 1.0, below the 1.5 target, whatever the crown temperature (DECISIONS.md, open items).
3. **Connecting rod:** fatigue factor 1.18 and yield factor 1.80 at overspeed (titanium rod).
4. **Tight valve-gear margins:** finger ratio 2.7 on the short valves; plug well vs cam core 0.945 mm; long-valve spring
   vs short-valve support-element boss 1.175 mm; piston-cooling jet vs rod about 2.3 mm (D-036).
4a. **Detail design — finger-follower corner walls 1.7 mm** (D-041 / D-042; logged 2026-11-18): the pivot-side chamfer leaves
   two 1.7 mm side walls, 10.8-11.0 mm high on the short-valve finger W16-06-007 (ratio 2.7, the higher load) and 11.8 mm on
   the long-valve finger W16-06-013; stiffness and stress at maximum cam force / overspeed not analysed (finger FE).
5. **Block thermal distortion:** block FE slice gives up to 511 µm bore out-of-round (upper bound, rigid base) — needs a
   full-block thermo-mechanical analysis with head clamp load.
6. **Packaging overlaps** outside the valve train (35 static pairs): air duct B vs charge pipe B (1.5 cm³), air duct A
   vs down-pipe B, chain guides through the chain housing, coolant pipes vs front cover, turbo vs down-pipe / shut-off
   valve / pre-cat, fuel rail vs head (0.12 cm³), engine-mount brackets, adjacent injectors, rod bearing shells on the
   crankpin (26.5 mm³).
7. Seven parts fail 3MF meshing; STL exists for all.

## Regenerating

```
python -m w16.reports             # analytical package
python -m w16.cad.assembly        # build + summary (castings cached in .cache/, ~12 min when the cache is cold)
python -m w16.cad.export all      # exports + hierarchy + validation (CR)
python -m w16.sim.fea <case>      # rod | piston | crank | insert | block | head  (after the assembly: it fills .cache/)
python -c "from w16.cad import export as E; E.interference(2, 1)"   # ~7 h (see below)
python -m w16.cad.render          # views + animations
python -m w16.cad.drawings        # drawings
python -m w16.diagrams
python -m w16.docs                # BOM, manufacturing spec, requirements, final report
```

Cautions:
- Any change to `params.py`, `layout.py` or `analysis/valvetrain.py` invalidates the casting cache.
- The geometry kernel is sensitive to tangent geometry in the head (D-039 item 8): keep the checked sequential cuts in
  `head.py`, and check the head FE mesh (`fea/head.json` → `dropped_zero_volume_tets`) after head changes.
- The kinematic interference sweep runs in one worker and takes ~7 h; ~70 % of it is the head / camshaft pairs (journals
  in their saddles at 0.03 mm clearance). Splitting the angles over more workers, e.g. `E.interference(2, 3)`, shortens it.
- The piston FE needs ~10 GB of the 15.6 GB RAM; run one heavy job at a time. Claude Code may stop background jobs when
  memory runs low while a session is idle.
- Work is committed on branch `bugatti-w16-engine` (see `git log -- .`); nothing has been pushed.
