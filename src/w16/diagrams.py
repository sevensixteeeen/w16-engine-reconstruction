"""System schematics (static) and flow animations (animated dashes): charge-air / exhaust with sequential
turbocharging, cooling circuits, lubrication circuit, fuel-ignition-engine-management architecture.

    python -m w16.diagrams
"""
from __future__ import annotations
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import imageio.v2 as imageio

from .params import P

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_D = os.path.join(ROOT, "06_ASSEMBLIES", "system_diagrams")
OUT_A = os.path.join(ROOT, "09_ANIMATIONS")
COL = dict(air="#2f7fd1", charge="#12a3a3", exh="#d1492f", cool="#2f62d1", lt="#39b3e6", oil="#c98a10", fuel="#7a3fb5", sig="#444444", off="#bbbbbb")


class Diagram:
    def __init__(self, title, size=(15, 9), xlim=(0, 100), ylim=(0, 60)):
        self.fig, self.ax = plt.subplots(figsize=size)
        self.ax.set_xlim(*xlim); self.ax.set_ylim(*ylim); self.ax.axis("off")
        self.ax.set_title(title, fontsize=13, loc="left")
        self.nodes, self.lines = {}, []

    def box(self, key, x, y, w, h, text, fc="#eef1f5", ec="#333333", fs=8):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=fc, ec=ec, lw=1.1, zorder=3))
        self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, zorder=4)
        self.nodes[key] = (x, y, w, h)

    def c(self, key, side="c", f=0.5):
        x, y, w, h = self.nodes[key]
        return dict(l=(x - 0.3, y + h * f), r=(x + w + 0.3, y + h * f), t=(x + w * f, y + h + 0.3), b=(x + w * f, y - 0.3), c=(x + w / 2, y + h / 2))[side]

    def flow(self, pts, kind, lw=2.6, label=None, group="always", lab_at=0.5, lab_dy=0.9):
        pts = np.array(pts, float)
        (ln,) = self.ax.plot(pts[:, 0], pts[:, 1], color=COL[kind], lw=lw, zorder=2, solid_capstyle="round")
        d = pts[-1] - pts[-2]
        d = d / np.linalg.norm(d)
        (ar,) = self.ax.plot([pts[-1][0]], [pts[-1][1]], marker=(3, 0, np.degrees(np.arctan2(d[1], d[0])) - 90), ms=8, color=COL[kind], zorder=2)
        if label:
            seg = np.cumsum(np.r_[0, np.linalg.norm(np.diff(pts, axis=0), axis=1)])
            s = lab_at * seg[-1]
            i = min(np.searchsorted(seg, s) - 1, len(pts) - 2); i = max(i, 0)
            p = pts[i] + (pts[i + 1] - pts[i]) * (s - seg[i]) / max(seg[i + 1] - seg[i], 1e-9)
            self.ax.text(p[0], p[1] + lab_dy, label, fontsize=6.5, color=COL[kind], ha="center", zorder=5)
        self.lines.append(dict(line=ln, arrow=ar, kind=kind, group=group))
        return ln

    def note(self, x, y, text, fs=7.5, **kw):
        return self.ax.text(x, y, text, fontsize=fs, va="top", **kw)

    def save(self, name):
        os.makedirs(OUT_D, exist_ok=True)
        self.fig.savefig(os.path.join(OUT_D, name + ".png"), dpi=140, bbox_inches="tight")
        self.fig.savefig(os.path.join(OUT_D, name + ".svg"), bbox_inches="tight")

    def animate(self, name, n=36, state=None, fps=12):
        """Marching-dash animation.  state(frame) -> dict(group -> bool active) and may update texts."""
        os.makedirs(OUT_A, exist_ok=True)
        frames = []
        for k in range(n):
            act = state(k) if state else {}
            for l in self.lines:
                on = act.get(l["group"], True)
                l["line"].set_color(COL[l["kind"]] if on else COL["off"])
                l["arrow"].set_color(COL[l["kind"]] if on else COL["off"])
                l["line"].set_linestyle((-(k % 12) * 1.0, (6.0, 3.0)) if on else (0, (1.0, 2.5)))
            self.fig.canvas.draw()
            frames.append(np.asarray(self.fig.canvas.buffer_rgba())[:, :, :3].copy())
        imageio.mimsave(os.path.join(OUT_A, name + ".gif"), frames, duration=1000 / fps, loop=0)
        try:
            h, w = frames[0].shape[:2]
            fr = [f[: h - h % 16, : w - w % 16] for f in frames]
            imageio.mimsave(os.path.join(OUT_A, name + ".mp4"), fr * 3, fps=fps)
        except Exception as e:
            print("mp4 failed", e)
        plt.close(self.fig)


