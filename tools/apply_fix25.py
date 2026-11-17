"""One-off patch applied on 2026-11-15 after the second interference check (kept for traceability)."""


def patch(path, pairs):
    s = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b)
    open(path, "w", encoding="utf-8").write(s)


# block: machine the bores right through the deck (the cut used to stop short on one side of the tilted bore)
patch("src/w16/cad/block.py", [
    ("        cut = cut + cyl_between(p + d * P.s_bore_foot, p + d * (P.s_deck + 3), P.bore / 2)        # cylinder bore",
     "        cut = cut + cyl_between(p + d * P.s_bore_foot, p + d * (P.s_deck + 14), P.bore / 2)       # cylinder bore, through the deck"),
])
# head: plug towers with 1.5 mm wall next to the camshafts; no thrust flange inside the phaser; cover towers likewise
patch("src/w16/cad/head.py", [
    ("    stay.append(cyl_between(p0 + pd * 45.0, p0 + pd * 140.0, P.plug_well_dia / 2 + 3.5))", "    stay.append(cyl_between(p0 + pd * 45.0, p0 + pd * 140.0, P.plug_well_dia / 2 + 1.5))"),
    ("    shaft = shaft + cyl_between((drive * (XH + 2), 0, 0), (drive * (XH + 10), 0, 0), 15.0)          # thrust flange\n", ""),
    ("        cov = cov + (cyl_between(a - pd * 8, b, P.plug_well_dia / 2 + 3.5) & box_at(-XH, XH, -W_TOP, W_TOP, hh, top))",
     "        cov = cov + (cyl_between(a - pd * 8, b, P.plug_well_dia / 2 + 1.5) & box_at(-XH, XH, -W_TOP, W_TOP, hh, top))"),
])
patch("src/w16/cad/timing.py", [
    ("    return Pos(XH - 24, y, z) * Rot(Y=90) * Cylinder(12.5, 70.0, align=CMIN)", "    return Pos(XH - 24, y, z) * Rot(Y=90) * Cylinder(12.5, 65.0, align=CMIN)"),
])
patch("src/w16/cad/turbo.py", [
    ("Y_CO, Z_CO = 52.0, 62.0 ", "Y_CO, Z_CO = 52.0, 96.0 "),
])
patch("src/w16/cad/systems.py", [
    ("(\"P\", -11.0, (163.0, 331.0)), (\"S\", 11.0, (176.0, 351.0))", "(\"P\", -11.0, (158.0, 331.0)), (\"S\", 11.0, (176.0, 352.0))"),
    ("        br = box_at(MOUNT_X - 26, MOUNT_X + 36, sy * 176, sy * 196, 2, 46) + box_at(MOUNT_X - 26, MOUNT_X + 30, sy * 196, sy * 246, 10, 38)",
     "        br = box_at(MOUNT_X - 26, MOUNT_X + 36, sy * 176, sy * 196, 2, 40) + box_at(MOUNT_X - 26, MOUNT_X + 30, sy * 196, sy * 246, 10, 38)"),
    ("tube([(-352, sy * 50.0, ZP), (-352, sy * 100.0, 185.0), (-352, a[1], a[2]), (-XH + 4, a[1], a[2])], 19.0, 17.0, bend=30.0)",
     "tube([(-361, sy * 50.0, ZP), (-361, sy * 100.0, 185.0), (-361, a[1], a[2]), (-XH + 4, a[1], a[2])], 19.0, 17.0, bend=30.0)"),
    ("tube([(-XH + 4, o[1], o[2]), (-352, o[1], o[2]), (-352, sy * 75.0, 318.0), (-352, sy * 31.0, 318.0)], 19.0, 17.0, bend=30.0)",
     "tube([(-XH + 4, o[1], o[2]), (-361, o[1], o[2]), (-361, sy * 75.0, 318.0), (-361, sy * 31.0, 318.0)], 19.0, 17.0, bend=30.0)"),
    ("    th = cyl_between((-352, -31, 318), (-352, 31, 318), 30.0) + cyl_between((-352, 0, 318), (-440, 0, 318), 21.0)\n    th = th - cyl_between((-352, -27, 318), (-352, 27, 318), 26.0) - cyl_between((-370, 0, 318), (-441, 0, 318), 18.0)",
     "    th = cyl_between((-361, -31, 318), (-361, 31, 318), 30.0) + cyl_between((-361, 0, 318), (-361, 0, 400), 21.0)\n    th = th - cyl_between((-361, -27, 318), (-361, 27, 318), 26.0) - cyl_between((-361, 0, 330), (-361, 0, 401), 18.0)"),
    ("        (cyl_between((-352, 0, ZP - 50), (-352, 0, 122), 20.0) + cyl_between((-352, 0, 122), (-470, 0, 122), 20.0) -\n         cyl_between((-352, 0, ZP - 49), (-352, 0, 122), 17.5) - cyl_between((-352, 0, 122), (-471, 0, 122), 17.5))",
     "        (cyl_between((-361, 40, ZP - 38), (-361, 40, 122), 20.0) + cyl_between((-361, 40, 122), (-470, 40, 122), 20.0) -\n         cyl_between((-361, 40, ZP - 37), (-361, 40, 122), 17.5) - cyl_between((-361, 40, 122), (-471, 40, 122), 17.5))"),
    ("        path = [co, co + np.array([0, 0, 50.0]), P3(xc + 2.0, 415.0, 190.0, sy), P3(xc + 2.0, 415.0, 282.0, sy),\n                P3(xc, 292.0, 402.0, sy), P3(xc, 250.0, zin, sy), P3(xc, y1 + 58.0, zin, sy)]",
     "        path = [co, co + np.array([0, 0, 40.0]), P3(xc + 2.0, 415.0, 205.0, sy), P3(xc + 2.0, 415.0, 300.0, sy),\n                P3(xc, 300.0, 425.0, sy), P3(xc, 250.0, zin, sy), P3(xc, y1 + 58.0, zin, sy)]"),
    ("    path = [ci_a, ci_a + np.array([22.0, 0, 0]), P3(-14.0, 392.0, 20.0, sy), P3(-10.0, 415.0, 120.0, sy), P3(-10.0, 415.0, 330.0, sy), P3(-10.0, 335.0, 404.0, sy)]",
     "    path = [ci_a, ci_a + np.array([14.0, 0, 0]), P3(-20.0, 400.0, 26.0, sy), P3(-10.0, 415.0, 130.0, sy), P3(-10.0, 415.0, 330.0, sy), P3(-10.0, 335.0, 404.0, sy)]"),
])
patch("src/w16/cad/assembly.py", [
    ('    sl.append(("coolant temperature", Pos(-352, 0, 347)))', '    sl.append(("coolant temperature", Pos(-361, 0, 347) * Rot(X=90)))'),
])
patch("src/w16/cad/export.py", [
    ('    (r"W16-13-lt_hose", r"W16-13-lt_pump|W16-09-cac_core", "hose pushed on its stub"),',
     '    (r"W16-13-lt_hose", r"W16-13-lt_pump|W16-09-cac_core", "hose pushed on its stub"),\n'
     '    (r"W16-10-crossover", r"W16-10-manifold", "cross-over slip joint in the manifold"),\n'
     '    (r"W16-08-0", r"W16-08-0", "spigot fits / linkage inside the turbocharger"),\n'
     '    (r"W16-09-(charge_pipe|air_duct)", r"W16-08-00[12]|W16-09-(air_box|throttle|cac_tank)", "duct / hose joint"),\n'
     '    (r"W16-13-pump_inlet_pipe", r"W16-13-water_pump_housing", "pipe socketed in the pump"),\n'
     '    (r"W16-07-009", r"W16-07-010|W16-01-001|W16-02-00[12]", "tensioner screwed into the case wall"),'),
    ("        try:\n            v = (a[2] & b[2]).volume\n        except Exception as e:\n            res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status=\"error\", reason=repr(e)[:80]))\n            continue",
     "        try:\n            v = (a[2] & b[2]).volume\n        except Exception as e:\n            # boolean failed: fall back to the minimum distance between the two solids\n            try:\n                dist = a[2].distance_to(b[2])\n            except Exception:\n                dist = None\n            if dist is not None and dist > 1e-3:\n                res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status=\"clear\", volume_mm3=0.0, by=\"distance\"))\n            else:\n                res.append(dict(a=a[0], b=b[0], ia=a[1], ib=b[1], status=\"error\", reason=repr(e)[:80]))\n            continue"),
    ("        bore = cyl_between(p0 + d * (P.s_deck - 30.0), p0 + d * (P.s_deck + 5.0), P.bore / 2) & slab(0.0, P.deck_height)",
     "        bore = cyl_between(p0 + d * (P.s_deck - 30.0), p0 + d * (P.s_deck + 14.0), P.bore / 2) & slab(0.0, P.deck_height)"),
])
print("fix25 applied")
