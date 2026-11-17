"""Off-screen rendering helpers (pyvista / VTK)."""
from __future__ import annotations
import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True


def to_mesh(shape, tol=0.25, ang=0.35):
    """Triangulate a solid.  Falls back to other tolerances and finally to an STL round trip if the kernel
    returns faces without a triangulation."""
    for t, a in ((tol, ang), (tol * 0.5, ang * 0.7), (tol * 2.0, ang)):
        try:
            verts, tris = shape.tessellate(t, a)
            if tris:
                v = np.array([(p.X, p.Y, p.Z) for p in verts], float)
                f = np.hstack([np.full((len(tris), 1), 3), np.array(tris)]).ravel()
                return pv.PolyData(v, f)
        except Exception:
            continue
    try:
        import os
        import tempfile
        from build123d import export_stl
        path = os.path.join(tempfile.gettempdir(), "w16_tess_fallback.stl")
        export_stl(shape, path, tolerance=tol, angular_tolerance=ang)
        return pv.read(path)
    except Exception:
        return None


def render(items, path, view="iso", size=(1500, 1100), zoom=1.25, bg="white", clip=None, edges=False):
    """items: list of (mesh_or_shape, rgb, opacity).  view: 'iso' | 'front' | 'rear' | 'left' | 'right' | 'top' | 'bottom'
    or a camera position tuple.  clip: (normal, origin) half-space removed."""
    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background(bg)
    for it in items:
        m, col, op = (list(it) + [1.0])[:3]
        if not isinstance(m, pv.PolyData):
            m = to_mesh(m)
        if m is None:
            continue
        if clip is not None:
            m = m.clip(normal=clip[0], origin=clip[1])
            if m.n_points == 0:
                continue
        pl.add_mesh(m, color=col, opacity=op, smooth_shading=True, split_sharp_edges=True, feature_angle=35.0,
                    specular=0.3, show_edges=edges)
    pl.enable_parallel_projection()
    views = {"iso": (-1.0, 1.25, 0.85), "iso2": (1.0, 1.25, 0.85), "front": (-1, 0, 0), "rear": (1, 0, 0), "left": (0, -1, 0),
             "right": (0, 1, 0), "top": (0, 0, 1), "bottom": (0, 0, -1)}
    d = np.array(views[view] if isinstance(view, str) else view, float)
    up = (0, 0, 1) if abs(d[2]) < 0.95 * np.linalg.norm(d) else (0, 1, 0)
    pl.view_vector(d, viewup=up)
    pl.camera.zoom(zoom)
    pl.add_axes()
    pl.screenshot(path)
    pl.close()
    return path
