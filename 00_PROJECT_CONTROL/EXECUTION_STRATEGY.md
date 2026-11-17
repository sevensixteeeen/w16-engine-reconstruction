# Execution strategy — W16 engineering reconstruction

Read this file first when resuming work. Then read `PROGRESS.md` (where we are) and
`DECISIONS.md` (what has been fixed and why).

## 1. What this project is

An engineering-grade digital reconstruction of an 8.0 L quad-turbocharged W16 based on the
**publicly documented** architecture of the Bugatti Chiron engine. It is not a copy of
proprietary drawings: every value is tagged as one of

| Tag | Meaning |
|---|---|
| `PUB` | Publicly documented (manufacturer press material or VW Group technical literature) |
| `SEC` | Reported by secondary sources only (spec databases, press articles) — unconfirmed |
| `CALC` | Calculated in this project from other values |
| `EST` | Engineering estimate / provisional design value chosen in this project |

## 2. Environment found on this machine (2026-11-14)

| Capability | Status | Consequence |
|---|---|---|
| Desktop CAD (FreeCAD, SolidWorks, Fusion, …) | none installed | CAD is done in code |
| Programmatic CAD | `build123d` (OpenCascade kernel) in `.venv` (Python 3.12 via `uv`) | Native model = parametric Python source + BREP; STEP/STL/3MF exports |
| FEA | `gmsh` (meshing) + `scikit-fem` (linear elastic / steady thermal, tetrahedra) | Real FE runs, linear only; no contact, no plasticity, no fatigue solver |
| CFD | none (no OpenFOAM/Fluent on Windows here) | 1-D network / analytical flow models only — stated as such, never called CFD |
| Rendering | `pyvista` (VTK off-screen) + `matplotlib` | Shaded views, cutaways, exploded views, GIF/MP4 animations |
| PDF | Edge/Chrome headless print-to-PDF from HTML | Final report PDF |
| System Python | 3.15.2 (no wheels for the CAD kernel) | Not used; `.venv` only |

## 3. Method

1. **Single source of truth.** `src/w16/params.py` holds every master dimension with its tag.
   No dimension is typed twice. Geometry, calculations, drawings and the BOM all import it.
2. **Top-down.** Research → reference spec → architecture/layout (skeleton) → analytical
   sizing → component CAD → assembly + interference check → simulation → documentation.
3. **Everything is regenerable.** `python -m w16.build <stage>` rebuilds any stage. Outputs are
   never edited by hand.
4. **Evidence over prose.** A result is only reported if the script that produced it ran;
   every report records its inputs, solver and limitations. Failures are logged, not hidden.
5. **Context management.** Work proceeds in stages; after each stage `PROGRESS.md` is updated
   with what was produced, what was verified and what is next, so a new session can resume
   from the files alone.

## 4. Stage list

| # | Stage | Main outputs |
|---|---|---|
| 0 | Environment, branch, skeleton | this folder |
| 1 | Research | `01_RESEARCH/` |
| 2 | Requirements + reference spec | `02_…/`, `03_…/` |
| 3 | Architecture + analytical models (kinematics, balance, cycle, turbo, thermal, lube) | `src/w16/analysis/`, `08_SIMULATIONS/analytical/` |
| 4 | Component CAD | `05_COMPONENT_CAD/` |
| 5 | Master assembly, interference checks, exports | `04_…/`, `06_…/`, `13_…/`, `14_…/` |
| 6 | Drawings, views, animations | `07_…/`, `09_…/` |
| 7 | FEA / thermal / flow simulation | `08_SIMULATIONS/` |
| 8 | BOM, manufacturing docs | `10_…/`, `11_…/` |
| 9 | Final report (MD + PDF), acceptance check | `12_FINAL_REPORT/` |

## 5. Honest scope limits (decided up front)

- No proprietary OEM geometry is available; internal dimensions are provisional (`EST`/`CALC`).
- No 3-D CFD, no combustion CFD, no non-linear/contact FEA, no fatigue solver, no ECU calibration.
- Turbomachinery is sized by 1-D matching; wheel geometry is representative, not aero-designed.
- The package is a foundation for prototype engineering, not a release-to-manufacture data set.
