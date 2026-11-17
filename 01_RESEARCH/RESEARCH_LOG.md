# Research log — Bugatti W16 public technical record

Compiled 2026-11-14. Every statement is tagged with a confidence level:

- **A — manufacturer primary** (Bugatti Newsroom press releases, VW Group service literature)
- **B — reputable secondary** (specialist press repeating manufacturer briefings)
- **C — aggregator / wiki / unattributed** (spec databases, fan wikis) — treated as unconfirmed
- **D — not found in public sources** — must be derived in this project

## 1. Sources consulted

| ID | Source | Type | URL |
|---|---|---|---|
| S1 | Bugatti Newsroom — "Bugatti W16 engine: the last of its kind" | A | https://newsroom.bugatti.com/press-releases/bugatti-w16-engine-the-last-of-its-kind |
| S2 | Bugatti Newsroom — Geneva International Motor Show 2016 (Chiron world premiere) | A | https://newsroom.bugatti.com/press-releases/geneva-international-motor-show-2016 |
| S3 | Bugatti Newsroom — 37th Vienna Motor Symposium: the new Bugatti Chiron | A | https://newsroom.bugatti.com/press-releases/37-wiener-motorensymposium-der-neue-bugatti-chiron |
| S4 | Bugatti model page (Centodieci / Chiron technical data) | A | https://www.bugatti.com/models/centodieci |
| S5 | VW Self-Study Programme 248 "The W Engine Concept" (W8/W12 family; copy saved in `sources/`) | A (for the VW W family, not W16-specific) | https://www.thedrive.com/uploads/2023/08/02/SSP_248.pdf |
| S6 | Jalopnik — "The incredible tech in the new Bugatti Chiron" | B | https://jalopnik.com/the-incredible-tech-in-the-new-bugatti-chiron-the-worl-1761998342 |
| S7 | Motor Authority — "A close look at the Bugatti Chiron's monster W-16 engine" | B | https://www.motorauthority.com/news/1102657_a-close-look-at-the-bugatti-chirons-monster-w-16-engine |
| S8 | Motor1 — "Bugatti highlights quad-turbo W16 engine's complex development" | B | https://www.motor1.com/news/601356/bugatti-quad-turbo-w16-engine/ |
| S9 | Simanaitis Says — "You want cylinders? We got 'em" (firing order, dry sump) | B/C | https://simanaitissays.com/2016/05/27/you-want-cylinders-we-got-em/ |
| S10 | Spec aggregators (autotijd.be, auto-data.net, zigwheels, W16 wiki mirrors) | C | https://www.auto-data.net/en/bugatti-chiron-8.0-w16-1500hp-awd-dsg-23587 ; https://automobile.fandom.com/wiki/W16_engine ; https://www.zigwheels.ae/car-news/bugatti-chiron-engine-explained-why-its-still-engineering-royalty |
| S11 | carscounsel.com W16 firing order (conflicting sequence) | C — rejected, see §3 | https://carscounsel.com/w16-firing-order/ |

## 2. Findings by research topic

