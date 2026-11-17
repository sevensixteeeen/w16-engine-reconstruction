"""Master assembly: builds every part, places all instances for a given crank angle and returns the registry.

    from w16.cad.assembly import build
    reg, info = build(alpha=0.0)
"""
from __future__ import annotations
import json
import math
import os
import numpy as np
from build123d import Location, Plane, Pos, Rot, mirror

from ..params import P
from .. import layout as L
from ..analysis import valvetrain as VT
from . import block as B, cranktrain as CT, head as H, systems as SY, timing as TM, turbo as TB
from .cache import cached
from .common import ROOT, Registry, head_plane, bank_plane, hex_bolt, mass_props

RESULTS = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "results.json")


def largest_solid(shape):
    sol = shape.solids()
    return shape if len(sol) <= 1 else max(sol, key=lambda s: s.volume)


def _cw():
    with open(RESULTS, encoding="utf-8") as fh:
        res = json.load(fh)["dynamics"]
    mr = {int(k): v * 1e3 for k, v in res["mr_cw"].items()}
    ang = {int(k): v for k, v in res["cw_angle"].items()}
    return CT.design_counterweights(mr, ang)


def build(alpha=0.0, systems=True):
    reg = Registry()
    info = {}
    A = reg.add
    # ================================================================= 05 crankshaft
    cw, cw_rep = _cw()
    info["counterweights"] = dict(design={k: v for k, v in cw.items()}, report={k: v for k, v in cw_rep.items() if k not in ("U", "W")})
    crank = cached("crankshaft", lambda: CT.crankshaft(cw)[0], ["cad/cranktrain.py"])
    A("W16-05-001", "Crankshaft", crank, "steel_qt", "05", [Rot(X=alpha)], process="die forged, QT, nitrided, ground", moving="crank")

    # ================================================================= 04 rods, 03 pistons
    body, cap, shell, bush, bolt = CT.rod_solids()
    pis, ring_c, ring_o, pin, clip, pinfo = CT.piston_solids()
    info["piston"] = pinfo
    rl = [CT.rod_location(c, alpha) for c in L.CYLS]
    A("W16-04-001", "Connecting rod", body, "ti", "04", rl, process="forged Ti-6Al-4V, machined, shot peened", moving="rod", inst=[c.no for c in L.CYLS])
    A("W16-04-002", "Connecting rod cap", cap, "ti", "04", rl, process="forged with rod, serrated joint", moving="rod")
    A("W16-04-003", "Big-end bearing shell", shell, "case_steel", "04", [l * r for l in rl for r in (Rot(X=0), Rot(X=180))],
      process="sputter AlSn20 on steel back", custom=False, moving="rod")
    A("W16-04-004", "Small-end bush", bush, "case_steel", "04", rl, process="bronze bush, pressed and honed", custom=False, moving="rod")
    A("W16-04-005", "Rod bolt M8x1", bolt, "steel", "04", [l * Pos(0, sy * CT.BOLT_Y, -21.0) for l in rl for sy in (-1, 1)],
      process="rolled thread, 12.9 / MP35N", custom=False, moving="rod")
    pl = [CT.piston_location(c, alpha) for c in L.CYLS]
    A("W16-03-001", "Piston", pis, "al_forged", "03", pl, process="forged, machined, crown anodised, skirt coated", moving="piston", inst=[c.no for c in L.CYLS])
    A("W16-03-002", "Compression ring", ring_c, "steel", "03", [l * Pos(0, 0, z) for l in pl for z in (pinfo["g1"], pinfo["g2"])],
      process="nitrided steel, PVD face", custom=False, moving="piston")
    A("W16-03-003", "Oil control ring", ring_o, "steel", "03", [l * Pos(0, 0, pinfo["g3"]) for l in pl], process="3-piece", custom=False, moving="piston")
    A("W16-03-004", "Gudgeon pin", pin, "case_steel", "03", pl, process="case hardened, DLC coated", moving="piston")
    A("W16-03-005", "Pin circlip", clip, "steel", "03", [l * Pos(sx * (P.pin_length / 2 + 0.95), 0, 0) for l in pl for sx in (-1, 1)], custom=False, moving="piston")

    # ================================================================= 01 crankcase
    blk = cached("block_upper", B.block_upper, ["cad/block.py"])
    A("W16-01-001", "Crankcase upper section (cylinder block)", blk, "al_cast", "01", process="low-pressure sand casting, HIP, T6, bores coated")
    bp = cached("bedplate", B.bedplate, ["cad/block.py"])
    A("W16-01-002", "Crankcase lower section (bearing support)", bp, "al_cast", "01", process="sand casting with cast-in bearing covers")
    A("W16-01-003", "Main bearing cover (cast-in insert)", B.bearing_insert(), "cast_steel", "01",
      [Pos(L.main_x(j), 0, 0) for j in range(1, P.n_main + 1)], process="nodular iron GJS-600, cast-in")
    A("W16-01-004", "Dry-sump pan", B.sump(), "al_cast", "01", process="die casting, machined")
    ms = B.main_shell()
    A("W16-01-005", "Main bearing shell", ms, "case_steel", "01", [Pos(L.main_x(j), 0, 0) * r for j in range(1, P.n_main + 1) for r in (Rot(X=0), Rot(X=180))],
      process="bimetal/sputter, upper half grooved", custom=False)
    gk = B.head_gasket()
    A("W16-01-006", "Cylinder-head gasket (MLS)", gk, "steel", "01", [Location(bank_plane(b)) for b in (1, 2)], process="3-layer embossed spring steel")
    A("W16-01-007", "Piston cooling jet", B.jet_solid(), "steel", "01", [B.jet_location(c) for c in L.CYLS], custom=False, inst=[c.no for c in L.CYLS])

    # ================================================================= 02 heads, 06 valve train
    jk_file = os.path.join(ROOT, ".cache", "head_jacket.json")

    def _head():
        c, jk = H.head_core()
        with open(jk_file, "w", encoding="utf-8") as fh:
            json.dump(dict(jacket_l=jk.volume / 1e6, jacket_solids=len(jk.solids()), shifted_cuts=len(H.CUT_LOG)), fh)
        return c
    core = cached("head_core", _head, ["cad/head.py", "cad/block.py"])
    if os.path.exists(jk_file):
        with open(jk_file, encoding="utf-8") as fh:
            info["head_jacket"] = json.load(fh)
    for b, fs in ((1, -1), (2, 1)):
        hd = H.head_for_bank(core, fs)
        info.setdefault("head_slivers_removed_mm3", {})[b] = sorted(round(s.volume, 1) for s in hd.solids())[:-1]
        A(f"W16-02-00{b}", f"Cylinder head, bank {b}", largest_solid(hd), "al_cast", "02", [Location(head_plane(b))],
          process="low-pressure sand casting, HIP, T6, 5-axis machined")
    for b, pn in ((1, "W16-02-003"), (2, "W16-02-008")):          # D-039: per bank (camshaft seal bores at the drive end)
        A(pn, f"Cam cover with coil towers, bank {b}", cached(f"cam_cover_b{b}", lambda b=b: H.cam_cover(b), ["cad/head.py", "cad/block.py"]),
          "cfrp", "02", [Location(head_plane(b))], process="CFRP / magnesium alternative")
    A("W16-02-004", "Camshaft bearing cap", H.cam_cap(), "al_cast", "02",
      [Location(head_plane(b)) * Pos(xw, su * P.cam_u, P.cam_w) for b in (1, 2) for xw in H.WEB_X for su in (-1, 1)], process="machined with head (line bored)")
    guide = H.guide_solid()
    lay = H.LAY
    vloc = {k: [] for k in ("in_short", "in_long", "ex_short", "ex_long")}
    seat = {"in": [], "ex": []}
    g_locs, r_locs, h_locs = [], [], []
    f_locs = {True: [], False: []}
    springs = {}
    for b in (1, 2):
        for i in range(1, 9):
            c = L.CYL[i if b == 1 else 17 - i]
            li, le = H.lifts(c, alpha)
            for kind, lift in (("in", li), ("ex", le)):
                v = lay[H.row_of(i)][kind]
                far = v["far"]
                for s in (-1, 1):
                    vloc[f"{kind}_{'long' if far else 'short'}"].append(H.valve_location(b, i, kind, s, lift))
                    seat[kind].append(H.seat_location(b, i, kind, s))
                    g_locs.append(H.along_valve(b, i, kind, s, v["length"] - 22.0))
                    r_locs.append(H.along_valve(b, i, kind, s, 4.0 + lift))
                    f_locs[far].append(H.finger_location(b, i, kind, s, lift))
                    h_locs.append(H.hla_location(b, i, kind, s))
                    hkey = round((H.SEAT_DROP - 4.0 - lift) * 2) / 2      # spring between seat and retainer (4 mm below the tip)
                    springs.setdefault(hkey, []).append(H.along_valve(b, i, kind, s, H.SEAT_DROP))
    lens = {"in_short": None, "in_long": None, "ex_short": None, "ex_long": None}
    for row in ("inner", "outer"):
        for kind in ("in", "ex"):
            v = lay[row][kind]
            far = v["far"]
            lens[f"{kind}_{'long' if far else 'short'}"] = v["length"]
    info["valve_lengths"] = lens
    names = {"in_short": "Intake valve, short", "in_long": "Intake valve, long", "ex_short": "Exhaust valve, short", "ex_long": "Exhaust valve, long (sodium-filled)"}
    for n, key in enumerate(("in_short", "in_long", "ex_short", "ex_long")):
        kind = key[:2]
        A(f"W16-06-00{n + 1}", names[key], H.valve_solid(kind, lens[key]), "steel", "06", vloc[key],
          process="X45CrSi9-3 / NiCr20TiAl head, friction welded, nitrided" if kind == "in" else "Nimonic 80A head, hollow stem", moving="valve")
    A("W16-02-005", "Valve guide", guide, "case_steel", "02", g_locs, process="sintered / CuBe, pressed in", custom=False)
    A("W16-02-006", "Valve seat insert, intake", H.seat_insert("in"), "case_steel", "02", seat["in"], process="sintered, shrink fitted", custom=False)
    A("W16-02-007", "Valve seat insert, exhaust", H.seat_insert("ex"), "case_steel", "02", seat["ex"], process="sintered Co-alloy, shrink fitted", custom=False)
    for hkey, locs in sorted(springs.items(), reverse=True):
        A(f"W16-06-005~h{int(hkey * 10):03d}", "Valve spring", H.spring_solid(hkey), "steel", "06", locs, process="OTEVA 90 class wire, shot peened", custom=False, moving="valve")
    A("W16-06-006", "Spring retainer with cotters", H.retainer_solid(), "ti", "06", r_locs, custom=False, moving="valve")
    A("W16-06-007", "Roller finger follower, short valves (ratio %.2f)" % lay["outer"]["ex"]["ratio"], H.finger_solid(False), "case_steel", "06", f_locs[False],
      process="precision cast / stamped, needle roller", custom=False, moving="valve")
    A("W16-06-013", "Roller finger follower, long valves (ratio %.2f)" % lay["outer"]["in"]["ratio"], H.finger_solid(True), "case_steel", "06", f_locs[True],
      process="precision cast / stamped, needle roller", custom=False, moving="valve")
    A("W16-06-008", "Hydraulic support element", H.hla_solid(), "case_steel", "06", h_locs, custom=False)
    n = 9
    for b in (1, 2):
        for kind in ("in", "ex"):
            cam = cached(f"camshaft_b{b}_{kind}", lambda b=b, kind=kind: H.camshaft(b, kind), ["cad/head.py", "cad/block.py"])
            A(f"W16-06-0{n:02d}", f"{'Intake' if kind == 'in' else 'Exhaust'} camshaft, bank {b}", cam, "steel_qt", "06",
              [H.cam_location(b, kind, alpha)], process="assembled / forged, induction hardened lobes, ground", moving="cam")
            n += 1

    # ================================================================= 11 ignition (plugs + coils)
    A("W16-11-001", "Spark plug M10", H.spark_plug(), "steel", "11", [H.plug_location(b, i) for b in (1, 2) for i in range(1, 9)], custom=False)
    A("W16-11-002", "Pencil coil with ion-current sensing", H.ignition_coil(), "polymer", "11",
      [H.plug_location(b, i, 31.5) for b in (1, 2) for i in range(1, 9)], custom=False, mass_override=0.21)

    # ================================================================= 07 timing drive
    r1c, r1i = TM.pitch_r(TM.P1, TM.Z_CRANK), TM.pitch_r(TM.P1, TM.Z_INT1)
    r2i, r2c = TM.pitch_r(TM.P2, TM.Z_INT2), TM.pitch_r(TM.P2, TM.Z_CAM)
    sp_c = TM.sprocket(TM.P1, TM.Z_CRANK, 6.5, 32.0, rows=2, row_gap=3.0)
    sp_i = TM.sprocket(TM.P1, TM.Z_INT1, 6.5, 12.5, rows=2, row_gap=3.0)
    sp_s = TM.sprocket(TM.P2, TM.Z_INT2, 3.5, 12.5)
    xs0 = TM.X_PRIM - 8.0
    A("W16-07-001", "Crank sprocket, duplex Z24", sp_c, "case_steel", "07", [Pos(xs0, 0, 0) * Rot(Y=90)], process="case hardened")
    A("W16-07-002", "Intermediate shaft", TM.intermediate_shaft(), "case_steel", "07")
    A("W16-07-003", "Intermediate sprocket, duplex Z36", sp_i, "case_steel", "07", [Pos(xs0, TM.INTER[0], TM.INTER[1]) * Rot(Y=90)])
    A("W16-07-004", "Intermediate sprocket, Z21", sp_s, "case_steel", "07", [Pos(xr - 1.75, TM.INTER[0], TM.INTER[1]) * Rot(Y=90) for xr in TM.ROWS.values()])
    path, pinf = TM.chain_path((0, 0), r1c, TM.INTER, r1i, TM.P1)
    info["chains"] = {"primary": {k: (float(v) if not hasattr(v, "shape") else v.tolist()) for k, v in pinf.items()}}
    A("W16-07-005", "Primary duplex roller chain 3/8in", TM.link_solid(TM.P1, 16.0), "case_steel", "07", TM.chain_locations(path, TM.X_PRIM, 16.0),
      custom=False, note=f"{pinf['n_links']} links", moving="chain")
    g_l, t_l, link_l = [], [], []
    g_shapes = []
    spans = [("prim", pinf, TM.X_PRIM, 16.0, TM.P1)]
    ph_l = []
    for (b, kind), xr in TM.ROWS.items():
        cy, cz = TM.cam_axis_yz(b, kind)
        pth, inf = TM.chain_path(TM.INTER, r2i, (cy, cz), r2c, TM.P2)
        info["chains"][f"bank{b}_{kind}"] = {k: (float(v) if not hasattr(v, "shape") else v.tolist()) for k, v in inf.items()}
        link_l += TM.chain_locations(pth, xr, 4.5)
        spans.append((f"b{b}{kind}", inf, xr, 4.5, TM.P2))
        inner_plane = xr < B.XH + 32.0
        ph_l.append(Pos(xr, cy, cz) * (Rot(Y=90) if inner_plane else Rot(Y=-90)))
    A("W16-07-006", "Secondary sleeve chain 8 mm", TM.link_solid(TM.P2, 4.5), "case_steel", "07", link_l, custom=False,
      note="4 chains: " + ", ".join(f"{k}: {int(v['n_links'])} links" for k, v in info["chains"].items() if k != "primary"), moving="chain")
    A("W16-07-007", "Cam phaser with sprocket Z28", TM.phaser(), "case_steel", "07", ph_l, custom=False)
    gi = 0
    for nm, inf, xr, w, p in spans:
        ga = TM.guide_rail(inf["A1"], inf["A2"], np.array(inf["na"]), xr, w, p)
        gb = TM.guide_rail(inf["B1"], inf["B2"], np.array(inf["nb"]), xr, w, p)
        for g, tag in ((ga, "fixed guide"), (gb, "tensioner rail")):
            gi += 1
            A(f"W16-07-008~{gi:02d}", f"Chain {tag}", g, "polymer", "07", note=nm)
        t_l.append(TM.tensioner_location(inf["B1"], inf["B2"], np.array(inf["nb"]), xr, p))
    A("W16-07-009", "Hydraulic chain tensioner", TM.tensioner_body(), "steel", "07", t_l, custom=False)
    A("W16-07-010", "Chain housing (rear cover)", cached("chain_cover", TM.chain_cover, ["cad/timing.py", "cad/block.py"]), "cfrp", "07", process="CFRP prepreg, bonded seal carrier")

    if not systems:
        return reg, info

    # ================================================================= 08 turbochargers
    tp = cached_turbo()
    names_t = dict(comp_housing=("Compressor housing", "al_cast"), turb_housing=("Turbine housing", "cast_steel"), chra=("Bearing housing (water cooled)", "cast_steel"),
                   rotor=("Turbine wheel and shaft", "inconel"), comp_wheel=("Compressor wheel", "al_forged"), bush=("Floating journal bearing", "case_steel"),
                   actuator=("Waste-gate actuator with rod", "steel"))
    n = 1
    for key, (nm, mat) in names_t.items():
        for hand, sy in (("RH", 1), ("LH", -1)):
            shp = tp[key] if sy > 0 else mirror(tp[key], about=Plane.XZ)
            locs = [Pos(xt, sy * SY.Y_T, SY.Z_T) for xt in (SY.X_TA, SY.X_TB)]
            if key == "bush":
                locs = [l * Pos(dx, 0, 0) for l in locs for dx in (-18.0, 16.0)]
            A(f"W16-08-0{n:02d}", f"{nm}, {hand}", shp, mat, "08", locs, custom=(key not in ("bush", "actuator")),
              process={"comp_housing": "gravity die cast", "turb_housing": "investment cast 1.4849", "chra": "sand cast", "rotor": "investment cast Inconel 713C, EB-welded shaft",
                       "comp_wheel": "5-axis milled forged 2618", "bush": "bronze", "actuator": "electric"}[key])
            n += 1

    # ================================================================= 09/10/11 side systems
    ex_names = dict(manifold_front=("Exhaust manifold, front group", "cast_steel"), manifold_rear=("Exhaust manifold, rear group", "cast_steel"),
                    crossover=("Manifold cross-over pipe with bellows", "inconel"), shutoff_valve=("Exhaust shut-off valve (register valve)", "inconel"),
                    precat_A=("Pre-catalyst housing A", "ti"), substrate_A=("Pre-catalyst substrate A", "cast_steel"), downpipe_B=("Down-pipe B", "ti"),
                    precat_B=("Pre-catalyst housing B", "ti"), substrate_B=("Pre-catalyst substrate B", "cast_steel"))
    in_names = dict(intake_manifold=("Intake manifold with plenum", "cfrp"), cac_core=("Charge-air cooler core (water-to-air)", "al_cast"),
                    cac_tank=("Charge-air cooler inlet tank", "cfrp"), throttle_A=("Throttle body A", "al_cast"), throttle_B=("Throttle body B / compressor cut-in valve", "al_cast"),
                    charge_pipe_A=("Charge pipe A", "cfrp"), charge_pipe_B=("Charge pipe B", "cfrp"), air_duct_A=("Clean-air duct A", "cfrp"),
                    air_duct_B=("Clean-air duct B", "cfrp"), air_box=("Air box", "cfrp"), air_filter=("Air filter element", "polymer"),
                    recirc_valve=("Compressor recirculation valve", "al_cast"))
    inj_locs = {}
    for sy, tag in ((1, "L1"), (-1, "L2")):
        ex = SY.exhaust_side(sy)
        for k, (nm, mat) in ex_names.items():
            A(f"W16-10-{k}-{tag}", f"{nm}, bank {1 if sy > 0 else 2}", ex[k], mat, "10", mass_override=(1.1 if k.startswith("substrate") else None),
              custom=not k.startswith("substrate"))
        it = SY.intake_side(sy)
        for k, (nm, mat) in in_names.items():
            A(f"W16-09-{k}-{tag}", f"{nm}, bank {1 if sy > 0 else 2}", it[k], mat, "09", custom=k not in ("air_filter", "recirc_valve", "throttle_A", "throttle_B"),
              mass_override={"cac_core": 6.5, "air_filter": 0.25}.get(k))
        fu = SY.fuel_side(sy)
        for r in ("P", "S"):
            A(f"W16-11-rail_{r}-{tag}", f"Fuel rail {'primary' if r == 'P' else 'secondary'}, bank {1 if sy > 0 else 2}", fu[f"rail_{r}"], "steel", "11")
        for loc, ln in fu["_injectors"]:
            inj_locs.setdefault(round(ln, 1), []).append(loc)
    for k, (ln, locs) in enumerate(sorted(inj_locs.items())):
        A(f"W16-11-003~{k}", "Port fuel injector", SY.injector_solid(ln), "steel", "11", locs, custom=False, mass_override=0.05)

    # ================================================================= 12/13/14
    lub_names = dict(oil_pump_stack=("Oil pump stack (1 pressure + 6 scavenge stages)", "al_cast"), scavenge_manifold=("Scavenge collector", "al_cast"),
                     oil_filter_module=("Oil filter module", "al_cast"), oil_cooler=("Oil-to-water cooler", "al_cast"), oil_tank=("Dry-sump oil tank (vehicle mounted)", "al_cast"),
                     oil_line_pressure=("Oil pressure line to main gallery", "steel"))
    for k, shp in SY.lubrication().items():
        A(f"W16-12-{k}", lub_names[k][0], shp, lub_names[k][1], "12", custom=k not in ("oil_filter_module", "oil_cooler"))
    for k, shp in SY.cooling().items():
        mat = "polymer" if "hose" in k else ("al_cast" if ("pump" in k or "thermostat" in k) else "al_cast")
        A(f"W16-13-{k}", k.replace("_", " ").capitalize(), shp, mat, "13", custom=("hose" not in k and k != "lt_pump"), mass_override=(1.9 if k == "lt_pump" else None))
    for k, shp in SY.accessories().items():
        mat = {"accessory_belt": "polymer", "alternator": "steel", "ac_compressor": "al_cast", "flex_plate": "steel_qt", "damper_ring": "steel_qt",
               "damper_hub_pulley": "steel_qt", "damper_bolt": "steel"}.get(k, "al_cast")
        if "isolator" in k:
            mat = "polymer"
        A(f"W16-14-{k}", k.replace("_", " ").capitalize(), shp, mat, "14", custom=k not in ("alternator", "ac_compressor", "accessory_belt", "damper_bolt") and "isolator" not in k,
          mass_override={"alternator": 6.8, "ac_compressor": 5.9}.get(k), moving=("crank" if k in ("damper_ring", "damper_hub_pulley", "damper_bolt", "flex_plate") else ""),
          locs=[Rot(X=alpha)] if k in ("damper_ring", "damper_hub_pulley", "damper_bolt", "flex_plate") else None)
    for k, shp in SY.harness().items():
        A(f"W16-14-{k}", "Engine harness trunk, bank " + k[-1], shp, "polymer", "14", custom=True, mass_override=1.4)
    # sensors
    sl = []
    ex1, eu1, ev1 = L.bank_axes(1)
    for b in (1, 2):
        ex, eu, ev = L.bank_axes(b)
        for xk in (-146.0, 146.0):
            p = L.to_global(b, xk, -117.0, 185.0)
            sl.append(("knock", Location(Plane(origin=tuple(p), z_dir=tuple(-eu)))))
        for su in (-1, 1):
            p = SY.hg(b, (-1 if b == 1 else 1) * 300.0, su * P.cam_u, 185.0)
            sl.append(("cam position", Location(Plane(origin=tuple(p), z_dir=tuple(ev)))))
    sl.append(("coolant temperature", Pos(-361, 0, 347) * Rot(X=90)))
    sl.append(("oil pressure / temperature", Pos(-470, 110, 19)))
    sl.append(("crank position", Pos(B.XH - 8, -92, 62) * Rot(Y=90)))
    for sy in (1, -1):
        sl.append(("manifold pressure / temperature", Pos(-292, sy * 87, 367) * Rot(Y=-90)))
        for xt in (SY.X_TA, SY.X_TB):
            sl.append(("exhaust gas temperature", Pos(xt + TB.X_T + 30, sy * (SY.Y_T + TB.Y_IN), SY.Z_T + TB.Z_IN + 22) * Rot(Y=90)))
            sl.append(("turbo speed", Pos(xt + TB.X_C + 30, sy * SY.Y_T, SY.Z_T + 58)))
        sl.append(("wide-band lambda", Pos(SY.X_TA + TB.X_TO - 110, sy * SY.Y_T, SY.Z_T + 38)))
        sl.append(("wide-band lambda", Pos(-B.XH - 215, sy * 208, -45 + 38)))
    A("W16-14-sensor", "Screw-in sensor (generic envelope)", SY.sensor_solid(), "steel", "14", [l for _, l in sl], custom=False, mass_override=0.06,
      note="; ".join(sorted({n for n, _ in sl})))
    info["sensors"] = [n for n, _ in sl]

    # ================================================================= 15 fasteners
    hb = hex_bolt(P.head_bolt_dia, 122.0, flange=True)
    A("W16-15-001", "Head bolt M11x1.25x122", hb, "steel", "15", [Location(head_plane(b)) * Pos(x, u, H.W_FLOOR) for b in (1, 2) for x, u in B.head_bolt_xy()], custom=False)
    mb = hex_bolt(P.main_bolt_dia, 110.0, flange=True)
    A("W16-15-002", "Main bearing bolt M12x1.5x110", mb, "steel", "15",
      [Pos(L.main_x(j), sy * yb, -72.0) * Rot(X=180) for j in range(1, P.n_main + 1) for sy in (-1, 1) for yb in (50.0, 108.0)], custom=False)
    pb = hex_bolt(8.0, 90.0, flange=True)
    A("W16-15-003", "Bedplate perimeter bolt M8x90", pb, "steel", "15", [Pos(-305 + i * 46.9, sy * 140, -72.0) * Rot(X=180) for i in range(14) for sy in (-1, 1)], custom=False)
    cb = hex_bolt(6.0, 40.0, flange=True)
    A("W16-15-004", "Cam cap bolt M6x40", cb, "steel", "15",
      [Location(head_plane(b)) * Pos(xw, su * P.cam_u + sv * 18.0, P.cam_w + 21.0) for b in (1, 2) for xw in H.WEB_X for su in (-1, 1) for sv in (-1, 1)], custom=False)
    return reg, info


