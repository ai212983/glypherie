import copy
import math
import os
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction

import numpy as np

from experiments.hobby_fitting import curve_contacts as kc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import exact_topology as topology
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting.real_outline import parse_commands

ROOT = Path(__file__).resolve().parents[3]
# Optional git-ignored corpus; regenerate with
# experiments/hobby_fitting/text_review.py (text-review).
CAPTURE = (ROOT / "out/diagnostics/direct-diagonal/text-review"
           / "ascii-captures/Roboto-400-16.json")
CAPTURE_REASON = (
    "missing optional capture %s (git-ignored corpus; regenerate with "
    "experiments/hobby_fitting/text_review.py)" % CAPTURE)


def topology_binary_present():
    path = os.environ.get("HOBBY_EXACT_TOPOLOGY_BINARY",
                          topology.DEFAULT_BINARY)
    return os.path.isfile(path) and os.access(path, os.X_OK)


TOPOLOGY_BINARY_REASON = (
    "missing optional exact-topology reference binary "
    "(git-ignored; build with sh "
    "experiments/hobby_fitting/exact_topology/build.sh, which needs CGAL, "
    "or set HOBBY_EXACT_TOPOLOGY_BINARY)")


def _pts(parsed):
    return parsed["oncurve"] + parsed["offcurve"]


def closed_loop():
    """Closed quad loop; last endpoint aliases the start coordinates."""
    return [
        {"op": "move_to", "x": 0.0, "y": 0.0},
        {"op": "quad_to", "x1": 1.0, "y1": 1.0, "x": 2.0, "y": 0.0},
        {"op": "quad_to", "x1": 1.0, "y1": -1.0, "x": 0.0, "y": 0.0},
        {"op": "close"},
    ]


def kinked_loop():
    """Loop with an internal zero-length line (genuine, not closure)."""
    return [
        {"op": "move_to", "x": 0.0, "y": 0.0},
        {"op": "line_to", "x": 2.0, "y": 0.0},
        {"op": "line_to", "x": 2.0, "y": 0.0},
        {"op": "line_to", "x": 2.0, "y": 2.0},
        {"op": "line_to", "x": 0.0, "y": 2.0},
        {"op": "close"},
    ]


class ClosureGeometryTests(unittest.TestCase):

    def test_alias_welds_to_start(self):
        parsed = parse_commands(closed_loop())
        pts = _pts(parsed)
        self.assertEqual(scf._weld_map(parsed, pts), {2: 0})

    def test_alias_joint_not_degenerate(self):
        parsed = parse_commands(closed_loop())
        pts = _pts(parsed)
        joints = scf._joints(parsed, pts, len(parsed["oncurve"]))
        self.assertGreater(len(joints), 0)
        for j, occs in joints.items():
            for occ in occs:
                self.assertFalse(occ["degenerate"], (j, occ))

    def test_internal_zero_length_stays_degenerate(self):
        # The old negation is preserved: a genuine internal zero-length
        # line still classifies degenerate instead of welding away.
        parsed = parse_commands(kinked_loop())
        pts = _pts(parsed)
        joints = scf._joints(parsed, pts, len(parsed["oncurve"]))
        degenerates = [j for j, occs in joints.items()
                       for occ in occs if occ["degenerate"]]
        self.assertGreater(len(degenerates), 0)


class HorizontalScopeTests(unittest.TestCase):

    def test_source_line_retains_whole_attachment_even_when_upstream_is_slanted(self):
        # Hersch section 2: retain the incident polynomial, not merely
        # the straight endpoint, irrespective of upstream orientation.
        source = closed_loop()
        source.insert(1, {"op": "line_to", "x": 0.0, "y": 2.0})
        upstream = copy.deepcopy(source)
        upstream[1]["x"] = 0.25
        with patch.object(scf, "fit_glyph", return_value={"applied": False}) as solve:
            result = scf.fit_horizontal_glyph(source, upstream, 16, {})
        self.assertFalse(result["applied"])
        self.assertEqual(solve.call_args.args[4], (False, True))
        self.assertEqual(set(solve.call_args.kwargs['fixed_x']), set(range(6)))

    def test_curve_only_outline_keeps_horizontal_solver(self):
        source = closed_loop()
        with patch.object(scf, "fit_glyph", return_value={"applied": False}) as solve:
            result = scf.fit_horizontal_glyph(source, source, 16, {})
        self.assertEqual(solve.call_args.args[4], (False, True))
        self.assertEqual(result["diagnostics"]["attachment_controls"], [])


