"""CAD exports, assembly hierarchy, mass properties, compression-ratio check and interference checks.

    python -m w16.cad.export components      STEP / BREP / STL / 3MF of every part
    python -m w16.cad.export assemblies      sub-assembly and master-assembly STEP, hierarchy, mass report
    python -m w16.cad.export validate        CAD-measured compression ratio, envelope, crank balance
    python -m w16.cad.export interference    static + kinematic clash check (spawns worker processes)
"""
from __future__ import annotations
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import numpy as np
from build123d import Align, Box, Color, Compound, Cylinder, Location, Mesher, Pos, Rot, export_brep, export_step, export_stl

from ..params import P, MATERIALS
from .. import layout as L
from ..analysis import valvetrain as VT
from . import assembly as ASM, block as B, cranktrain as CT, head as H
from .common import COLORS, GROUPS, MAT, ROOT, bank_plane, cyl_between, head_plane, mass_props

D_COMP = os.path.join(ROOT, "05_COMPONENT_CAD")
D_ASM = os.path.join(ROOT, "06_ASSEMBLIES")
D_STEP = os.path.join(ROOT, "13_EXPORTS_STEP")
D_MESH = os.path.join(ROOT, "14_EXPORTS_STL_3MF")
D_MASTER = os.path.join(ROOT, "04_MASTER_CAD")


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def fname(p):
    return f"{slug(p.pn)}__{slug(p.name)}"


def gdir(base, g):
    d = os.path.join(base, f"{g}_{slug(GROUPS[g])}")
    os.makedirs(d, exist_ok=True)
    return d


