"""One-off patch applied on 2026-11-15 after the first interference check (kept for traceability)."""
BS = chr(92)


def patch(path, pairs):
    s = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80])
        s = s.replace(a, b)
    open(path, "w", encoding="utf-8").write(s)


# ---- crank: extrude all web / counterweight sketches explicitly towards +X; longer rear shaft
patch("src/w16/cad/cranktrain.py", [
    ("    wa = extrude(Plane.YZ.offset(px - hw - P.web_thk) * sk, amount=P.web_thk)\n    wb = extrude(Plane.YZ.offset(px + hw) * sk, amount=P.web_thk)",
     "    ex = lambda face, x0: extrude(Plane.YZ.offset(x0) * face, amount=P.web_thk, dir=(1, 0, 0))     # always towards +X\n    wa = ex(sk, px - hw - P.web_thk)\n    wb = ex(sk, px + hw)"),
    ("        body = body + extrude(Plane.YZ.offset(px - hw - P.web_thk) * cwp, amount=P.web_thk) + extrude(Plane.YZ.offset(px + hw) * cwp, amount=P.web_thk)",
     "        body = body + ex(cwp, px - hw - P.web_thk) + ex(cwp, px + hw)"),
    ("REAR_SEAT, REAR_SEAL = 55.0, 8.0 ", "REAR_SEAT, REAR_SEAL = 67.0, 12.0"),
])
# ---- timing: lower shell covers crank + intermediate (depth 46), upper shell only the four cam ends
patch("src/w16/cad/timing.py", [
    ("    pts = [Pos(INTER[0], INTER[1]) * Circle(78.0)]\n    for b in (1, 2):", "    pts = []\n    for b in (1, 2):"),
    ("    d_lo, d_up, wall = 28.0, 64.0, 3.5", "    d_lo, d_up, wall = 46.0, 64.0, 3.5"),
])
# ---- turbo: waste-gate actuator between the housings, below the bearing housing
patch("src/w16/cad/turbo.py", [
    ("    act = cyl_between((X_C + 4, -r2c - 44, -18), (X_C + 46, -r2c - 44, -18), 27.0) + box_at(X_C + 4, X_C + 14, -r2c - 50, -r2c - 14, -40, 4)\n    rod = cyl_between((X_C + 4, -r2c - 44, -18), (X_T - 24, -30.0, 30.0), 3.0)",
     "    act = cyl_between((-20, -52, -42), (20, -52, -42), 21.0) + box_at(-6, 6, -52, -30, -30, -18)          # bracket to the bearing housing\n    rod = cyl_between((-20, -52, -42), (X_T - 52, -40.0, -30.0), 3.0)"),
])
# ---- head: coil boot hollow over the plug, coil head above the cover tower; cover towers start on the joint
patch("src/w16/cad/head.py", [
    ("    pts = [(0, 0), (8.5, 0), (8.5, 118.0), (13.0, 120.0), (13.0, 146.0), (0, 146.0)]\n    body = revolve(Plane.XZ * poly(pts), axis=Axis.Z)\n    return body + box_at(-9, 9, 6, 30, 126.0, 146.0)",
     "    pts = [(5.2, 0), (8.5, 0), (8.5, 158.0), (13.0, 160.0), (13.0, 184.0), (0, 184.0), (0, 27.0), (5.2, 27.0)]\n    body = revolve(Plane.XZ * poly(pts), axis=Axis.Z)\n    return body + box_at(-9, 9, 6, 30, 166.0, 184.0)"),
    ("        a = p0 + pd * ((hh - 2 - p0[2]) / pd[2])", "        a = p0 + pd * ((hh + 0.0 - p0[2]) / pd[2])"),
    ("        cov = cov + (cyl_between(a, b, P.plug_well_dia / 2 + 3.5) & box_at(-XH, XH, -W_TOP, W_TOP, hh - 2, top))",
     "        cov = cov + (cyl_between(a - pd * 8, b, P.plug_well_dia / 2 + 3.5) & box_at(-XH, XH, -W_TOP, W_TOP, hh, top))"),
])

