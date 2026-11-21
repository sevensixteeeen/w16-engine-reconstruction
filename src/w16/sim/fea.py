"""Finite-element analyses with gmsh (tetrahedral meshing of the CAD solids) and scikit-fem (linear elasticity and
steady heat conduction).  Every case writes a JSON record with inputs, mesh statistics and results; nothing is
reported unless the solver ran.

    python -m w16.sim.fea [case ...]        cases: rod piston crank insert block head
"""
from __future__ import annotations
import json
import math
import os
import sys
import tempfile
import time
import numpy as np
import gmsh
import pyvista as pv
import scipy.sparse as sp
from scipy.sparse.linalg import splu, spsolve
from skfem import Basis, BilinearForm, ElementTetP1, ElementTetP2, ElementVector, FacetBasis, LinearForm, MeshTet, asm, condense
from skfem.helpers import ddot, div, dot, grad, sym_grad, trace
from skfem.models.elasticity import lame_parameters, linear_elasticity
from build123d import Align, Box, Cylinder, Location, Pos, Rot, export_step, import_brep

from ..params import P, MATERIALS
from .. import layout as L
from ..analysis import cycle as CY
from ..cad import block as B, cranktrain as CT, head as H
from ..cad.common import MAT, ROOT, bank_plane, head_plane

pv.OFF_SCREEN = True
OUT = os.path.join(ROOT, "08_SIMULATIONS", "fea")
ANA = os.path.join(ROOT, "08_SIMULATIONS", "analytical", "results.json")


def results():
    with open(ANA, encoding="utf-8") as fh:
        return json.load(fh)


def mat(key):
    m = MATERIALS[MAT[key]]
    return dict(name=MAT[key], E=m["E"] * 1e3, nu=m["nu"], alpha=m["alpha"], k=m["k"] * 1e-3, yield_=m["yield_"], fatigue=m["fatigue"], rho=m["rho"])
    # units: N, mm, MPa; conductivity in W/(mm K)


def mesh_shape(shape, h, name, h_min=None, refine=None):
    """Tetrahedral mesh of a build123d solid.  refine: list of (point, radius, size) local refinements."""
    path = os.path.join(tempfile.gettempdir(), f"w16_fea_{name}.step")
    export_step(shape, path)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(name)
    gmsh.model.occ.importShapes(path)
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h_min or h / 5)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 9)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.Optimize", 1)
    if refine:
        fields = []
        for i, (pt, rad, size) in enumerate(refine):
            f = gmsh.model.mesh.field.add("Ball")
            gmsh.model.mesh.field.setNumber(f, "XCenter", pt[0]); gmsh.model.mesh.field.setNumber(f, "YCenter", pt[1]); gmsh.model.mesh.field.setNumber(f, "ZCenter", pt[2])
            gmsh.model.mesh.field.setNumber(f, "Radius", rad); gmsh.model.mesh.field.setNumber(f, "VIn", size); gmsh.model.mesh.field.setNumber(f, "VOut", h)
            gmsh.model.mesh.field.setNumber(f, "Thickness", rad)
            fields.append(f)
        fm = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(fm, "FieldsList", fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(fm)
    gmsh.model.mesh.generate(3)
    tags, coords, _ = gmsh.model.mesh.getNodes()
    etags, enodes = gmsh.model.mesh.getElementsByType(4)
    q = np.asarray(gmsh.model.mesh.getElementQualities(list(etags), "gamma"))
    gmsh.finalize()
    # zero-volume slivers (gamma ~ 0) - produced where the CAD has steps far below the mesh size, e.g. the 0.05 mm steps at
    # the head port bends (D-039) - make the element matrices singular; they are dropped (25 of 57,185 in the head slice).
    # The meshes of all other cases have gamma >= 2e-5 (2026-11-17), so they are unaffected.
    keep = q > 1e-6
    n_drop = int((~keep).sum())
    enodes = np.asarray(enodes).reshape(-1, 4)[keep].ravel()
    q = q[keep]
    idx = np.zeros(int(tags.max()) + 1, dtype=np.int64)
    idx[tags.astype(np.int64)] = np.arange(len(tags))
    p = coords.reshape(-1, 3).T.copy()
    t = idx[enodes.astype(np.int64)].reshape(-1, 4).T.copy()
    used = np.unique(t)
    remap = -np.ones(p.shape[1], dtype=np.int64); remap[used] = np.arange(len(used))
    p, t = p[:, used], remap[t]
    v = np.einsum("ij,ij->j", np.cross(p[:, t[1]] - p[:, t[0]], p[:, t[2]] - p[:, t[0]], axis=0), p[:, t[3]] - p[:, t[0]])
    neg = v < 0
    t[0, neg], t[1, neg] = t[1, neg].copy(), t[0, neg].copy()
    m = MeshTet(p, t)
    stats = dict(nodes=int(p.shape[1]), tets=int(t.shape[1]), h_max=h, quality_gamma_min=float(q.min()), quality_gamma_mean=float(q.mean()),
                 quality_below_0p1=int((q < 0.1).sum()), volume_mm3=float(np.abs(v).sum() / 6), dropped_zero_volume_tets=n_drop)
    return m, stats


def facets(m, cond):
    return m.facets_satisfying(cond, boundaries_only=True)


def facets_by_normal(m, fc, direction, cos_min=0.9):
    """Subset of facets fc whose (unsigned) unit normal is within acos(cos_min) of direction."""
    a, b, c = (m.p[:, m.facets[k, fc]] for k in range(3))
    nn = np.cross(b - a, c - a, axis=0)
    nn /= np.maximum(np.linalg.norm(nn, axis=0), 1e-12)
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    return fc[np.abs(d @ nn) >= cos_min]


def facets_radial(m, fc, axis, cos_min=0.9):
    """Subset of facets fc whose (unsigned) unit normal is within acos(cos_min) of the radial direction about a coordinate
    axis through the origin (axis 0 = x, 2 = z)."""
    a, b, c = (m.p[:, m.facets[k, fc]] for k in range(3))
    nn = np.cross(b - a, c - a, axis=0)
    nn /= np.maximum(np.linalg.norm(nn, axis=0), 1e-12)
    mid = (a + b + c) / 3
    mid[axis] = 0.0
    er = mid / np.maximum(np.linalg.norm(mid, axis=0), 1e-12)
    return fc[np.abs((er * nn).sum(0)) >= cos_min]


def spd_factor(A):
    """Direct sparse factorisation of a symmetric positive-definite system (constrained stiffness matrix).  SuperLU with a
    symmetric fill-reducing ordering and diagonal pivots: the same direct solution as the default spsolve (COLAMD column
    ordering, meant for unsymmetric matrices) with less fill-in, memory and time on 3-D meshes (piston, coarse mesh:
    identical displacements to 1e-12, half the time)."""
    return splu(A, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))


class CGSolver:
    """Low-memory alternative to spd_factor: Jacobi-preconditioned conjugate gradients (same interface: .solve(b)).
    Matched the direct solver to 1e-11 on the piston; used where a fine local mesh makes the direct factorisation too large."""
    def __init__(self, A, rtol=1e-10):
        from scipy.sparse.linalg import cg
        self.A, self.cg, self.rtol = A.tocsr(), cg, rtol
        self.M = sp.diags(1.0 / self.A.diagonal())

    def solve(self, b):
        t, it = time.time(), [0]
        x, info = self.cg(self.A, b, rtol=self.rtol, maxiter=500000, M=self.M, callback=lambda xk: it.__setitem__(0, it[0] + 1))
        if info != 0:
            raise RuntimeError(f"CG did not converge (info {info}, {it[0]} iterations)")
        print(f"    CG converged: {it[0]} iterations, {time.time() - t:.0f} s", flush=True)
        return x


def spd_solve(A, b):
    lu = spd_factor(A)
    x = lu.solve(b)
    del lu
    return x


