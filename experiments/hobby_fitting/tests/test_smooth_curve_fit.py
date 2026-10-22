import itertools
import math
import struct
import unittest
from fractions import Fraction

import numpy as np

from experiments.hobby_fitting import curve_contacts as kc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting.real_outline import parse_commands


def _mv(p):
    return {"op": "move_to", "x": p[0], "y": p[1]}


def _qu(c, p):
    return {"op": "quad_to", "x1": c[0], "y1": c[1], "x": p[0], "y": p[1]}


def _ln(p):
    return {"op": "line_to", "x": p[0], "y": p[1]}


def _bits(cmds):
    for c in cmds:
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in c:
                c[key + "_bits"] = struct.unpack(">I", struct.pack(">f", c[key]))[0]
    return cmds


def arch():
    """Closed arch: opposing horizontal quads, vertical crown contacts."""
    cmds = [_mv((0.0, 2.0)), _qu((2.0, 3.0), (4.0, 2.0)), _ln((4.0, 0.0)),
            _qu((2.0, -1.0), (0.0, 0.0)), {"op": "close"}]
    return _bits(cmds)


def lens():
    """Closed diagonal lens: opposing slanted quads, diagonal contacts."""
    a0, ca, a1 = (0.0, 0.0), (0.5, 1.0), (2.0, 2.0)
    b0 = (a1[0] + 1.5, a1[1])
    cb = (ca[0] + 1.5, ca[1])
    b1 = (a0[0] + 1.5, a0[1])
    return _bits([_mv(a0), _qu(ca, a1), _ln(b0), _qu(cb, b1), {"op": "close"}])


def kinked():
    """Bar with one kinked joint: top line meets the right side at an angle."""
    cmds = [_mv((0.0, 2.0)), _qu((2.0, 3.0), (4.0, 2.0)), _ln((5.0, 0.5)),
            _qu((2.0, -1.0), (0.0, 0.0)), {"op": "close"}]
    return _bits(cmds)


def closed_lens():
    """Closed diagonal loop; last endpoint aliases the start coordinates."""
    return _bits([_mv((0.0, 0.0)), _qu((1.0, 1.0), (2.0, 0.0)),
                  _qu((1.0, -1.0), (0.0, 0.0)), {"op": "close"}])


def translated(cmds, dx, dy):
    out = []
    for c in cmds:
        d = dict(c)
        for key in ("x", "x1", "x2"):
            if key in d:
                d[key] += dx
        for key in ("y", "y1", "y2"):
            if key in d:
                d[key] += dy
        out.append(d)
    return _bits(out)


def scaled(cmds, f):
    out = []
    for c in cmds:
        d = dict(c)
        for key in ("x", "x1", "x2", "y", "y1", "y2"):
            if key in d:
                d[key] *= f
        out.append(d)
    return _bits(out)


REF = {"anchors": [{"source_width": 1.5, "fitted_width": 1.0,
                    "rel": -1.0 / 3.0, "length": 9.875,
                    "tangent": [0.0, 1.0]}],
       "size_px": 16.0}


def mk_pair(a_ctrl=(0, 4, 1), b_ctrl=(2, 5, 3), width_2r=2.0):
    return {"a_ctrl": list(a_ctrl), "b_ctrl": list(b_ctrl),
            "a_t": 0.5, "b_t": 0.5, "medial": [2.0, 1.0],
            "normal": [0.0, -1.0], "width_2r": width_2r,
            "radii": [1.0, 1.0], "approx_bound": 1e-9, "arc": 2.0,
            "shape_ctrl": [list(a_ctrl), list(b_ctrl)]}


