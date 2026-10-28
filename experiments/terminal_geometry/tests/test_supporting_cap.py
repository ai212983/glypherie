"""Synthetic and captured replay tests for supporting-cap certification.

Source: SCANTYPE Rules 5/6; FreeType ftraster.c stub test; Hersch 1993
section 7; 26.6 conversion per crates/generator/src/mono.rs. Captured
oracles: corpus.json before/after fixed FreeType scans (same frames) plus
source-controls.json source outlines; parent k-tip and R/6/9 findings.
"""

import json
import math
import os
import unittest

from experiments.terminal_geometry.supporting_cap import (
    classify_edge, eligible_caps, certified_caps, parse, quantize_contours,
    q26, clip_positive_length, pixel_square, attribute_pixel,
    convex_hull, hull_meets_square, _curve_hulls,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def cmds(points, close=True):
    out = [{"op": "move_to", "x": points[0][0], "y": points[0][1]}]
    for p in points[1:]:
        out.append({"op": "line_to", "x": p[0], "y": p[1]})
    if close:
        out.append({"op": "close"})
    return out


def xform(commands, f):
    out = []
    for c in commands:
        d = dict(c)
        for k in ("x", "x1", "x2"):
            yk = {"x": "y", "x1": "y1", "x2": "y2"}[k]
            if k in d:
                d[k], d[yk] = f(d[k], d.get(yk, 0.0))
        out.append(d)
    return out


def bar():
    return cmds([(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (0.0, 1.0)])


def load_corpus():
    with open(os.path.join(
            ROOT, "out/diagnostics/terminal-stub-correction-20261020",
            "corpus.json")) as f:
        return json.load(f)


def load_sources():
    with open(os.path.join(
            ROOT, "out/diagnostics/source-feature-work-20261020",
            "source-controls.json")) as f:
        data = json.load(f)
    idx = {}
    for ent in data:
        for r in ent["source"]["records"]:
            idx[(ent["font"], ent["size"], ent.get("weight"),
                 r["codepoint"])] = r["fitted_commands"]
    return idx


def find_entry(corpus, font, size, weight, glyph):
    for case in corpus["cases"]:
        if (case["font"], case["size"], case.get("weight")) == (font, size, weight):
            for g in case["changed"]:
                if g["glyph"] == glyph:
                    return g
    raise AssertionError("missing capture")


class ValidationTest(unittest.TestCase):
    def test_rejects_malformed(self):
        nan_cmds = [{"op": "move_to", "x": float("nan"), "y": 0.0},
                    {"op": "close"}]
        inf_cmds = [{"op": "move_to", "x": 0.0, "y": 0.0},
                    {"op": "line_to", "x": float("inf"), "y": 0.0},
                    {"op": "close"}]
        big_cmds = [{"op": "move_to", "x": 0.0, "y": 0.0},
                    {"op": "line_to", "x": 40000.0, "y": 0.0},
                    {"op": "close"}]
        unclosed = [{"op": "move_to", "x": 0.0, "y": 0.0},
                    {"op": "line_to", "x": 1.0, "y": 0.0}]
        stray = [{"op": "line_to", "x": 1.0, "y": 0.0}]
        stray_close = [{"op": "move_to", "x": 0.0, "y": 0.0},
                       {"op": "close"}, {"op": "close"}]
        unknown = [{"op": "move_to", "x": 0.0, "y": 0.0},
                   {"op": "spline_to", "x": 1.0, "y": 0.0},
                   {"op": "close"}]
        for bad in (nan_cmds, inf_cmds, big_cmds, unclosed, stray,
                    stray_close, unknown, "notalist"):
            with self.assertRaises(ValueError):
                parse(bad)

    def test_bound_documents_i64_headroom(self):
        self.assertEqual(2097152, math.floor(32768.0 * 64.0 + 0.5))
        self.assertLess(2 * (2 * 2097152) ** 2, 2 ** 63)


class QuantizationTest(unittest.TestCase):
    def test_half_rounds_up(self):
        # Source: floor(x*64+0.5) per crates/generator/src/mono.rs.
        self.assertEqual(1, q26(1.0 / 64.0))
        self.assertEqual(0, q26(0.0))
        self.assertEqual(-1, q26(-1.0 / 64.0))
        self.assertEqual(0, q26(-0.5 / 64.0))
        self.assertEqual(374, q26(5.84375))

    def test_degenerate_after_quant_abstains(self):
        outline = cmds([(0.0, 0.0), (0.007, 0.0), (0.007, 1.0), (0.0, 1.0)])
        _, caps = eligible_caps(outline)
        short = [c for c in caps
                 if abs(c["a"][0] - c["b"][0]) < 64 and c["a"][1] == c["b"][1] == 0]
        self.assertEqual([], short)

    def test_structure_mismatch_yields_no_caps(self):
        other = cmds([(0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (4.0, 1.0),
                      (0.0, 1.0)])
        _, caps, info = certified_caps(bar(), other)
        self.assertEqual([], caps)
        self.assertFalse(info["structure_match"])


class SyntheticTest(unittest.TestCase):
    def test_bar_end_eligible_with_filled_side(self):
        _, caps = eligible_caps(bar())
        ends = [c for c in caps if c["a"][0] in (0, 256) and c["b"][0] in (0, 256)]
        self.assertTrue(ends)
        for c in ends:
            self.assertIn(c["filled_side"], (1, -1))

    def test_transform_covariance(self):
        base = len(eligible_caps(bar())[1])
        for f in (lambda x, y: (x + 5.0, y - 3.0),
                  lambda x, y: (-y, x),
                  lambda x, y: (-x, -y),
                  lambda x, y: (-x, y),
                  lambda x, y: (y, -x)):
            self.assertEqual(base, len(eligible_caps(xform(bar(), f))[1]))

    def test_bridge_edge_fails_supporting(self):
        outline = cmds([(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (3.0, 3.0),
                        (3.0, 1.0), (1.0, 1.0), (1.0, 3.0), (0.0, 3.0)])
        contours, _ = parse(outline)
        hulls = [_curve_hulls(c) for c in contours]
        ei = next(ei for ei, (a, b) in enumerate(contours[0]["edges"])
                  if (a, b) == ((3.0, 1.0), (1.0, 1.0)))
        verdict, gates = classify_edge(contours, hulls, 0, ei)
        self.assertEqual("ABSTAIN", verdict)
        self.assertTrue(gates["continuation"])
        self.assertFalse(gates["supporting"])

    def test_coincident_overlap_abstains(self):
        both = bar() + cmds([(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (0.0, 1.0)])
        self.assertEqual([], eligible_caps(both)[1])

    def test_touching_contour_abstains(self):
        both = bar() + cmds([(4.0, 0.0), (6.0, 0.0), (6.0, 1.0), (4.0, 1.0)])
        _, caps = eligible_caps(both)
        touched = [c for c in caps if c["contour"] == 0 and 256 in (c["a"][0], c["b"][0])]
        self.assertEqual([], touched)

    def test_inverse_winding_hole(self):
        outer = cmds([(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)])
        hole = cmds([(4.0, 4.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0)])
        _, caps = eligible_caps(outer + hole)
        self.assertTrue([c for c in caps if c["b"] == [384, 0]])
        hole_tops = [c for c in caps if c["contour"] == 1 and c["a"][1] == c["b"][1] == 256]
        self.assertEqual([], hole_tops)

    def test_curve_adjacent_abstains(self):
        outline = ([{"op": "move_to", "x": 0.0, "y": 0.0},
                    {"op": "line_to", "x": 2.0, "y": 0.0},
                    {"op": "quad_to", "x": 4.0, "y": 0.0,
                     "x1": 3.0, "y1": 1.0},
                    {"op": "line_to", "x": 0.0, "y": 2.0},
                    {"op": "close"}])
        self.assertEqual([], eligible_caps(outline)[1])

    def test_hull_catches_curve_interior(self):
        # Source: hull contains the curve; legs alone miss the square.
        curve = tuple((q26(x), q26(y))
                      for x, y in ((0.0, 3.0), (2.0, 2.9375), (4.0, 3.0)))
        hull = convex_hull(list(curve))
        sq = ((100, 189), (156, 190))
        self.assertTrue(hull_meets_square(hull, sq))
        legs = [(curve[0], curve[1]), (curve[1], curve[2])]
        self.assertTrue(all(not clip_positive_length(a, b, sq)
                            for a, b in legs))

    def test_curve_hull_abstains_in_attribution(self):
        outline = bar() + ([{"op": "move_to", "x": 6.0, "y": -0.5},
                            {"op": "quad_to", "x": 6.0, "y": 1.5,
                             "x1": 3.5, "y1": 0.5},
                            {"op": "close"}])
        quantized, caps = eligible_caps(bar())
        tip = [c for c in caps if c["b"] == [256, 64]]
        self.assertTrue(tip)
        contours, _ = parse(outline)
        quantized = quantize_contours(contours)
        sq = ((256, 0), (320, 64))
        cap, reason = attribute_pixel(sq, tip, quantized)
        self.assertIsNone(cap)
        self.assertEqual("curve", reason)

    def test_collinear_continuation_abstains(self):
        outline = cmds([(0.0, 0.0), (2.0, 0.0), (4.0, 0.0),
                        (4.0, 1.0), (0.0, 1.0)])
        contours, _ = parse(outline)
        hulls = [_curve_hulls(c) for c in contours]
        verdict, gates = classify_edge(contours, hulls, 0, 0)
        self.assertEqual("ABSTAIN", verdict)
        self.assertFalse(gates["continuation"])

    def test_multi_cap_pixel_abstains(self):
        first = bar()
        second = xform(bar(), lambda x, y: (x + 5.0, y))
        quantized, caps = eligible_caps(first + second)
        sq = ((256, 0), (384, 64))
        cap, reason = attribute_pixel(sq, caps, quantized)
        self.assertIsNone(cap)
        self.assertEqual("multiple", reason)

    def test_nearby_other_contour_abstains(self):
        both = bar() + cmds([(2.5, -1.0), (3.0, -1.0),
                             (3.0, 2.0), (2.5, 2.0)])
        quantized, caps = eligible_caps(both)
        tip = [c for c in caps if c["contour"] == 0 and c["b"] == [256, 64]]
        self.assertTrue(tip)
        sq = ((192, 0), (256, 64))
        cap, reason = attribute_pixel(sq, [tip[0]], quantized)
        self.assertIsNone(cap)
        self.assertEqual("other-contour", reason)

    def test_zero_touch_point_abstains(self):
        tall = cmds([(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)])
        both = tall + cmds([(2.0, 1.0), (3.0, 1.0), (2.5, 2.0)])
        quantized, caps = eligible_caps(both)
        tip = [c for c in caps if c["contour"] == 0 and c["b"] == [256, 0]]
        self.assertTrue(tip)
        sq = ((128, 0), (192, 64))
        cap, reason = attribute_pixel(sq, [tip[0]], quantized)
        self.assertIsNone(cap)
        self.assertEqual("other-contour", reason)

    def test_long_border_midspan_associates(self):
        # Limitation: needs a square meeting only the cap wedge; a 1px bar
        # shares its far boundary with the square and abstains instead.
        long_bar = cmds([(0.0, 0.0), (8.0, 0.0), (8.0, 2.0), (0.0, 2.0)])
        quantized, caps = eligible_caps(long_bar)
        bottom = [c for c in caps if c["a"] == [0, 0] and c["b"] == [512, 0]]
        self.assertEqual(1, len(bottom))
        sq = ((192, 0), (256, 64))
        cap, reason = attribute_pixel(sq, bottom, quantized)
        self.assertIsNotNone(cap, reason)

    def test_long_border_with_crossing_abstains(self):
        both = cmds([(0.0, 0.0), (8.0, 0.0), (8.0, 1.0), (0.0, 1.0)]) + \
            cmds([(3.0, -1.0), (4.0, -1.0), (4.0, 2.0), (3.0, 2.0)])
        quantized, caps = eligible_caps(both)
        bottom = [c for c in caps if c["contour"] == 0 and c["b"] == [512, 0]]
        sq = ((192, 0), (256, 64))
        if bottom:
            cap, reason = attribute_pixel(sq, [bottom[0]], quantized)
            self.assertIsNone(cap)
        else:
            self.assertEqual([], bottom)

    def test_graze_point_does_not_associate(self):
        _, caps = eligible_caps(bar())
        tip = [c for c in caps if c["b"] == [256, 0]][0]
        self.assertFalse(clip_positive_length(
            tuple(tip["a"]), tuple(tip["b"]), ((256, 64), (320, 128))))


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Optional git-ignored replay corpora (see README for the owning
        # studies); synthetic ValidationTest coverage runs without them.
        missing = [os.path.join(ROOT, d, f) for d, f in (
            ("out/diagnostics/terminal-stub-correction-20261020",
             "corpus.json"),
            ("out/diagnostics/source-feature-work-20261020",
             "source-controls.json"))]
        if not all(os.path.isfile(p) for p in missing):
            raise unittest.SkipTest(
                "missing optional captures %s (git-ignored; regenerate via "
                "the owning terminal-stub-correction-20261020 and "
                "source-feature-work-20261020 studies)" % ", ".join(missing))
        cls.corpus = load_corpus()
        cls.sources = load_sources()

    def _certified(self, font, size, weight, glyph):
        g = find_entry(self.corpus, font, size, weight, glyph)
        b = g["before"]
        src = self.sources[(font, size, weight, b["codepoint"])]
        quantized, caps, info = certified_caps(src, b["fitted_commands"])
        self.assertTrue(info["structure_match"])
        return b, quantized, caps

    def test_k16_tip_removed(self):
        b, quantized, caps = self._certified("RobotoFlex", 16, 400.0, "k")
        a = find_entry(self.corpus, "RobotoFlex", 16, 400.0, "k")["after"]
        self.assertEqual(b["fitted_commands"], a["fitted_commands"])
        self.assertEqual(b["advance_26_6"], a["advance_26_6"])
        diff = [i for i in range(len(b["pixels"]))
                if b["pixels"][i] == 1 and a["pixels"][i] == 0]
        self.assertEqual([(6, 12)],
                         [(i % b["width"], i // b["width"]) for i in diff])
        sq = pixel_square(b["left"], b["top"], 6, 12)
        cap, reason = attribute_pixel(sq, caps, quantized)
        self.assertIsNotNone(cap, reason)
        self.assertEqual((7, -1), (b["left"] + 6, b["top"] + 12))

    def test_r12_bytes_preserved(self):
        b, quantized, caps = self._certified("SourceSans3", 12, 200.0, "R")
        a = find_entry(self.corpus, "SourceSans3", 12, 200.0, "R")["after"]
        diff = [i for i in range(len(b["pixels"]))
                if b["pixels"][i] == 1 and a["pixels"][i] == 0]
        self.assertTrue(diff)
        removed = []
        for idx in diff:
            sq = pixel_square(b["left"], b["top"],
                              idx % b["width"], idx // b["width"])
            cap, _ = attribute_pixel(sq, caps, quantized)
            if cap is not None:
                removed.append(idx)
        self.assertEqual([], removed)

    def test_bowls_bytes_preserved(self):
        for size, glyph in ((12, "6"), (13, "6"), (12, "9"), (15, "9")):
            b, quantized, caps = self._certified(
                "SourceSans3", size, 200.0, glyph)
            a = find_entry(self.corpus, "SourceSans3", size, 200.0,
                           glyph)["after"]
            diff = [i for i in range(len(b["pixels"]))
                    if b["pixels"][i] == 1 and a["pixels"][i] == 0]
            self.assertTrue(diff)
            removed = []
            for idx in diff:
                sq = pixel_square(b["left"], b["top"],
                                  idx % b["width"], idx // b["width"])
                cap, _ = attribute_pixel(sq, caps, quantized)
                if cap is not None:
                    removed.append(idx)
            self.assertEqual([], removed, glyph)


if __name__ == "__main__":
    unittest.main()