def cached_turbo():
    out = {}
    for k in ("comp_housing", "turb_housing", "chra", "rotor", "comp_wheel", "bush", "actuator"):
        out[k] = cached(f"turbo_{k}", lambda k=k: largest_solid(_turbo_parts()[k]), ["cad/turbo.py"])
    return out


_TP = None


def _turbo_parts():
    global _TP
    if _TP is None:
        _TP = TB.assembly_parts()
    return _TP


def summary(reg, info):
    from .common import GROUPS
    rows = []
    for g, parts in sorted(reg.by_group().items()):
        rows.append(dict(group=g, name=GROUPS[g], part_numbers=len({p.pn.split("~")[0] for p in parts}), instances=sum(p.qty for p in parts),
                         mass_kg=round(sum(p.mass * p.qty for p in parts), 2)))
    bad = [(p.pn, bool(p.shape.is_valid), len(p.shape.solids())) for p in reg.parts.values() if (not p.shape.is_valid) or len(p.shape.solids()) != 1]
    return dict(groups=rows, total_mass_kg=round(reg.total_mass(), 1), part_numbers=len({p.pn.split("~")[0] for p in reg.parts.values()}),
                instances=sum(p.qty for p in reg.parts.values()), invalid_or_multi_solid=bad)


if __name__ == "__main__":
    import time
    t = time.time()
    reg, info = build(0.0)
    s = summary(reg, info)
    for r in s["groups"]:
        print(r)
    print("total mass", s["total_mass_kg"], "kg; part numbers", s["part_numbers"], "; instances", s["instances"], "; build", round(time.time() - t, 1), "s")
    print("invalid or multi-solid:", s["invalid_or_multi_solid"])
    with open(os.path.join(ROOT, "06_ASSEMBLIES", "assembly_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)
