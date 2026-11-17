"""W16 skeleton: coordinate system, cylinder table, crankpin phasing and slider-crank kinematics.

Global frame (right-handed)
    X  crankshaft axis, +X towards the flywheel / output end, x = 0 at main bearing 5
    Z  up (engine vertical, bisector of the 90 deg bank angle)
    Y  lateral; bank 1 (cylinders 1-8) leans towards +Y, bank 2 (cylinders 9-16) towards -Y
Angles phi are measured in the Y-Z plane from +Z towards +Y.
Crank angle alpha is a right-hand rotation about +X (clockwise seen from the free end);
a crankpin with phase psi sits at phi = psi - alpha.

Bank-local frame (x_l, u, v): v along the bank centre line (outwards from the crank),
u lateral and positive OUTBOARD, x_l = +x for bank 1 and -x for bank 2.  In these local
coordinates both banks are identical (the engine has 2-fold symmetry about the Z axis).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from scipy.optimize import brentq

from .params import P

D2R = math.pi / 180.0


def vec(phi_deg):
    """Unit vector (y, z) for angle phi."""
    p = np.asarray(phi_deg) * D2R
    return np.stack([np.sin(p), np.cos(p)], axis=-1)


@dataclass(frozen=True)
class Cyl:
    no: int            # 1..16
    bank: int          # 1 | 2
    row: str           # 'outer' | 'inner'
    pin: int           # crankpin 1..8
    x: float           # axial position of the cylinder axis
    theta: float       # axis direction angle (deg)
    q: tuple           # (y, z) of the axis point at crank-centre height in the bank frame
    fire: float        # crank angle of firing TDC (deg, 0..720)

    @property
    def d(self):       # axis unit vector (y, z)
        return vec(self.theta)

    @property
    def d3(self):
        d = self.d
        return np.array([0.0, d[0], d[1]])

    @property
    def q3(self):
        return np.array([self.x, self.q[0], self.q[1]])


# ------------------------------------------------------------------ bank frames
def bank_beta(bank):
    return 0.5 * P.bank_angle if bank == 1 else -0.5 * P.bank_angle


def bank_axes(bank):
    """Return (ex, eu, ev) global unit vectors of the bank-local frame (x_l, u_out, v)."""
    b = bank_beta(bank) * D2R
    s = 1.0 if bank == 1 else -1.0
    ev = np.array([0.0, math.sin(b), math.cos(b)])
    eu = s * np.array([0.0, math.cos(b), -math.sin(b)])
    ex = np.array([s, 0.0, 0.0])
    return ex, eu, ev


def to_global(bank, xl, u, v):
    ex, eu, ev = bank_axes(bank)
    return xl * ex + u * eu + v * ev


def to_local(bank, pt):
    ex, eu, ev = bank_axes(bank)
    pt = np.asarray(pt, float)
    return np.array([pt @ ex, pt @ eu, pt @ ev])


# ------------------------------------------------------------------ slider-crank with offset
def _s_tdc(r, l=None):
    l = P.rod_length if l is None else l
    g = 0.5 * P.vr_angle * D2R
    e = P.row_offset
    return -e * math.sin(g) + math.sqrt((l + r) ** 2 - (e * math.cos(g)) ** 2)


def _s_bdc(r, l=None):
    l = P.rod_length if l is None else l
    g = 0.5 * P.vr_angle * D2R
    e = P.row_offset
    return -e * math.sin(g) + math.sqrt((l - r) ** 2 - (e * math.cos(g)) ** 2)


def solve_throw():
    """Crank throw that gives exactly the reference stroke with the offset (desaxe) bores."""
    return brentq(lambda r: _s_tdc(r) - _s_bdc(r) - P.stroke, 30.0, 50.0, xtol=1e-12)


if not hasattr(P, "throw"):
    P.add("throw", solve_throw(), "mm", "CALC", "crank radius giving 86.000 mm stroke with offset bores (< stroke/2)")
    P.add("s_tdc", _s_tdc(P.throw), "mm", "CALC", "piston-pin distance along the cylinder axis from the axis foot point at TDC")
    P.add("s_bdc", _s_bdc(P.throw), "mm", "CALC", "same at BDC")
    P.add("bank_offset", P.rod_be_width + P.rod_side_clear, "mm", "CALC", "axial offset bank 2 vs bank 1 (one rod width)")
    P.add("disp_cyl_cc", math.pi / 4 * P.bore ** 2 * P.stroke / 1000.0, "cm3", "CALC", "swept volume per cylinder")
    P.add("displacement_cc", 16 * math.pi / 4 * P.bore ** 2 * P.stroke / 1000.0, "cm3", "CALC", "total swept volume")
    P.add("v_clear_cc", P.disp_cyl_cc / (P.compression_ratio - 1.0), "cm3", "CALC", "clearance volume per cylinder for CR 9.0")


def pin_x(k):
    return (k - 4.5) * P.cyl_pitch


def main_x(j):
    return (j - 5) * P.cyl_pitch


def _build():
    g = 0.5 * P.vr_angle
    fo = P.firing_order
    fire = {c: 720.0 / 16 * i for i, c in enumerate(fo)}
    cyls = []
    for k in range(1, 9):
        for bank in (1, 2):
            no = k if bank == 1 else k + 8
            outer = (k % 2 == 1) if bank == 1 else (k % 2 == 0)
            rho = 1.0 if outer else -1.0
            s_out = 1.0 if bank == 1 else -1.0
            beta = bank_beta(bank)
            theta = beta + rho * s_out * g
            n_out = s_out * np.array([math.cos(beta * D2R), -math.sin(beta * D2R)])
            q = rho * P.row_offset * n_out
            x = pin_x(k) + (-0.5 if bank == 1 else 0.5) * P.bank_offset
            cyls.append(Cyl(no, bank, "outer" if outer else "inner", k, x, theta, (float(q[0]), float(q[1])), fire[no]))
    cyls.sort(key=lambda c: c.no)
    return cyls


CYLS = _build()
CYL = {c.no: c for c in CYLS}


def tdc_phi(c: Cyl):
    """Crankpin angle phi at which the piston of cylinder c is at TDC."""
    p = np.array(c.q) + P.s_tdc * c.d
    return math.degrees(math.atan2(p[0], p[1]))


def _pin_phases():
    psi = {}
    err = 0.0
    for c in CYLS:
        val = (tdc_phi(c) + c.fire) % 360.0
        if c.pin in psi:
            d = (val - psi[c.pin] + 180.0) % 360.0 - 180.0
            err = max(err, abs(d))
        else:
            psi[c.pin] = val
    return psi, err


PIN_PHASE, PIN_PHASE_ERR = _pin_phases()   # deg; error = mismatch between the two cylinders sharing a pin


def pin_pos(k, alpha_deg):
    """(y, z) of crankpin k at crank angle alpha."""
    return P.throw * vec(PIN_PHASE[k] - np.asarray(alpha_deg))


def piston_s(c: Cyl, alpha_deg):
    """Piston-pin coordinate s along the cylinder axis (from the axis foot point q)."""
    w = pin_pos(c.pin, alpha_deg) - np.array(c.q)
    wd = w @ c.d
    return wd + np.sqrt(P.rod_length ** 2 - (w * w).sum(-1) + wd ** 2)


def piston_pin_pos(c: Cyl, alpha_deg):
    s = piston_s(c, alpha_deg)
    return np.array(c.q) + np.multiply.outer(s, c.d)


def rod_angle(c: Cyl, alpha_deg):
    """Angle between rod and cylinder axis (deg, signed)."""
    pp = piston_pin_pos(c, alpha_deg)
    cp = pin_pos(c.pin, alpha_deg)
    r = pp - cp
    n = np.array([c.d[1], -c.d[0]])
    return np.degrees(np.arctan2(r @ n, r @ c.d))


def piston_x_from_tdc(c: Cyl, alpha_deg):
    return P.s_tdc - piston_s(c, alpha_deg)


def cyl_volume_cc(c: Cyl, alpha_deg):
    return P.v_clear_cc + math.pi / 4 * P.bore ** 2 * piston_x_from_tdc(c, alpha_deg) / 1000.0


# ------------------------------------------------------------------ derived block / deck geometry
def _derived():
    g = 0.5 * P.vr_angle * D2R
    # v-coordinate (along bank centre line) of a point at distance s on a row axis:
    #   v = -e*sin(g)*cos(g)... derive directly from vectors to stay exact
    c = CYL[1]
    ex, eu, ev = bank_axes(1)
    q3 = c.q3 - np.array([c.x, 0, 0])
    v_of_s = lambda s: float((q3 + s * c.d3) @ ev)
    u_of_s = lambda s: float((q3 + s * c.d3) @ eu)
    v_crown = v_of_s(P.s_tdc + P.comp_height)
    # the crown plane may be tilted towards the chamber roof (see valvetrain.finalize_geometry): the deck
    # clearance is defined at the LOW edge of the crown, the compression height on the piston axis.
    deck = v_crown + P.deck_clearance - getattr(P, "crown_rise_axis", 0.0)
    s_deck = (deck - v_of_s(0.0)) / math.cos(g)
    u_deck = abs(u_of_s(s_deck))
    return deck, s_deck, u_deck, v_of_s, u_of_s


_deck, _s_deck, _u_deck, v_of_s, u_of_s = _derived()


def set_deck():
    """(Re)compute everything that depends on the deck height.  Called again after the crown tilt is known."""
    global _deck, _s_deck, _u_deck
    _deck, _s_deck, _u_deck = _derived()[:3]
    P.add("deck_height", _deck, "mm", "CALC", "block deck plane height along the bank centre line from the crank axis")
    P.add("s_deck", _s_deck, "mm", "CALC", "axis coordinate s where a row axis pierces the deck")
    P.add("u_bore_deck", _u_deck, "mm", "CALC", "lateral distance of a bore centre from the bank centre plane at the deck")
    # bore foot: bottom of the machined bore.  The skirt may protrude slightly at BDC.
    s_skirt_bdc = P.s_bdc + P.comp_height - P.piston_height
    P.add("s_bore_foot", s_skirt_bdc + 8.0, "mm", "CALC", "bore foot; skirt protrudes 8 mm (EST) below it at BDC")
    u_foot = abs(u_of_s(P.s_bore_foot))
    cc_foot = math.hypot(P.cyl_pitch, 2 * u_foot)
    cc_deck = math.hypot(P.cyl_pitch, 2 * _u_deck)
    P.add("web_bore_foot", cc_foot - P.bore, "mm", "CALC", "solid web between adjacent zig-zag bores at the bore foot")
    P.add("web_bore_deck", cc_deck - P.bore, "mm", "CALC", "solid web between adjacent zig-zag bores at the deck")
    P.add("bore_length", P.s_deck - P.s_bore_foot, "mm", "CALC", "machined bore length on the axis")
    P.add("head_face_height", P.deck_height + P.gasket_thk, "mm", "CALC", "cylinder-head joint face height (v)")
    # the row axes lean outwards by vr_angle / 2, so at the head joint face (one gasket thickness above the deck) the bore
    # centre lies further out than at the deck; the head chamber and the valve layout are centred on this point (D-039)
    s_head = (P.head_face_height - v_of_s(0.0)) / math.cos(0.5 * P.vr_angle * D2R)
    P.add("u_bore_head", abs(u_of_s(s_head)), "mm", "CALC", "lateral distance of a bore centre from the bank centre plane at the head joint face")


set_deck()


def bore_centre_local(c: Cyl, v=None):
    """Bore centre in bank-local coordinates (x_l, u, v) at height v (default: deck)."""
    v = P.deck_height if v is None else v
    g = 0.5 * P.vr_angle * D2R
    s = (v - v_of_s(0.0)) / math.cos(g)
    u = abs(u_of_s(s)) * (1.0 if c.row == "outer" else -1.0)
    xl = c.x if c.bank == 1 else -c.x
    return np.array([xl, u, v])


def firing_check():
    """Numerically locate every piston's TDC and return the sorted firing intervals (deg)."""
    al = np.linspace(-45.0, 765.0, 81001)
    t = []
    for c in CYLS:
        s = piston_s(c, al)
        # firing TDC = the TDC nearest to the nominal firing angle
        idx = np.where((s[1:-1] >= s[:-2]) & (s[1:-1] > s[2:]))[0] + 1
        cand = al[idx]
        dif = np.abs((cand - c.fire + 360.0) % 720.0 - 360.0)
        t.append(cand[np.argmin(dif)] % 720.0)
    t = np.sort(np.array(t))
    return np.diff(np.concatenate([t, [t[0] + 720.0]]))