def solve_elastic(m, mt, fixed, tractions=(), body=None, thermal=None, order=2, fixed_dirs=None, pressures=(), balance=None, points=(),
                  factor_cache=None, iterative=False):
    """fixed: facet index array (all displacement components fixed) ; tractions: list of (facets, fn(x) -> 3 x ... array, MPa);
    body: fn(x) -> force density N/mm3; thermal: nodal temperature rise array on P1 nodes (K).
    pressures: list of (facets, p MPa) acting against the outward facet normal.  balance: (facets, fn, component) - a traction
    shape scaled so that the total applied force along that component is exactly zero (load-controlled support, e.g. a
    bearing reaction).  points: list of (node index, components) fixed at single nodes (statically determinate support).
    factor_cache: dict shared by load cases on the same mesh, material and constraints - the factorisation is reused."""
    e = ElementVector(ElementTetP2() if order == 2 else ElementTetP1())
    ib = Basis(m, e, intorder=4 if order == 2 else 2)
    lam, mu = lame_parameters(mt["E"], mt["nu"])
    K = asm(linear_elasticity(lam, mu), ib)
    f = np.zeros(ib.N)

    def resultant(vec):
        return np.array([vec[ib.nodal_dofs[i]].sum() + (vec[ib.edge_dofs[i]].sum() if order == 2 else 0.0) for i in range(3)])

    def traction_vector(fc, fn):
        fb = FacetBasis(m, e, facets=fc, intorder=4)

        @LinearForm
        def trac(v, w):
            tv = fn(w.x)
            return tv[0] * v.value[0] + tv[1] * v.value[1] + tv[2] * v.value[2]
        return asm(trac, fb)
    for fc, fn in tractions:
        f += traction_vector(fc, fn)
    for fc, pr in pressures:
        fb = FacetBasis(m, e, facets=fc, intorder=4)

        @LinearForm
        def prs(v, w):
            return -pr * (w.n[0] * v.value[0] + w.n[1] * v.value[1] + w.n[2] * v.value[2])
        f += asm(prs, fb)
    if body is not None:
        @LinearForm
        def bf(v, w):
            b = body(w.x)
            return b[0] * v.value[0] + b[1] * v.value[1] + b[2] * v.value[2]
        f += asm(bf, ib)
    Tq = None
    if thermal is not None:
        tb = ib.with_element(ElementTetP1())
        Tq = tb.interpolate(thermal)

        @LinearForm
        def th(v, w):
            return (3 * lam + 2 * mu) * mt["alpha"] * w["dT"] * div(v)
        f += asm(th, ib, dT=Tq)
    applied = resultant(f)                               # all external loads (thermal loads are self-equilibrated)
    scale, bal_force = None, np.zeros(3)
    if balance is not None:
        fc, fn, comp = balance
        g = traction_vector(fc, fn)
        scale = -applied[comp] / resultant(g)[comp]
        f += scale * g
        bal_force = scale * resultant(g)
    D = ib.get_dofs(fixed).all() if fixed is not None and len(fixed) else np.zeros(0, dtype=np.int64)
    for fc, comp in (fixed_dirs or ()):                  # symmetry planes: one displacement component fixed
        D = np.union1d(D, ib.get_dofs(fc).all(f"u^{comp + 1}"))
    pt = [(int(ib.nodal_dofs[c][n]), c) for n, comps in points for c in comps]
    if pt:
        D = np.union1d(D, [d for d, _ in pt])
    u = np.zeros(ib.N)
    I = np.setdiff1d(np.arange(ib.N), D)
    t0 = time.time()
    if factor_cache is not None and factor_cache.get("N") == ib.N and np.array_equal(factor_cache.get("D"), D):
        u[I] = factor_cache["lu"].solve(f[I])
    elif factor_cache is not None:
        factor_cache.clear()
        factor_cache.update(N=ib.N, D=D, lu=spd_factor(K[I][:, I].tocsc()))
        u[I] = factor_cache["lu"].solve(f[I])
    elif iterative:
        u[I] = CGSolver(K[I][:, I]).solve(f[I])
    else:
        u[I] = spd_solve(K[I][:, I].tocsc(), f[I])
    t_solve = time.time() - t0
    # stresses at quadrature points -> element means and nodal displacement magnitudes
    ui = ib.interpolate(u)
    eps = sym_grad(ui)
    tr = eps[0, 0] + eps[1, 1] + eps[2, 2]
    sig = 2 * mu * eps
    th_s = (3 * lam + 2 * mu) * mt["alpha"] * Tq.value if Tq is not None else 0.0
    for i in range(3):
        sig[i, i] = sig[i, i] + lam * tr - th_s
    vm = np.sqrt(0.5 * ((sig[0, 0] - sig[1, 1]) ** 2 + (sig[1, 1] - sig[2, 2]) ** 2 + (sig[2, 2] - sig[0, 0]) ** 2) +
                 3 * (sig[0, 1] ** 2 + sig[1, 2] ** 2 + sig[0, 2] ** 2))
    vm_el = vm.mean(axis=1)
    s1 = None
    nd = ib.nodal_dofs
    U = np.vstack([u[nd[0]], u[nd[1]], u[nd[2]]])
    react = K @ u - f
    point_reaction = np.zeros(3)
    for d, c in pt:
        point_reaction[c] += react[d]
    return dict(u=u, U=U, vm=vm_el, dofs=int(ib.N), t_solve=t_solve, applied=applied, balance_scale=scale, balance_force=bal_force,
                point_reaction=point_reaction)


def solve_thermal(m, k, robin=(), flux=()):
    """Steady conduction.  robin: list of (facets, h [W/mm2K], T_inf [K]); flux: list of (facets, q [W/mm2])."""
    e = ElementTetP1()
    ib = Basis(m, e)

    @BilinearForm
    def cond(u, v, w):
        return k * dot(grad(u), grad(v))
    A = asm(cond, ib)
    b = np.zeros(ib.N)
    q_in = 0.0
    for fc, h, T in robin:
        fb = FacetBasis(m, e, facets=fc)
        A = A + asm(BilinearForm(lambda u, v, w: h * u * v), fb)
        b += asm(LinearForm(lambda v, w: h * T * v), fb)
    for fc, q in flux:
        fb = FacetBasis(m, e, facets=fc)
        b += asm(LinearForm(lambda v, w: q * v), fb)
    T = spsolve(A.tocsc(), b)
    out = []
    for fc, h, Tinf in robin:
        fb = FacetBasis(m, e, facets=fc)
        out.append(float(asm(LinearForm(lambda v, w: h * (Tinf - w["T"]) * 1.0), fb, T=fb.interpolate(T)).sum()) if False else
                   float((h * (Tinf - fb.interpolate(T).value) * fb.dx).sum()))
    return T, out


def picture(m, cell=None, point=None, title="", path="", view=(1, -1, 0.6), clim=None, units=""):
    cells = np.hstack([np.full((m.t.shape[1], 1), 4), m.t.T]).ravel()
    g = pv.UnstructuredGrid(cells, np.full(m.t.shape[1], 10, dtype=np.uint8), m.p.T.copy())
    name = title
    if cell is not None:
        g.cell_data[name] = cell
    else:
        g.point_data[name] = point
    pl = pv.Plotter(off_screen=True, window_size=(1300, 950))
    pl.set_background("white")
    pl.add_mesh(g, scalars=name, cmap="turbo", clim=clim, show_edges=False, scalar_bar_args=dict(title=f"{title} {units}", color="black", n_labels=6, fmt="%.0f"))
    pl.enable_parallel_projection()
    pl.view_vector(view, viewup=(0, 0, 1))
    pl.camera.zoom(1.25)
    pl.screenshot(path)
    pl.close()


