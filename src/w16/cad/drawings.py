"""Engineering drawings: hidden-line projections of the CAD solids on A3 sheets with overall dimensions, a
key-dimension table (values from the master parameters, with provenance tags) and a title block.

    python -m w16.cad.drawings            (component sheets + general arrangement)

Outputs PDF, SVG and PNG per sheet in 07_ENGINEERING_DRAWINGS.  The sheets are layout / design-review drawings:
tolerances are classes, not released values.
"""
from __future__ import annotations
import json
import math
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from build123d import Compound, GeomType, Location, Pos, Rot

from ..params import P
from .. import layout as L
from . import assembly as ASM, cranktrain as CT, head as H
from .common import MAT, ROOT

OUT = os.path.join(ROOT, "07_ENGINEERING_DRAWINGS")
VIEWS = {  # name: (viewport origin direction, up)
    "FRONT (view on +Y)": ((0, -1, 0), (0, 0, 1)), "TOP (view on -Z)": ((0, 0, 1), (0, 1, 0)), "SIDE (view on -X)": ((1, 0, 0), (0, 0, 1)),
    "ISOMETRIC": ((1, -1, 0.7), (0, 0, 1)),
}


def project(shape, direction, up, hidden=True):
    bb = shape.bounding_box()
    c = np.array([(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2])
    d = np.array(direction, float); d /= np.linalg.norm(d)
    org = c + d * 4000.0
    vis, hid = shape.project_to_viewport(tuple(org), viewport_up=up, look_at=tuple(c))
    def polys(edges):
        out = []
        for e in edges:
            n = 2 if e.geom_type == GeomType.LINE else 14
            pts = [e.position_at(t) for t in np.linspace(0, 1, n)]
            out.append(np.array([(p.X, p.Y) for p in pts]))
        return out
    return polys(vis), (polys(hid) if hidden else [])


def draw_view(ax, shape, direction, up, title, hidden=True, dims=True):
    vis, hid = project(shape, direction, up, hidden)
    for p in hid:
        ax.plot(p[:, 0], p[:, 1], color="#888888", lw=0.25, ls=(0, (3, 2)))
    for p in vis:
        ax.plot(p[:, 0], p[:, 1], color="black", lw=0.5)
    allp = np.vstack(vis) if vis else np.zeros((1, 2))
    x0, y0 = allp.min(0); x1, y1 = allp.max(0)
    w, h = x1 - x0, y1 - y0
    m = 0.10 * max(w, h) + 6
    if dims:
        yb = y0 - 0.55 * m
        ax.annotate("", (x0, yb), (x1, yb), arrowprops=dict(arrowstyle="<->", lw=0.6, color="#0b3d91"))
        ax.plot([x0, x0], [y0, yb - 0.1 * m], color="#0b3d91", lw=0.3); ax.plot([x1, x1], [y0, yb - 0.1 * m], color="#0b3d91", lw=0.3)
        ax.text((x0 + x1) / 2, yb - 0.02 * m, f"{w:.1f}", ha="center", va="top", fontsize=6.5, color="#0b3d91")
        xr = x1 + 0.55 * m
        ax.annotate("", (xr, y0), (xr, y1), arrowprops=dict(arrowstyle="<->", lw=0.6, color="#0b3d91"))
        ax.plot([x1, xr + 0.1 * m], [y0, y0], color="#0b3d91", lw=0.3); ax.plot([x1, xr + 0.1 * m], [y1, y1], color="#0b3d91", lw=0.3)
        ax.text(xr + 0.04 * m, (y0 + y1) / 2, f"{h:.1f}", ha="left", va="center", fontsize=6.5, color="#0b3d91", rotation=90)
    ax.set_xlim(x0 - m, x1 + 1.5 * m); ax.set_ylim(y0 - 1.3 * m, y1 + m)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(title, fontsize=7, loc="left", pad=1)


def title_block(fig, pn, name, material, mass, sheet, note=""):
    ax = fig.add_axes([0.60, 0.035, 0.375, 0.13]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, lw=1.0))
    for y in (0.25, 0.5, 0.75):
        ax.plot([0, 1], [y, y], color="black", lw=0.5)
    ax.plot([0.62, 0.62], [0, 0.75], color="black", lw=0.5)
    ax.text(0.01, 0.875, f"{name}", fontsize=10, va="center", weight="bold")
    ax.text(0.01, 0.625, f"Part no.  {pn}", fontsize=8, va="center")
    ax.text(0.63, 0.625, f"Sheet {sheet}   A3   mm", fontsize=7.5, va="center")
    ax.text(0.01, 0.375, f"Material  {material}", fontsize=7, va="center")
    ax.text(0.63, 0.375, f"Mass (CAD)  {mass}", fontsize=7.5, va="center")
    ax.text(0.01, 0.125, "W16 reconstruction project - PROVISIONAL, not released for manufacture", fontsize=6.5, va="center")
    ax.text(0.63, 0.125, "First-angle views generated\nfrom CAD 2026-11-14", fontsize=6, va="center")
    fig.text(0.025, 0.055, "General tolerances ISO 2768-mK unless stated. Dimensions in blue are overall extents measured on the CAD solid.\n"
             "Tags: PUB published, SEC secondary source, CALC calculated, EST engineering estimate. " + note, fontsize=6, va="bottom")


