"""Analytic topology contract for the exact filled-join reference.

Binds the public `exact_topology` API to hand-known answers only: CGAL
arrangements classify filled faces by nonzero winding of the original
directed contours, so internal seams may move while attachments, holes and
contacts must not. No glyph outlines, no pixel counts, no resampling.
"""

import math
import os
import unittest

from experiments.hobby_fitting import exact_topology
from experiments.hobby_fitting.exact_topology import DEFAULT_BINARY


def binary_path():
    path = os.environ.get("HOBBY_EXACT_TOPOLOGY_BINARY", DEFAULT_BINARY)
    assert os.path.isfile(path) and os.access(path, os.X_OK), (
        "exact topology binary missing: %s "
        "(build the helper or set HOBBY_EXACT_TOPOLOGY_BINARY)" % path
    )
    return path


def rotate_contour(contour, start):
    """Rotate contour start; move stays first, close stays last."""
    pts = [(c["x"], c["y"]) for c in contour if c["op"] in ("move_to", "line_to")]
    order = pts[start % len(pts):] + pts[:start % len(pts)]
    return [{"op": "move_to", "x": order[0][0], "y": order[0][1]}] + [
        {"op": "line_to", "x": x, "y": y} for x, y in order[1:]
    ] + [{"op": "close"}]


def rect(x0, y0, x1, y1, cw=False):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if cw:
        pts = [pts[0]] + pts[:0:-1]
    return [{"op": "move_to", "x": pts[0][0], "y": pts[0][1]}] + [
        {"op": "line_to", "x": x, "y": y} for x, y in pts[1:]
    ] + [{"op": "close"}]