def peak(m, vm, frac=0.999):
    """Peak and 99.9th-percentile element von Mises stress and the location of the peak.  The percentile is taken over the
    element values unweighted - every element counts once whatever its volume, so locally refined regions weigh more.  Kept
    unweighted so that the results stay comparable with the earlier runs (the docstring said volume-weighted until D-043)."""
    i = int(np.argmax(vm))
    c = m.p[:, m.t[:, i]].mean(axis=1)
    return float(vm[i]), float(np.quantile(vm, frac)), c.tolist()


def save(name, rec):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(name, json.dumps({k: v for k, v in rec.items() if k in ("mesh", "results")}, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))[:900])


def progress(name, rec, *keys):
    """Print finished sub-cases to the log as soon as they are solved, so a run that is stopped part-way keeps them
    (the case JSON is written only at the end; no partial JSON goes into the results folder, which the report reads)."""
    for k in keys:
        print(name, k, json.dumps(rec["results"][k], default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)), flush=True)


def cos_load(axis_pt, axis_dir, load_dir, F, m, fc):
    """Bearing load F (N) along load_dir applied as a cosine pressure on the half of a bore facing load_dir."""
    e = ElementTetP1()
    fb = FacetBasis(m, e, facets=fc)
    ld = np.array(load_dir, float) / np.linalg.norm(load_dir)

    def weight(x):
        r = x - np.array(axis_pt, float).reshape(3, 1, 1)
        ad = np.array(axis_dir, float).reshape(3, 1, 1)
        r = r - ad * (r * ad).sum(0)
        rn = r / np.maximum(np.sqrt((r * r).sum(0)), 1e-9)
        return np.clip((rn * ld.reshape(3, 1, 1)).sum(0), 0, None)
    w_int = float((weight(fb.global_coordinates().value) * fb.dx).sum())          # traction acts along load_dir: resultant = p0 * sum(cos dA)
    p0 = F / w_int
    return (lambda x: weight(x) * p0 * ld.reshape(3, 1, 1)), p0


# ====================================================================== cases
def case_rod():
    R = results()["dynamics"]
    body, cap, shell, bush, bolt = CT.rod_solids()
    shape = body + cap
    mt = mat("ti")
    l = P.rod_length
    m, st = mesh_shape(shape, 4.2, "rod", refine=[((0, 0, l - 22), 18, 2.4), ((0, 0, 30), 18, 2.6)])
    be = facets(m, lambda x: np.hypot(x[1], x[2]) < CT.BE_BORE_R + 0.05)
    se = facets(m, lambda x: np.hypot(x[1], x[2] - l) < CT.SE_BORE_R + 0.05)
    rec = dict(case="connecting rod", material=mt, mesh=st, element="P2 tetrahedra", results={}, inputs={})
    for name, F, se_dir, be_half in (("compression_design_gas_force", R["F_design_gas"], (0, 0, -1), 1.0), ("tension_overspeed_inertia", R["rod_peak_tens_overspeed"], (0, 0, 1), -1.0)):
        fix = facets(m, lambda x: (np.hypot(x[1], x[2]) < CT.BE_BORE_R + 0.05) & (x[2] * be_half > 6.0))
        fn, p0 = cos_load((0, 0, l), (1, 0, 0), se_dir, F, m, se)
        s = solve_elastic(m, mt, fix, tractions=[(se, fn)])
        pk, p999, loc = peak(m, s["vm"])
        dz = float(np.abs(s["U"][2]).max())
        rec["results"][name] = dict(force_N=F, applied_force_check_N=s["applied"].tolist(), peak_bearing_pressure_MPa=p0, vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc,
                                    max_axial_displacement_mm=dz, dofs=s["dofs"], solve_s=s["t_solve"], yield_factor_on_p999=mt["yield_"] / p999)
        picture(m, cell=s["vm"], title="von Mises", units="[MPa]", path=os.path.join(OUT, f"rod_{name}.png"), view=(1, -0.5, 0.2), clim=(0, p999))
    a = rec["results"]
    sc, stn = a["compression_design_gas_force"]["vm_p999_MPa"], a["tension_overspeed_inertia"]["vm_p999_MPa"]
    rec["results"]["fatigue_estimate"] = dict(note="alternating stress taken as half the sum of the two p99.9 stresses (conservative, locations differ)",
                                              sigma_a_MPa=0.5 * (sc + stn), fatigue_limit_MPa=mt["fatigue"], factor=mt["fatigue"] / (0.5 * (sc + stn)))
    rec["boundary_conditions"] = "big-end bore half fixed (loaded half); cosine bearing pressure on the loaded half of the small-end bore; no bolt preload, no contact"
    save("rod", rec)


PISTON_H = dict(gas=0.9e-3, gallery=2.5e-3, undercrown=0.5e-3)       # W/mm2K, EST film coefficients (sensitivity: see piston_sensitivity)
# D-043 load-model guards of the piston case (see piston_checks).  Limits as fractions: gas force and gas-side heat against
# their targets, side force and point-support reaction against the gas force, loaded areas against PISTON_AREA_REF.
PISTON_LIMITS = dict(force=0.03, side=0.01, heat=0.03, area=0.05)
# Loaded areas measured on the D-040 piston (tag pre-D041: 1.6 mm valve pockets, crown tilt 15.76 deg; same mesh settings;
# the old and the new selection rule give the same facets there).  D-042 (2.2 mm pockets): crown +0.1 %, chamber +1.7 %
# (deeper pocket walls).  An area change beyond PISTON_LIMITS["area"] fails the case: if a geometry change explains it,
# re-measure both areas and record the decision and the reason here.
PISTON_AREA_REF = dict(basis="D-040 piston (tag pre-D041, 81,998 tets)", crown_mm2=5912.6, chamber_mm2=10829.1)


class FECheckError(RuntimeError):
    """A load-model check failed: the case is not reported (the runner writes <case>_FAILED.json)."""