class RecognizeTests(unittest.TestCase):

    def test_arch_crowns_recognized(self):
        pairs, diag = scf.recognize(arch())
        self.assertGreater(len(pairs), 0, diag)
        for p in pairs:
            self.assertGreater(p["width_2r"], 0)
            self.assertGreaterEqual(p["approx_bound"], 0)
            self.assertEqual(len(p["radii"]), 2)
            self.assertLessEqual(abs(p["radii"][0] - p["width_2r"] / 2),
                                 p["approx_bound"] + 1e-9)
            self.assertLessEqual(abs(p["radii"][1] - p["width_2r"] / 2),
                                 p["approx_bound"] + 1e-9)

    def test_lens_diagonal_contact_recognized(self):
        pairs, diag = scf.recognize(lens())
        diags = [p for p in pairs
                 if abs(p["normal"][0]) > 0.2 and abs(p["normal"][1]) > 0.2]
        self.assertGreater(len(diags), 0, diag)

    def test_translation_invariant_widths(self):
        p0, _ = scf.recognize(lens())
        p1, _ = scf.recognize(translated(lens(), 3.25, -1.5))
        self.assertEqual(len(p0), len(p1))
        w0 = sorted(p["width_2r"] for p in p0)
        w1 = sorted(p["width_2r"] for p in p1)
        for a, b in zip(w0, w1):
            self.assertAlmostEqual(a, b, places=9)

    def test_scale_doubles_widths(self):
        p0, _ = scf.recognize(lens())
        p1, _ = scf.recognize(scaled(lens(), 2.0))
        w0 = sorted(p["width_2r"] for p in p0)
        w1 = sorted(p["width_2r"] for p in p1)
        self.assertEqual(len(w0), len(w1))
        for a, b in zip(w0, w1):
            self.assertAlmostEqual(b, 2 * a, places=6)

    def test_multi_contour_abstains(self):
        two = [_mv((0.0, 0.0)), _ln((1.0, 0.0)), _ln((1.0, 1.0)),
               {"op": "close"},
               _mv((2.0, 2.0)), _ln((3.0, 2.0)), _ln((3.0, 3.0)),
               {"op": "close"}]
        pairs, diag = scf.recognize(_bits(two))
        self.assertEqual(pairs, [])
        self.assertIn("multi-contour-unsupported", diag["rejected"])

    def test_cubic_abstains(self):
        cmds = _bits([_mv((0.0, 0.0)),
                      {"op": "curve_to", "x1": 0.0, "y1": 1.0,
                       "x2": 1.0, "y2": 1.0, "x": 1.0, "y": 0.0},
                      {"op": "close"}])
        pairs, diag = scf.recognize(cmds)
        self.assertEqual(pairs, [])
        self.assertIn("cubic-curve-present", diag["rejected"])