s = open("src/w16/cad/systems.py", encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b)


rep("        out[f\"manifold_{name}\"] = (log + pl) - cav",
    "        zf = Z_T + TB.Z_IN\n        out[f\"manifold_{name}\"] = ((log + pl) - cav) - box_at(xt - 60, xt + 60, sy * (Y_T + TB.Y_IN) - 60, sy * (Y_T + TB.Y_IN) + 60, zf - 40, zf)")
rep("P3(250.0, 400.0, 420.0, sy), P3(150.0, 335.0, 440.0, sy)]", "P3(250.0, 400.0, 420.0, sy), P3(112.0, 335.0, 440.0, sy)]")
rep("    box = box_at(-65, 155, sy * 225, sy * 335, 400, 640) - box_at(-62, 152, sy * 228, sy * 332, 403, 637)\n    box = box + (cyl_between((155, sy * 280, 590), (200, sy * 280, 590), 40.0) - cyl_between((150, sy * 280, 590), (201, sy * 280, 590), 37.0))   # snorkel",
    "    box = box_at(-65, 118, sy * 225, sy * 335, 400, 640) - box_at(-62, 115, sy * 228, sy * 332, 403, 637)\n    box = box + (cyl_between((118, sy * 280, 590), (158, sy * 280, 590), 40.0) - cyl_between((113, sy * 280, 590), (159, sy * 280, 590), 37.0))   # snorkel")
rep("    out[\"air_filter\"] = box_at(-58, 148, sy * 232, sy * 328, 520, 548)", "    out[\"air_filter\"] = box_at(-58, 111, sy * 232, sy * 328, 520, 548)")
rep("(\"P\", -11.0, (150.0, 336.0)), (\"S\", 11.0, (167.0, 356.0))", "(\"P\", -11.0, (163.0, 331.0)), (\"S\", 11.0, (176.0, 351.0))")
rep("    pump = box_at(-400, -335, -165, -100, -100, -38)", "    pump = box_at(-404, -339.5, -172, -122, -100, -38)")
rep("        pump = pump - box_at(-397 + k * 9.0 + 6.5, -397 + k * 9.0 + 7.5, -166, -164, -101, -37)", "        pump = pump - box_at(-401 + k * 9.0 + 6.5, -401 + k * 9.0 + 7.5, -173, -171, -101, -37)")
rep("    rail = cyl_between((-XH - 34, SCAV_Y[0] - 20, -89.0), (-XH - 34, SCAV_Y[-1] + 14, -89.0), 13.0) - " + BS + "\n        cyl_between((-XH - 34, SCAV_Y[0] - 21, -89.0), (-XH - 34, SCAV_Y[-1] + 10, -89.0), 10.0)",
    "    rail = cyl_between((-XH - 26, -121.5, -89.0), (-XH - 26, SCAV_Y[-1] + 14, -89.0), 9.0) - " + BS + "\n        cyl_between((-XH - 26, -122.5, -89.0), (-XH - 26, SCAV_Y[-1] + 10, -89.0), 7.0)")
rep("cyl_between((-XH - 20, ys, -89.0), (-XH - 34, ys, -89.0), 11.0) - cyl_between((-XH - 19, ys, -89.0), (-XH - 35, ys, -89.0), 8.5)",
    "cyl_between((-XH - 22.5, ys, -89.0), (-XH - 26, ys, -89.0), 9.0)")
rep("    filt = cyl_between((-455, 130, -60), (-340, 130, -60), 43.0) + box_at(-345, -333, 92, 168, -100, -20)", "    filt = cyl_between((-470, 110, -100), (-470, 110, 20), 43.0)")
rep("    out[\"oil_tank\"] = cyl_between((-560, -150, -90), (-560, -150, 390), 115.0) - cyl_between((-560, -150, -86), (-560, -150, 386), 112.0)",
    "    out[\"oil_tank\"] = cyl_between((-760, 0, -90), (-760, 0, 390), 115.0) - cyl_between((-760, 0, -86), (-760, 0, 386), 112.0)")
