# Master CAD definition

The master model is **parametric source code**, not a binary CAD file. One parameter file drives every solid, every
calculation and every document.

| What | Where |
|---|---|
| Master parameters (single source of truth, with provenance tags) | `src/w16/params.py` |
| Skeleton: coordinate system, cylinder table, crankpin phasing, deck geometry, kinematics | `src/w16/layout.py` |
| Head layout that closes the compression ratio (crown tilt) | `src/w16/analysis/valvetrain.py` (`finalize_geometry`) |
| Sub-assembly geometry | `src/w16/cad/block.py`, `cranktrain.py`, `head.py`, `timing.py`, `turbo.py`, `systems.py` |
| Master assembly (places every instance for a given crank angle) | `src/w16/cad/assembly.py` |
| Generated parameter table | `03_REFERENCE_SPECIFICATIONS/MASTER_PARAMETERS.md` |
| Native kernel geometry per part (OpenCascade BREP) + STEP | `05_COMPONENT_CAD/` |
| Neutral assembly files | `13_EXPORTS_STEP/W16_MASTER_ASSEMBLY.step`, `06_ASSEMBLIES/step/` |

## Datum system

- X = crankshaft axis, +X towards the flywheel end; x = 0 at main bearing 5.
- Z up (bisector of the 90 deg bank angle); bank 1 (cylinders 1-8) leans towards +Y, bank 2 (9-16) towards -Y.
- Crank angle 0 deg = cylinder 1 at firing TDC; the crank turns clockwise seen from the free end.
- Bank-local frame (x_l, u, v): v along the bank centre line, u outboard; in this frame both banks are identical
  (the long block has 2-fold symmetry about Z).

## How to edit

1. Change a value in `src/w16/params.py` (keep the tag honest: PUB / SEC / CALC / EST).
2. `python -m w16.reports` (calculations), then `python -m w16.cad.export all` (rebuild + exports + validation).
   Castings are cached in `.cache/`; a change to the parameters rebuilds them (about 10 minutes).
3. Check `06_ASSEMBLIES/cad_validation.json` (compression ratio, envelope) and re-run the interference check.

To open the geometry in a desktop CAD system, import the STEP files; each part is an exact B-rep solid.