class ApproximationBoundTests(unittest.TestCase):

    def test_piece_eps_matches_analytic_peak(self):
        # Q(t)-chord(t) = t(1-t)(2C-P0-P1) peaks at t=1/2.
        piece = [(Fraction(0), Fraction(0)), (Fraction(0), Fraction(2)),
                 (Fraction(2), Fraction(0))]
        self.assertAlmostEqual(scf._piece_eps(piece), math.sqrt(5) / 2,
                               places=12)

    def test_piece_eps_zero_for_straight(self):
        piece = [(Fraction(0), Fraction(0)), (Fraction(1), Fraction(0)),
                 (Fraction(2), Fraction(0))]
        self.assertEqual(scf._piece_eps(piece), 0.0)


@unittest.skipUnless(CAPTURE.is_file(), CAPTURE_REASON)
class RecognitionInvariantTests(unittest.TestCase):

    def test_s_pairs_carry_explicit_bounds(self):
        import json
        with open("out/diagnostics/direct-diagonal/text-review/"
                  "ascii-captures/Roboto-400-16.json") as h:
            case = json.load(h)[0]
        rec = {r["codepoint"]: r
               for r in case["modes"]["selective_default"]["records"]}
        pairs, diag = scf.recognize(rec[115]["source_commands"], size_px=16)
        self.assertGreater(len(pairs), 0, diag)
        self.assertGreater(diag.get("eps_global", 0.0), 0.0)
        shell = 2.0 * diag["eps_global"]
        for p in pairs:
            # Radii agreement against the certified polyline diameter,
            # recomputed here from the recorded fields (not the module).
            self.assertLessEqual(
                abs(p["radii"][0] - p["width_2r"] / 2), shell + 1e-9)
            self.assertLessEqual(
                abs(p["radii"][1] - p["width_2r"] / 2), shell + 1e-9)
            # Medial diameter is twice the certified radius, never the
            # mapped true chord: the mapping deviation stays explicit.
            self.assertGreaterEqual(p["approx_bound"], 0.0)
            self.assertGreater(p["arc"], 0.0)
            self.assertTrue(all(math.isfinite(v) for v in p["medial"]))

    def test_s_pairs_exclude_axis_only_crowns(self):
        import json
        with open("out/diagnostics/direct-diagonal/text-review/"
                  "ascii-captures/Roboto-400-16.json") as h:
            case = json.load(h)[0]
        rec = {r["codepoint"]: r
               for r in case["modes"]["selective_default"]["records"]}
        pairs, diag = scf.recognize(rec[115]["source_commands"], size_px=16)
        diags = [p for p in pairs
                 if abs(p["normal"][0]) > 0.15
                 and abs(p["normal"][1]) > 0.15]
        self.assertGreater(len(diags), 0, diag)

    def test_s_pairs_clear_upper_radius(self):
        # Full-shell third-boundary margin, re-derived from the pair
        # record against the source outline with the independent exact
        # predicate: disk(M, r_poly + shell) must clear every true
        # primitive outside the paired curves. Guards the old
        # quarter-eps under-margin from returning silently.
        import json
        with open("out/diagnostics/direct-diagonal/text-review/"
                  "ascii-captures/Roboto-400-16.json") as h:
            case = json.load(h)[0]
        rec = {r["codepoint"]: r
               for r in case["modes"]["selective_default"]["records"]}
        src = rec[115]["source_commands"]
        pairs, diag = scf.recognize(src, size_px=16)
        self.assertGreater(len(pairs), 0, diag)
        shell = 2.0 * diag["eps_global"]
        for p in pairs:
            self.assertAlmostEqual(p["approx_bound"], 2.0 * shell,
                                   places=9)
        parsed = parse_commands(src)
        pts = parsed["oncurve"] + parsed["offcurve"]
        no = len(parsed["oncurve"])
        quads, lines = [], []
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] == "quad":
                    quads.append([seg[2], no + seg[1], seg[3]])
                elif seg[0] == "line":
                    lines.append((seg[1], seg[2]))
        for p in pairs:
            own = {tuple(sorted(p["a_ctrl"])), tuple(sorted(p["b_ctrl"]))}
            mfr = (Fraction(p["medial"][0]), Fraction(p["medial"][1]))
            r2 = (Fraction(p["width_2r"]) / 2 + Fraction(shell)) ** 2
            for ctrl in quads:
                if tuple(sorted(ctrl)) in own:
                    continue
                ctrls = tuple((Fraction(pts[i][0]), Fraction(pts[i][1]))
                              for i in ctrl)
                self.assertTrue(kc._quad_disk_clear(mfr, r2, ctrls), p)
            for a, b in lines:
                fa = (Fraction(pts[a][0]), Fraction(pts[a][1]))
                fb = (Fraction(pts[b][0]), Fraction(pts[b][1]))
                self.assertTrue(kc._seg_clear(mfr, r2, fa, fb), p)