rep("tube([(-368, -132, -38), (-368, -132, 150), (-368, -20, 175), (-XH - 1, GAL_C[0], GAL_C[1])], 11.0, 9.0, bend=24.0)",
    "tube([(-352, -140, -38), (-352, -140, 100), (-352, -60, GAL_C[1]), (-XH - 9, GAL_C[0], GAL_C[1])], 10.0, 8.0, bend=22.0)")
rep("    pump = cyl_between((-392, 0, 205), (-XH - 2, 0, 205), 55.0) + cyl_between((-430, 0, 205), (-392, 0, 205), 16.0)\n    pump = pump - cyl_between((-388, 0, 205), (-XH - 8, 0, 205), 48.0)",
    "    ZP = 215.0\n    pump = cyl_between((-372, 0, ZP), (-XH - 9.5, 0, ZP), 55.0) + cyl_between((-400, 0, ZP), (-372, 0, ZP), 16.0)\n    pump = pump - cyl_between((-368, 0, ZP), (-XH - 14, 0, ZP), 48.0) - cyl_between((-401, 0, ZP), (-360, 0, ZP), 9.5)")
rep("    imp = cyl_between((-380, 0, 205), (-372, 0, 205), 44.0)\n    for k in range(7):\n        imp = imp + Pos(-372, 0, 205) * Rot(X=360.0 * k / 7) * box_at(-0.0, 16.0, 10.0, 43.0, -1.5, 1.5)\n    out[\"water_pump_impeller\"] = imp + cyl_between((-430, 0, 205), (-372, 0, 205), 9.0)\n    out[\"water_pump_pulley\"] = cyl_between((-452, 0, 205), (-430, 0, 205), 48.0) - cyl_between((-453, 0, 205), (-429, 0, 205), 9.0)",
    "    imp = cyl_between((-366, 0, ZP), (-360, 0, ZP), 44.0)\n    for k in range(7):\n        imp = imp + Pos(-360, 0, ZP) * Rot(X=360.0 * k / 7) * box_at(-0.0, 14.0, 10.0, 43.0, -1.5, 1.5)\n    out[\"water_pump_impeller\"] = imp + cyl_between((-403, 0, ZP), (-360, 0, ZP), 9.0)\n    out[\"water_pump_pulley\"] = cyl_between((-423, 0, ZP), (-403, 0, ZP), 48.0)")
rep("tube([(-362, sy * 50.0, 205.0), (-362, sy * 92.0, 180.0), (-362, a[1], a[2]), (-XH + 4, a[1], a[2])], 19.0, 17.0, bend=34.0)",
    "tube([(-352, sy * 50.0, ZP), (-352, sy * 100.0, 185.0), (-352, a[1], a[2]), (-XH + 4, a[1], a[2])], 19.0, 17.0, bend=30.0)")
rep("tube([(-XH + 4, o[1], o[2]), (-352, o[1], o[2]), (-362, sy * 60.0, 310.0), (-362, sy * 28.0, 310.0)], 19.0, 17.0, bend=34.0)",
    "tube([(-XH + 4, o[1], o[2]), (-352, o[1], o[2]), (-352, sy * 75.0, 318.0), (-352, sy * 31.0, 318.0)], 19.0, 17.0, bend=30.0)")
rep("    th = cyl_between((-362, -32, 310), (-362, 32, 310), 34.0) + cyl_between((-362, 0, 310), (-440, 0, 310), 21.0)\n    th = th - cyl_between((-362, -28, 310), (-362, 28, 310), 30.0) - cyl_between((-380, 0, 310), (-441, 0, 310), 18.0)",
    "    th = cyl_between((-352, -31, 318), (-352, 31, 318), 30.0) + cyl_between((-352, 0, 318), (-440, 0, 318), 21.0)\n    th = th - cyl_between((-352, -27, 318), (-352, 27, 318), 26.0) - cyl_between((-370, 0, 318), (-441, 0, 318), 18.0)")