def shift(commands, dx, dy=0.0):
    out = []
    for cmd in commands:
        cmd = dict(cmd)
        if "x" in cmd:
            cmd["x"] = cmd["x"] + dx
            cmd["y"] = cmd["y"] + dy
        out.append(cmd)
    return out


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = binary_path()

    def analyze(self, commands):
        result = exact_topology.analyze_commands(commands, binary=self.binary)
        for key in ("supported", "reason", "signature", "details"):
            self.assertIn(key, result)
        return result

    def compare(self, source, upstream, candidate):
        result = exact_topology.compare_commands(
            source, upstream, candidate, binary=self.binary
        )
        for key in ("supported", "ok", "reason", "source", "upstream",
                    "candidate", "source_upstream_match"):
            self.assertIn(key, result)
        return result

    def test_overlap_internal_seam_may_move(self):
        # Union [0,0]x[6,4] with internal borders shifted: the seam moves
        # but the union and its area contacts are unchanged.
        source = rect(0, 0, 4, 4) + rect(2, 0, 6, 4)
        shifted = rect(0, 0, 3.5, 4) + rect(2.5, 0, 6, 4)
        result = self.compare(source, source, shifted)
        self.assertTrue(result["supported"], result["reason"])
        self.assertTrue(result["ok"], result["reason"])

    def test_hole_preserved_under_rotation(self):
        outer = rect(0, 0, 8, 8)
        hole = rect(2, 2, 6, 6, cw=True)
        result = self.compare(outer + hole, outer + hole,
                              outer + rotate_contour(hole, 2))
        self.assertTrue(result["supported"], result["reason"])
        self.assertTrue(result["ok"], result["reason"])

    def test_detached_stroke_fails(self):
        stem = rect(0, 0, 2, 8)
        arm = rect(2, 4, 6, 6)
        bad = rect(2.5, 4, 6.5, 6)
        result = self.compare(stem + arm, stem + arm, stem + bad)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"])

    def test_opened_counter_fails(self):
        outer = rect(0, 0, 8, 8)
        hole = rect(2, 2, 6, 6, cw=True)
        filled = self.compare(outer + hole, outer + hole, outer)
        self.assertTrue(filled["supported"], filled["reason"])
        self.assertFalse(filled["ok"])
        punched = self.compare(outer, outer, outer + hole)
        self.assertTrue(punched["supported"], punched["reason"])
        self.assertFalse(punched["ok"])

    def test_point_contact_lost_or_filled_fails(self):
        a = rect(0, 0, 2, 2)
        b = rect(2, 2, 4, 4)
        gap = self.compare(a + b, a + b, rect(0, 0, 2, 2) + rect(2.5, 2.5, 4.5, 4.5))
        self.assertTrue(gap["supported"], gap["reason"])
        self.assertFalse(gap["ok"])
        filled = self.compare(a + b, a + b, rect(0, 0, 4, 4))
        self.assertTrue(filled["supported"], filled["reason"])
        self.assertFalse(filled["ok"])

    def test_edge_contact_separated_or_filled_fails(self):
        a = rect(0, 0, 2, 2)
        b = rect(2, 0, 4, 2)
        gap = self.compare(a + b, a + b, rect(0, 0, 2, 2) + rect(2.5, 0, 4.5, 2))
        self.assertTrue(gap["supported"], gap["reason"])
        self.assertFalse(gap["ok"])
        area = self.compare(a + b, a + b, rect(0, 0, 2, 2) + rect(1.5, 0, 3.5, 2))
        self.assertTrue(area["supported"], area["reason"])
        self.assertFalse(area["ok"])

    def test_cancelling_pair_reports_difference(self):
        square = rect(0, 0, 4, 4)
        cancelled = rect(0, 0, 4, 4) + rect(0, 0, 4, 4, cw=True)
        result = self.compare(square, square, cancelled)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["ok"])
        result = self.compare(cancelled, cancelled, square)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["ok"])

    def test_subpixel_gap_distinguished(self):
        gap = 2.0 ** -30
        a = rect(0, 0, 2, 2)
        b = rect(2, 0, 4, 2)
        split = self.compare(a + b, a + b, rect(0, 0, 2, 2) + rect(2 + gap, 0, 4 + gap, 2))
        self.assertTrue(split["supported"], split["reason"])
        self.assertFalse(split["ok"])
        # Off-grid native coordinates attach exactly: no snapping allowed.
        off = 0.1
        kept = self.compare(
            rect(off, 0, 2 + off, 2) + rect(2 + off, 0, 4 + off, 2),
            rect(off, 0, 2 + off, 2) + rect(2 + off, 0, 4 + off, 2),
            rect(off, 0, 2 + off, 2) + rect(2 + off, 0, 4 + off, 2),
        )
        self.assertTrue(kept["supported"], kept["reason"])
        self.assertTrue(kept["ok"], kept["reason"])

    def test_transforms_and_reorder_consistent(self):
        base = rect(0, 0, 4, 4) + rect(2, 0, 6, 4)
        merged = rect(0, 0, 6, 4)
        expected = self.compare(base, base, merged)
        moved = self.compare(
            shift(base, 3, -2), shift(base, 3, -2), shift(merged, 3, -2))
        self.assertEqual(moved["supported"], expected["supported"])
        self.assertEqual(moved["ok"], expected["ok"])
        mirrored = [
            {**c, **({"x": -c["x"]} if "x" in c else {})} for c in base
        ]
        mirrored_merged = [
            {**c, **({"x": -c["x"]} if "x" in c else {})} for c in merged
        ]
        flipped = self.compare(mirrored, mirrored, mirrored_merged)
        self.assertEqual(flipped["ok"], expected["ok"])
        reordered = base[len(base) // 2:] + base[:len(base) // 2]
        reordered_merged = merged
        self.assertEqual(
            self.compare(reordered, reordered, reordered_merged)["ok"],
            expected["ok"])

    def test_curves_unsupported_closed(self):
        curved = [
            {"op": "move_to", "x": 0.0, "y": 0.0},
            {"op": "quad_to", "x1": 1.0, "y1": 2.0, "x": 2.0, "y": 0.0},
            {"op": "close"},
        ]
        result = self.analyze(curved)
        self.assertFalse(result["supported"])
        self.assertTrue(result["reason"])
        result = self.compare(curved, curved, curved)
        self.assertFalse(result["supported"])
        self.assertTrue(result["reason"])

    def test_source_upstream_discrepancy_explicit(self):
        outer = rect(0, 0, 8, 8)
        hole = rect(2, 2, 6, 6, cw=True)
        result = self.compare(outer + hole, outer, outer)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["source_upstream_match"])
        clean = self.compare(outer, outer, outer)
        self.assertTrue(clean["supported"], clean["reason"])
        self.assertTrue(clean["source_upstream_match"])

    def test_segmentation_churn_passes(self):
        # Same boundary under rotated starts and reordered contours.
        # Hand-known same fill, no production outlines.
        a = rect(0, 0, 4, 4)
        b = rect(5, 0, 9, 4)
        source = a + b
        for candidate in (rotate_contour(a, 1) + b, b + a):
            result = self.compare(source, source, candidate)
            self.assertTrue(result["supported"], result["reason"])
            self.assertTrue(result["ok"], result["reason"])

    def test_area_to_point_with_bridge_fails(self):
        # Pair attachment drops area contact to a point while a third
        # bridge contour keeps the global component count at one.
        a = rect(0, 0, 4, 4)
        b = rect(4, 0, 8, 4)
        bridge = rect(0, 4, 8, 8)
        point = rect(4, 4, 8, 8)
        result = self.compare(a + b + bridge, a + b + bridge, a + point + bridge)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"])

    def test_pair_overlap_count_with_bridge_fails(self):
        # One contour pair overlaps in two components; losing one must fail
        # even though a bridge keeps every global count unchanged.
        bar = rect(0, 4, 10, 6)
        comb = [
            {"op": "move_to", "x": 2.0, "y": 0.0},
            {"op": "line_to", "x": 8.0, "y": 0.0},
            {"op": "line_to", "x": 8.0, "y": 10.0},
            {"op": "line_to", "x": 6.0, "y": 10.0},
            {"op": "line_to", "x": 6.0, "y": 2.0},
            {"op": "line_to", "x": 4.0, "y": 2.0},
            {"op": "line_to", "x": 4.0, "y": 10.0},
            {"op": "line_to", "x": 2.0, "y": 10.0},
            {"op": "close"},
        ]
        bridge = rect(0, 8, 10, 12)
        short = rect(0, 4, 5, 6)
        result = self.compare(bar + comb + bridge, bar + comb + bridge,
                              short + comb + bridge)
        self.assertTrue(result["supported"], result["reason"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"])


if __name__ == "__main__":
    unittest.main()