### 2.1 History of the W16 (S1)
- Development began 1997 (Ferdinand Piëch's envelope sketch); first concept was an 18-cylinder, then the W16. — A
- First ran at 1,001 PS in 2001; Veyron 16.4 (2005) 1,001 PS; Veyron Super Sport (2010) 1,200 PS; Chiron (2016) 1,500 PS; Chiron Super Sport / Centodieci 1,600 PS. — A
- Chiron engine was "almost completely redesigned"; the only carry-over items were the compact shape and the **cylinder pitch of 73 mm**. — A
- 3,712 individual parts; hand-assembled by two specialists in six days at Salzgitter. — A
- "No bigger than a V12", about **400 kg**. — A. Length 710 mm. — C

### 2.2 Bank arrangement (S1, S5, S10)
- 16 cylinders in W layout: two eight-cylinder banks at a right angle (90°). — A
- Each eight-cylinder bank is a narrow-angle "VR" unit with two staggered rows of four cylinders at 15°. — A for the VW W family (S5); B/C for the W16 specifically
- VW W8/W12 use 72° between VR banks; the W16 uses 90°. — B

### 2.3 Crankshaft (S1, S9, S10)
- Single shared crankshaft; die-forged steel. — C
- Firing gaps of 45° ("asymmetric firing order with firing gaps of just 45 degrees"). — A
- Firing order 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10. — B/C (two independent secondary sources agree)
- Number of main bearings, journal diameters, crankpin phasing, counterweighting: **D**

### 2.4 Cylinder block (S1, S10)
- Aluminium alloy block is generally reported; exact alloy, liner technology and bedplate design: **D** for the W16. VW W12 practice (S5) is used as the engineering precedent.

### 2.5 Cylinder heads and valves (S5, S10)
- 64 valves (4 per cylinder). — A
- Four overhead camshafts in total: because of the narrow VR angle one head serves both rows of a bank, with two camshafts per head. — B/C (consistent with VW W-family practice in S5)
- Valve sizes, lift, timing, follower type for the W16: **D**

### 2.6 Pistons and connecting rods
- Titanium connecting rods. — C. Piston design, rod length, pin diameter: **D**
- Compression ratio 9.0:1 (widely quoted, originates from Veyron data). — C
- Bore × stroke 86 × 86 mm. — C, but arithmetically consistent with the A-level displacement of 7,993 cm³ (see `03_REFERENCE_SPECIFICATIONS`)

### 2.7 Turbocharging (S1, S2, S6)
- Four exhaust-gas turbochargers, two per eight-cylinder bank. — A
- Two-stage **sequential** (register) charging: only two turbochargers run at low speed; the other two are brought in at about **3,800 rpm**. — A
- The permanently running and the switchable turbocharger are the same size; each must supply air for about 380 PS; Chiron turbochargers are 69 % larger than the Veyron's. — A
- The exhaust-side switching valve must survive 980 °C (special high-temperature alloy). — A
- Boost pressure: Veyron "15.8 psi" (C); Chiron values of about 1.85 bar gauge circulate but no A/B source was found — **D**, derived here from airflow.
- Compressor/turbine wheel sizes and maps: **D**

### 2.8 Intake (S2)
- More than 60,000 litres of air per minute at full load. — A
- Carbon-fibre intake tube and charge-air system. — A. Manifold/plenum geometry: **D**

### 2.9 Exhaust (S2, S6)
- Titanium exhaust system with reduced back-pressure; 4 pre-catalysts + 2 main catalysts (each about six times the size of a mid-size car's); 230,266 m² active surface; titanium silencer 20 kg; six tailpipes. — A
- Manifold layout and port routing: **D**

### 2.10 Charge-air cooling (S1, S2)
- Water-to-air intercooling with **two heat exchangers on the engine**, a separate low-temperature circuit (12–15 L of coolant, one radiator, own pump). — A
- Charge air is cooled by as much as 130 K. — A

### 2.11 Engine cooling (S1, S2)
- High-temperature circuit 37–40 L, one main + two auxiliary radiators at the front; coolant pump moves **800 L/min**; whole volume circulated in about 3 s. — A
- Total heat to be rejected at full load "more than 3,000 hp". — A
- Ten coolers in the car in total (three engine-oil coolers reported by S6). — A/B

### 2.12 Fuel injection (S1, S2, S3)
- "Duplex" fuel injection with **32 injectors** (two per cylinder). — A
- Whether both injectors are port injectors: public descriptions indicate manifold injection; injector flow and rail pressure: **D**
- Bugatti Ion Current Sensing (BIS) at each spark plug for knock and misfire detection; reactions: retard ignition, cut the cylinder, or reduce boost. — A

### 2.13 Lubrication (S9)
- Dry-sump lubrication. — B/C. Pump stages, flows, pressures, tank volume: **D**

### 2.14 Timing drive (S2, S5)
- Chain drive ("chain housing" in carbon fibre is listed among the Chiron's lightweight parts). — A
- VW W-family practice: chain drive on the flywheel side with a primary chain to an intermediate shaft and secondary chains to the cylinder heads. — A for W8/W12 (S5); assumed for the W16

### 2.15 Accessory drive and mounting
- No reliable public data. **D** — engineered here.

## 3. Conflicts and how they were resolved

| Item | Conflict | Resolution |
|---|---|---|
| Firing order | S9/S10 give 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10; S11 gives a different sequence | A kinematic consistency test was run (see `03_REFERENCE_SPECIFICATIONS/REFERENCE_SPEC.md` §4): with cylinders *k* and *k+8* on a common crankpin and a 90° bank angle, the S9/S10 sequence gives exactly 90° between every pair and even 45° gaps. The S11 sequence does not. S9/S10 adopted. |
| Number of cylinder heads | The project brief asks for "four cylinder heads"; the documented architecture has **two** head castings, each covering the two rows of one VR8 bank | Follow the documented architecture: two head castings, four cylinder rows, four camshafts. Recorded as decision D-003. |
| Engine weight | "about 400 kg" (S1) vs. higher figures in some secondary sources for the Chiron | 400 kg used only as a plausibility reference for the CAD mass, as the brief requires. |

## 4. Unresolved engineering questions (carried into the design as provisional values)

1. Crankpin phasing and number of main bearings.
2. Connecting-rod length, journal diameters, bank offset.
3. Row offset ("désaxé") of the VR bores.
4. Valve sizes, lift, timing, follower type, cam-phaser fitment.
5. Compressor and turbine sizes, boost pressure versus speed, change-over logic details.
6. Injector sizing and fuel pressure.
7. Oil-pump stage count, flows and pressures.
8. Peak cylinder pressure and combustion phasing.
9. Exhaust manifold grouping per turbocharger.
10. Engine-mount positions and accessory layout.

Each is answered in `00_PROJECT_CONTROL/DECISIONS.md` with a derivation and labelled `EST` or `CALC`.