rep("        (cyl_between((-375, 0, 152), (-375, 0, 110), 22.0) + cyl_between((-375, 0, 110), (-470, 0, 110), 22.0) -\n         cyl_between((-375, 0, 153), (-375, 0, 110), 19.5) - cyl_between((-375, 0, 110), (-471, 0, 110), 19.5))",
    "        (cyl_between((-352, 0, ZP - 50), (-352, 0, 122), 20.0) + cyl_between((-352, 0, 122), (-470, 0, 122), 20.0) -\n         cyl_between((-352, 0, ZP - 49), (-352, 0, 122), 17.5) - cyl_between((-352, 0, 122), (-471, 0, 122), 17.5))")
rep("tube([(-250, sy * 20.0, 305.0), (-262, sy * 87.0, 330.0), (-262, sy * 87.0, CAC_Z[0] + 30.0), (-CAC_X - 30, sy * 87.0, CAC_Z[0] + 30.0)], 14.0, 11.0, bend=22.0)",
    "tube([(-301, sy * 12.0, 285.0), (-316, sy * 87.0, 300.0), (-316, sy * 87.0, CAC_Z[0] + 30.0), (-CAC_X - 30, sy * 87.0, CAC_Z[0] + 30.0)], 13.0, 10.5, bend=22.0)")
i0 = s.index("    damper = cyl_between((x_n - 70, 0, 0), (x_n - 36, 0, 0), 95.0)")
i1 = s.index("    x_fl = L.main_x(P.n_main)")
s = s[:i0] + (
    "    damper = cyl_between((x_n - 72, 0, 0), (x_n - 40, 0, 0), 95.0) - cyl_between((x_n - 73, 0, 0), (x_n - 39, 0, 0), 68.0)      # inertia ring\n"
    "    hub = cyl_between((x_n - 94, 0, 0), (x_n - 10, 0, 0), 40.0) + cyl_between((x_n - 64, 0, 0), (x_n - 48, 0, 0), 68.0) + " + BS + "\n"
    "        cyl_between((x_n - 93, 0, 0), (x_n - 73, 0, 0), 70.0)                                                                   # hub, web, poly-V pulley\n"
    "    hub = hub - cyl_between((x_n - 95, 0, 0), (x_n - 8, 0, 0), 25.02)\n"
    "    out[\"damper_ring\"] = damper\n"
    "    out[\"damper_hub_pulley\"] = hub\n"
    "    out[\"damper_bolt\"] = cyl_between((x_n - 106, 0, 0), (x_n - 94, 0, 0), 15.0) + cyl_between((x_n - 94, 0, 0), (x_n - 72.5, 0, 0), 12.0)\n") + s[i1:]
rep("    x_fl = L.main_x(P.n_main) + P.main_width / 2 + 55.0 + 8.0 + 14.0",
    "    from .cranktrain import REAR_SEAL, REAR_SEAT\n    x_fl = L.main_x(P.n_main) + P.main_width / 2 + REAR_SEAT + REAR_SEAL + 14.0")
rep("        body = cyl_between((-345 - ln, sy * 78.0, 290.0), (-345, sy * 78.0, 290.0), r) + cyl_between((-345 - ln - 26, sy * 78.0, 290.0), (-345 - ln, sy * 78.0, 290.0), 32.0)",
    "        body = cyl_between((-425 - ln, sy * 120.0, 290.0), (-425, sy * 120.0, 290.0), r) + cyl_between((-423, sy * 120.0, 290.0), (-403, sy * 120.0, 290.0), 32.0)")