def piston_checks(m, pinfo, crown, chamber, p_d, q_p, q_cal):
    """D-043 guards on the piston load model, evaluated on the facet selections before any solve (seconds; the solve
    takes ~45 min).  crown: gas-side thermal set; chamber: pressure set (crown, valve pockets, top land); q_cal: gas-side
    flux at the cycle-model wall temperature (W/mm2), so that q_cal * crown area is the heat the boundary condition applies.
    The case fails (FECheckError) if
      - the gas force differs from the design pressure on the bore area by more than PISTON_LIMITS["force"] (the annulus
        that the top-land relief opens is not loaded: -2.0 % by design, D-040), or the side force exceeds
        PISTON_LIMITS["side"] of it;
      - the applied gas-side heat differs from the cycle-model piston heat by more than PISTON_LIMITS["heat"] (-2.0 %, same
        annulus).  The solved heat is lower again (D-040: -10 %) because the crown runs hotter than the cycle model's
        560 K wall - a result, not an input, so it is not checked;
      - a loaded area differs from PISTON_AREA_REF by more than PISTON_LIMITS["area"];
      - a selected facet lies at or below the top of the top-ring groove (ring-groove flank or second land)."""
    lim, ref = PISTON_LIMITS, PISTON_AREA_REF
    e = ElementTetP1()
    fb_ch, fb_cr = FacetBasis(m, e, facets=chamber), FacetBasis(m, e, facets=crown)
    F = np.array([-p_d * float((fb_ch.normals[i] * fb_ch.dx).sum()) for i in range(3)])      # pressure against the outward normal
    a_ch, a_cr = float(fb_ch.dx.sum()), float(fb_cr.dx.sum())
    F_exp = p_d * math.pi * (P.bore / 2) ** 2
    z_groove = pinfo["g1"] + P.ring1_h                                                      # top of the top-ring groove
    z_mid = lambda fc: m.p[2, m.facets[:, fc]].mean(axis=0)
    chk = dict(gas_force_N=F.tolist(), gas_force_expected_N=F_exp, gas_force_dev=float(-F[2] / F_exp - 1.0),
               side_force_frac=float(math.hypot(F[0], F[1]) / F_exp),
               heat_applied_W=q_cal * a_cr, heat_target_W=q_p, heat_dev=float(q_cal * a_cr / q_p - 1.0),
               crown_area_mm2=a_cr, chamber_area_mm2=a_ch, area_ref=ref,
               crown_area_dev=a_cr / ref["crown_mm2"] - 1.0, chamber_area_dev=a_ch / ref["chamber_mm2"] - 1.0,
               min_facet_height_above_top_groove_mm=float(min(z_mid(chamber).min(), z_mid(crown).min()) - z_groove), limits=lim)
    bad = []
    if abs(chk["gas_force_dev"]) > lim["force"]:
        bad.append(f"gas force {-F[2]:.0f} N vs {F_exp:.0f} N ({chk['gas_force_dev']:+.1%})")
    if chk["side_force_frac"] > lim["side"]:
        bad.append(f"side force ({F[0]:.0f}, {F[1]:.0f}) N ({chk['side_force_frac']:.1%} of the gas force)")
    if abs(chk["heat_dev"]) > lim["heat"]:
        bad.append(f"gas-side heat {q_cal * a_cr:.0f} W vs {q_p:.0f} W ({chk['heat_dev']:+.1%})")
    for k in ("crown", "chamber"):
        if abs(chk[k + "_area_dev"]) > lim["area"]:
            bad.append(f"{k} area {chk[k + '_area_mm2']:.0f} mm2 vs {ref[k + '_mm2']:.0f} ({chk[k + '_area_dev']:+.1%}; geometry change? see PISTON_AREA_REF)")
    if chk["min_facet_height_above_top_groove_mm"] < 0.01:
        bad.append(f"facet at or below the top-ring groove top ({chk['min_facet_height_above_top_groove_mm']:+.3f} mm)")
    if bad:
        raise FECheckError("piston load checks failed: " + "; ".join(bad))
    return chk


def piston_solve_checks(s, F_exp, what):
    """D-043: a solved piston case must carry the gas load and nothing else - the assembled force within
    PISTON_LIMITS["force"] of F_exp, side force and point-support reaction within PISTON_LIMITS["side"] of it."""
    lim = PISTON_LIMITS
    F, Rp = s["applied"], s["point_reaction"]
    chk = dict(gas_force_dev=float(-F[2] / F_exp - 1.0), side_force_frac=float(math.hypot(F[0], F[1]) / F_exp),
               support_reaction_frac=float(np.linalg.norm(Rp) / F_exp))
    bad = []
    if abs(chk["gas_force_dev"]) > lim["force"]:
        bad.append(f"gas force {-F[2]:.0f} N vs {F_exp:.0f} N")
    if chk["side_force_frac"] > lim["side"]:
        bad.append(f"side force ({F[0]:.0f}, {F[1]:.0f}) N")
    if chk["support_reaction_frac"] > lim["side"]:
        bad.append(f"point-support reaction ({Rp[0]:.0f}, {Rp[1]:.0f}, {Rp[2]:.0f}) N")
    if bad:
        raise FECheckError(f"piston {what}: solved load checks failed: " + "; ".join(bad))
    return chk