def results():
    with open(os.path.join(ROOT, "08_SIMULATIONS", "analytical", "results.json"), encoding="utf-8") as fh:
        return json.load(fh)


def air_exhaust(R):
    d = Diagram("Charge-air and exhaust system with sequential (register) turbocharging - one of two identical banks (cylinders 1-8 shown)")
    d.box("abox", 2, 44, 12, 7, "Air box +\nfilter")
    d.box("cA", 20, 47, 11, 6, "Compressor A\n(always active)", fc="#dbe9fb")
    d.box("cB", 20, 36, 11, 6, "Compressor B\n(switchable)", fc="#dbe9fb")
    d.box("rv", 45.5, 30.6, 9, 3.8, "Recirculation\nvalve B", fs=7)
    d.box("thA", 38, 47, 9, 6, "Throttle A")
    d.box("thB", 38, 36, 9, 6, "Throttle B /\ncut-in valve")
    d.box("cac", 52, 40, 11, 12, "Water-to-air\ncharge-air cooler\n(on the plenum)", fc="#d9f3f3")
    d.box("plen", 67, 40, 9, 12, "Plenum +\n8 runners\n16 injectors", fc="#d9f3f3")
    d.box("eng", 80, 22, 16, 30, "VR8 bank\ncyl 1-8\n\nfront group\ncyl 1-4\n\nrear group\ncyl 5-8", fc="#f3f0e6")
    d.box("mF", 60, 26, 12, 5, "Front manifold (1-4)", fc="#fbe3dc")
    d.box("mR", 60, 14, 12, 5, "Rear manifold (5-8)", fc="#fbe3dc")
    d.box("xo", 62.5, 20.2, 7, 3.4, "Cross-over", fs=7, fc="#fbe3dc")
    d.box("sv", 46, 13.5, 10, 6, "Exhaust shut-off\nvalve (980 degC)", fc="#fbd0c5", fs=7.5)
    d.box("tA", 30, 25.5, 11, 6, "Turbine A\n+ waste-gate", fc="#fbe3dc")
    d.box("tB", 30, 13.5, 11, 6, "Turbine B\n+ waste-gate", fc="#fbe3dc")
    d.box("pcA", 14, 25.5, 11, 6, "Pre-catalyst A")
    d.box("pcB", 14, 13.5, 11, 6, "Pre-catalyst B")
    d.box("main", 2, 18, 8, 9, "Main\ncatalyst\n+ silencer")
    d.flow([d.c("abox", "r", 0.75), d.c("cA", "l")], "air", label="ambient air")
    d.flow([d.c("abox", "r", 0.25), (17, 45.7), (17, 39), d.c("cB", "l")], "air", group="B")
    d.flow([d.c("cA", "r"), d.c("thA", "l")], "charge", label="~173 degC")
    d.flow([d.c("cB", "r"), d.c("thB", "l")], "charge", group="B")
    d.flow([d.c("cB", "r", 0.2), (35.5, 37.2), (35.5, 32.5), d.c("rv", "l")], "charge", lw=1.4, group="recirc")
    d.flow([d.c("rv", "t"), (50, 35.2), (18.5, 35.2), (18.5, 37.5), d.c("cB", "l", 0.25)], "charge", lw=1.4, group="recirc")
    d.flow([d.c("thA", "r"), d.c("cac", "l", 0.83)], "charge")
    d.flow([d.c("thB", "r"), d.c("cac", "l", 0.17)], "charge", group="B")
    d.flow([d.c("cac", "r"), d.c("plen", "l")], "charge", label="~58 degC", lab_dy=1.2)
    d.flow([d.c("plen", "r"), d.c("eng", "l", 0.8)], "charge")
    d.flow([d.c("eng", "l", 0.22), d.c("mF", "r")], "exh")
    d.flow([d.c("eng", "l", 0.0 + 0.02), (77.5, 16.5), d.c("mR", "r")], "exh")
    d.flow([d.c("mR", "t", 0.5), d.c("xo", "b")], "exh", lw=1.8, group="xover")
    d.flow([d.c("xo", "t"), d.c("mF", "b", 0.5)], "exh", lw=1.8, group="xover")
    d.flow([d.c("mF", "l"), d.c("tA", "r")], "exh", label="<= 980 degC")
    d.flow([d.c("mR", "l"), d.c("sv", "r")], "exh", group="B")
    d.flow([d.c("sv", "l"), d.c("tB", "r")], "exh", group="B")
    d.flow([d.c("tA", "l"), d.c("pcA", "r")], "exh")
    d.flow([d.c("tB", "l"), d.c("pcB", "r")], "exh", group="B")
    d.flow([d.c("pcA", "l"), (12, 28.5), (12, 24), d.c("main", "r", 0.7)], "exh")
    d.flow([d.c("pcB", "l"), (12, 16.5), (12, 21), d.c("main", "r", 0.3)], "exh", group="B")
    d.ax.plot([35.5, 25.5], [31.8, 46.7], color="#555", lw=1.2, ls=":", zorder=1); d.ax.plot([35.5, 25.5], [19.8, 35.7], color="#555", lw=1.2, ls=":", zorder=1)
    d.note(26.5, 34.0, "shaft", fs=6, color="#555"); d.note(31.5, 44.5, "shaft", fs=6, color="#555")
    d.note(2, 10.5, "Operating logic (model results, 08_SIMULATIONS/analytical/01):\n"
           f"- below ~{P.rpm_turbo_switch:.0f} rpm: shut-off valve and throttle B closed; all eight cylinders feed turbine A through the cross-over; "
           "compressor B idles on its recirculation valve.\n"
           "- change-over: the shut-off valve opens progressively, turbo B is pre-spun; throttle B opens when compressor-B outlet pressure reaches manifold pressure.\n"
           "- above: both turbochargers of each bank work in parallel; boost is controlled by the waste-gates; T3 is limited by enrichment.", fs=7.5)
    d.save("01_air_exhaust_sequential_turbocharging")
    cur = R["curve"]
    rp = np.array([r["rpm"] for r in cur])
    txt = d.ax.text(52, 58.5, "", fontsize=10, family="monospace", va="top", zorder=6)
    n = 60

    def state(k):
        rpm = 1000 + (6800 - 1000) * k / (n - 1)
        b_on = rpm >= P.rpm_turbo_switch
        g = lambda key: float(np.interp(rpm, rp, [r[key] for r in cur]))
        txt.set_text(f"{rpm:5.0f} rpm | {g('torque'):5.0f} N m | boost {g('boost_bar'):4.2f} bar | waste-gate {max(g('wg_frac'), 0) * 100:3.0f} % | "
                     f"{'4' if b_on else '2'} turbos active")
        return dict(B=b_on, recirc=not b_on, xover=not b_on)
    d.animate("05_sequential_turbocharging_flow", n=n, state=state, fps=8)