def summary():
    lines = []
    lines.append(f"throw r = {P.throw:.4f} mm (stroke/2 = {P.stroke/2:.3f}); rod ratio = {P.throw/P.rod_length:.4f}")
    lines.append(f"displacement = {P.displacement_cc:.2f} cm3 (reference {P.displacement_ref_cc})")
    lines.append(f"deck height = {P.deck_height:.3f} mm; bore centre at deck u = +/-{P.u_bore_deck:.3f} mm")
    lines.append(f"bore foot s = {P.s_bore_foot:.2f}; web at foot = {P.web_bore_foot:.2f} mm; web at deck = {P.web_bore_deck:.2f} mm")
    lines.append(f"pin phase mismatch between paired cylinders = {PIN_PHASE_ERR:.2e} deg")
    lines.append("crankpin phases psi_k (deg): " + ", ".join(f"{k}:{PIN_PHASE[k]:.3f}" for k in range(1, 9)))
    fi = firing_check()
    lines.append(f"firing intervals: min {fi.min():.3f}, max {fi.max():.3f} deg")
    return "\n".join(lines)


from .analysis import valvetrain as _vt        # noqa: E402  (needs the names above)
_vt.finalize_geometry()


if __name__ == "__main__":
    print(summary())
    for c in CYLS:
        print(c.no, c.bank, c.row, c.pin, round(c.x, 2), c.theta, round(tdc_phi(c), 3), c.fire)