def case_piston(thermal_only=False):
    """thermal_only: mesh + steady thermal only (design iteration); returns the record without saving."""
    R = results()
    pis, _, _, _, _, pinfo = CT.piston_solids()
    mt = mat("al_forged")
    m, st = mesh_shape(pis, 4.0, "piston", refine=[((0, 0, 0), 26, 2.6), ((0, 0, 26.0), 42, 2.4)])
    ch = P.comp_height
    ta = math.tan(math.radians(P.crown_tilt_axis))
    r = P.bore / 2
    nrm = np.array([0.0, -math.sin(math.radians(P.crown_tilt_axis)), math.cos(math.radians(P.crown_tilt_axis))])
    cos_t = math.cos(math.radians(P.crown_tilt_axis))
    depth = lambda x: (ch + x[1] * ta - x[2]) * cos_t                # depth below the crown plane, normal to it
    # D-043: the chamber-side band reaches 0.5 mm below the valve-pocket floors.  It was a fixed 2.2 mm (measured vertically
    # for the crown set) - right for the 1.6 mm pockets; with the 2.2 mm pockets of D-042 the floors fell outside and carried
    # neither gas pressure nor gas-side heat (run of 2026-11-17 23:21: 58.4 kN + 5.3 kN sideways instead of 76.8 kN, 3.7
    # instead of 5.4 kW).  The top-ring groove is 5 mm (vertical) below the low edge of the crown, far below the band.
    band = P.piston_valve_pocket_depth + 0.5
    # crown = facets on the crown plane and the valve-pocket floors facing along the crown normal - the side wall is excluded
    crown = facets_by_normal(m, facets(m, lambda x: (np.abs(depth(x)) < band) & (np.hypot(x[0], x[1]) < r - 0.2)), nrm, 0.9)
    pinb = facets(m, lambda x: (np.hypot(x[1], x[2]) < P.pin_dia_piston / 2 + 0.06) & (np.abs(x[0]) > 10))
    pin_up = facets(m, lambda x: (np.hypot(x[1], x[2]) < P.pin_dia_piston / 2 + 0.06) & (np.abs(x[0]) > 10) & (x[2] > 0))
    dg0, dg1 = pinfo["gallery_depth"]                                # gallery depth below the crown plane, normal to it
    gal = facets(m, lambda x: (np.hypot(x[0], x[1]) > P.gallery_r_in - 0.2) & (np.hypot(x[0], x[1]) < P.gallery_r_out + 0.2)
                 & (depth(x) > dg0 - 0.2) & (depth(x) < dg1 + 0.2))
    under = facets(m, lambda x: (x[2] < ch + x[1] * ta - 5.0) & (np.hypot(x[0], x[1]) < r - 4.0) & (np.hypot(x[1], x[2]) > P.pin_dia_piston / 2 + 0.5))
    under = np.setdiff1d(under, gal)
    side = facets(m, lambda x: (np.hypot(x[0], x[1]) > r - 0.6))
    p_d = P.p_max_design_bar * 0.1                                   # MPa
    rec = dict(case="piston", material=mt, mesh=st, results={}, inputs=dict(p_design_MPa=p_d),
               facet_counts=dict(crown=int(len(crown)), gallery=int(len(gal)), under_crown=int(len(under)), pin_upper=int(len(pin_up))),
               design=dict(gallery_area_mm2=pinfo["gallery_area"], gallery_z=pinfo["gallery_z"], crown_thk=P.piston_crown_thk,
                           ring_belt_inner_r=P.piston_uc_r, mass_kg=pis.volume * 1e-9 * MATERIALS[MAT["al_forged"]]["rho"]))
    # Support model (D-037), used by the gas and the gas + thermal case.  Holding the pin bores (whole bores: 1,550 MPa;
    # upper halves: 1,190 MPa; a +/-45 deg contact band: 1,191 MPa, D-035/D-036) always restrained the thermal growth of the
    # bosses and produced the peak.  Now: the gas pressure acts on every chamber-side surface above the top ring (crown,
    # valve pockets, top land - this also cancels the sideways load that the slanted crown alone would carry); the pin
    # reaction is a cosine bearing pressure on the upper half of both bores, scaled so that it balances the gas load
    # exactly; a statically determinate 3-2-1 point support (both bore bottoms, skirt bottom) removes only the rigid-body
    # modes, so it carries no load (its reaction is reported as a check) and does not restrain the thermal growth.
    r_tl = r - P.piston_clear_dia / 2 - P.piston_top_land_relief     # turned-down top land (D-040)
    land = facets_radial(m, facets(m, lambda x: (np.hypot(x[0], x[1]) > r_tl - 0.2) & (x[2] > pinfo["g1"] + P.ring1_h + 0.05)), axis=2)
    chamber = np.union1d(facets(m, lambda x: (depth(x) < band) & (np.hypot(x[0], x[1]) < r - 0.2)), land)
    # the pin bears on the bores from the boss inner faces to its ends (|x| <= pin_length / 2, inside the circlip grooves);
    # the bore cut continues through the pin ends (assembly passage) but carries no pin there
    pin_brg = facets_radial(m, facets(m, lambda x: (np.hypot(x[1], x[2]) < P.pin_dia_piston / 2 + 0.06) & (np.abs(x[0]) > 10)
                                      & (np.abs(x[0]) < P.pin_length / 2) & (x[2] > 0)), axis=0)
    fn_pin, p0_unit = cos_load((0, 0, 0), (1, 0, 0), (0, 0, 1), 1.0, m, pin_brg)
    near = lambda pt: int(np.argmin(((m.p - np.reshape(pt, (3, 1))) ** 2).sum(0)))
    R_pb = P.pin_dia_piston / 2
    pts = [(near((22.0, 0.0, -R_pb)), (1, 2)), (near((-22.0, 0.0, -R_pb)), (1, 2)), (near((0.0, r - P.piston_skirt_wall / 2, pinfo["z_bot"])), (0, 2))]
    sup = dict(pressures=[(chamber, p_d)], balance=(pin_brg, fn_pin, 2), points=pts, factor_cache={})
    n_brg, n_crown = np.unique(m.facets[:, pin_brg]), np.unique(m.facets[:, crown])
    rec["facet_counts"].update(chamber=int(len(chamber)), top_land=int(len(land)), pin_bearing=int(len(pin_brg)))
    # gas-side thermal data (cycle-mean), needed by the checks below and by the thermal case
    q_p = R["energy"]["wall_parts"][1] * 1e3 / 16                                   # W per piston (cycle model)
    a_cr = math.pi * r * r / math.cos(math.radians(P.crown_tilt_axis))
    h_g = PISTON_H["gas"]                                                            # W/mm2K (EST cycle-mean gas-side coefficient)
    T_w = CY.A["T_wall_piston"]                                                      # K, gas-side piston wall temperature of the cycle model
    T_g = T_w + q_p / a_cr / h_g                                                     # effective gas temperature: the cycle-model heat at that wall temperature
    F_exp = p_d * math.pi * r * r
    rec["checks"] = piston_checks(m, pinfo, crown, chamber, p_d, q_p, h_g * (T_g - T_w))      # D-043: before any solve
    print("piston checks", json.dumps(rec["checks"], default=str), flush=True)
    if not thermal_only:
        s = solve_elastic(m, mt, None, **sup)
        rec["checks"]["solved_gas"] = piston_solve_checks(s, F_exp, "gas")
        pk, p999, loc = peak(m, s["vm"])
        uz_ref = s["U"][2][n_brg].mean()                                 # crown deflection relative to the pin-bore tops
        rec["results"]["gas_pressure"] = dict(applied_force_N=s["applied"].tolist(), expected_force_N=F_exp,
                                              pin_reaction_N=s["balance_force"].tolist(), support_reaction_N=s["point_reaction"].tolist(),
                                              peak_bearing_pressure_MPa=p0_unit * s["balance_scale"], vm_max_MPa=pk, vm_p999_MPa=p999,
                                              vm_max_location=loc, crown_deflection_mm=float(np.abs(s["U"][2][n_crown] - uz_ref).max()),
                                              dofs=s["dofs"], solve_s=s["t_solve"])
        picture(m, cell=s["vm"], title="von Mises (gas load)", units="[MPa]", path=os.path.join(OUT, "piston_gas_vm.png"), view=(1, -1, -0.5), clim=(0, p999))
        progress("piston", rec, "gas_pressure")
    # steady thermal: crown gas side (cycle-mean), under-crown oil jet, ring belt / skirt to the liner, pin bore
    h_gal, h_uc = PISTON_H["gallery"], PISTON_H["undercrown"]                        # W/mm2K: shaker-cooled gallery / splash under the crown (EST)
    T, flows = solve_thermal(m, mt["k"], robin=[(crown, h_g, T_g), (gal, h_gal, 400.0), (under, h_uc, 400.0), (side, 1.1e-3, 430.0), (pinb, 0.5e-3, 420.0)])
    rec["inputs"].update(q_piston_W=q_p, h_gas=h_g * 1e6, T_gas_eff_K=T_g, h_gallery=h_gal * 1e6, h_undercrown=h_uc * 1e6, T_oil_K=400.0,
                         h_ring_skirt=1100.0, T_liner_K=430.0)
    zc = m.p[2] - (ch + m.p[1] * ta)
    top = zc > -1.0
    g1 = (np.abs(m.p[2] - pinfo["g1"]) < 1.5) & (np.hypot(m.p[0], m.p[1]) > r - 4)
    rec["results"]["thermal"] = dict(T_max_C=float(T.max() - 273.15), T_crown_mean_C=float(T[top].mean() - 273.15), T_top_ring_groove_C=float(T[g1].mean() - 273.15),
                                     T_min_C=float(T.min() - 273.15), heat_in_crown_W=flows[0], heat_to_gallery_W=-flows[1], heat_to_undercrown_W=-flows[2],
                                     heat_to_liner_W=-flows[3], heat_to_pin_W=-flows[4],
                                     energy_balance_error_pct=100.0 * sum(flows) / flows[0])
    i_max = int(np.argmax(T))
    rec["results"]["thermal"]["T_max_location"] = m.p[:, i_max].tolist()
    # sensitivity to the two EST oil-side film coefficients (they decide the crown temperature; not calibrated by test)
    sens = []
    for label, hg, hu in (("gallery 1,500 W/m2K", 1.5e-3, h_uc), ("gallery 4,000 W/m2K", 4.0e-3, h_uc),
                          ("under-crown 1,000 W/m2K", h_gal, 1.0e-3), ("gallery 4,000 + under-crown 1,000 W/m2K", 4.0e-3, 1.0e-3)):
        Ts, _ = solve_thermal(m, mt["k"], robin=[(crown, h_g, T_g), (gal, hg, 400.0), (under, hu, 400.0), (side, 1.1e-3, 430.0), (pinb, 0.5e-3, 420.0)])
        sens.append(dict(case=label, T_max_C=float(Ts.max() - 273.15), T_crown_mean_C=float(Ts[top].mean() - 273.15),
                         T_top_ring_groove_C=float(Ts[g1].mean() - 273.15)))
    rec["results"]["thermal_sensitivity"] = sens
    if thermal_only:
        rec["_mesh"], rec["_T"] = m, T
        return rec
    picture(m, point=T - 273.15, title="temperature", units="[degC]", path=os.path.join(OUT, "piston_temperature.png"), view=(1, -1, -0.5))
    T_at = lambda loc: float(T[near(loc)] - 273.15)                    # metal temperature at a stress peak (hot strength)
    rec["results"]["gas_pressure"]["T_at_vm_max_C"] = T_at(rec["results"]["gas_pressure"]["vm_max_location"])
    progress("piston", rec, "thermal", "thermal_sensitivity")
    # gas + thermal: same support model as the gas case (see above)
    s2 = solve_elastic(m, mt, None, thermal=T - 293.15, **sup)
    sup["factor_cache"].clear()                                          # release the factorisation
    rec["checks"]["solved_gas_thermal"] = piston_solve_checks(s2, F_exp, "gas + thermal")
    pk, p999, loc = peak(m, s2["vm"])
    rec["results"]["gas_plus_thermal"] = dict(vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc, T_at_vm_max_C=T_at(loc),
                                              support_reaction_N=s2["point_reaction"].tolist(),
                                              max_displacement_mm=float(np.sqrt((s2["U"] ** 2).sum(0)).max()))
    picture(m, cell=s2["vm"], title="von Mises (gas + thermal)", units="[MPa]", path=os.path.join(OUT, "piston_gas_thermal_vm.png"), view=(1, -1, -0.5), clim=(0, p999))
    rad = np.hypot(m.p[0], m.p[1])
    ur_all = (s2["U"][0] * m.p[0] + s2["U"][1] * m.p[1]) / np.maximum(rad, 1e-9)
    sk = rad > r - 0.3                                                   # skirt and second land
    tl = (np.abs(rad - r_tl) < 0.05) & (m.p[2] > pinfo["g1"] + P.ring1_h + 0.05)    # top land (D-040)
    rec["results"]["gas_plus_thermal"]["radial_growth_max_mm"] = float(ur_all[sk].max())
    rec["results"]["gas_plus_thermal"]["top_land_radial_growth_max_mm"] = float(ur_all[tl].max()) if tl.any() else None
    rec["results"]["gas_plus_thermal"]["top_land_cold_clearance_mm"] = P.piston_clear_dia / 2 + P.piston_top_land_relief
    sa = 0.5 * rec["results"]["gas_pressure"]["vm_p999_MPa"]
    rec["results"]["fatigue_estimate"] = dict(note="gas load from zero to the design pressure every cycle: alternating stress = half the 99.9th-percentile "
                                                   "gas-case stress, against the room-temperature fatigue limit (no mean-stress or temperature correction - "
                                                   "the hot strength at the boss and ring belt is lower)",
                                              sigma_a_MPa=sa, fatigue_limit_MPa=mt["fatigue"], factor=mt["fatigue"] / sa)
    rec["boundary_conditions"] = ("gas and gas + thermal: design gas pressure on all chamber-side surfaces above the top ring (crown, valve pockets, "
                                  "top land; ring-groove and second-land pressures neglected); pin reaction as a cosine bearing pressure on the upper "
                                  "half of both pin bores, scaled to balance the gas load; statically determinate 3-2-1 point support (bore bottoms, "
                                  "skirt bottom) - no restraint of the thermal growth. "
                                  f"Thermal: cycle-mean gas side, oil gallery {PISTON_H['gallery'] * 1e6:,.0f} W/m2K and under-crown splash {PISTON_H['undercrown'] * 1e6:,.0f} W/m2K at 127 degC, "
                                  "ring belt and skirt to the liner. No skirt contact, no pin deformation")
    save("piston", rec)