rep("    sk = Pos(0, 0) * Circle(70.0) + Pos(0, 205) * Circle(48.0) + Pos(-78, 290) * Circle(32.0) + Pos(78, 290) * Circle(32.0)",
    "    sk = Pos(0, 0) * Circle(70.0) + Pos(0, 215) * Circle(48.0) + Pos(-120, 290) * Circle(32.0) + Pos(120, 290) * Circle(32.0)")
rep("extrude(Plane(origin=(-476, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * ring, amount=20.0)",
    "extrude(Plane(origin=(-423, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * ring, amount=20.0, dir=(1, 0, 0))")
rep("        br = box_at(MOUNT_X - 36, MOUNT_X + 36, sy * 176, sy * 196, 2, 46) + box_at(MOUNT_X - 30, MOUNT_X + 30, sy * 196, sy * 236, 10, 38)",
    "        br = box_at(MOUNT_X - 26, MOUNT_X + 36, sy * 176, sy * 196, 2, 46) + box_at(MOUNT_X - 26, MOUNT_X + 30, sy * 196, sy * 246, 10, 38)")
rep("cyl_between((MOUNT_X, sy * 216, -22), (MOUNT_X, sy * 216, 10), 30.0)", "cyl_between((MOUNT_X + 2, sy * 228, -22), (MOUNT_X + 2, sy * 228, 10), 18.0)")
open("src/w16/cad/systems.py", "w", encoding="utf-8").write(s)

patch("src/w16/cad/assembly.py", [
    ("[H.plug_location(b, i, 34.0) for b in (1, 2) for i in range(1, 9)]", "[H.plug_location(b, i, 31.5) for b in (1, 2) for i in range(1, 9)]"),
    ('    sl.append(("oil pressure / temperature", Pos(-400, 130, -18)))', '    sl.append(("oil pressure / temperature", Pos(-470, 110, 19)))'),
    ('    sl.append(("coolant temperature", Pos(-362, 0, 343)))', '    sl.append(("coolant temperature", Pos(-352, 0, 347)))'),
])
patch("src/w16/cad/export.py", [
    ('    (r"W16-14-harness", r".*", "harness routing envelope"),',
     '    (r"W16-14-harness", r".*", "harness routing envelope"),\n'
     '    (r"W16-10-shutoff_valve", r"W16-10-manifold_rear", "flap-valve spindle through the manifold neck"),\n'
     '    (r"W16-09-recirc_valve", r"W16-09-charge_pipe_B|W16-08-00[12]", "valve flanged to the charge pipe"),\n'
     '    (r"W16-11-002", r"W16-11-001", "coil boot over the plug terminal"),\n'
     '    (r"W16-13-water_pump_impeller", r"W16-13-water_pump_(housing|pulley)", "impeller shaft in the pump bearing / pulley hub"),\n'
     '    (r"W16-14-damper_hub_pulley", r"W16-14-damper_ring|W16-14-damper_bolt", "bonded damper ring / bolt in hub"),\n'
     '    (r"W16-14-accessory_belt", r"W16-14-|W16-13-water_pump_pulley", "belt wrapped on its pulleys"),\n'
     '    (r"W16-14-mount_", r"W16-14-mount_", "isolator bonded to bracket"),\n'
     '    (r"W16-12-scavenge_manifold", r"W16-12-oil_pump_stack|W16-01-004", "collector joined to pump and sump ports"),\n'
     '    (r"W16-13-lt_hose", r"W16-13-lt_pump|W16-09-cac_core", "hose pushed on its stub"),\n'
     '    (r"W16-13-pipe_", r"W16-13-(water_pump_housing|thermostat_housing)|W16-01-001|W16-02-00[12]", "pipe socketed in its port"),\n'
     '    (r"W16-12-oil_line_pressure", r"W16-12-oil_pump_stack|W16-14-front_cover|W16-01-001", "oil line fitting"),'),
])
print("fix24 applied")