def cooling(R):
    d = Diagram("Thermal management: high-temperature engine circuit and low-temperature charge-air circuit")
    d.box("pump", 6, 30, 11, 7, f"Main water pump\n{R['coolant']['flow_lpm']:.0f} L/min", fc="#dbe5fb")
    d.box("b1", 24, 40, 13, 7, "Block bank 1\njackets cyl 1-8", fc="#e9eefc")
    d.box("b2", 24, 20, 13, 7, "Block bank 2\njackets cyl 9-16", fc="#e9eefc")
    d.box("h1", 43, 40, 13, 7, "Head bank 1\nexh -> intake side", fc="#e9eefc")
    d.box("h2", 43, 20, 13, 7, "Head bank 2\nexh -> intake side", fc="#e9eefc")
    d.box("tc", 43, 30.5, 13, 5, "4 turbo bearing\nhousings (parallel)", fs=7, fc="#e9eefc")
    d.box("oc", 24, 30.5, 13, 5, "Oil-to-water cooler", fs=7.5, fc="#e9eefc")
    d.box("th", 62, 30, 10, 7, "Thermostat\nhousing")
    d.box("rad", 78, 26, 14, 15, "Main radiator\n+ 2 auxiliary\nradiators\n(vehicle front)")
    d.box("exp", 78, 46, 14, 5, "Expansion tank / de-aeration", fs=7)
    d.flow([d.c("pump", "t"), (11.5, 43.5), d.c("b1", "l")], "cool", label=f"{R['coolant']['flow_lpm'] / 2:.0f} L/min")
    d.flow([d.c("pump", "b"), (11.5, 23.5), d.c("b2", "l")], "cool")
    d.flow([d.c("pump", "r", 0.7), (20, 34.9), (20, 33), d.c("oc", "l")], "cool", lw=1.5)
    d.flow([d.c("b1", "r"), d.c("h1", "l")], "cool", label="gasket metering holes")
    d.flow([d.c("b2", "r"), d.c("h2", "l")], "cool")
    d.flow([d.c("oc", "r"), d.c("tc", "l")], "cool", lw=1.5)
    d.flow([d.c("h1", "r"), (67, 43.5), d.c("th", "t")], "cool", label=f"+{R['coolant']['dT']:.1f} K", lab_at=0.3)
    d.flow([d.c("h2", "r"), (67, 23.5), d.c("th", "b")], "cool")
    d.flow([d.c("tc", "r"), d.c("th", "l", 0.4)], "cool", lw=1.5)
    d.flow([d.c("th", "r"), d.c("rad", "l", 0.5)], "cool")
    d.flow([d.c("rad", "b"), (85, 12), (3, 12), (3, 33.5), d.c("pump", "l")], "cool", label="return")
    d.flow([d.c("th", "t", 0.8), (70, 48.5), d.c("exp", "l")], "cool", lw=1.0)
    d.box("ltp", 6, 2, 11, 6, f"Electric LT pump\n{R['cac']['lt_flow_total_lpm']:.0f} L/min", fc="#d9f1fb")
    d.box("c1", 30, 4.6, 14, 4.4, "Charge-air cooler bank 1", fs=7.5, fc="#d9f1fb")
    d.box("c2", 30, -1.4, 14, 4.4, "Charge-air cooler bank 2", fs=7.5, fc="#d9f1fb")
    d.box("ltr", 62, 1, 14, 7, "LT radiator\n(vehicle front)", fc="#d9f1fb")
    d.flow([d.c("ltp", "r", 0.7), (24, 6.2), d.c("c1", "l")], "lt")
    d.flow([d.c("ltp", "r", 0.3), (24, 1.2), d.c("c2", "l")], "lt")
    d.flow([d.c("c1", "r"), (52, 6.8), d.c("ltr", "l", 0.7)], "lt", label=f"{R['cac']['q_total_kw']:.0f} kW from charge air")
    d.flow([d.c("c2", "r"), (52, 0.8), d.c("ltr", "l", 0.3)], "lt")
    d.flow([d.c("ltr", "r"), (80, 4.5), (80, -4), (3, -4), (3, 5), d.c("ltp", "l")], "lt")
    d.ax.set_ylim(-6, 60)
    d.note(60, 58, f"HT heat load at rated power: {R['energy']['q_coolant_ht']:.0f} kW  |  LT: {R['cac']['q_total_kw']:.0f} kW  |  oil: {R['lube']['q_oil_kw']:.0f} kW", fs=8)
    d.save("02_cooling_circuits")
    d.animate("07_cooling_circulation", n=24)