def sheet(shape, pn, name, material, mass, dims_table, fname, hidden=True, sheet_no="1/1", note=""):
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.add_artist(plt.Rectangle((0.012, 0.018), 0.976, 0.964, fill=False, lw=1.2, transform=fig.transFigure))
    pos = [[0.03, 0.56, 0.44, 0.40], [0.03, 0.17, 0.44, 0.37], [0.49, 0.56, 0.26, 0.40], [0.49, 0.185, 0.26, 0.355]]
    for (title, (d, up)), bx in zip(VIEWS.items(), pos):
        ax = fig.add_axes(bx)
        try:
            draw_view(ax, shape, d, up, title, hidden=hidden and title != "ISOMETRIC", dims=title != "ISOMETRIC")
        except Exception as e:
            ax.text(0.5, 0.5, f"projection failed: {e!r}"[:80], ha="center", fontsize=6); ax.axis("off")
    ax = fig.add_axes([0.765, 0.185, 0.215, 0.775]); ax.axis("off")
    ax.text(0, 1.0, "KEY DIMENSIONS AND REQUIREMENTS", fontsize=8, weight="bold", va="top")
    y = 0.965
    for row in dims_table:
        txt = f"{row[0]}:  {row[1]}" + (f"   [{row[2]}]" if len(row) > 2 and row[2] else "")
        ax.text(0, y, txt, fontsize=6.3, va="top", wrap=True)
        y -= 0.0215 * (1 + txt.count("\n") + len(txt) // 62)
    title_block(fig, pn, name, material, mass, sheet_no, note)
    os.makedirs(OUT, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(os.path.join(OUT, f"{fname}.{ext}"), dpi=110 if ext == "png" else None)
    plt.close(fig)
    print("drawing", fname)


def ga_sheet(val):
    """General-arrangement sheet from rendered orthographic views with overall envelope dimensions."""
    vdir = os.path.join(ROOT, "06_ASSEMBLIES", "views")
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.add_artist(plt.Rectangle((0.012, 0.018), 0.976, 0.964, fill=False, lw=1.2, transform=fig.transFigure))
    lay = [("engine_left_bank1_side.png", [0.03, 0.55, 0.46, 0.41], "LEFT SIDE (bank 1)"), ("engine_front_free_end.png", [0.51, 0.55, 0.46, 0.41], "FREE END"),
           ("engine_top.png", [0.03, 0.17, 0.46, 0.37], "TOP"), ("engine_isometric.png", [0.51, 0.19, 0.46, 0.35], "ISOMETRIC")]
    for f, bx, t in lay:
        ax = fig.add_axes(bx); ax.axis("off")
        p = os.path.join(vdir, f)
        if os.path.exists(p):
            ax.imshow(mpimg.imread(p))
        ax.set_title(t, fontsize=8, loc="left", pad=1)
    e, lb = val["envelope_dressed_mm"], val["envelope_long_block_mm"]
    txt = (f"Overall envelope, dressed engine (CAD):  L {e['size'][0]:.0f}  x  W {e['size'][1]:.0f}  x  H {e['size'][2]:.0f} mm     "
           f"x {e['min'][0]:.0f}...{e['max'][0]:.0f},  y {e['min'][1]:.0f}...{e['max'][1]:.0f},  z {e['min'][2]:.0f}...{e['max'][2]:.0f}\n"
           f"Long block (crankcase, heads, covers, timing):  L {lb['size'][0]:.0f}  x  W {lb['size'][1]:.0f}  x  H {lb['size'][2]:.0f} mm     "
           f"Published reference length 710 mm (SEC).   Datum: x = 0 main bearing 5, crank axis y = z = 0, +x flywheel end.\n"
           f"CAD mass {val['mass_total_kg']:.0f} kg dressed, dry (see ASSEMBLY_HIERARCHY.md);  centre of mass x {val['centre_of_mass_mm'][0]:.0f}, y {val['centre_of_mass_mm'][1]:.0f}, z {val['centre_of_mass_mm'][2]:.0f} mm.   "
           f"Bore x stroke {P.bore:.0f} x {P.stroke:.0f} mm, cylinder pitch {P.cyl_pitch:.0f} mm, bank angle {P.bank_angle:.0f} deg, VR angle {P.vr_angle:.0f} deg.")
    fig.text(0.03, 0.165, txt, fontsize=7.5, va="top")
    title_block(fig, "W16-00-000", "W16 engine - general arrangement", "assembly", f"{val['mass_total_kg']:.0f} kg", "1/1")
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"W16-00-000_general_arrangement.{ext}"), dpi=120 if ext == "png" else 200)
    plt.close(fig)
    print("drawing GA")


