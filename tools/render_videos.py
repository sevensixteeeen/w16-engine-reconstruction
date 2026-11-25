"""Presentation videos of the W16 (1080p H.264 MP4) with the PyVista pipeline of w16.cad.render (2026-11-25).

Separate from the engineering render: w16/cad/render.py and its outputs (06_ASSEMBLIES/views, 09_ANIMATIONS/*.gif|mp4) are
not touched; this script only imports its scene, kinematics and explosion helpers.  Output: 09_ANIMATIONS/video_1080p/
(or --out).

Clips (seconds at --time-scale 1):
  turntable   01  360 deg turntable of the dressed engine                                           12 s
  push_in     02  push-in from the dressed engine to the crank train: outer systems, heads and block
                  fade, the crank train keeps turning                                                  8 s
  exploded    03  exploded view apart and back, slow orbit                                            10 s
  cutaway     04  transparent block, pistons and crank running (one 720 deg cycle)                     8 s
  valvetrain  05  bank-1 close-up, cylinders 1-2: cams, fingers, valves, retainers and springs moving
                  (springs compress with the lift), head transparent                                    8 s
  rows        06  front view, the four rows highlighted one by one, crank turning                      10 s
  turbos      07  sequential turbocharging: the two A turbochargers, then all four                     10 s

Rendering: one plotter per clip and every mesh added once; moving parts are instance actors on shared meshes whose
matrices change per frame (kinematics of w16.cad.render.moving_locs); static parts are merged per sub-system (or per
explosion vector / highlight class).  Frames go straight to the encoder (libx264, CRF 18, yuv420p) - nothing is held in
memory.  One colour per sub-system (PALETTE) in every clip; highlights in one accent colour; clean gradient background.

Quality (--quality, QUALITY below):
  draft  FXAA, default light kit, render tessellation (0.5 mm / 0.45 rad) - the preview look
  high   (default) 2 x 2 supersampling (four renders per frame with sub-pixel camera jitter, averaged in linear light:
         the box filter of a render at twice the size, with frame buffers of the output size - a single render at
         2 x 1080p with SSAO and depth peeling needed ~1 GB of shared GPU memory on this machine), screen-space ambient
         occlusion in the clips without translucent parts (turntable, exploded; radius scaled to each shot), soft studio
         light kit (lower key-to-fill / key-to-head ratios, softer
         speculars), finer tessellation of parts >= 3 cm3 (0.2 mm / 0.2 rad: smoother silhouettes of round parts; the
         small many-instance parts as in draft), 10 depth-peeling layers.
         --ssaa 1 for one render per frame (about 4 x faster; FXAA only).
Translucency needs depth peeling AND FXAA here: without FXAA the off-screen read-back loses the translucent geometry (FXAA
stays on in every preset).  SSAO is not combined with translucent parts: PyVista's SSAO pass bypasses the renderer's depth
peeling, and with a dual depth-peeling pass inserted into its render steps the translucent parts came out coloured by the
SSAO position buffer (screen quadrants in red / green / yellow / black; 1080p test 2026-11-25) - so the clips with
translucent parts (push-in, cutaway, valvetrain, rows, turbos) render without SSAO, with the rest of the preset.
Tested with pyvista 0.49.2, VTK 9.7.2, AMD Radeon 740M.

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\render_videos.py [clip ...] [--size 1080p|4k|WxH] [--fps 30|60] [--quality high|draft]
                                                   [--ssaa N] [--time-scale 1] [--out DIR] [--preview]
  --preview     = --size 640x360 --quality draft --out 09_ANIMATIONS/video_preview (git-ignored)
  default output: 09_ANIMATIONS/video_<height>p[<fps> if not 30]/, e.g. video_1080p, video_2160p60

Final set (decision 2026-11-25, rendered after the 12 Dec freeze): 1080p, 30 fps, --quality high = the defaults.
Measured 2026-11-25 at 1920 x 1080, high: push-in 0.71 s per frame (translucent parts, no SSAO), turntable 0.32 s per
frame (SSAO); peak working set 1.71 GB, free system RAM fell by up to ~3 GB in all (the integrated GPU's memory is
shared) - about 20 min estimated for the seven clips.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import imageio.v2 as imageio  # noqa: E402
import pyvista as pv  # noqa: E402
from vtkmodules.vtkRenderingCore import vtkLightKit  # noqa: E402
from w16 import layout as L  # noqa: E402
from w16.params import P  # noqa: E402
from w16.cad import assembly as ASM, head as H, render as R, systems as SY, viz  # noqa: E402

pv.OFF_SCREEN = True
ANIM = os.path.join(ROOT, "09_ANIMATIONS")
PREVIEW_OUT = os.path.join(ANIM, "video_preview")
SIZES = {"preview": (640, 360), "720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "4k": (3840, 2160),
         "2160p": (3840, 2160)}
QUALITY = {
    # ssaa: supersampling factor per axis; ssao: ambient occlusion; soft: studio light kit and material; peels: depth
    # peeling layers; tol / ang: tessellation of parts >= 3 cm3 (linear mm, angular rad); ang_small: angular tolerance of the
    # parts < 3 cm3 (linear 0.25 mm as in render.Scene) - these are the many-instance parts (fasteners, keepers, rings),
    # whose finer tessellation multiplied the merged geometry beyond the free RAM in the first high-quality test
    "draft": dict(ssaa=1, ssao=False, soft=False, peels=6, tol=0.5, ang=0.45, ang_small=0.45),     # = render.Scene
    "high": dict(ssaa=2, ssao=True, soft=True, peels=10, tol=0.2, ang=0.2, ang_small=0.45),
}
SSAO_RADIUS, SSAO_BIAS, SSAO_KERNEL = 0.035, 0.0015, 128   # radius and bias as fractions of the half-height of the view

# one colour per sub-system (group), used in every clip
PALETTE = {"01": (0.80, 0.82, 0.85), "02": (0.69, 0.72, 0.77), "03": (0.88, 0.86, 0.80), "04": (0.56, 0.58, 0.64),
           "05": (0.33, 0.35, 0.40), "06": (0.29, 0.42, 0.63), "07": (0.74, 0.56, 0.27), "08": (0.91, 0.50, 0.15),
           "09": (0.20, 0.48, 0.82), "10": (0.62, 0.25, 0.17), "11": (0.28, 0.62, 0.36), "12": (0.92, 0.70, 0.14),
           "13": (0.12, 0.62, 0.66), "14": (0.27, 0.28, 0.31), "15": (0.32, 0.32, 0.35)}
ACCENT = (0.95, 0.30, 0.08)                     # highlight
DIM = (0.82, 0.83, 0.85)                        # de-emphasised parts
BG = ("white", "#d9e1ea")                       # bottom, top of the background gradient
CRANK_GROUPS = ("03", "04", "05")


# ---------------------------------------------------------------------------------------------------------- helpers
def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ramp(t, t0, t1):
    return ease((t - t0) / (t1 - t0))


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def visible(p):
    return "vehicle mounted" not in p.name


def is_spring(pn):
    return pn.startswith("W16-06-005")


def crank_train_pns(reg):
    """Kinematic crank-train parts: pistons with rings / pins / clips, rods with caps / shells / bushes / bolts, and every
    part turning with the crank."""
    return [pn for pn, p in reg.parts.items() if pn.startswith(("W16-03-", "W16-04-")) or p.moving == "crank"]


def cyl_of(pn, j, n):
    """Cylinder (layout.CYLS index) of instance j of a crank-train part with n instances (k instances per cylinder, in the
    order of render.moving_locs); None for parts turning with the crank."""
    if n % 16 or not pn.startswith(("W16-03-", "W16-04-")):
        return None
    return j // (n // 16)


_TO_LIN = np.where(np.arange(256) / 255.0 <= 0.04045, np.arange(256) / 255.0 / 12.92,
                   ((np.arange(256) / 255.0 + 0.055) / 1.055) ** 2.4).astype(np.float32)
_LIN_STEPS = 8192
_TO_SRGB = np.round(255.0 * np.where(np.linspace(0.0, 1.0, _LIN_STEPS) <= 0.0031308, 12.92 * np.linspace(0.0, 1.0, _LIN_STEPS),
                                     1.055 * np.linspace(0.0, 1.0, _LIN_STEPS) ** (1 / 2.4) - 0.055)).astype(np.uint8)


class TessScene:
    """The tessellation of render.Scene (only .base is used here), with the angular tolerance of the small parts set
    separately.  draft = render.Scene(reg) exactly."""

    def __init__(self, reg, tol, ang, ang_small):
        self.reg, self.base = reg, {}
        for pn, p in reg.parts.items():
            small = p.shape.volume < 3000.0
            m = viz.to_mesh(p.shape, 0.25 if small else tol, ang_small if small else ang)
            if m is not None:
                self.base[pn] = m


class Stage:
    """One off-screen plotter per clip; actors are added once and only matrices, colours, opacities and the camera change
    from frame to frame."""

    def __init__(self, sc, size, peel, q=QUALITY["draft"]):
        """size: output size (also the render size); q['ssaa'] = k: grab() averages k x k sub-pixel jittered renders."""
        self.sc, self.q, self.k, self.peel = sc, q, q["ssaa"], peel
        self.size = tuple(size)
        self._jit = [((i + 0.5) / self.k - 0.5, (j + 0.5) / self.k - 0.5) for j in range(self.k) for i in range(self.k)]
        self.pl = pv.Plotter(off_screen=True, window_size=self.size, lighting="none" if q["soft"] else "light kit")
        self.pl.set_background(BG[0], top=BG[1])
        if q["soft"]:
            lk = vtkLightKit()                         # softer than the default kit (key/fill 3, key/head 3)
            lk.SetKeyLightIntensity(0.80)
            lk.SetKeyToFillRatio(1.8)
            lk.SetKeyToHeadRatio(2.4)
            lk.SetKeyToBackRatio(2.6)
            lk.AddLightsToRenderer(self.pl.renderer)
        if peel:
            self.pl.enable_depth_peeling(number_of_peels=q["peels"], occlusion_ratio=0.0)
        self.pl.enable_anti_aliasing("fxaa")           # keep: with depth peeling the off-screen read-back needs it (module doc)
        self.mat = (dict(specular=0.22, specular_power=14.0, ambient=0.10, diffuse=0.90) if q["soft"] else
                    dict(specular=0.35, specular_power=25.0))
        self._norm, self._cap = {}, None
        self.aspect = size[0] / size[1]

    def ssao(self, half_height):
        """Screen-space ambient occlusion scaled to the shot (half-height of the view at the focal point, mm); only for
        stages without translucent parts (module doc)."""
        assert not self.peel, "SSAO is not combined with translucent parts"
        self.pl.enable_ssao(radius=SSAO_RADIUS * half_height, bias=SSAO_BIAS * half_height, kernel_size=SSAO_KERNEL, blur=True)

    def normals(self, pn, mesh=None):
        if pn not in self._norm:
            m = self.sc.base[pn] if mesh is None else mesh
            self._norm[pn] = m.compute_normals(split_vertices=True, feature_angle=35.0, cell_normals=False)
        return self._norm[pn]

    def add(self, mesh, color, opacity=1.0, M=None):
        a = self.pl.add_mesh(mesh, color=color, opacity=opacity, smooth_shading=False, show_scalar_bar=False, **self.mat)
        a.prop.interpolation = "phong"
        if M is not None:
            a.user_matrix = M
        return a

    def instances(self, pn, mats, color, opacity=1.0, mesh=None):
        m = self.normals(pn, mesh)
        return [self.add(m, color, opacity, M) for M in mats]

    def merged(self, items, color, opacity=1.0):
        """items: [(pn, M)] static instances merged into one actor, from the per-part meshes with their normals (computed
        once per part; the rigid transform carries them); points are not merged, which keeps the split normals."""
        parts = [self.normals(pn).transform(M, inplace=False) for pn, M in items]
        m = parts[0].merge(parts[1:], merge_points=False) if len(parts) > 1 else parts[0]
        return self.add(m, color, opacity)

    def camera(self, pos, focal, up=(0, 0, 1), angle=30.0):
        # through the plotter API, so the first render does not replace it with the default view
        self.pl.camera_position = [tuple(float(v) for v in pos), tuple(float(v) for v in focal), tuple(float(v) for v in up)]
        self.pl.camera.view_angle = angle
        self.pl.renderer.ResetCameraClippingRange()

    def caption(self, text):
        if text != self._cap:
            self.pl.add_text(text or " ", position="lower_left", font_size=max(int(self.size[1] / 54), 7), color="#2b2f36", name="cap")
            self._cap = text

    def grab(self):
        # render before each screenshot: an off-screen screenshot does not re-render by itself (every frame would be the first)
        if self.k == 1:
            self.pl.render()
            return self.pl.screenshot(return_img=True)
        cam, (w, h), acc = self.pl.camera, self.size, None
        for dx, dy in self._jit:                       # k x k sub-pixel offsets of the projection centre, box filter
            cam.SetWindowCenter(2.0 * dx / w, 2.0 * dy / h)
            self.pl.render()
            lin = _TO_LIN[self.pl.screenshot(return_img=True)[..., :3]]
            acc = lin if acc is None else acc + lin
        cam.SetWindowCenter(0.0, 0.0)
        return _TO_SRGB[np.minimum((acc * ((_LIN_STEPS - 1) / len(self._jit)) + 0.5).astype(np.int32), _LIN_STEPS - 1)]

    def close(self):
        self.pl.close()


def corners(actors, offsets=None, per_actor=1500):
    """World points of the visible actors for the framing: their mesh vertices (subsampled to per_actor), through each
    actor's user matrix, optionally shifted per actor.  (Bounding-box corners of merged meshes span a lot of empty space.)"""
    pts = []
    for k, a in enumerate(actors):
        if not a.GetVisibility():
            continue
        v = np.asarray(a.mapper.dataset.points)
        v = v[:: max(1, len(v) // per_actor)]
        M = np.asarray(a.user_matrix) if a.user_matrix is not None else np.eye(4)
        w = v @ M[:3, :3].T + M[:3, 3]
        if offsets is not None:
            w = w + offsets[k]
        pts.append(w)
    return np.vstack(pts)


def fit(pts, direction, aspect, angle=30.0, up=(0, 0, 1), focal=None, margin=1.06):
    """Perspective framing of the points seen from `direction` (camera on that side): focal point centred on their
    projection (or the given focal point) and the distance at which they fill the frustum (vertical view angle, aspect)."""
    f = -unit(direction)
    r = unit(np.cross(f, up))
    u = np.cross(r, f)
    x, y, z = pts @ r, pts @ u, pts @ f
    if focal is None:
        xc, yc, zc = (x.min() + x.max()) / 2, (y.min() + y.max()) / 2, (z.min() + z.max()) / 2
        focal = xc * r + yc * u + zc * f
    else:
        focal = np.asarray(focal, float)
        xc, yc, zc = focal @ r, focal @ u, focal @ f
    tv = math.tan(math.radians(angle / 2))
    th = tv * aspect
    dist = max(float(np.max(np.abs(x - xc) / th - (z - zc))), float(np.max(np.abs(y - yc) / tv - (z - zc))))
    return focal, margin * dist


def orbit(a_deg, el_deg):
    a, el = math.radians(a_deg), math.radians(el_deg)
    return np.array([math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)])


def orbit_fit(pts, a0, a1, el, aspect, angle=30.0, margin=1.06, n=12):
    """Fixed focal point (centre of the points' box) and the largest fitting distance along an orbit a0 -> a1."""
    c = (pts.min(0) + pts.max(0)) / 2
    return c, max(fit(pts, orbit(a, el), aspect, angle, focal=c, margin=margin)[1] for a in np.linspace(a0, a1, n))


def set_opacity(actors, op):
    for a in actors:
        a.prop.opacity = op
        a.SetVisibility(op > 0.01)


class CrankTrain:
    """Instance actors of the kinematic crank-train parts, moved with render.moving_locs."""

    def __init__(self, st, reg, cyls=None, color=None, select=None):
        """cyls: indices into layout.CYLS to keep (None = all); parts turning with the crank are always kept.
        select: optional filter on the part number."""
        self.reg, self.acts, self.cyl = reg, {}, {}
        ml = R.moving_locs(reg, 0.0)
        for pn in crank_train_pns(reg):
            if pn not in st.sc.base or (select is not None and not select(pn)):
                continue
            locs = ml.get(pn, self.reg.parts[pn].locs)
            idx = [j for j in range(len(locs)) if cyls is None or cyl_of(pn, j, len(locs)) is None or cyl_of(pn, j, len(locs)) in cyls]
            col = color(self.reg.parts[pn]) if color else PALETTE[self.reg.parts[pn].group]
            self.acts[pn] = list(zip(idx, st.instances(pn, [R.loc_matrix(locs[j]) for j in idx], col)))
            self.cyl[pn] = [cyl_of(pn, j, len(locs)) for j in idx]

    def all(self):
        return [a for v in self.acts.values() for _, a in v]

    def move(self, alpha, ml=None):
        ml = ml or R.moving_locs(self.reg, alpha)
        for pn, lst in self.acts.items():
            locs = ml.get(pn, self.reg.parts[pn].locs)
            for j, a in lst:
                a.user_matrix = R.loc_matrix(locs[j])


# ---------------------------------------------------------------------------------------------------------- clips
class Clip:
    name, file, seconds, peel, loop = "", "", 10.0, False, False

    def setup(self, st, reg):
        raise NotImplementedError

    def frame(self, st, t):
        raise NotImplementedError


def static_by_group(st, reg, select, exclude=()):
    """{group: [(pn, M)]} of the static instances of the selected parts."""
    out = {}
    for pn, p in reg.parts.items():
        if pn in st.sc.base and visible(p) and select(p) and pn not in exclude:
            out.setdefault(p.group, []).extend((pn, R.loc_matrix(l)) for l in p.locs)
    return out


class Turntable(Clip):
    name, file, seconds, loop = "turntable", "01_turntable_360", 12.0, True
    EL = 22.0

    def setup(self, st, reg):
        self.acts = [st.merged(items, PALETTE[g]) for g, items in static_by_group(st, reg, lambda p: True).items()]
        self.c, self.d = orbit_fit(corners(self.acts), 0.0, 360.0, self.EL, st.aspect, n=24)

    def frame(self, st, t):
        st.camera(self.c + self.d * orbit(135.0 + 360.0 * t, self.EL), self.c)      # starts at the front-left three-quarter view


class PushIn(Clip):
    name, file, seconds, peel = "push_in", "02_push_in_crank_train", 8.0, True
    DIR0, DIR1 = (-1.0, 1.1, 0.75), (-1.0, 0.85, 0.42)

    def setup(self, st, reg):
        self.reg = reg
        self.ct = CrankTrain(st, reg)
        moving = set(self.ct.acts)
        cls = {"outer": [], "heads": [], "block": [], "inner": []}
        def fade_class(p):
            if p.group in CRANK_GROUPS or p.pn in ("W16-01-005", "W16-01-007"):
                return "inner"
            if p.group == "01":
                return "block"
            if p.group in ("02", "06", "07", "15"):
                return "heads"
            return "outer"
        for g, items in static_by_group(st, reg, lambda p: True, exclude=moving).items():
            by = {}
            for pn, M in items:
                by.setdefault(fade_class(reg.parts[pn]), []).append((pn, M))
            for k, it in by.items():
                cls[k].append(st.merged(it, PALETTE[g]))
        self.cls = cls
        self.f0, self.d0 = fit(corners([a for v in cls.values() for a in v] + self.ct.all()), self.DIR0, st.aspect)
        self.f1, self.d1 = fit(corners(cls["block"] + self.ct.all()), self.DIR1, st.aspect, margin=1.02)

    def frame(self, st, t):
        self.ct.move(540.0 * t)
        set_opacity(self.cls["outer"], 1.0 - ramp(t, 0.10, 0.40))
        set_opacity(self.cls["heads"], 1.0 - ramp(t, 0.25, 0.55))
        set_opacity(self.cls["block"], 1.0 - 0.87 * ramp(t, 0.35, 0.70))
        s = ease(t)
        focal = (1 - s) * self.f0 + s * self.f1
        d = unit((1 - s) * unit(self.DIR0) + s * unit(self.DIR1))
        st.camera(focal + ((1 - s) * self.d0 + s * self.d1) * d, focal)


class Exploded(Clip):
    name, file, seconds = "exploded", "03_exploded_apart_and_back", 10.0
    A0, A1, EL = 140.0, 190.0, 24.0

    def setup(self, st, reg):
        groups = {}
        for pn, p in reg.parts.items():
            if pn not in st.sc.base or not visible(p):
                continue
            for l in p.locs:
                M = R.loc_matrix(l)
                v = R.exploded_offset(p, M)
                groups.setdefault((p.group, tuple(np.round(v, 3))), []).append((pn, M))
        self.acts = [(st.merged(items, PALETTE[g]), np.array(v)) for (g, v), items in groups.items()]
        acts = [a for a, _ in self.acts]
        self.c0, self.d0 = orbit_fit(corners(acts), self.A0, self.A1, self.EL, st.aspect)                           # assembled
        self.c1, self.d1 = orbit_fit(corners(acts, [v for _, v in self.acts]), self.A0, self.A1, self.EL, st.aspect)  # fully exploded

    def frame(self, st, t):
        e = ramp(t, 0.12, 0.42) - ramp(t, 0.62, 0.92)               # apart, hold, back
        for a, v in self.acts:
            M = np.eye(4)
            M[:3, 3] = e * v
            a.user_matrix = M
        c, d = (1 - e) * self.c0 + e * self.c1, (1 - e) * self.d0 + e * self.d1      # the framing follows the explosion
        st.camera(c + d * orbit(self.A0 + (self.A1 - self.A0) * t, self.EL), c)


class Cutaway(Clip):
    name, file, seconds, peel = "cutaway", "04_cutaway_crank_running", 8.0, True
    A0, A1, EL = 140.0, 165.0, 26.0

    def setup(self, st, reg):
        self.ct = CrankTrain(st, reg)
        sel = lambda p: p.group == "01" and p.pn != "W16-01-006"
        self.shell, self.inner = [], []
        for g, items in static_by_group(st, reg, sel, exclude=set(self.ct.acts)).items():
            outer = [(pn, M) for pn, M in items if pn in ("W16-01-001", "W16-01-002", "W16-01-003", "W16-01-004")]
            rest = [(pn, M) for pn, M in items if pn not in ("W16-01-001", "W16-01-002", "W16-01-003", "W16-01-004")]
            if outer:
                self.shell.append(st.merged(outer, PALETTE[g], 0.14))
            if rest:
                self.inner.append(st.merged(rest, PALETTE[g]))
        self.c, self.d = orbit_fit(corners(self.shell + self.ct.all()), self.A0, self.A1, self.EL, st.aspect)

    def frame(self, st, t):
        self.ct.move(720.0 * t)
        st.camera(self.c + self.d * orbit(self.A0 + (self.A1 - self.A0) * t, self.EL), self.c)


class Valvetrain(Clip):
    name, file, seconds, peel = "valvetrain", "05_valvetrain_closeup", 8.0, True
    MOVING = ("W16-06-001", "W16-06-002", "W16-06-003", "W16-06-004", "W16-06-006", "W16-06-007", "W16-06-013", "W16-06-009", "W16-06-010")
    CAMS = ("W16-06-009", "W16-06-010")

    def setup(self, st, reg):
        self.reg = reg
        x_max = 0.5 * (L.CYL[2].x + L.CYL[3].x)                     # bank-1 cylinders 1 and 2 (free end)
        keep = lambda M: M[1, 3] > 0.0 and M[0, 3] < x_max
        self.ct = CrankTrain(st, reg, cyls={k for k, c in enumerate(L.CYLS) if c.bank == 1 and c.no in (1, 2)},
                             select=lambda pn: pn.startswith("W16-03-"))          # pistons only: rods and crank would clutter the shot
        ml = R.moving_locs(reg, 0.0)
        self.vt = {}
        for pn in self.MOVING:
            if pn not in st.sc.base:
                continue
            locs = ml[pn]
            idx = [j for j, l in enumerate(locs) if keep(R.loc_matrix(l)) or pn in self.CAMS]
            self.vt[pn] = list(zip(idx, st.instances(pn, [R.loc_matrix(locs[j]) for j in idx], PALETTE["06"])))
        # springs: one mesh at the closed-valve height, compressed along its axis with the lift of its valve
        h0 = H.SEAT_DROP - 4.0
        sm = viz.to_mesh(H.spring_solid(h0), 0.25, 0.35)
        self.springs = []
        for i in range(1, 9):
            c = L.CYL[i]
            for kind in ("in", "ex"):
                for s in (-1, 1):
                    M = R.loc_matrix(H.along_valve(1, i, kind, s, H.SEAT_DROP))
                    if keep(M):
                        self.springs.append((c, kind, M, st.instances("_spring", [M], PALETTE["06"], mesh=sm)[0]))
        self.h0 = h0
        # bank-1 head casting transparent; guides, seat inserts, cam bearing caps and support elements of cylinders 1-2 opaque
        head = [(pn, R.loc_matrix(l)) for pn in ("W16-02-001",) for l in reg.parts[pn].locs]
        small = {}
        for pn in ("W16-02-004", "W16-02-005", "W16-02-006", "W16-02-007", "W16-06-008"):
            for l in reg.parts[pn].locs:
                M = R.loc_matrix(l)
                if keep(M):
                    small.setdefault(reg.parts[pn].group, []).append((pn, M))
        self.head = [st.merged(head, PALETTE["02"], 0.09)] + [st.merged(items, PALETTE[g]) for g, items in small.items()]
        pts = corners([a for *_, a in self.springs] + [a for pn, v in self.vt.items() if pn not in self.CAMS for _, a in v])
        cam = corners([a for pn, v in self.vt.items() if pn in self.CAMS for _, a in v], per_actor=20000)
        x0, x1 = pts[:, 0].min(), pts[:, 0].max()
        pts = np.vstack([pts, cam[(cam[:, 0] >= x0) & (cam[:, 0] <= x1)]])          # with the cam lobes over cylinders 1-2
        ex, eu, ev = L.bank_axes(1)
        self.dir = unit(0.85 * np.asarray(ev) + 0.55 * np.asarray(eu) - 0.65 * np.asarray(ex))
        self.c, self.d = fit(pts, self.dir, st.aspect, angle=32.0, margin=1.22)

    def frame(self, st, t):
        alpha = 720.0 * t
        ml = R.moving_locs(self.reg, alpha)
        self.ct.move(alpha, ml)
        for pn, lst in self.vt.items():
            for j, a in lst:
                a.user_matrix = R.loc_matrix(ml[pn][j])
        for c, kind, M, a in self.springs:
            li, le = H.lifts(c, alpha)
            S = np.eye(4)
            S[2, 2] = (self.h0 - (li if kind == "in" else le)) / self.h0
            a.user_matrix = M @ S
        st.camera(self.c + (1.0 - 0.10 * ease(t)) * self.d * self.dir, self.c, up=(0, 0, 1), angle=32.0)


class Rows(Clip):
    name, file, seconds, peel = "rows", "06_four_bank_rows", 10.0, True
    DIR = (-1.0, 0.0, 0.10)
    HIDE = ("W16-14-damper_ring", "W16-14-damper_hub_pulley", "W16-14-damper_bolt", "W16-14-flex_plate")

    def setup(self, st, reg):
        self.ct = CrankTrain(st, reg, select=lambda pn: pn not in self.HIDE)      # the damper would cover the throws
        self.shell = [st.merged(items, PALETTE[g], 0.10)                          # block only: the heads read as haze
                      for g, items in static_by_group(st, reg, lambda p: p.pn in ("W16-01-001", "W16-01-002")).items()]
        self.rows = []
        for bank in (1, 2):
            for row in (("outer", "inner") if bank == 1 else ("inner", "outer")):
                cyls = [k for k, c in enumerate(L.CYLS) if c.bank == bank and c.row == row]
                nos = ", ".join(str(L.CYLS[k].no) for k in cyls)
                self.rows.append((set(cyls), f"Bank {bank} - {row} row: cylinders {nos}"))
        self.c, self.d = fit(corners(self.shell + self.ct.all()), self.DIR, st.aspect, angle=24.0, margin=1.04)

    def frame(self, st, t):
        self.ct.move(360.0 * t)
        k = int((t - 0.12) / 0.22) if t >= 0.12 else -1
        k = min(k, 3)
        cur, cap = self.rows[k] if k >= 0 else (set(), f"Four rows: two VR8 banks {P.bank_angle:.0f} deg apart, each with two rows "
                                                         f"{P.vr_angle:.0f} deg apart")
        for pn, lst in self.ct.acts.items():
            for (j, a), cy in zip(lst, self.ct.cyl[pn]):
                a.prop.color = ACCENT if (cy is not None and cy in cur) else PALETTE[self.ct.reg.parts[pn].group]
        st.caption(cap)
        st.camera(self.c + self.d * unit(self.DIR), self.c, angle=24.0)


class Turbos(Clip):
    name, file, seconds, peel = "turbos", "07_sequential_turbos", 10.0, True
    A0, A1, EL = 200.0, 228.0, 20.0                 # front-left: the four turbochargers (both sides, crank height) stay apart
    GHOST = ("01", "02", "09", "10")                # block, heads, intake, exhaust as a ghost; the rest is left out

    def setup(self, st, reg):
        self.A, self.B, rest = [], [], {}
        for pn, p in reg.parts.items():
            if pn not in st.sc.base or not visible(p):
                continue
            for l in p.locs:
                M = R.loc_matrix(l)
                if p.group == "08":
                    (self.A if abs(M[0, 3] - SY.X_TA) < abs(M[0, 3] - SY.X_TB) else self.B).append((pn, M))
                elif p.group in self.GHOST:
                    rest.setdefault(p.group, []).append((pn, M))
        self.rest = [st.merged(items, DIM, 0.22) for items in rest.values()]
        self.a, self.b = st.merged(self.A, DIM), st.merged(self.B, DIM)
        self.c, self.d = orbit_fit(corners(self.rest + [self.a, self.b]), self.A0, self.A1, self.EL, st.aspect)

    def frame(self, st, t):
        fa, fb = ramp(t, 0.18, 0.30), ramp(t, 0.58, 0.70)
        self.a.prop.color = tuple((1 - fa) * np.array(DIM) + fa * np.array(PALETTE["08"]))
        self.b.prop.color = tuple((1 - fb) * np.array(DIM) + fb * np.array(PALETTE["08"]))
        st.caption("" if t < 0.18 else ("Up to about 3,800 rpm: the two turbochargers A" if t < 0.58 else
                                         "Above about 3,800 rpm: all four turbochargers (A + B)"))
        st.camera(self.c + self.d * orbit(self.A0 + (self.A1 - self.A0) * t, self.EL), self.c)


CLIPS = {c.name: c for c in (Turntable, PushIn, Exploded, Cutaway, Valvetrain, Rows, Turbos)}


# ---------------------------------------------------------------------------------------------------------- driver
def render_clip(clip, sc, reg, size, fps, time_scale, out_dir, proc, peak, q=QUALITY["draft"]):
    n = max(2, int(round(clip.seconds * time_scale * fps)))
    st = Stage(sc, size, clip.peel, q)
    t0 = time.time()
    clip.setup(st, reg)
    ssao = bool(q["ssao"]) and not clip.peel                    # not with translucent parts (module doc)
    if ssao:
        clip.frame(st, 0.5)                                    # scale of the shot (every frame() sets its full state)
        cam = st.pl.camera
        st.ssao(cam.distance * math.tan(math.radians(cam.view_angle) / 2))
    t_setup = time.time() - t0
    path = os.path.join(out_dir, f"{clip.file}.mp4")
    w = imageio.get_writer(path, fps=fps, codec="libx264", quality=None, pixelformat="yuv420p", macro_block_size=8,
                           ffmpeg_params=["-crf", "18", "-preset", "medium"])
    t1 = time.time()
    for k in range(n):
        clip.frame(st, k / n if clip.loop else k / (n - 1))
        w.append_data(st.grab())
        peak[0] = max(peak[0], proc.memory_info().rss)
    w.close()
    st.close()
    dt = time.time() - t1
    return dict(clip=clip.name, file=path, frames=n, size=list(size), renders_per_frame=st.k ** 2, ssao=ssao, fps=fps, setup_s=round(t_setup, 1),
                render_s=round(dt, 1), s_per_frame=round(dt / n, 3), mb=round(os.path.getsize(path) / 2**20, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*", default=list(CLIPS), help=f"any of {', '.join(CLIPS)} (default: all)")
    ap.add_argument("--size", default=None, help=f"{' | '.join(SIZES)} | WxH (default 1080p)")
    ap.add_argument("--fps", type=int, default=30, help="30 or 60 (any value works)")
    ap.add_argument("--quality", choices=list(QUALITY), default=None, help="default high (draft with --preview)")
    ap.add_argument("--ssaa", type=int, default=None, help="supersampling factor per axis = jittered renders k x k (default: the preset's)")
    ap.add_argument("--time-scale", type=float, default=1.0, help="scales the clip lengths (e.g. 0.5 for a short test)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--preview", action="store_true", help="640x360, draft quality, into 09_ANIMATIONS/video_preview (git-ignored)")
    a = ap.parse_args()
    sz = (a.size or ("preview" if a.preview else "1080p")).lower()
    size = SIZES[sz] if sz in SIZES else tuple(int(v) for v in sz.split("x"))
    q = dict(QUALITY[a.quality or ("draft" if a.preview else "high")])
    if a.ssaa is not None:
        q["ssaa"] = a.ssaa
    if a.out is None:
        a.out = PREVIEW_OUT if a.preview else os.path.join(ANIM, f"video_{size[1]}p" + ("" if a.fps == 30 else str(a.fps)))
    os.makedirs(a.out, exist_ok=True)
    print(f"output {a.out}: {size[0]}x{size[1]}, {a.fps} fps, quality {q}", flush=True)
    proc, peak = psutil.Process(), [0]
    t0 = time.time()
    reg, info = ASM.build(alpha=0.0)
    R.RING_Z = (info["piston"]["g1"], info["piston"]["g2"], info["piston"]["g3"])
    t_build = time.time() - t0
    peak[0] = max(peak[0], proc.memory_info().rss)
    t0 = time.time()
    sc = TessScene(reg, q["tol"], q["ang"], q["ang_small"])
    t_scene = time.time() - t0
    peak[0] = max(peak[0], proc.memory_info().rss)
    n_tri = sum(m.n_cells for m in sc.base.values())
    print(f"build {t_build:.0f} s, tessellation {t_scene:.0f} s, {len(sc.base)} part meshes ({n_tri / 1e6:.2f} M triangles), "
          f"RSS {proc.memory_info().rss / 2**30:.2f} GB", flush=True)
    res = []
    for name in a.clips:
        r = render_clip(CLIPS[name](), sc, reg, size, a.fps, a.time_scale, a.out, proc, peak, q)
        res.append(r)
        print(json.dumps(r), flush=True)
    mi = proc.memory_info()
    summary = dict(quality=q, part_triangles=n_tri, build_s=round(t_build, 1), tessellation_s=round(t_scene, 1), clips=res,
                   peak_rss_sampled_gb=round(peak[0] / 2**30, 2),
                   peak_working_set_gb=round(getattr(mi, "peak_wset", peak[0]) / 2**30, 2))
    with open(os.path.join(a.out, "render_videos_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "clips"}), flush=True)


if __name__ == "__main__":
    main()