class FitTests(unittest.TestCase):

    def test_lens_fit_restores_within_envelope(self):
        # Upstream carries the hinter overshoot (defect envelope); a small
        # correction back toward source delivers with continuity intact.
        import copy
        src = lens()
        pairs, _ = scf.recognize(src, size_px=16)
        self.assertGreater(len(pairs), 0)
        up = copy.deepcopy(src)
        up[2]["x"] += 0.4
        up[3]["x1"] += 0.4
        up[3]["x"] += 0.4
        ref = {"anchors": [{"source_width": 1.5, "fitted_width": 1.5 * 0.98,
                            "rel": -0.02, "length": 9.875,
                            "tangent": [0.0, 1.0]}],
               "size_px": 16.0}
        out = scf.fit(src, up, 16.0, ref, (False, False), pairs)
        self.assertTrue(out["applied"], out.get("reason"))
        w = out["widths"][0]
        self.assertLess(w["candidate"], w["upstream"])
        for r in out["continuity"]:
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["fwd_dot"], r)
            self.assertTrue(r["legs_ok"], r)

    def test_moved_quads_keep_interval_gate(self):
        # Independent check: every moved incident quad of a delivered
        # candidate keeps curvature sign and tangent orientation.
        import copy
        from experiments.hobby_fitting.real_outline import parse_commands
        src = lens()
        pairs, _ = scf.recognize(src, size_px=16)
        up = copy.deepcopy(src)
        up[2]["x"] += 0.4
        up[3]["x1"] += 0.4
        up[3]["x"] += 0.4
        ref = {"anchors": [{"source_width": 1.5, "fitted_width": 1.5 * 0.98,
                            "rel": -0.02, "length": 9.875,
                            "tangent": [0.0, 1.0]}],
               "size_px": 16.0}
        out = scf.fit(src, up, 16.0, ref, (False, False), pairs)
        self.assertTrue(out["applied"], out.get("reason"))
        parsed = parse_commands(src)
        no = len(parsed["oncurve"])
        base = np.asarray(parsed["oncurve"] + parsed["offcurve"], float)
        cand_cmds = out["candidate_commands"]
        on_pts, off_pts = [], []
        for c in cand_cmds:
            op = c.get("op")
            if op in ("move_to", "line_to"):
                on_pts.append((c["x"], c["y"]))
            elif op == "quad_to":
                off_pts.append((c["x1"], c["y1"]))
                on_pts.append((c["x"], c["y"]))
        cand = np.asarray(on_pts + off_pts, float)
        fitted = parse_commands(up)
        up_pts = np.asarray(fitted["oncurve"] + fitted["offcurve"], float)
        incident = cw._incident_curves(parsed)
        moved = [v for v in range(len(base))
                 if any(cand[v][a] != up_pts[v][a] for a in (0, 1))]
        self.assertGreater(len(moved), 0)
        for v in moved:
            for ctrl in incident.get(v, []):
                if len(ctrl) != 3:
                    continue
                ok, why = cw._quad_interval_ok(
                    [tuple(base[i]) for i in ctrl],
                    [tuple(cand[i]) for i in ctrl])
                self.assertTrue(ok, (ctrl, why))

    def test_native_y_keeps_y_bits(self):
        src = up = lens()
        out = scf.fit_glyph(src, up, 16.0, REF, (False, True))
        for before, after in zip(up, out["candidate_commands"]):
            for key in ("y", "y1"):
                if key in before:
                    self.assertEqual(before[key], after[key])

    def test_both_native_abstains(self):
        src = up = arch()
        out = scf.fit(src, up, 16.0, REF, (True, True), [mk_pair()])
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-free-controls")

    def test_no_anchors_abstains(self):
        src = up = lens()
        out = scf.fit(src, up, 16.0, {"anchors": []}, (False, False),
                      [mk_pair()])
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-reference-anchors")

    def test_closure_alias_welded_not_degenerate(self):
        # The closing-line alias shares coordinates with the start vertex;
        # it must weld instead of poisoning joints with a zero leg.
        parsed = parse_commands(closed_lens())
        pts = parsed["oncurve"] + parsed["offcurve"]
        no = len(parsed["oncurve"])
        self.assertEqual(scf._weld_map(parsed, pts), {2: 0})
        joints = scf._joints(parsed, pts, no)
        self.assertGreater(len(joints), 0)
        for j, occs in joints.items():
            for occ in occs:
                self.assertFalse(occ["degenerate"], (j, occ))

    def test_closure_weld_mismatch_abstains(self):
        # Upstream broke the weld (duplicate endpoint moved alone).
        import copy
        src = closed_lens()
        up = copy.deepcopy(src)
        up[2]["x"] += 0.5
        out = scf.fit(src, up, 16.0, REF, (False, False), [mk_pair()])
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "weld-mismatch")

    def test_closure_alias_passes_weld_gate(self):
        # Identical welds in source and upstream proceed past the gate.
        import copy
        src = closed_lens()
        up = copy.deepcopy(src)
        out = scf.fit(src, up, 16.0, REF, (False, False), [mk_pair()])
        self.assertNotEqual(out.get("reason"), "weld-mismatch")

    def test_kink_preserved_within_envelope(self):
        # The width correction keeps every kink inside its defect envelope
        # with orientation preserved; any row failing this is a blocker.
        src = up = kinked()
        pairs = [mk_pair()]
        out = scf.fit(src, up, 16.0, REF, (False, False), pairs)
        self.assertTrue(out["applied"], out.get("reason"))
        rows = [r for r in out["continuity"] if not r["smooth"]]
        self.assertGreater(len(rows), 0, out["continuity"])
        for r in rows:
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["fwd_dot"], r)
            self.assertLessEqual(r["defect"], r["allowed"])
            if abs(r["cross_up"]) > 1e-9:
                self.assertGreater(r["cross_cand"] * r["cross_up"], 0)

    def test_nearby_size_same_outcome(self):
        src = up = lens()
        small = scf.fit_glyph(src, up, 12.0, REF, (False, False))
        large = scf.fit_glyph(src, up, 16.0, REF, (False, False))
        self.assertEqual(small["applied"], large["applied"])
        if small["applied"]:
            self.assertAlmostEqual(small["diagnostics"]["bound"],
                                   large["diagnostics"]["bound"], places=9)

    def test_quant_bound_grows_with_legs(self):
        all_moved = ((True, True), (True, True), (True, True))
        tiny = scf._quant_cross_bound((0.1, 0.0), (0.0, 0.1), all_moved)
        big = scf._quant_cross_bound((2.0, 1.0), (1.0, 2.0), all_moved)
        self.assertGreaterEqual(tiny, 0.0)
        self.assertGreater(big, tiny)
        none_moved = ((False, False), (False, False), (False, False))
        self.assertEqual(
            scf._quant_cross_bound((2.0, 1.0), (1.0, 2.0), none_moved), 0.0)

    def test_quant_bound_brute_force(self):
        # Independent falsifier: exhaust the 64-corner rounding cube in
        # exact arithmetic; the analytic bound must cover the worst case.
        li, lo = (0.3, 0.2), (-0.1, 0.4)
        e = scf.ROUND_HALF
        base = li[0] * lo[1] - li[1] * lo[0]
        worst = 0.0
        for bits in itertools.product((-e, e), repeat=6):
            dxI, dyI, dxJ, dyJ, dxO, dyO = bits
            nli = (li[0] + dxJ - dxI, li[1] + dyJ - dyI)
            nlo = (lo[0] + dxO - dxJ, lo[1] + dyO - dyJ)
            worst = max(worst, abs(nli[0] * nlo[1] - nli[1] * nlo[0]
                                   - base))
        all_moved = ((True, True), (True, True), (True, True))
        bound = scf._quant_cross_bound(li, lo, all_moved)
        self.assertGreaterEqual(bound, worst)
        self.assertLess(bound, 2 * worst)

    def test_g1_row_finite_difference(self):
        # Independent residual check: central differences of the exact
        # cross function against the linearized row coefficients.
        parsed = parse_commands(lens())
        pts = parsed["oncurve"] + parsed["offcurve"]
        no = len(parsed["oncurve"])
        up = np.asarray(pts, float)
        joints = scf._joints(parsed, pts, no)
        h, checked = 1e-6, 0
        for j, occs in joints.items():
            for occ in occs:
                grow, res = scf._g1_row(
                    up, j, occ["prev"], occ["seg"], no, 16.0, occ["smooth"])
                self.assertIsNotNone(grow, res)
                row, const, _ = grow
                num = np.zeros_like(row)
                for v in range(len(pts)):
                    for axis in (0, 1):
                        d = np.zeros_like(up)
                        d[v][axis] = h
                        cp = scf._cross_of(
                            up + d, j, occ["prev"], occ["seg"], no)[0]
                        d[v][axis] = -h
                        cm = scf._cross_of(
                            up + d, j, occ["prev"], occ["seg"], no)[0]
                        num[2 * v + axis] = (cp - cm) / (2 * h)
                rn = np.linalg.norm(row)
                nn = np.linalg.norm(num)
                self.assertGreater(rn, 0.0)
                self.assertGreater(nn, 0.0)
                cosine = float(row @ num) / (rn * nn)
                self.assertGreater(cosine, 1 - 1e-9)
                checked += 1
        self.assertGreater(checked, 0)

    def test_g1_rigid_x_translation_invariant(self):
        # Native-Y rigid X translation must leave every G1 residual zero.
        parsed = parse_commands(lens())
        pts = parsed["oncurve"] + parsed["offcurve"]
        no = len(parsed["oncurve"])
        up = np.asarray(pts, float)
        joints = scf._joints(parsed, pts, no)
        for j, occs in joints.items():
            for occ in occs:
                (row, const, _), _ = scf._g1_row(
                    up, j, occ["prev"], occ["seg"], no, 16.0, occ["smooth"])
                for t in (0.25, -1.0 / 64.0):
                    delta = np.zeros(2 * len(pts))
                    delta[0::2] = t
                    self.assertLess(abs(float(row @ delta)), 1e-9)

    def test_piece_eps_analytic(self):
        # Host example: deviation peaks at t=1/2 with norm(P0-2C+P1)/4.
        piece = [(Fraction(0), Fraction(0)), (Fraction(0), Fraction(2)),
                 (Fraction(2), Fraction(0))]
        self.assertAlmostEqual(scf._piece_eps(piece), math.sqrt(5) / 2,
                               places=12)

    def test_quad_disk_clear_predicate(self):
        tangent = ((Fraction(1), Fraction(-1)), (Fraction(1), Fraction(0)),
                   (Fraction(1), Fraction(1)))
        self.assertTrue(kc._quad_disk_clear(
            (Fraction(0), Fraction(0)), Fraction(1), tangent))
        intrude = ((Fraction(0), Fraction(-1)), (Fraction(0), Fraction(0)),
                   (Fraction(0), Fraction(1)))
        self.assertFalse(kc._quad_disk_clear(
            (Fraction(0), Fraction(0)), Fraction(1), intrude))

    def test_scale_to_bound_diagonal(self):
        # A diagonal move peaks at its hypotenuse, not its max coordinate.
        sol = np.array([0.3, 0.4])
        out, peak = scf._scale_to_bound(sol, [(0, 0), (0, 1)], 0.25)
        self.assertAlmostEqual(peak, 0.25)
        self.assertAlmostEqual(float(np.linalg.norm(out)), 0.25)
        self.assertAlmostEqual(out[0] / out[1], 0.3 / 0.4)

    def test_malformed_abstains(self):
        bad = [{"op": "move_to", "x": 0.0, "y": 0.0}, {"op": "close"}]
        out = scf.fit_glyph(bad, bad, 16.0, REF, (False, False),
                            pairs=[mk_pair(a_ctrl=(0,), b_ctrl=(0,))])
        self.assertFalse(out["applied"])


if __name__ == "__main__":
    unittest.main()
