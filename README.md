# W16 engine reconstruction — engineering package

An 8.0 L quad-turbocharged W16 reconstructed from publicly documented information on the Bugatti Chiron engine.
Concept-level digital engineering: not manufacturer data, not released for manufacture. Every value is tagged
PUB (published), SEC (secondary source), CALC (calculated here) or EST (engineering estimate).

Start with `12_FINAL_REPORT/W16_ENGINEERING_REPORT.pdf`. To continue the work, read `00_PROJECT_CONTROL/PROGRESS.md`.

| Folder | Content |
|---|---|
| `00_PROJECT_CONTROL` | execution strategy, decision log, progress / resume notes |
| `01_RESEARCH` | source log with confidence levels, VW SSP 248 reference |
| `02_ENGINEERING_REQUIREMENTS` | requirements trace and acceptance table |
| `03_REFERENCE_SPECIFICATIONS` | reference specification, master parameter table |
| `04_MASTER_CAD` | how the parametric master model is defined and edited |
| `05_COMPONENT_CAD` | every part as STEP + BREP |
| `06_ASSEMBLIES` | sub-assembly STEP files, hierarchy, views, schematics, validation and interference reports |
| `07_ENGINEERING_DRAWINGS` | drawing sheets (PDF, SVG, PNG) |
| `08_SIMULATIONS` | analytical reports, FE results |
| `09_ANIMATIONS` | GIF + MP4 |
| `10_BOM_AND_PROCUREMENT` | BOM (Markdown + CSV) |
| `11_MANUFACTURING_DOCUMENTATION` | materials, processes, tolerances classes, assembly sequence |
| `12_FINAL_REPORT` | engineering report (Markdown, HTML, PDF) |
| `13_EXPORTS_STEP` | master assembly STEP + component STEP |
| `14_EXPORTS_STL_3MF` | component STL / 3MF |
| `src/w16` | the parametric model, calculations and generators (Python) |
| `tools` | wheel downloader, one-off patch scripts kept for traceability |
