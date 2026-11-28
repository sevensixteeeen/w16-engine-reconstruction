"""Per-node reactions of the crank slice's 3-2-1 point support, from statics of the discrete load vector - no solve
(2026-11-27, D-050 regeneration check).

The support check in the FE record (point_reaction_N) adds each component over the three support nodes; a couple carried by
two nodes cancels in that sum.  The 3-2-1 support is statically determinate, so its six nodal reactions follow from the
resultant force and moment of the applied nodal loads alone: this tool re-meshes the slice exactly as fea.case_crank does
(checked against the record's mesh statistics), assembles the same pin load and balanced bearing-land load
(fea.crank_solve(assemble_only=True)) and solves the 6 x 6 statics.  It also lists the elements around support node A,
where the record's overall von Mises peak lies, the load on each bearing land (by dof index) and the bending moment at the
feature sections (loads + support reactions) against the intended simply supported bay (half the pin load at each main).

Finding 2026-11-27: lands 35 / 65 % instead of 50 / 50 - in fea.crank_solve.fn_land "r = x.copy(); r[0] = 0.0" does not zero
the axial coordinate of skfem's DiscreteField (skfem 12.0.2), so the "radial" direction includes x and each land's weight
scales with r / sqrt(x^2 + r^2); the supports carry the difference as a couple (about 9.4 kN at nodes A and B).

    set PYTHONPATH=src
    .venv\\Scripts\\python tools\\crank_support_reactions.py          -> 08_SIMULATIONS/fea/crank_support_check.json
    .venv\\Scripts\\python tools\\crank_support_reactions.py --selftest
"""
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank_support_check.json")


def statics_reactions(a, supports):
    """a: fea.solve_elastic(..., assemble_only=True); supports: [(position xyz, components)].  Reactions on the body that
    make sum(force) = 0 and sum(moment) = 0 with the applied nodal loads: list of (position, component, reaction N)."""
    f, X, c = a["f"], a["X"], a["comp"]
    E = np.eye(3)
    Fr = np.array([f[c == i].sum() for i in range(3)])
    M = np.cross(X.T, (f[:, None] * E[c])).sum(0)
    cols, rows = [], []
    for P, comps in supports:
        for k in comps:
            cols.append(np.concatenate([E[k], np.cross(np.asarray(P, float), E[k])]))
            rows.append((tuple(np.round(P, 3)), "xyz"[k]))
    A = np.array(cols).T
    r = np.linalg.solve(A, -np.concatenate([Fr, M]))
    return [(p, k, float(v)) for (p, k), v in zip(rows, r)], Fr, M


def selftest():
    """Statics reactions against K u - f of a real solve on a small block with unbalanced loads."""
    from skfem import MeshTet
    from w16.sim import fea as FE
    m = MeshTet.init_tensor(np.linspace(0, 10, 4), np.linspace(0, 6, 3), np.linspace(0, 4, 3))
    mt = dict(E=210000.0, nu=0.3, alpha=1.2e-5)
    top, bot = FE.facets(m, lambda x: x[2] > 4 - 1e-9), FE.facets(m, lambda x: x[2] < 1e-9)
    fn = lambda x: np.array([0.3 * np.ones_like(x[0]), 0.1 * x[0], -1.0 + 0 * x[0]])
    fb = lambda x: np.array([0 * x[0], 0 * x[0], 1.0 + 0 * x[0]])
    node = lambda q: int(np.argmin(((m.p - np.reshape(q, (3, 1))) ** 2).sum(0)))
    pts = [(node((0, 0, 0)), (0, 1, 2)), (node((10, 0, 0)), (1, 2)), (node((10, 6, 0)), (2,))]
    a = FE.solve_elastic(m, mt, None, tractions=[(top, fn)], balance=(bot, fb, 2), assemble_only=True)
    st, _, _ = statics_reactions(a, [(m.p[:, n], comps) for n, comps in pts])
    s = FE.solve_elastic(m, mt, None, tractions=[(top, fn)], balance=(bot, fb, 2), points=pts)
    ref = [r for _, _, r in s["point_reactions"]]
    got = [r for _, _, r in st]
    print("statics:", np.round(got, 6).tolist())
    print("solve:  ", np.round(ref, 6).tolist())
    assert np.allclose(got, ref, atol=1e-6), "statics reactions differ from the solve"
    print("selftest OK")