def tag(name):
    u, t, n = P._meta[name]
    v = getattr(P, name)
    return (f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)) + f" {u}", t


def rows(*items):
    out = []
    for label, key in items:
        if key in P._meta:
            v, t = tag(key)
            out.append((label, v, t))
        else:
            out.append((label, key, ""))
    return out


def main(which=None):
    reg, info = ASM.build(0.0)
    g = lambda pn: reg[pn]
    m = lambda p: f"{p.mass:.3f} kg" if p.mass < 20 else f"{p.mass:.1f} kg"
    jobs = {
        "crankshaft": lambda: sheet(g("W16-05-001").shape, "W16-05-001", "Crankshaft", MAT["steel_qt"], m(g("W16-05-001")), rows(
            ("Stroke", "stroke"), ("Crank throw (offset bores)", "throw"), ("Main journal dia", "main_dia"), ("Main journal width", "main_width"),
            ("Crankpin dia", "pin_dia"), ("Crankpin width", "pin_width"), ("Web thickness", "web_thk"), ("Throw pitch", "cyl_pitch"),
            ("Counterweight radius", "cw_radius"), ("Crankpins", "solid, no lightening bore (D-049)"),
            ("Crankpin phases 1-8 [deg]", ", ".join(f"{L.PIN_PHASE[k]:.2f}" for k in range(1, 9))),
            ("Journal fillets", f"pins: R2.5 semicircular relief groove, 2.5 deep into the web (D-048); mains: R{P.main_fillet_r:.1f}, rolled - "
                                + (f"main shells {P.main_shell_width:.1f} mm with {P.main_shell_chamfer:.1f} x 45 deg chamfers (D-050)" if P.main_shell_chamfer > 0
                                   else f"main shells {P.main_shell_width:.1f} mm, unchamfered (D-050 option (b))")),
            ("Journal tolerance", "main h5 / pin h5 (class, provisional); Ra 0.1 um ground + lapped"),
            ("Runout", "main journals 0.02 mm total indicated (class)"),
            ("Oil drillings", f"dia 5, one per rod: main surface -> pin surface at {CT.OIL_PHI:.0f} deg (pin frame, low-load zone); "
                              "inlet at the main centre (180-deg groove of the upper shell); 0.5 x 45 deg chamfers, polished (D-049)"),
            ("Balance", "dynamic, with bob weights for the rotating + 50 % of the reciprocating masses; see dynamics report"),
            ("Heat treatment", "QT to 1000-1100 MPa, gas nitrided 0.3-0.5 mm"), ("Inspection", "MPI 100 %, CMM journals, hardness, balance")),
            "W16-05-001_crankshaft", hidden=False),
        "rod": lambda: sheet(g("W16-04-001").shape + g("W16-04-002").shape, "W16-04-001/-002", "Connecting rod with cap", MAT["ti"],
                             f"{(g('W16-04-001').mass + g('W16-04-002').mass):.3f} kg", rows(
            ("Centre distance", "rod_length"), ("Big-end bore (housing)", f"{2 * CT.BE_BORE_R:.2f} mm H6 (class)"), ("Small-end bore (housing)", f"{2 * CT.SE_BORE_R:.2f} mm H6 (class)"),
            ("Big-end width", "rod_be_width"), ("Small-end width (trapezoidal)", "rod_se_width"), ("Bolt", "2 x M8x1, bolt circle +/- " + f"{CT.BOLT_Y:.1f} mm"),
            ("Parallelism of bores", "0.02 / 100 mm (class)"), ("Twist", "0.04 / 100 mm (class)"), ("Surface", "shot peened; bores honed Ra 0.4"),
            ("Weight class", "+/- 1 g, big-end / small-end masses matched per set"), ("Joint", "serrated, bolts torque + angle"),
            ("Inspection", "FPI 100 %, CMM, weight split")), "W16-04-001_connecting_rod"),
        "piston": lambda: sheet(g("W16-03-001").shape, "W16-03-001", "Piston", MAT["al_forged"], m(g("W16-03-001")), rows(
            ("Nominal diameter (bore)", "bore"), ("Skirt clearance (dia, cold)", "piston_clear_dia"), ("Compression height (axis)", "comp_height"),
            ("Overall height", "piston_height"), ("Crown tilt to pin-axis normal", "crown_tilt_axis"), ("Crown tilt to head face", "crown_tilt"),
            ("Pin bore", "pin_dia_piston"), ("Ring grooves", f"{P.ring1_h} / {P.ring2_h} / {P.ring3_h} mm axial"), ("Top land (low side)", "top_land"),
            ("Valve pockets", "2, depth 1.6 mm, far-side valves"), ("Skirt profile", "barrel + oval, to be developed on test (not modelled)"),
            ("Coatings", "hard-anodised top groove and crown, graphite skirt coating"), ("Inspection", "CMM, groove flatness, ultrasonic for forging laps")),
            "W16-03-001_piston"),
        "block": lambda: sheet(g("W16-01-001").shape, "W16-01-001", "Crankcase upper section (cylinder block)", MAT["al_cast"], m(g("W16-01-001")), rows(
            ("Bore", "bore"), ("Cylinder pitch", "cyl_pitch"), ("Bank angle", "bank_angle"), ("VR angle", "vr_angle"), ("Row offset", "row_offset"),
            ("Bank offset", "bank_offset"), ("Deck height (along bank centre line)", "deck_height"), ("Bore centre at deck (u)", "u_bore_deck"),
            ("Bore length", "bore_length"), ("Web between bores, deck / foot", f"{P.web_bore_deck:.1f} / {P.web_bore_foot:.1f} mm"),
            ("Main bearing bore", f"{P.main_dia + 2 * P.main_shell_thk:.1f} mm H6, line bored with bedplate (class)"),
            ("Water jacket", f"{P.jacket_width:.0f} mm wide, {P.jacket_depth:.0f} mm deep, closed deck {P.deck_thk:.0f} mm"),
            ("Oil galleries", f"central dia {P.oil_gallery_dia:.0f}; 2 x dia 12 for piston jets"), ("Head bolts", "25 x M11 per bank"),
            ("Bore finish", "plateau honed after coating, cylindricity 8 um (class)"), ("Deck flatness", "0.03 mm / bank (class)"),
            ("Inspection", "CT scan of casting, pressure test jackets 3 bar and galleries 10 bar, CMM")), "W16-01-001_cylinder_block", hidden=False),
        "head": lambda: sheet(g("W16-02-001").shape, "W16-02-001", "Cylinder head, bank 1", MAT["al_cast"], m(g("W16-02-001")), rows(
            ("Valve head dia, in / ex", f"{P.valve_in_dia:.0f} / {P.valve_ex_dia:.0f} mm"), ("Valve stem", "valve_stem_dia"), ("Camshaft axes u", "cam_u"),
            ("Camshaft axis height", "cam_w"), ("Chamber roof tilt", "roof_tilt"), ("Plug thread", "M10x1"), ("Head height", "head_height"),
            ("Valve stem tilt, short / long", f"{abs(H.LAY['inner']['in']['tilt']):.2f} / {abs(H.LAY['inner']['ex']['tilt']):.2f} deg"),
            ("Seat / guide", "inserts shrink-fitted; seat run-out to guide 0.03 mm (class)"), ("Joint face flatness", "0.03 mm (class)"),
            ("Cam bearing bores", "line bored with caps, H6 (class)"), ("Water jacket", "core between w = 11 and 52 mm, single connected volume (CAD-verified)"),
            ("Inspection", "CT scan, leak test, CMM, port flow test")), "W16-02-001_cylinder_head", hidden=False),
        "camshaft": lambda: sheet(g("W16-06-009").shape, "W16-06-009", "Intake camshaft, bank 1", MAT["steel_qt"], m(g("W16-06-009")), rows(
            ("Base circle radius", "cam_base_r"), ("Journal dia", "cam_journal_dia"), ("Follower ratio", "2.00"),
            ("Valve lift in / ex", f"{P.valve_lift_in} / {P.valve_lift_ex} mm"), ("Lobes", "16, width 11 mm, phased for firing order " + "-".join(map(str, P.firing_order))),
            ("Lobe profile", "conjugate to dia 17 roller, half-sine acceleration law (see valve-train report)"), ("Lobe hardness", "58 HRC min, ground Ra 0.2"),
            ("Inspection", "cam-form measurement (Adcole), MPI")), "W16-06-009_intake_camshaft_bank1", hidden=False),
        "valves": lambda: sheet(Compound(children=[Pos(40 * i, 0, 0) * g(f"W16-06-00{i + 1}").shape for i in range(4)]), "W16-06-001...004", "Valves (short/long intake, short/long exhaust)",
                                "X45CrSi9-3 / NiCr20TiAl", "44-60 g", rows(
            ("Head dia in / ex", f"{P.valve_in_dia:.0f} / {P.valve_ex_dia:.0f} mm"), ("Stem dia", "valve_stem_dia"),
            ("Lengths head-to-tip", ", ".join(f"{k}: {v:.1f}" for k, v in info["valve_lengths"].items()) + " mm"), ("Seat angle", "45 deg"),
            ("Stem finish", "nitrided or chrome flashed, Ra 0.2"), ("Exhaust", "hollow, sodium filled (recommended at 980 degC gas temperature)")), "W16-06-00x_valves"),
        "turbo": lambda: sheet(Compound(children=[reg[f"W16-08-0{n:02d}"].shape for n in (1, 3, 5, 7, 9, 13)]), "W16-08-001...013 (RH)", "Turbocharger assembly, RH", "see BOM",
                               f"{sum(reg[f'W16-08-0{n:02d}'].mass for n in (1, 3, 5, 7, 9, 13)):.1f} kg", rows(
            ("Compressor wheel exducer / inducer", f"{ASM.TB.S['d2c']:.1f} / {ASM.TB.S['d1c']:.1f} mm  [CALC]"), ("Turbine wheel inducer / exducer", f"{ASM.TB.S['dt']:.1f} / {ASM.TB.S['dte']:.1f} mm  [CALC/EST]"),
            ("Design flow / pressure ratio", "see performance report"), ("Bearings", "2 floating bushes + thrust bearing, oil 3-5 bar"),
            ("Housing cooling", "water-cooled bearing housing"), ("Note", "wheel blading is representative, not an aerodynamic design")), "W16-08-00x_turbocharger_RH", hidden=False),
    }
    for name, job in jobs.items():
        if which and name not in which:
            continue
        try:
            job()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("drawing FAILED:", name, repr(e)[:200])
    if not which or "ga" in which:
        vp = os.path.join(ROOT, "06_ASSEMBLIES", "cad_validation.json")
        if os.path.exists(vp):
            with open(vp, encoding="utf-8") as fh:
                ga_sheet(json.load(fh))
        else:
            print("GA sheet skipped: run export validate and render stills first")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