def _chain_cmds():
    def mv(p):
        return {"op": "move_to", "x": p[0], "y": p[1]}

    def qu(c, p):
        return {"op": "quad_to", "x1": c[0], "y1": c[1],
                "x": p[0], "y": p[1]}

    def ln(p):
        return {"op": "line_to", "x": p[0], "y": p[1]}

    cmds = [mv((0.0, 2.0)), qu((2.0, 3.0), (4.0, 2.0)), ln((5.0, 0.5)),
            qu((3.5, -0.25), (2.25, -0.375)), qu((1.0, -0.5), (0.0, 0.0)),
            {"op": "close"}]
    for c in cmds:
        for k in ("x", "y", "x1", "y1"):
            if k in c:
                c[k + "_bits"] = struct.unpack(">I", struct.pack(">f", c[k]))[0]
    return cmds


@unittest.skipUnless(topology_binary_present(), TOPOLOGY_BINARY_REASON)
class IncidentRegularizationTests(unittest.TestCase):

    def test_unpaired_incident_curve_regularized(self):
        # The middle quad shares a joint with the paired curve but is
        # never width-paired itself: delivery must still bound its
        # movement and keep its curvature gate.
        src = _chain_cmds()
        up = copy.deepcopy(src)
        up[1]["x"] += 0.3
        pair = {"a_ctrl": [0, 5, 1], "b_ctrl": [3, 7, 4],
                "a_t": 0.5, "b_t": 0.5, "medial": [2.0, 1.0],
                "normal": [0.0, -1.0], "width_2r": 2.0,
                "radii": [1.0, 1.0], "approx_bound": 1e-9, "arc": 2.0,
                "shape_ctrl": [[0, 5, 1], [3, 7, 4]]}
        ref = {"anchors": [{"source_width": 1.5, "fitted_width": 1.4,
                            "rel": -0.0667, "length": 9.875,
                            "tangent": [0.0, 1.0]}],
               "size_px": 16.0}
        out = scf.fit(src, up, 16.0, ref, (False, False), [pair])
        self.assertTrue(out["applied"], out.get("reason"))
        bound = out["diagnostics"]["bound"]
        parsed = parse_commands(src)
        no = len(parsed["oncurve"])
        base = np.asarray(parsed["oncurve"] + parsed["offcurve"], float)
        fitted = parse_commands(up)
        up_pts = np.asarray(fitted["oncurve"] + fitted["offcurve"], float)
        on, off = [], []
        for c in out["candidate_commands"]:
            if c["op"] in ("move_to", "line_to"):
                on.append((c["x"], c["y"]))
            elif c["op"] == "quad_to":
                off.append((c["x1"], c["y1"]))
                on.append((c["x"], c["y"]))
        cand = np.asarray(on + off, float)
        for v in (2, 6, 3):
            self.assertLessEqual(
                float(np.linalg.norm(cand[v] - up_pts[v])), bound + 1e-9)
        ok, why = cw._quad_interval_ok(
            [tuple(base[i]) for i in (2, 6, 3)],
            [tuple(cand[i]) for i in (2, 6, 3)])
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
