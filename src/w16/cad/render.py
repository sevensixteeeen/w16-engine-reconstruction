"""Technical visualisation: orthographic views, cutaways, exploded view, subsystem views and animations.

    python -m w16.cad.render            (all stills + animations)
"""
from __future__ import annotations
import math
import os
import sys
import numpy as np
import pyvista as pv
import imageio.v2 as imageio

from ..params import P
from .. import layout as L
from . import assembly as ASM, cranktrain as CT, head as H, viz
from .common import COLORS, GROUPS, ROOT

pv.OFF_SCREEN = True
OUT_V = os.path.join(ROOT, "06_ASSEMBLIES", "views")
OUT_A = os.path.join(ROOT, "09_ANIMATIONS")
GROUP_TINT = {"08": (0.55, 0.45, 0.40), "09": (0.16, 0.17, 0.20), "10": (0.50, 0.36, 0.28), "11": (0.80, 0.55, 0.15), "12": (0.75, 0.60, 0.20),
              "13": (0.25, 0.45, 0.75), "07": (0.60, 0.62, 0.30), "15": (0.30, 0.30, 0.32)}


def loc_matrix(loc):
    t = loc.wrapped.Transformation()
    m = np.eye(4)
    for r in range(3):
        for c in range(4):
            m[r, c] = t.Value(r + 1, c + 1)
    return m


def color_of(p):
    if p.group in GROUP_TINT and p.material not in ("al_cast",):
        return GROUP_TINT[p.group]
    if p.group in ("09", "10", "12", "13") :
        return GROUP_TINT[p.group]
    return COLORS[p.material]


class Scene:
    """Tessellates every part once and instantiates meshes for arbitrary locations."""

    def __init__(self, reg, tol=0.5, ang=0.45):
        self.reg = reg
        self.base = {}
        for pn, p in reg.parts.items():
            small = p.shape.volume < 3000.0
            m = viz.to_mesh(p.shape, 0.25 if small else tol, ang)
            if m is not None:
                self.base[pn] = m

    def items(self, select=None, locs=None, offset=None, color=None, opacity=None):
        out = []
        for pn, p in self.reg.parts.items():
            if pn not in self.base or (select and not select(p)):
                continue
            ll = (locs or {}).get(pn, p.locs)
            col = color(p) if color else color_of(p)
            op = opacity(p) if opacity else 1.0
            if col is None:
                continue
            merged = []
            for k, loc in enumerate(ll):
                M = loc_matrix(loc)
                if offset is not None:
                    d = offset(p, M)
                    M = M.copy()
                    M[:3, 3] += d
                merged.append(self.base[pn].transform(M, inplace=False))
            if merged:
                out.append((merged[0].merge(merged[1:]) if len(merged) > 1 else merged[0], col, op))
        return out


def moving_locs(reg, alpha):
    """Locations of all kinematic parts at crank angle alpha (springs keep their reference state)."""
    from build123d import Pos, Rot
    out = {}
    for pn, p in reg.parts.items():
        if p.moving == "crank":
            out[pn] = [Rot(X=alpha)]
    rl = [CT.rod_location(c, alpha) for c in L.CYLS]
    pl = [CT.piston_location(c, alpha) for c in L.CYLS]
    out["W16-04-001"] = rl
    out["W16-04-002"] = rl
    out["W16-04-003"] = [l * r for l in rl for r in (Rot(X=0), Rot(X=180))]
    out["W16-04-004"] = rl
    out["W16-04-005"] = [l * Pos(0, sy * CT.BOLT_Y, -21.0) for l in rl for sy in (-1, 1)]
    out["W16-03-001"] = pl
    out["W16-03-004"] = pl
    g = reg.parts["W16-03-002"]
    out["W16-03-002"] = [l * Pos(0, 0, z) for l in pl for z in RING_Z[:2]]
    out["W16-03-003"] = [l * Pos(0, 0, RING_Z[2]) for l in pl]
    out["W16-03-005"] = [l * Pos(sx * (P.pin_length / 2 + 0.95), 0, 0) for l in pl for sx in (-1, 1)]
    lay = H.LAY
    vloc = {k: [] for k in ("in_short", "in_long", "ex_short", "ex_long")}
    r_locs = []
    f_locs = {True: [], False: []}
    for b in (1, 2):
        for i in range(1, 9):
            c = L.CYL[i if b == 1 else 17 - i]
            li, le = H.lifts(c, alpha)
            for kind, lift in (("in", li), ("ex", le)):
                v = lay[H.row_of(i)][kind]
                far = v["far"]
                for s in (-1, 1):
                    vloc[f"{kind}_{'long' if far else 'short'}"].append(H.valve_location(b, i, kind, s, lift))
                    r_locs.append(H.along_valve(b, i, kind, s, 4.0 + lift))
                    f_locs[far].append(H.finger_location(b, i, kind, s, lift))
    for n, key in enumerate(("in_short", "in_long", "ex_short", "ex_long")):
        out[f"W16-06-00{n + 1}"] = vloc[key]
    out["W16-06-006"] = r_locs
    out["W16-06-007"] = f_locs[False]
    out["W16-06-013"] = f_locs[True]
    n = 9
    for b in (1, 2):
        for kind in ("in", "ex"):
            out[f"W16-06-0{n:02d}"] = [H.cam_location(b, kind, alpha)]
            n += 1
    return out