def lubrication(R):
    lu = R["lube"]
    d = Diagram("Dry-sump lubrication circuit")
    d.box("tank", 3, 34, 11, 14, "Oil tank\n(de-aeration)", fc="#fbf1d9")
    d.box("pp", 19, 38, 11, 7, f"Pressure stage\n{lu['q_pump_lpm']:.0f} L/min")
    d.box("flt", 35, 38, 9, 7, "Filter")
    d.box("clr", 49, 38, 10, 7, "Oil-to-water\ncooler")
    d.box("gal", 64, 38, 12, 7, f"Main gallery\n{lu['p_gallery_bar']:.0f} bar", fc="#fbf1d9")
    d.box("mb", 82, 50, 15, 5, f"9 main bearings  {lu['q_main_lpm']:.1f}", fs=7.5)
    d.box("rb", 82, 43.5, 15, 5, f"16 big ends (via crank)  {lu['q_rod_lpm']:.1f}", fs=7)
    d.box("jet", 82, 37, 15, 5, f"16 piston jets  {lu['q_jets_lpm']:.0f}", fs=7.5)
    d.box("hd", 82, 30.5, 15, 5, f"heads: cams, HLA, phasers  {lu['q_cam_lpm'] + lu['q_hla_lpm'] + lu['q_phaser_lpm']:.0f}", fs=6.5)
    d.box("tb", 82, 24, 15, 5, f"4 turbochargers  {lu['q_turbo_lpm']:.1f}", fs=7.5)
    d.box("ch", 82, 17.5, 15, 5, f"chain tensioners + spray  {lu['q_chain_lpm']:.1f}", fs=7)
    d.box("sump", 40, 8, 30, 7, "Dry-sump pan: 4 scavenge bays (+ head / chain-case / turbo returns)", fc="#fbf1d9", fs=7.5)
    d.box("sc", 19, 8, 13, 7, f"6 scavenge stages\n{lu['q_scavenge_lpm']:.0f} L/min capacity")
    d.flow([d.c("tank", "r", 0.5), d.c("pp", "l")], "oil")
    d.flow([d.c("pp", "r"), d.c("flt", "l")], "oil")
    d.flow([d.c("flt", "r"), d.c("clr", "l")], "oil")
    d.flow([d.c("clr", "r"), d.c("gal", "l")], "oil")
    for k in ("mb", "rb", "jet", "hd", "tb", "ch"):
        y = d.c(k, "l")[1]
        d.flow([d.c("gal", "r"), (79, 41.5), (79, y), d.c(k, "l")], "oil", lw=1.6)
    d.flow([(97.6, 34), (99, 34), (99, 11.5), d.c("sump", "r")], "oil", lw=1.6, label="drain by gravity", lab_at=0.55, lab_dy=-2.0)
    d.flow([d.c("sump", "l"), d.c("sc", "r")], "oil", label="oil + blow-by gas")
    d.flow([d.c("sc", "l"), (8.5, 11.5), d.c("tank", "b")], "oil")
    d.note(3, 58, f"Engine demand {lu['q_total_lpm']:.0f} L/min hot | oil heat {lu['q_oil_kw']:.0f} kW -> temperature rise {lu['oil_dT']:.0f} K | flows in L/min", fs=8)
    d.save("03_lubrication_circuit")
    d.animate("08_lubrication_circulation", n=24)


