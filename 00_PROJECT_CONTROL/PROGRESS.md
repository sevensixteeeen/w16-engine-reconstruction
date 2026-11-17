# Progress — resume from here

_Last updated: 2026-11-17 18:30_

Read `EXECUTION_STRATEGY.md` and `DECISIONS.md` (D-001…D-040) first. Run everything from the project root with
`PYTHONPATH=src` and `.venv\Scripts\python.exe`.

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

1. **Three small valve-train contacts remain** (kinematic check, D-039): intake camshaft vs long-valve finger 0.72 / 1.26 mm³
   (lobe flank vs the finger-body corner on the pivot side of the roller) and head vs short intake valve 0.67 mm³ (seat
   pocket 1.5 mm deep is too shallow for the 1.2 mm valve margin between ~1.5 and 2.8 mm lift — applies to every valve).
   Proposed fixes (not applied, awaiting approval): seat pocket 3.5 mm deep; finger body corner lowered. Re-check needs a
   full interference run (~7 h).
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