RING_Z = None


def shot(items, path, view, size=(1600, 1150), zoom=1.2, clip=None, parallel=True):
    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background("white")
    for m, col, op in items:
        if clip is not None:
            m = m.clip(normal=clip[0], origin=clip[1])
            if m.n_points == 0:
                continue
        pl.add_mesh(m, color=col, opacity=op, smooth_shading=True, split_sharp_edges=True, feature_angle=35.0, specular=0.25)
    if parallel:
        pl.enable_parallel_projection()
    d = np.array(view, float)
    up = (0, 0, 1) if abs(d[2]) < 0.95 * np.linalg.norm(d) else (1, 0, 0)
    pl.view_vector(d, viewup=up)
    pl.camera.zoom(zoom)
    img = pl.screenshot(path, return_img=True)
    pl.close()
    return img


VIEWS = {"front_free_end": (-1, 0, 0), "rear_flywheel_end": (1, 0, 0), "left_bank1_side": (0, 1, 0), "right_bank2_side": (0, -1, 0),
         "top": (0, 0, 1), "bottom": (0, 0, -1), "isometric": (-1.0, 1.1, 0.75), "isometric_rear": (1.0, -1.1, 0.75)}


def exploded_offset(p, M):
    """Explosion vector for an instance (group-wise, bank-aware)."""
    c = M[:3, 3]
    g = p.group
    name = p.name.lower()
    pn = p.pn
    side = 1.0 if c[1] >= 0 else -1.0
    ev = np.array([0, side * math.sin(math.radians(45)), math.cos(math.radians(45))])
    if pn == "W16-01-001":
        return np.zeros(3)
    if pn in ("W16-01-002", "W16-01-003", "W16-15-002", "W16-15-003"):
        return np.array([0, 0, -330.0])
    if pn == "W16-01-004":
        return np.array([0, 0, -450.0])
    if pn in ("W16-01-005",) or g == "05":
        return np.array([0, 0, -170.0])
    if g == "04":
        return np.array([0, 0, -170.0]) + 0.0 * ev
    if g == "03":
        return np.array([0, 0, -60.0])
    if pn in ("W16-01-006",):
        return _bank_ev(M) * 110.0
    if g == "02" or pn in ("W16-15-001",):
        k = 380.0 if "cover" in name else (300.0 if ("cap" in name) else 220.0)
        return _bank_ev(M) * k
    if g == "06" or g == "11" and ("plug" in name or "coil" in name):
        k = 300.0 if "camshaft" in name else (460.0 if ("plug" in name or "coil" in name) else 260.0)
        return _bank_ev(M) * k
    if pn == "W16-15-004":
        return _bank_ev(M) * 320.0
    if g == "07":
        return np.array([260.0 if "housing" in name else 150.0, 0, 0])
    if g == "08":
        return np.array([0, side * 330.0, -120.0])
    if g == "10":
        return np.array([0, side * 200.0, -40.0])
    if g == "09":
        return np.array([0, side * 150.0 if ("duct" in name or "pipe" in name or "box" in name or "filter" in name) else 0.0, 420.0 if "cooler" in name or "tank" in name or "throttle" in name else 300.0])
    if g == "11":
        return np.array([0, side * 60.0, 250.0])
    if g == "12":
        return np.array([-260.0, 0, -150.0]) if "cooler" not in name else np.array([0, 0, 180.0])
    if g == "13":
        return np.array([-300.0, 0, 120.0])
    if g == "14":
        if "flex" in name:
            return np.array([330.0, 0, -170.0])
        if "damper" in name:
            return np.array([-200.0, 0, -170.0])
        if "mount" in name:
            return np.array([0, side * 150.0, -200.0])
        if "harness" in name or "sensor" in name:
            return _bank_ev(M) * 420.0 if "harness" in name else np.zeros(3)
        return np.array([-380.0, 0, 160.0])
    return np.zeros(3)