def ems(R):
    fu = R["fuel"]
    d = Diagram("Fuel, ignition and engine-management architecture (conceptual - no calibration exists)")
    d.box("ecu1", 38, 34, 24, 12, "Engine control unit - master\ntorque structure, air path, bank 1\n(cyl 1-8 injection + ignition)", fc="#e8e4f6")
    d.box("ecu2", 38, 18, 24, 12, "Engine control unit - slave\nbank 2 (cyl 9-16 injection + ignition)\nplausibility / limp-home", fc="#e8e4f6")
    d.box("sens", 2, 22, 22, 30, "Sensors\ncrank 60-2, 4 x cam phase\n2 x MAP/T, 4 x boost, 4 x turbo speed\n4 x EGT, 4 x wide-band lambda\n4 x knock, 16 x ion current\ncoolant T, oil p/T, fuel p (2 rails x 2)\npedal, ambient p/T", fs=7.5)
    d.box("inj", 74, 46, 24, 7, f"32 port injectors ({fu['injector_selected_cc_min']:.0f} cm3/min)\nprimary + secondary per cylinder", fs=7.5, fc="#efe3fb")
    d.box("ign", 74, 37, 24, 7, "16 pencil coils with\nion-current measurement", fs=7.5)
    d.box("thr", 74, 28, 24, 7, "4 throttle bodies\n(2 act as compressor cut-in valves)", fs=7.5)
    d.box("wg", 74, 19, 24, 7, "4 waste-gate actuators\n2 exhaust shut-off valves, 2 recirc valves", fs=7.5)
    d.box("ph", 74, 10, 24, 7, "4 cam phasers, LT pump,\nfuel pumps, thermostat", fs=7.5)
    d.box("fp", 30, 2, 16, 7, f"Tank + LP pumps\n{fu['pump_flow_lph']:.0f} L/h", fc="#efe3fb")
    d.box("reg", 52, 2, 16, 7, f"Pressure regulator\n{fu['rail_dp_bar']:.0f} bar over manifold", fc="#efe3fb", fs=7.5)
    d.flow([d.c("sens", "r", 0.7), d.c("ecu1", "l")], "sig", lw=1.6)
    d.flow([d.c("sens", "r", 0.25), d.c("ecu2", "l")], "sig", lw=1.6)
    d.flow([d.c("ecu1", "b"), d.c("ecu2", "t")], "sig", lw=1.6, label="CAN / sync", lab_dy=-0.2)
    for k, f in (("inj", 0.9), ("ign", 0.7), ("thr", 0.45), ("wg", 0.2)):
        d.flow([d.c("ecu1", "r", f), (68, d.c("ecu1", "r", f)[1]), (68, d.c(k, "l")[1]), d.c(k, "l")], "sig", lw=1.3)
    d.flow([d.c("ecu2", "r", 0.3), (70, d.c("ecu2", "r", 0.3)[1]), (70, d.c("ph", "l")[1]), d.c("ph", "l")], "sig", lw=1.3)
    d.flow([d.c("fp", "r"), d.c("reg", "l")], "fuel")
    d.flow([d.c("reg", "r"), (72, 5.5), (72, 55.5), (86, 55.5), d.c("inj", "t")], "fuel", label="4 fuel rails (2 per bank)", lab_at=0.75)
    d.note(2, 20, "Functions (concept): cylinder-individual injection and ignition timing; knock / misfire detection\n"
           "by ion current -> retard, cylinder cut-out or boost reduction; boost control by waste-gates;\n"
           "register change-over sequencing; T3 protection by enrichment (model) / EGT; fail-safe: boost\n"
           "to waste-gate spring pressure, 2-turbo mode, rev limit, bank-wise injection cut.", fs=7.5)
    d.save("04_fuel_ignition_ems_architecture")
    plt.close(d.fig)


def main():
    R = results()
    air_exhaust(R)
    cooling(R)
    lubrication(R)
    ems(R)
    print("diagrams written to", OUT_D, "and", OUT_A)


if __name__ == "__main__":
    main()
