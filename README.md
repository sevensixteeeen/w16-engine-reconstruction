# W16 engine reconstruction — engineering package

> **Independent reconstruction from public data.** This is not manufacturer data and contains no Bugatti or
> Volkswagen Group drawings, CAD or documents. Every dimension and result is reconstructed here from published sources
> (listed with confidence levels in `01_RESEARCH`) or is an engineering estimate, and is tagged as such. Not affiliated
> with or endorsed by Bugatti or the Volkswagen Group; names are used only to identify the engine being studied.
> Not released for manufacture.

An 8.0 L quad-turbocharged W16 reconstructed from publicly documented information on the Bugatti Chiron engine.
Concept-level digital engineering: not manufacturer data, not released for manufacture. Every value is tagged
PUB (published), SEC (secondary source), CALC (calculated here) or EST (engineering estimate).

Start with `12_FINAL_REPORT/W16_ENGINEERING_REPORT.pdf`. To continue the work, read `00_PROJECT_CONTROL/PROGRESS.md`.

| Folder | Content |
|---|---|
| `00_PROJECT_CONTROL` | execution strategy, decision log, progress / resume notes |
| `01_RESEARCH` | source log with confidence levels (third-party sources are cited, not included) |
| `02_ENGINEERING_REQUIREMENTS` | requirements trace and acceptance table |
| `03_REFERENCE_SPECIFICATIONS` | reference specification, master parameter table |
| `04_MASTER_CAD` | how the parametric master model is defined and edited |
| `05_COMPONENT_CAD` | every part as STEP + BREP |
| `06_ASSEMBLIES` | hierarchy, views, schematics, validation and interference reports |
| `07_ENGINEERING_DRAWINGS` | drawing sheets (PDF, SVG, PNG) |
| `08_SIMULATIONS` | analytical reports, FE results |
| `09_ANIMATIONS` | GIF + MP4 |
| `10_BOM_AND_PROCUREMENT` | BOM (Markdown + CSV) |
| `11_MANUFACTURING_DOCUMENTATION` | materials, processes, tolerances classes, assembly sequence |
| `12_FINAL_REPORT` | engineering report (Markdown, HTML, PDF) |
| `13_EXPORTS_STEP` | master assembly STEP + component STEP - **not in the repository, regenerate (below)** |
| `14_EXPORTS_STL_3MF` | component STL / 3MF - **not in the repository, regenerate (below)** |
| `src/w16` | the parametric model, calculations and generators (Python) |
| `tools` | regeneration driver, checks, GitHub publishing script, one-off patch scripts kept for traceability |

## Regenerating the exports

The large generated CAD exports - `13_EXPORTS_STEP/`, `14_EXPORTS_STL_3MF/` and `06_ASSEMBLIES/step/` - are not tracked
(git-ignored). Everything is generated from `src/w16/params.py`. Windows, Python 3.12, from the repository root:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python -m w16.cad.export all
```

`export all` writes the component and assembly STEP / STL / 3MF files and the CAD validation (a few minutes, about 2 GB RAM).
The interference check is a separate, long run (`python -m w16.cad.export interference`, about 14 h). The full chain -
analysis, CAD, FE (except the piston), interference, renders, drawings, diagrams, report - is `run_regeneration.cmd`
(logs in `regen_logs/`; it stops at the first failing stage).