def _bank_ev(M):
    """Unit vector of the bank the instance belongs to (from its position)."""
    y = M[1, 3]
    b = 1 if y >= 0 else 2
    return L.bank_axes(b)[2]


def stills(sc):
    os.makedirs(OUT_V, exist_ok=True)
    reg = sc.reg
    full = sc.items(select=lambda p: "vehicle mounted" not in p.name)
    for nm, v in VIEWS.items():
        shot(full, os.path.join(OUT_V, f"engine_{nm}.png"), v)
    # long block without external systems
    lb = sc.items(select=lambda p: p.group in ("01", "02", "03", "04", "05", "06", "07", "15"))
    shot(lb, os.path.join(OUT_V, "long_block_isometric.png"), VIEWS["isometric"])
    # transverse section through cylinder 1 / the paired cylinder 9 (four-bank arrangement)
    x1 = L.CYL[1].x
    shot(sc.items(select=lambda p: p.group in ("01", "02", "03", "04", "05", "06", "11", "15")), os.path.join(OUT_V, "section_transverse_cyl1.png"),
         (-1, 0, 0), clip=((-1, 0, 0), (x1, 0, 0)), zoom=1.5)
    shot(sc.items(select=lambda p: p.group in ("01", "02", "03", "04", "05", "06", "11", "15")), os.path.join(OUT_V, "section_transverse_cyl2.png"),
         (-1, 0, 0), clip=((-1, 0, 0), (L.CYL[2].x, 0, 0)), zoom=1.5)
    # transparent block cutaway with the crank train
    trans = sc.items(select=lambda p: p.group in ("01", "03", "04", "05"),
                     opacity=lambda p: 0.22 if p.pn in ("W16-01-001", "W16-01-002", "W16-01-004") else 1.0)
    shot(trans, os.path.join(OUT_V, "cutaway_transparent_block.png"), VIEWS["isometric"], zoom=1.25)
    shot(trans, os.path.join(OUT_V, "four_bank_arrangement_front.png"), (-1, 0, 0), zoom=1.4)
    ct = sc.items(select=lambda p: p.group in ("03", "04", "05") or p.pn == "W16-01-005")
    shot(ct, os.path.join(OUT_V, "crank_train_isometric.png"), VIEWS["isometric"], zoom=1.3)
    shot(ct, os.path.join(OUT_V, "crank_train_side.png"), (0, -1, 0), zoom=1.3)
    # head + valve train cutaway (bank 1, cover removed, head semi-transparent)
    vt = sc.items(select=lambda p: (p.group in ("06",) or p.pn in ("W16-02-001", "W16-02-004", "W16-02-005", "W16-11-001", "W16-11-002", "W16-07-007")),
                  opacity=lambda p: 0.25 if p.pn == "W16-02-001" else 1.0)
    vt = [(m.clip(normal=(0, -1, 0), origin=(0, 60, 0)), c, o) for m, c, o in vt]
    shot(vt, os.path.join(OUT_V, "valvetrain_cutaway_bank1.png"), (-0.6, 0.3, 1.0), zoom=1.5)
    tm = sc.items(select=lambda p: p.group in ("07", "05") or "camshaft" in p.name.lower())
    shot(tm, os.path.join(OUT_V, "timing_drive_rear.png"), (1, 0, 0), zoom=1.4)
    # turbocharger arrangement, intake path, exhaust path
    hot = lambda p: (0.85, 0.30, 0.10) if p.group == "10" else ((0.70, 0.25, 0.10) if "turbine" in p.name.lower() else None)
    cold = lambda p: (0.15, 0.45, 0.85) if p.group == "09" else ((0.35, 0.60, 0.90) if "compressor" in p.name.lower() else None)
    grey = lambda p: (0.82, 0.82, 0.84)
    base = sc.items(select=lambda p: p.group in ("01", "02"), color=grey, opacity=lambda p: 0.35)
    shot(base + sc.items(select=lambda p: p.group in ("08", "10"), color=lambda p: hot(p) or COLORS[p.material]) +
         sc.items(select=lambda p: p.group == "09", color=cold), os.path.join(OUT_V, "turbo_arrangement_isometric.png"), VIEWS["isometric"])
    shot(base + sc.items(select=lambda p: p.group in ("08", "10"), color=lambda p: hot(p) or COLORS[p.material]),
         os.path.join(OUT_V, "exhaust_gas_path_left.png"), (0.15, 1, 0.25))
    shot(base + sc.items(select=lambda p: p.group in ("08", "09"), color=lambda p: cold(p) or COLORS[p.material]),
         os.path.join(OUT_V, "intake_air_path_isometric.png"), VIEWS["isometric_rear"])
    shot(base + sc.items(select=lambda p: p.group == "13", color=lambda p: (0.10, 0.40, 0.85)) + sc.items(select=lambda p: "cooler core" in p.name.lower(), color=lambda p: (0.3, 0.6, 0.9)),
         os.path.join(OUT_V, "cooling_circuit_front.png"), (-1, 0.6, 0.6))
    shot(base + sc.items(select=lambda p: p.group == "12" or p.pn in ("W16-01-004", "W16-01-007"), color=lambda p: (0.85, 0.62, 0.10)),
         os.path.join(OUT_V, "lubrication_circuit_front.png"), (-1, -0.6, 0.3))
    # exploded view
    ex = sc.items(offset=exploded_offset)
    shot(ex, os.path.join(OUT_V, "exploded_isometric.png"), VIEWS["isometric"], size=(2200, 1600), zoom=1.1)
    shot(ex, os.path.join(OUT_V, "exploded_front.png"), (-1, 0, 0.15), size=(2200, 1600), zoom=1.1)