def components(reg):
    log = []
    for p in reg.parts.values():
        base = fname(p)
        d5 = gdir(D_COMP, p.group)
        d13 = gdir(os.path.join(D_STEP, "components"), p.group)
        d14 = gdir(os.path.join(D_MESH, "components"), p.group)
        row = dict(pn=p.pn, name=p.name, group=p.group, step=False, brep=False, stl=False, threemf=False)
        shp = p.shape
        shp.label = base
        try:
            export_step(shp, os.path.join(d5, base + ".step"))
            shutil.copyfile(os.path.join(d5, base + ".step"), os.path.join(d13, base + ".step"))
            row["step"] = True
        except Exception as e:
            row["step_error"] = repr(e)[:120]
        try:
            export_brep(shp, os.path.join(d5, base + ".brep"))
            row["brep"] = True
        except Exception as e:
            row["brep_error"] = repr(e)[:120]
        tol = 0.05 if shp.volume < 5e4 else 0.12
        try:
            export_stl(shp, os.path.join(d14, base + ".stl"), tolerance=tol, angular_tolerance=0.2)
            row["stl"] = os.path.getsize(os.path.join(d14, base + ".stl")) > 200
        except Exception as e:
            row["stl_error"] = repr(e)[:120]
        try:
            m = Mesher()
            m.add_shape(shp, linear_deflection=tol, angular_deflection=0.2)
            m.write(os.path.join(d14, base + ".3mf"))
            row["threemf"] = True
        except Exception as e:
            row["threemf_error"] = repr(e)[:160]
        log.append(row)
    with open(os.path.join(D_STEP, "component_export_log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1)
    ok = lambda k: sum(1 for r in log if r[k])
    print(f"components: {len(log)} parts; STEP {ok('step')}, BREP {ok('brep')}, STL {ok('stl')}, 3MF {ok('threemf')}")
    return log


def group_compound(reg, g):
    kids = []
    for p in reg.by_group()[g]:
        col = Color(*COLORS[p.material])
        for k, loc in enumerate(p.locs):
            s = loc * p.shape
            s.label = f"{slug(p.pn)}_{k + 1:03d}"
            s.color = col
            kids.append(s)
    return Compound(children=kids, label=f"{g}_{slug(GROUPS[g])}")


def assemblies(reg, info):
    os.makedirs(os.path.join(D_ASM, "step"), exist_ok=True)
    comps = []
    log = {}
    for g in sorted(reg.by_group()):
        c = group_compound(reg, g)
        path = os.path.join(D_ASM, "step", f"W16_SUBASSY_{g}_{slug(GROUPS[g])}.step")
        t = time.time()
        export_step(c, path)
        log[g] = dict(file=os.path.basename(path), size_mb=round(os.path.getsize(path) / 1e6, 2), instances=len(c.children), seconds=round(time.time() - t, 1))
        comps.append(c)
        print("sub-assembly", g, log[g])
    master = Compound(children=comps, label="W16_ENGINE_MASTER_ASSEMBLY")
    path = os.path.join(D_STEP, "W16_MASTER_ASSEMBLY.step")
    t = time.time()
    export_step(master, path)
    log["master"] = dict(file=os.path.basename(path), size_mb=round(os.path.getsize(path) / 1e6, 2), seconds=round(time.time() - t, 1))
    print("master", log["master"])
    with open(os.path.join(D_STEP, "assembly_export_log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1)
    hierarchy(reg, info)
    return log


def bom_rows(reg):
    """One row per part number (geometry variants such as compressed springs are merged)."""
    rows = {}
    for p in reg.parts.values():
        key = p.pn.split("~")[0]
        r = rows.setdefault(key, dict(pn=key, name=p.name, group=p.group, material=MAT[p.material], qty=0, mass_each=p.mass, mass_total=0.0,
                                      process=p.process, custom=p.custom, note=p.note, moving=p.moving))
        chain = p.moving == "chain"
        r["qty"] += 0 if chain else p.qty
        r["mass_total"] += p.mass * p.qty
        if chain:
            r["qty"] = 4 if "Secondary" in p.name else 1
            r["mass_each"] = r["mass_total"] / r["qty"]
        if key.startswith("W16-07-008"):
            r["name"] = "Chain guide / tensioner rail"
    for r in rows.values():
        if r["qty"] and not r["pn"].startswith("W16-07-00"):
            r["mass_each"] = r["mass_total"] / r["qty"]
    return sorted(rows.values(), key=lambda r: r["pn"])


def hierarchy(reg, info):
    rows = bom_rows(reg)
    tot = sum(r["mass_total"] for r in rows)
    md = ["# Assembly hierarchy and mass report", "",
          "Generated by `python -m w16.cad.export assemblies` from the CAD registry (reference crank angle 0 deg = cylinder 1 at firing TDC).", "",
          "Masses are CAD volume x material density; items marked * use a catalogue/estimated mass (purchased parts whose solid is only an envelope).", "",
          "```", "W16_ENGINE_MASTER_ASSEMBLY"]
    for g in sorted(GROUPS):
        gr = [r for r in rows if r["group"] == g]
        if not gr:
            continue
        md.append(f"|- {g} {GROUPS[g]}   ({sum(r['qty'] for r in gr)} parts, {sum(r['mass_total'] for r in gr):.1f} kg)")
        for r in gr:
            md.append(f"|   |- {r['pn']:<28} x{r['qty']:<3} {r['name']}")
    md += ["```", "", "## Mass by sub-assembly", "", "| Group | Sub-assembly | Part numbers | Parts | Mass [kg] |", "|---|---|---|---|---|"]
    for g in sorted(GROUPS):
        gr = [r for r in rows if r["group"] == g]
        if gr:
            md.append(f"| {g} | {GROUPS[g]} | {len(gr)} | {sum(r['qty'] for r in gr)} | {sum(r['mass_total'] for r in gr):.1f} |")
    md.append(f"| | **Total** | **{len(rows)}** | **{sum(r['qty'] for r in rows)}** | **{tot:.1f}** |")
    veh = sum(r["mass_total"] for r in rows if "vehicle mounted" in r["name"] or r["pn"].endswith(("air_box-L1", "air_box-L2")))
    md += ["", f"Published reference: about {P.mass_ref_kg:.0f} kg (not a design target). The CAD total includes dressing items that published "
           f"engine weights usually exclude (pre-catalysts, air boxes, oil tank, charge-air coolers and ducts, accessories); "
           f"fluids are not included. Brackets, hoses, small fasteners, seals and wiring not modelled are also not included."]
    with open(os.path.join(D_ASM, "ASSEMBLY_HIERARCHY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    with open(os.path.join(D_ASM, "bom_rows.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    with open(os.path.join(D_ASM, "assembly_info.json"), "w", encoding="utf-8") as fh:
        json.dump(ASM_info_json(info), fh, indent=1)


def ASM_info_json(o):
    if isinstance(o, dict):
        return {str(k): ASM_info_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [ASM_info_json(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return float(o)
    return o


# ====================================================================== validation
def validate(reg, info):
    out = {}
    # --- compression ratio from CAD volumes: cylinder 1 (outer row) and 2 (inner row) at firing TDC
    for cno in (1, 2):
        c = L.CYL[cno]
        al = c.fire
        gp = bank_plane(c.bank)
        i = cno
        p0, d = B.axis_local(i)
        slab = lambda z0, h: Pos(0, 0, z0) * Box(2000, 2000, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        bore = cyl_between(p0 + d * (P.s_deck - 30.0), p0 + d * (P.s_deck + 14.0), P.bore / 2) & slab(0.0, P.deck_height)
        gask = cyl_between(p0 + d * (P.s_deck - 5.0), p0 + d * (P.s_deck + 8.0), P.gasket_bore / 2) & slab(P.deck_height, P.gasket_thk)
        gas_g = Location(gp) * (bore + gask)
        ch = Location(head_plane(c.bank)) * (H.chamber_tool(i) & slab(0.0, 200.0))
        vol = gas_g + ch
        # gas volume = everything above the piston crown surface (crown plane + valve pockets) + ring-land crevice
        from build123d import Plane
        ta = math.radians(P.crown_tilt_axis)
        n = (0.0, -math.sin(ta), math.cos(ta))
        ploc = CT.piston_location(c, al)
        above = ploc * (Plane(origin=(0, 0, P.comp_height), x_dir=(1, 0, 0), z_dir=n) * Box(400, 400, 300, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        v_above = (vol & above).volume
        pk = None
        for sx in (-1, 1):
            y0 = -P.valve_du_in
            zc = P.comp_height + y0 * math.tan(ta)
            org = (sx * 17.6 - 1.6 * n[0], y0 - 1.6 * n[1], zc - 1.6 * n[2])
            cyl = Plane(origin=org, x_dir=(1, 0, 0), z_dir=n) * Cylinder(P.valve_in_dia / 2 + 1.8, 1.6, align=(Align.CENTER, Align.CENTER, Align.MIN))
            pk = cyl if pk is None else pk + cyl
        v_pockets = ((ploc * pk) & vol).volume
        v_crev = VT.crevice_volume(P.crown_tilt_axis)            # top-land annulus (with the D-040 relief) + ring-groove clearances
        v_tdc = (v_above + v_pockets + v_crev) / 1000.0
        out[f"cyl{cno}"] = dict(v_tdc_cc=v_tdc, v_above_crown_cc=v_above / 1000.0, v_pockets_cc=v_pockets / 1000.0, v_crevice_cc=v_crev / 1000.0,
                                cr=(P.disp_cyl_cc + v_tdc) / v_tdc)
    out["cr_target"] = P.compression_ratio
    out["jacket_block_bank_l"] = B.jacket_void().volume / 1e6
    out["head_jacket"] = info.get("head_jacket", {})
    # --- envelope and centre of mass
    lo = np.array([1e9] * 3); hi = -lo
    lo_lb = lo.copy(); hi_lb = hi.copy()
    m_tot = 0.0; mom = np.zeros(3)
    for p in reg.parts.values():
        rho = p.mass / (p.shape.volume * 1e-9) if p.shape.volume > 0 else 0
        for loc in p.locs:
            s = loc * p.shape
            bb = s.bounding_box()
            a, b = np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])
            if "vehicle mounted" not in p.name:
                lo, hi = np.minimum(lo, a), np.maximum(hi, b)
            if p.group in ("01", "02", "03", "04", "05", "06", "07"):
                lo_lb, hi_lb = np.minimum(lo_lb, a), np.maximum(hi_lb, b)
            from build123d import CenterOf
            cm = s.center(CenterOf.MASS)
            mom += p.mass * np.array([cm.X, cm.Y, cm.Z]); m_tot += p.mass
    out["envelope_dressed_mm"] = dict(min=lo.tolist(), max=hi.tolist(), size=(hi - lo).tolist())
    out["envelope_long_block_mm"] = dict(min=lo_lb.tolist(), max=hi_lb.tolist(), size=(hi_lb - lo_lb).tolist())
    out["mass_total_kg"] = m_tot
    out["centre_of_mass_mm"] = (mom / m_tot).tolist()
    # --- crank balance from CAD mass properties + equivalent rod/piston masses
    cw = info["counterweights"]
    out["counterweights"] = cw["report"]
    with open(os.path.join(D_ASM, "cad_validation.json"), "w", encoding="utf-8") as fh:
        json.dump(ASM_info_json(out), fh, indent=1)
    print(json.dumps(ASM_info_json({k: out[k] for k in ("cyl1", "cyl2", "envelope_dressed_mm", "envelope_long_block_mm", "mass_total_kg", "centre_of_mass_mm")}), indent=1))
    return out


# ====================================================================== interference
EXPECTED = [  # (pattern a, pattern b, reason) - contacts / fits that are intentional
    (r"W16-15-|W16-04-005|damper_bolt", r".*", "threaded fastener in its thread / clearance hole"),
    (r"W16-06-005", r"W16-06-006|W16-02-00[12]", "valve spring seated on retainer / head"),
    (r"W16-02-00[567]", r"W16-02-00[12]", "press fit in the head"),
    (r"W16-07-00[56]", r"W16-07-00[13478]", "chain meshing with sprocket (links are envelopes)"),
    (r"W16-07-00[56]", r"W16-07-00[56]", "adjacent chain links"),
    (r"W16-11-003", r"W16-09-intake_manifold|W16-11-rail", "injector seated in manifold / rail"),
    (r"W16-14-sensor", r".*", "screw-in sensor in its boss"),
    (r"W16-11-001", r"W16-02-00[12]", "spark-plug thread"),
    (r"W16-01-007", r"W16-01-001", "jet pressed into the block"),
    (r"W16-14-harness", r".*", "harness routing envelope"),
    (r"W16-10-shutoff_valve", r"W16-10-manifold_rear", "flap-valve spindle through the manifold neck"),
    (r"W16-09-recirc_valve", r"W16-09-charge_pipe_B|W16-08-00[12]", "valve flanged to the charge pipe"),
    (r"W16-11-002", r"W16-11-001", "coil boot over the plug terminal"),
    (r"W16-13-water_pump_impeller", r"W16-13-water_pump_(housing|pulley)", "impeller shaft in the pump bearing / pulley hub"),
    (r"W16-14-damper_hub_pulley", r"W16-14-damper_ring|W16-14-damper_bolt", "bonded damper ring / bolt in hub"),
    (r"W16-14-accessory_belt", r"W16-14-|W16-13-water_pump_pulley", "belt wrapped on its pulleys"),
    (r"W16-14-mount_", r"W16-14-mount_", "isolator bonded to bracket"),
    (r"W16-12-scavenge_manifold", r"W16-12-oil_pump_stack|W16-01-004", "collector joined to pump and sump ports"),
    (r"W16-13-lt_hose", r"W16-13-lt_pump|W16-09-cac_core", "hose pushed on its stub"),
    (r"W16-10-crossover", r"W16-10-manifold", "cross-over slip joint in the manifold"),
    (r"W16-08-0", r"W16-08-0", "spigot fits / linkage inside the turbocharger"),
    (r"W16-09-(charge_pipe|air_duct)", r"W16-08-00[12]|W16-09-(air_box|throttle|cac_tank)", "duct / hose joint"),
    (r"W16-13-pump_inlet_pipe", r"W16-13-water_pump_housing", "pipe socketed in the pump"),
    (r"W16-07-009", r"W16-07-010|W16-01-001|W16-02-00[12]", "tensioner screwed into the case wall"),
    (r"W16-13-pipe_", r"W16-13-(water_pump_housing|thermostat_housing)|W16-01-001|W16-02-00[12]", "pipe socketed in its port"),
    (r"W16-12-oil_line_pressure", r"W16-12-oil_pump_stack|W16-14-front_cover|W16-01-001", "oil line fitting"),
]


def expected(a, b):
    for pa, pb, why in EXPECTED:
        if (re.match(pa, a) and re.match(pb, b)) or (re.match(pa, b) and re.match(pb, a)):
            return why
    return None


def instances(reg, locs=None, subset=False):
    """All placed solids with bounding boxes.  subset=True keeps, of the reciprocating / valve-gear parts, only those of
    the first two cylinders of each bank (the others are kinematically identical in their bank frames)."""
    out = []
    for p in reg.parts.values():
        ll = (locs or {}).get(p.pn, p.locs)
        n = len(ll)
        for k, loc in enumerate(ll):
            if subset and p.moving in ("rod", "piston", "valve") and n >= 16 and (k % (n // 2)) >= n // 8:
                continue
            s = loc * p.shape
            bb = s.bounding_box()
            out.append((p.pn, k, s, np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])))
    return out


def candidate_pairs(inst, only=None):
    n = len(inst)
    order = np.argsort([i[3][0] for i in inst])
    pairs = []
    for ii in range(n):
        a = inst[order[ii]]
        for jj in range(ii + 1, n):
            b = inst[order[jj]]
            if b[3][0] > a[4][0] - 0.05:
                break
            if np.any(a[3] > b[4] - 0.05) or np.any(b[3] > a[4] - 0.05):
                continue
            if a[0] == b[0] and a[0] not in ("W16-04-001", "W16-04-002", "W16-03-001"):
                continue
            if only and not (only(a[0]) or only(b[0])):
                continue
            pairs.append((int(order[ii]), int(order[jj])))
    return pairs


def check_pairs(inst, pairs, tol=0.5, budget=None):
    res = []
    t0 = time.time()
    for i, j in pairs:
        if budget and time.time() - t0 > budget:
            res.append(dict(a=inst[i][0], b=inst[j][0], status="unchecked"))
            continue
        a, b = inst[i], inst[j]
        why = expected(a[0], b[0])
        if why:
            res.append(dict(a=a[0], b=b[0], status="expected", reason=why))
            continue
        try:
            v = (a[2] & b[2]).volume
        except Exception as e:
            # boolean failed: fall back to the minimum distance between the two solids
            try:
                dist = a[2].distance_to(b[2])
            except Exception:
                dist = None
            if dist is not None and dist > 1e-3:
                res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status="clear", volume_mm3=0.0, by="distance"))
            else:
                res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status="error", reason=repr(e)[:80]))
            continue
        res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status="clash" if v > tol else "clear", volume_mm3=round(float(v), 2)))
    return res


def spring_instances(alpha, cache):
    """Valve springs of cylinder positions 1 and 2 of each bank (the kinematic subset) compressed to the lift at alpha."""
    out = []
    for b in (1, 2):
        for i in (1, 2):
            c = L.CYL[i if b == 1 else 17 - i]
            li, le = H.lifts(c, alpha)
            for kind, lift in (("in", li), ("ex", le)):
                for s in (-1, 1):
                    hkey = round((H.SEAT_DROP - 4.0 - lift) * 2) / 2
                    if hkey not in cache:
                        cache[hkey] = H.spring_solid(hkey)
                    sh = H.along_valve(b, i, kind, s, H.SEAT_DROP) * cache[hkey]
                    bb = sh.bounding_box()
                    out.append((f"W16-06-005~h{int(hkey * 10):03d}", len(out), sh, np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])))
    return out


def worker(k, n, mode):
    reg, info = ASM.build(0.0)
    out_dir = os.path.join(D_ASM, "interference")
    os.makedirs(out_dir, exist_ok=True)
    res = []
    if mode == "static":
        inst = instances(reg)
        pairs = candidate_pairs(inst)
        mine = pairs[k::n]
        res = check_pairs(inst, mine, budget=float(os.environ.get("W16_IC_BUDGET", "2700")))
        meta = dict(candidates=len(pairs), checked=sum(1 for r in res if r["status"] != "unchecked"), unchecked=sum(1 for r in res if r["status"] == "unchecked"), instances=len(inst))
    else:
        from . import render as R
        R.RING_Z = (info["piston"]["g1"], info["piston"]["g2"], info["piston"]["g3"])
        is_spring = lambda pn: pn.startswith("W16-06-005")
        mov = lambda pn: is_spring(pn) or reg.parts[pn].moving in ("crank", "rod", "piston", "valve", "cam")
        angles = list(np.arange(0.0, 720.0, 60.0))[k::n]
        meta = dict(angles=angles, checked=0)
        spring_cache = {}
        for al in angles:
            inst = instances(reg, R.moving_locs(reg, al), subset=True)
            # D-039: the registry holds the valve springs in their crank-angle-0 state; replace them by springs compressed
            # to the valve lift at this angle (the uncompressed springs used to run into the fingers of open valves)
            inst = [x for x in inst if not is_spring(x[0])] + spring_instances(al, spring_cache)
            pairs = candidate_pairs(inst, only=mov)
            r = check_pairs(inst, pairs)
            for x in r:
                x["alpha"] = al
            res += [x for x in r if x["status"] != "clear"] + [dict(status="clear_count", alpha=al, n=sum(1 for x in r if x["status"] == "clear"))]
            meta["checked"] += len(pairs)
    with open(os.path.join(out_dir, f"{mode}_{k}_of_{n}.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(meta=meta, results=res), fh)
    print("worker", mode, k, n, meta.get("checked"))


def interference(n_static=3, n_kin=2):
    out_dir = os.path.join(D_ASM, "interference")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    procs = [subprocess.Popen([sys.executable, "-m", "w16.cad.export", "worker", str(k), str(n_static), "static"], env=env, cwd=ROOT) for k in range(n_static)]
    procs += [subprocess.Popen([sys.executable, "-m", "w16.cad.export", "worker", str(k), str(n_kin), "kin"], env=env, cwd=ROOT) for k in range(n_kin)]
    codes = [p.wait() for p in procs]
    print("worker exit codes", codes)
    merge_interference()


def merge_interference():
    out_dir = os.path.join(D_ASM, "interference")
    stat, kin = [], []
    meta = dict(static_candidates=0, static_checked=0, kin_checked=0, kin_angles=[])
    for f in sorted(os.listdir(out_dir)):
        if not re.match(r"(static|kin)_\d+_of_\d+\.json", f):
            continue
        with open(os.path.join(out_dir, f), encoding="utf-8") as fh:
            d = json.load(fh)
        if f.startswith("static"):
            stat += d["results"]; meta["static_candidates"] = d["meta"]["candidates"]; meta["static_checked"] += d["meta"]["checked"]; meta["instances"] = d["meta"]["instances"]
            meta["static_unchecked"] = meta.get("static_unchecked", 0) + d["meta"].get("unchecked", 0)
        else:
            kin += d["results"]; meta["kin_checked"] += d["meta"]["checked"]; meta["kin_angles"] += d["meta"]["angles"]
    def agg(rows):
        g = {}
        for r in rows:
            if r["status"] != "clash":
                continue
            key = tuple(sorted((r["a"], r["b"])))
            e = g.setdefault(key, dict(a=key[0], b=key[1], count=0, max_volume_mm3=0.0, angles=set()))
            e["count"] += 1; e["max_volume_mm3"] = max(e["max_volume_mm3"], r["volume_mm3"])
            if "alpha" in r:
                e["angles"].add(r["alpha"])
        return sorted(({**e, "angles": sorted(e["angles"])} for e in g.values()), key=lambda e: -e["max_volume_mm3"])
    summ = dict(meta=meta,
                static=dict(clear=sum(1 for r in stat if r["status"] == "clear"), expected=sum(1 for r in stat if r["status"] == "expected"),
                            errors=sum(1 for r in stat if r["status"] == "error"), clashes=agg(stat)),
                kinematic=dict(clear=sum(r.get("n", 0) for r in kin if r["status"] == "clear_count"), expected=sum(1 for r in kin if r["status"] == "expected"),
                               errors=sum(1 for r in kin if r["status"] == "error"), clashes=agg(kin)))
    with open(os.path.join(D_ASM, "interference_report.json"), "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=1)
    print("static: clear", summ["static"]["clear"], "expected", summ["static"]["expected"], "errors", summ["static"]["errors"], "clash pairs", len(summ["static"]["clashes"]))
    for c in summ["static"]["clashes"][:60]:
        print("  S", c["a"], "|", c["b"], "x", c["count"], "max", c["max_volume_mm3"])
    print("kinematic: clear", summ["kinematic"]["clear"], "errors", summ["kinematic"]["errors"], "clash pairs", len(summ["kinematic"]["clashes"]))
    for c in summ["kinematic"]["clashes"][:40]:
        print("  K", c["a"], "|", c["b"], "x", c["count"], "max", c["max_volume_mm3"], "angles", c["angles"][:6])
    return summ


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "worker":
        return worker(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    if cmd == "interference":
        return interference()
    if cmd == "merge":
        return merge_interference()
    reg, info = ASM.build(0.0)
    if cmd in ("components", "all"):
        components(reg)
    if cmd in ("assemblies", "all"):
        assemblies(reg, info)
    if cmd in ("validate", "all"):
        validate(reg, info)


if __name__ == "__main__":
    main()
