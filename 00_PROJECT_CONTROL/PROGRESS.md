# Progress — resume from here

_Last updated: 2026-11-18_

Read `EXECUTION_STRATEGY.md` and `DECISIONS.md` (D-001…D-042) first. Run everything from the project root with
`PYTHONPATH=src` and `.venv\Scripts\python.exe`.

## D-041 + D-042 — applied in the source, verified by targeted checks, NOT regenerated (awaiting approval)

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

**Piston FE — NOT verified.** The run started here at 22:12 was stopped by Claude Code's low-memory guard. The user re-ran it in
their own terminal; it finished 23:21 and wrote `08_SIMULATIONS/fea/piston.json`. Reported by the user, not yet checked: peak
stress 640 MPa (182 MPa on D-040), crown temperature 332 degC (380 degC on D-040). The run log
`08_SIMULATIONS/fea_piston_run.log` was not updated (still the 22:31 file, restored to the D-040 log content). A 3.5x jump in
peak stress from a 0.6 mm deeper pocket is not plausible on its own — check the peak location, mesh (gamma min, dropped
tets), load balance and support reactions in `piston.json` before using any of these numbers. D-042 in DECISIONS.md still says
the piston FE is not available.

**Not regenerated** (still the D-040 state): CAD exports, `cad_validation.json`, `interference_report.json`, views, animations,
drawings, BOM and final report. To finish, after approval: verify the piston FE; assembly; export all; FE rod (piston mass),
crank, insert, block (deck moved); interference (~7 h, faster with `E.interference(2, 3)`); render; drawings; diagrams; docs.

**Open items from D-041 / D-042.**
- Piston FE result above — unverified, suspect.
- Oil-ring land over the pin-bore exit 0.97 → 0.77 mm; crown under the pockets to the oil gallery 3.9 → 3.3 mm.
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
3. **Connecting rod:** fatigue factor 1.18 and yield factor 1.80 at overspeed (titanium rod).
4. **Tight valve-gear margins:** finger ratio 2.7 on the short valves; plug well vs cam core 0.945 mm; long-valve spring
   vs short-valve support-element boss 1.175 mm; piston-cooling jet vs rod about 2.3 mm (D-036).
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
- Nothing is committed; branch `bugatti-w16-engine`.