CRANK_FILLET_MESH = 1.0          # mm, element size along both pin-fillet circles (D-047 standard; was 2.4 mm in a 34 mm ball)


def case_crank():
    """Crank throw 3 in bending.  D-047 (2026-11-21): undercut pin fillets (cranktrain default), 1.0 mm elements along both
    fillet circles (40 refinement balls each), CG solver (the direct factorisation of ~1 M dof is too large), and the
    fatigue factor on the fillet-zone peak instead of the whole-part 99.9th percentile."""
    R = results()["dynamics"]
    from ..cad.assembly import _cw
    cw, _ = _cw()
    k = 3
    thr = CT.throw_solid(k, (cw[k][0], cw[k][1]))
    hm = P.main_width / 2
    for j in (k, k + 1):
        thr = thr + Pos(L.main_x(j) - hm, 0, 0) * Rot(Y=90) * Cylinder(P.main_dia / 2, P.main_width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    mt = mat("steel_qt")
    psi = math.radians(L.PIN_PHASE[k])
    pc = np.array([L.pin_x(k), P.throw * math.sin(psi), P.throw * math.cos(psi)])
    xa, xb = pc[0] - P.pin_width / 2, pc[0] + P.pin_width / 2
    ref = [((xa, pc[1], pc[2]), 34, 2.4), ((xb, pc[1], pc[2]), 34, 2.4)]
    rf0 = P.pin_dia / 2 + 1.25                                        # centre radius of the fillet zone
    e1, up = np.array([0.0, math.cos(psi), -math.sin(psi)]), np.array([0.0, math.sin(psi), math.cos(psi)])
    for xf in (xa, xb):
        for a in np.linspace(0, 2 * math.pi, 40, endpoint=False):
            ref.append((tuple(np.array([xf, pc[1], pc[2]]) + rf0 * (math.cos(a) * e1 + math.sin(a) * up)), 4.5, CRANK_FILLET_MESH))
    m, st = mesh_shape(thr, 5.0, "crank", refine=ref)
    mains = facets(m, lambda x: (np.hypot(x[1], x[2]) < P.main_dia / 2 + 0.05) & ((x[0] < L.main_x(k) + hm + 0.01) | (x[0] > L.main_x(k + 1) - hm - 0.01)))
    pin = facets(m, lambda x: (np.hypot(x[1] - pc[1], x[2] - pc[2]) < P.pin_dia / 2 + 0.05) & (np.abs(x[0] - pc[0]) < P.pin_width / 2 - 2.6))
    F = 2 * 0.0 + R["F_design_gas"]                                   # one rod at design peak pressure; partner cylinder near BDC
    e_pin = np.array([0, math.sin(psi), math.cos(psi)])
    fn, p0 = cos_load(pc, (1, 0, 0), -e_pin, F, m, pin)
    s = solve_elastic(m, mt, mains, tractions=[(pin, fn)], iterative=True)
    pk, p999, loc = peak(m, s["vm"])
    vm = np.asarray(s["vm"])
    cen = m.p[:, m.t].mean(axis=1)
    rp = np.hypot(cen[1] - pc[1], cen[2] - pc[2])
    fz = (np.hypot(cen[0] - xa, rp - rf0) < 5.0) | (np.hypot(cen[0] - xb, rp - rf0) < 5.0)
    web = (((cen[0] < xa) & (cen[0] > xa - P.web_thk)) | ((cen[0] > xb) & (cen[0] < xb + P.web_thk))) & ~fz & (np.hypot(cen[1], cen[2]) > P.main_dia / 2 + 6.0)
    zone = lambda msk: dict(vm_max_MPa=float(vm[msk].max()), vm_p999_MPa=float(np.percentile(vm[msk], 99.9)),
                            at=cen[:, int(np.argmax(np.where(msk, vm, -1)))].round(2).tolist())
    fil, wb = zone(fz), zone(web)
    rec = dict(case="crank throw 3 in bending", material=mt, mesh=st, inputs=dict(force_N=F, direction="towards the crank axis (firing TDC)",
                                                                                 pin_fillet="undercut R2.5 (D-047)", fillet_mesh_mm=CRANK_FILLET_MESH),
               results=dict(applied_force_check_N=s["applied"].tolist(), vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc,
                            fillet_vm_max_MPa=fil["vm_max_MPa"], fillet_vm_p999_MPa=fil["vm_p999_MPa"], fillet_vm_max_location=fil["at"],
                            web_vm_max_MPa=wb["vm_max_MPa"], pin_deflection_mm=float(np.sqrt((s["U"] ** 2).sum(0)).max()),
                            dofs=s["dofs"], solve_s=s["t_solve"], fatigue_limit_MPa=mt["fatigue"],
                            factor_on_fillet_max=mt["fatigue"] / (0.5 * fil["vm_max_MPa"])),
               boundary_conditions="both main-journal surfaces fully fixed (stiffer than real bearings -> fillet stress over-predicted); load on the central part of the pin; "
                                   "pulsating load, alternating stress = half the peak; the main-journal / web corners are unfilleted in this slice, so the "
                                   "whole-part peak can sit there - the fatigue factor uses the pin-fillet zone (within 5 mm of either fillet circle); "
                                   "bending only - combined bending + torsion at the fillet is an open item (D-047)")
    picture(m, cell=s["vm"], title="von Mises", units="[MPa]", path=os.path.join(OUT, "crank_throw_vm.png"), view=(0.3, -1, 0.3), clim=(0, p999))
    save("crank", rec)


def case_insert():
    R = results()["dynamics"]
    ins = B.bearing_insert()
    mt = mat("cast_steel")
    mt.update(E=170e3, nu=0.28, yield_=370.0, fatigue=190.0, name="EN-GJS-600 nodular iron")
    m, st = mesh_shape(ins, 3.5, "insert")
    r_mb = P.main_dia / 2 + P.main_shell_thk
    bore = facets(m, lambda x: np.hypot(x[1], x[2]) < r_mb + 0.05)
    bolts = facets(m, lambda x: (np.hypot(np.abs(x[1]) - 50.0, 0 * x[2]) < 6.4) & (x[2] < -1) & (x[2] > -57))
    F = R["main_peak"]
    fn, p0 = cos_load((0, 0, 0), (1, 0, 0), (0, 0, -1), F, m, bore)
    s = solve_elastic(m, mt, bolts, tractions=[(bore, fn)])
    pk, p999, loc = peak(m, s["vm"])
    rec = dict(case="main bearing cover (cast-in insert)", material=mt, mesh=st, inputs=dict(force_N=F, direction="-Z (into the cover)"),
               results=dict(applied_force_check_N=s["applied"].tolist(), peak_bearing_pressure_MPa=p0, vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc,
                            bore_deflection_mm=float(np.abs(s["U"][2]).max()), dofs=s["dofs"], solve_s=s["t_solve"], yield_factor_on_p999=mt["yield_"] / p999),
               boundary_conditions="bolt-hole surfaces fixed; support from the surrounding aluminium bedplate neglected (conservative)")
    picture(m, cell=s["vm"], title="von Mises", units="[MPa]", path=os.path.join(OUT, "bearing_cover_vm.png"), view=(1, -0.3, -0.6), clim=(0, p999))
    save("insert", rec)


def _cached(name):
    d = os.path.join(ROOT, ".cache")
    f = [x for x in os.listdir(d) if x.startswith(name + "_")]
    return import_brep(os.path.join(d, sorted(f)[-1]))


def case_block():
    """Slice of the cylinder block around cylinder 3 (bank 1, outer row): gas pressure + thermal field."""
    R = results()
    blk = _cached("block_upper")
    c = L.CYL[3]
    # The slice must contain the complete wall ring of the 86 mm bore (hoop tension carries the gas load), so it is
    # 100 mm wide although the cylinder pitch is 73 mm; it therefore also contains parts of the neighbouring inner-row bores.
    HW = 50.0
    sl = blk & Pos(c.x, 250, 150) * Box(2 * HW, 500, 300)
    sl = max(sl.solids(), key=lambda s: s.volume)
    mt = mat("al_cast")
    m, st = mesh_shape(sl, 5.0, "block", h_min=1.6)
    q = np.array(c.q3); d = c.d3
    def rad(x):
        r = x - q.reshape(3, 1) if x.ndim == 2 else x - q.reshape(3, 1, 1)
        s = (r * (d.reshape(3, 1) if x.ndim == 2 else d.reshape(3, 1, 1))).sum(0)
        rr = r - (d.reshape(3, 1) if x.ndim == 2 else d.reshape(3, 1, 1)) * s
        return np.sqrt((rr * rr).sum(0)), s
    bore_top = facets(m, lambda x: (rad(x)[0] < P.bore / 2 + 0.08) & (rad(x)[1] > P.s_deck - 50.0))
    bore_all = facets(m, lambda x: (rad(x)[0] < P.bore / 2 + 0.08) & (rad(x)[1] > P.s_bore_foot))
    base = facets(m, lambda x: x[2] < 0.05)
    ev = L.bank_axes(1)[2]
    jacket = facets(m, lambda x: (rad(x)[0] > P.bore / 2 + P.liner_wall - 0.3) & (rad(x)[0] < P.bore / 2 + P.liner_wall + P.jacket_width + 0.6) &
                    ((x * ev.reshape(3, 1)).sum(0) < P.deck_height - P.deck_thk + 0.2) & ((x * ev.reshape(3, 1)).sum(0) > P.deck_height - P.deck_thk - P.jacket_depth - 0.2))
    p_d = P.p_max_design_bar * 0.1

    def press(x):
        r = x - q.reshape(3, 1, 1)
        s = (r * d.reshape(3, 1, 1)).sum(0)
        rr = r - d.reshape(3, 1, 1) * s
        return p_d * rr / np.maximum(np.sqrt((rr * rr).sum(0)), 1e-9)
    sym = facets(m, lambda x: (np.abs(x[0] - (c.x - HW)) < 0.05) | (np.abs(x[0] - (c.x + HW)) < 0.05))
    order = 2 if st["tets"] < 45000 else 1
    s = solve_elastic(m, mt, base, tractions=[(bore_top, press)], order=order, fixed_dirs=[(sym, 0)])
    pk, p999, loc = peak(m, s["vm"])
    umax = float(np.sqrt((s["U"] ** 2).sum(0)).max())
    rec = dict(case="cylinder block slice, cylinder 3", material=mt, mesh=st, element=f"P{order} tetrahedra", inputs=dict(p_design_MPa=p_d),
               facet_counts=dict(base=int(len(base)), symmetry=int(len(sym)), bore_loaded=int(len(bore_top)), jacket=int(len(jacket))),
               results=dict(gas_pressure=dict(vm_max_MPa=pk, vm_p999_MPa=p999, vm_max_location=loc, dofs=s["dofs"], solve_s=s["t_solve"],
                                              applied_force_check_N=s["applied"].tolist(), max_displacement_mm=umax,
                                              plausible=bool(umax < 1.0))),
               boundary_conditions="100 mm slice centred on cylinder 3 (contains its complete bore wall ring); crank-axis split plane fixed; the two "
                                   "cut faces (x = cyl. 3 +/- 50 mm) are symmetry planes (axial displacement fixed); design pressure on the upper 50 mm "
                                   "of the bore of cylinder 3 only; no head clamp load, no bolt preload. A first 73 mm slice (narrower than the bore) "
                                   "had no complete hoop ring and gave a meaningless 95 mm deflection - rejected")
    picture(m, cell=s["vm"], title="von Mises (gas)", units="[MPa]", path=os.path.join(OUT, "block_slice_vm.png"), view=(-1, 0.4, 0.5), clim=(0, p999))
    # thermal: liner heat flux (cycle model) on the bore, jacket convection
    q_top = R["wall"]["q_liner_top_wm2"] * 1e-6                       # W/mm2
    fl_top = facets(m, lambda x: (rad(x)[0] < P.bore / 2 + 0.08) & (rad(x)[1] > P.s_deck - 30.0))
    fl_low = facets(m, lambda x: (rad(x)[0] < P.bore / 2 + 0.08) & (rad(x)[1] <= P.s_deck - 30.0) & (rad(x)[1] > P.s_bore_foot))
    T, flows = solve_thermal(m, mt["k"], robin=[(jacket, R["coolant"]["h_jacket"] * 1e-6, 368.0), (base, 0.2e-3, 400.0)], flux=[(fl_top, q_top), (fl_low, 0.12 * q_top)])
    on_bore = np.zeros(m.p.shape[1], bool)
    r_n, s_n = rad(m.p)
    on_bore = (r_n < P.bore / 2 + 0.1) & (s_n > P.s_bore_foot)
    rec["results"]["thermal"] = dict(T_bore_max_C=float(T[on_bore].max() - 273.15), T_bore_mean_C=float(T[on_bore].mean() - 273.15), T_max_C=float(T.max() - 273.15),
                                     heat_to_jacket_W=-flows[0], jacket_facets=int(len(jacket)), q_top_W_mm2=q_top)
    picture(m, point=T - 273.15, title="temperature", units="[degC]", path=os.path.join(OUT, "block_slice_temperature.png"), view=(-1, 0.4, 0.5))
    s2 = solve_elastic(m, mt, base, thermal=T - 293.15, order=order, fixed_dirs=[(sym, 0)])
    r_vec = m.p[:, on_bore] - q.reshape(3, 1)
    r_vec = r_vec - d.reshape(3, 1) * (r_vec * d.reshape(3, 1)).sum(0)
    r_hat = r_vec / np.sqrt((r_vec * r_vec).sum(0))
    ur = (s2["U"][:, on_bore] * r_hat).sum(0)
    rec["results"]["thermal_expansion"] = dict(bore_radial_growth_mean_um=float(ur.mean() * 1e3), bore_out_of_round_um=float((ur.max() - ur.min()) * 1e3),
                                               note="thermal growth with the same supports as the gas case (split plane fixed, cut faces symmetric); "
                                                    "includes bending of the bank, so out-of-round is an upper bound")
    save("block", rec)


def case_head():
    """Slice of the cylinder head over cylinder position 3: steady temperature field (chamber roof, exhaust ports, jacket)."""
    R = results()
    core = _cached("head_core")
    x3 = B.loc_x(3)
    sl = core & Pos(x3, 0, 31.0) * Box(73.0, 400, 62.0)
    sl = max(sl.solids(), key=lambda s: s.volume)
    mt = mat("al_cast")
    m, st = mesh_shape(sl, 4.5, "head", h_min=1.4)
    pt, n = H.roof(3)
    uc = B.rho(3) * P.u_bore_head                                     # bore centre on the joint face (D-039)
    roof = facets(m, lambda x: (np.abs((x - pt.reshape(3, 1)).T @ n) < 0.8) & (np.hypot(x[0] - x3, x[1] - uc) < P.bore / 2 + 2))
    wj = facets(m, lambda x: (x[2] > H.W_JKT[0] - 0.3) & (x[2] < H.W_JKT[1] + 0.3) & (np.abs(x[0] - x3) < 36.0) & (np.abs(x[1]) < B.W_TOP - 9.5))
    q_roof = R["wall"]["q_deck_wm2"] * 1e-6
    hx = R["wall"]["h_head"] * 1e-6
    # The valve heads cover about 60 % of the chamber roof but are separate parts; their share of the chamber heat reaches the
    # head through the valve seats.  It is applied as a uniform flux on the seat-insert pockets so that the total heat entering
    # the head equals the cycle-model chamber heat.
    def farea(fc):
        a, b, c = (m.p[:, m.facets[k, fc]] for k in range(3))
        return float(0.5 * np.linalg.norm(np.cross(b - a, c - a, axis=0), axis=0).sum())
    seat_masks = []
    for kind in ("in", "ex"):
        rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
        for s in (-1, 1):
            Hh, _, a = H.valve_geo(3, kind, s)

            def cond(x, Hh=Hh, a=a, rv=rv):
                r = x - Hh.reshape(3, 1)
                ax = (r * a.reshape(3, 1)).sum(0)
                rad = np.sqrt(np.maximum((r * r).sum(0) - ax ** 2, 0))
                return (ax > -1.6) & (ax < 6.2) & (rad > rv - 4.0) & (rad < rv + 1.9)
            seat_masks.append(facets(m, cond))
    seat = np.unique(np.concatenate(seat_masks))
    seat = np.setdiff1d(seat, roof)
    q_total = float(q_roof * math.pi * (P.bore / 2) ** 2 / n[2])        # chamber heat of one cylinder (cycle model)
    a_roof, a_seat = farea(roof), farea(seat)
    q_seat = max(q_total - q_roof * a_roof, 0.0) / a_seat if a_seat > 0 else 0.0
    T, flows = solve_thermal(m, mt["k"], robin=[(wj, hx, 368.0)], flux=[(roof, q_roof), (seat, q_seat)])
    near = np.abs((m.p - pt.reshape(3, 1)).T @ n) < 1.0
    applied = q_roof * a_roof + q_seat * a_seat
    i_max = int(np.argmax(T))
    # bridge between adjacent seat pockets: nodes within 4 mm of two different pockets
    def near_pocket(k):
        kind, s = (("in", -1), ("in", 1), ("ex", -1), ("ex", 1))[k]
        Hh, _, a = H.valve_geo(3, kind, s)
        rv = (P.valve_in_dia if kind == "in" else P.valve_ex_dia) / 2
        r = m.p - Hh.reshape(3, 1)
        ax = (r * a.reshape(3, 1)).sum(0)
        rad = np.sqrt(np.maximum((r * r).sum(0) - ax ** 2, 0))
        return (ax > -2) & (ax < 8) & (rad < rv + 6.0)
    cnt = sum(near_pocket(k).astype(int) for k in range(4))
    bridge = cnt >= 2
    gas_side = near | bridge | (cnt >= 1)
    rec_extra = dict(T_max_location=m.p[:, i_max].round(1).tolist(), T_gas_side_p99_C=float(np.quantile(T[gas_side], 0.99) - 273.15),
                     T_valve_bridge_max_C=float(T[bridge].max() - 273.15) if bridge.any() else None,
                     T_valve_bridge_mean_C=float(T[bridge].mean() - 273.15) if bridge.any() else None,
                     note="The slice faces (x = position 3 +/- 36.5 mm) cut through the outer intake-valve seat pockets, leaving thin "
                          "adiabatic slivers; T_max and the gas-side 99th percentile are dominated by these slivers and are slice artefacts. "
                          "Representative results: valve-bridge maximum and mean, roof mean.")
    rec = dict(case="cylinder head slice, cylinder position 3 (thermal)", material=mt, mesh=st, element="P1 tetrahedra",
               inputs=dict(q_roof_W_mm2=q_roof, q_seat_W_mm2=q_seat, roof_area_mm2=a_roof, seat_area_mm2=a_seat,
                           h_jacket_W_m2K=R["wall"]["h_head"], T_coolant_K=368.0),
               results=dict(T_max_C=float(T.max() - 273.15), T_roof_max_C=float(T[near].max() - 273.15) if near.any() else None,
                            T_roof_mean_C=float(T[near].mean() - 273.15) if near.any() else None, heat_to_coolant_W=-flows[0],
                            heat_target_W=q_total, heat_applied_W=applied, energy_balance_error_pct=100.0 * (applied + flows[0]) / applied,
                            roof_facets=int(len(roof)), seat_facets=int(len(seat)), jacket_facets=int(len(wj)), **rec_extra),
               boundary_conditions="cycle-mean chamber heat of one cylinder: roof area at the 1-D roof flux, the valve-head share through the "
                                   "seat-insert pockets; convection on all water-jacket walls inside the slice; port gas-side heat input "
                                   "(exhaust ports) not applied; cut faces adiabatic")
    picture(m, point=T - 273.15, title="temperature", units="[degC]", path=os.path.join(OUT, "head_slice_temperature.png"), view=(-0.4, -0.5, -1))
    save("head", rec)


CASES = dict(rod=case_rod, piston=case_piston, crank=case_crank, insert=case_insert, block=case_block, head=case_head)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name in (sys.argv[1:] or list(CASES)):
        t = time.time()
        try:
            CASES[name]()
            print(name, "finished in", round(time.time() - t, 1), "s")
            stale = os.path.join(OUT, name + "_FAILED.json")
            if os.path.exists(stale):
                os.remove(stale)                     # a successful run supersedes an earlier failure record
        except Exception as e:
            import traceback
            traceback.print_exc()
            with open(os.path.join(OUT, name + "_FAILED.json"), "w", encoding="utf-8") as fh:
                json.dump(dict(case=name, status="FAILED - not reported as a result", error=repr(e)[:400]), fh, indent=1)