def write_anim(frames, name, fps=20):
    os.makedirs(OUT_A, exist_ok=True)
    imageio.mimsave(os.path.join(OUT_A, name + ".gif"), frames[::2] if len(frames) > 60 else frames, duration=1000 / fps * (2 if len(frames) > 60 else 1), loop=0)
    try:
        imageio.mimsave(os.path.join(OUT_A, name + ".mp4"), frames, fps=fps, macro_block_size=8)
    except Exception as e:                                     # pragma: no cover
        print("mp4 failed:", e)


def animations(sc):
    reg = sc.reg
    size = (1040, 760)
    # 1. turntable of the complete engine
    full = sc.items(select=lambda p: "vehicle mounted" not in p.name)
    frames = []
    for k in range(48):
        a = 2 * math.pi * k / 48
        frames.append(shot(full, os.path.join(OUT_A, "_tmp.png"), (math.cos(a), math.sin(a), 0.45), size=size, zoom=1.15))
    write_anim(frames, "01_engine_turntable", fps=12)
    # 2. crank train: crankshaft rotation and piston motion over 720 deg
    sel = lambda p: p.group in ("03", "04", "05")
    frames = []
    for al in np.arange(0, 720, 10.0):
        frames.append(shot(sc.items(select=sel, locs=moving_locs(reg, al)), os.path.join(OUT_A, "_tmp.png"), (-1.0, 1.1, 0.6), size=size, zoom=1.25))
    write_anim(frames, "02_crank_piston_motion", fps=18)
    frames = []
    for al in np.arange(0, 720, 10.0):
        frames.append(shot(sc.items(select=sel, locs=moving_locs(reg, al)), os.path.join(OUT_A, "_tmp.png"), (-1, 0, 0), size=size, zoom=1.4))
    write_anim(frames, "03_crank_piston_motion_front", fps=18)
    # 3. valve train of bank 1 with timing drive, pistons 1-2 visible through a transparent head
    x_lim = L.CYL[2].x + 50.0
    def sel_v(p):
        return p.group in ("05", "07") or p.group == "06" or p.pn in ("W16-02-001", "W16-03-001", "W16-04-001", "W16-04-002", "W16-06-008")
    frames = []
    for al in np.arange(0, 720, 8.0):
        it = sc.items(select=sel_v, locs=moving_locs(reg, al), opacity=lambda p: 0.18 if p.pn == "W16-02-001" else 1.0)
        it = [(m.clip(normal=(0, -1, 0), origin=(0, 30, 0)), c, o) for m, c, o in it]
        it = [(m, c, o) for m, c, o in it if m.n_points > 0]
        frames.append(shot(it, os.path.join(OUT_A, "_tmp.png"), (0.75, 0.25, 0.9), size=size, zoom=1.35))
    write_anim(frames, "04_valvetrain_timing_bank1", fps=18)
    try:
        os.remove(os.path.join(OUT_A, "_tmp.png"))
    except OSError:
        pass


def main(what="all"):
    global RING_Z
    reg, info = ASM.build(alpha=0.0)
    RING_Z = (info["piston"]["g1"], info["piston"]["g2"], info["piston"]["g3"])
    sc = Scene(reg)
    if what in ("all", "stills"):
        stills(sc)
    if what in ("all", "anim"):
        animations(sc)
    print("render done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