def main():
    from w16.sim import fea as FE
    from w16.cad import cranktrain as CT
    from w16.cad.assembly import _cw
    rec = json.load(open(os.path.join(ROOT, "08_SIMULATIONS", "fea", "crank.json"), encoding="utf-8"))
    t0 = time.time()
    R = FE.results()["dynamics"]
    cw, _ = _cw()
    k = 3
    thr = CT.fe_throw(k, (cw[k][0], cw[k][1]))
    mt = FE.mat("steel_qt")
    G = FE.crank_geometry(k)
    m, st = FE.mesh_shape(thr, 5.0, "crank", refine=FE.crank_refine(G))
    F = R["F_design_gas"]
    same = {key: (st[key], rec["mesh"][key]) for key in ("nodes", "tets", "volume_mm3", "quality_gamma_min")}
    identical = all(abs(a - b) <= 1e-6 * max(1.0, abs(b)) for a, b in same.values())
    print("mesh", st, "identical to the record:" if identical else "DIFFERS from the record:", same, flush=True)
    a, pts = FE.crank_solve(m, G, F, mt, assemble_only=True)
    sup = [(m.p[:, n], comps) for n, comps in pts]
    reac, Fr, M = statics_reactions(a, sup)
    node_max = max(abs(r) for _, _, r in reac)
    # elements around support node A and the record's peak element
    nA = pts[0][0]
    elA = np.where((m.t == nA).any(axis=0))[0]
    cen = m.p[:, m.t[:, elA]].mean(axis=1)
    edges = lambda e: max(np.linalg.norm(m.p[:, m.t[i, e]] - m.p[:, m.t[j, e]]) for i in range(4) for j in range(i + 1, 4))
    vol = lambda e: abs(np.linalg.det(np.array([m.p[:, m.t[i, e]] - m.p[:, m.t[0, e]] for i in (1, 2, 3)]))) / 6
    loc = np.array(rec["results"]["vm_max_location"])
    d_peak = np.linalg.norm(cen - loc[:, None], axis=0)
    # load per bearing land, by the dofs of its facets
    from skfem import FacetBasis, ElementVector, ElementTetP2
    from w16.params import P
    e_pin, (mx0, mx1), hl = G["e_pin"], G["mains"], G["land"] / 2
    land_N = {}
    for name, mx in (("main_k", mx0), ("main_k_plus_1", mx1)):
        fcl = FE.facets(m, lambda x: (np.hypot(x[1], x[2]) < P.main_dia / 2 + 0.05) & (np.abs(x[0] - mx) <= hl + 0.01))
        d = np.unique(FacetBasis(m, ElementVector(ElementTetP2()), facets=fcl, intorder=4).element_dofs)
        land_N[name] = float(sum(a["f"][d][a["comp"][d] == i].sum() * e_pin[i] for i in range(3)))
    # bending moment at the feature sections: model (loads + support reactions) vs intended bay
    E3 = np.eye(3)
    nz = np.nonzero(np.abs(a["f"]) > 0)[0]
    Pp = np.vstack([a["X"][:, nz].T] + [np.asarray(p, float)[None] for p, _, _ in reac])
    Vv = np.vstack([a["f"][nz, None] * E3[a["comp"][nz]]] + [r * E3["xyz".index(k_)][None] for _, k_, r in reac])
    n_ax = np.cross([1.0, 0.0, 0.0], e_pin)

    def m_model(xs):
        Lm = Pp[:, 0] < xs
        return float((np.cross(Pp[Lm] - np.array([xs, 0.0, 0.0]), Vv[Lm]) @ n_ax).sum()) / 1e3

    def m_ideal(xs):
        tot = 0.0
        for xi, Fi in ((mx0, F / 2), (G["pc"][0], -F), (mx1, F / 2)):
            if xi < xs:
                tot += float(np.cross(np.array([xi - xs, 0.0, 0.0]), Fi * e_pin) @ n_ax)
        return tot / 1e3
    sections = [dict(section=nm, x=round(float(xs), 2), M_model_Nm=round(m_model(xs), 1), M_intended_Nm=round(m_ideal(xs), 1),
                     ratio=round(m_model(xs) / m_ideal(xs), 3))
                for nm, xs in (("main fillet, main k (web face)", G["xfa"]), ("pin groove a", G["xa"]), ("pin groove b", G["xb"]),
                               ("main fillet, main k+1 (web face)", G["xfb"]))]
    out = dict(
        note=("statics of the discrete load vector of fea.case_crank on a re-mesh of the slice (no solve): reactions of the 3-2-1 "
              "point support per node and component; the record's support check adds each component over the nodes, so a couple "
              "carried by two nodes cancels in it"),
        mesh=st, mesh_identical_to_record=identical, mesh_compare=same, pin_load_N=F,
        applied_resultant_force_N=Fr.tolist(), applied_resultant_moment_Nmm=M.tolist(),
        reactions=[dict(at=list(p), component=k, reaction_N=r, pct_of_pin_load=100 * abs(r) / F) for p, k, r in reac],
        node_reaction_max_N=node_max, node_reaction_max_pct=100 * node_max / F,
        land_load_N=land_N, land_share=[round(v / sum(land_N.values()), 3) for v in land_N.values()],
        section_moments=sections,
        support_node_A=dict(node=int(nA), at=m.p[:, nA].round(3).tolist(), elements=int(len(elA)),
                            element_max_edge_mm=[round(float(edges(e)), 2) for e in elA],
                            element_volume_mm3=[round(float(vol(e)), 3) for e in elA]),
        record_peak=dict(vm_max_MPa=rec["results"]["vm_max_MPa"], at=loc.tolist(),
                         distance_to_node_A_mm=float(np.linalg.norm(loc - m.p[:, nA])),
                         nearest_element_centroid_around_A_mm=float(d_peak.min()),
                         peak_element_touches_node_A=bool(d_peak.min() < 1e-3)),
        seconds=round(time.time() - t0, 1))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("support_node_A",)}, indent=1))
    print("node A elements:", out["support_node_A"])


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
