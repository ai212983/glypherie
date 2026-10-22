import unittest

from experiments.hobby_fitting import curve_contacts as kc
from experiments.hobby_fitting.tests.test_curved_width import (
    REF,
    bar,
    bar_pair,
    lens,
)

REF_WIDE = {"anchors": [{"source_width": 4.0, "fitted_width": 8.0 / 3.0,
                         "rel": -1.0 / 3.0, "length": 9.875,
                         "tangent": [0.0, 1.0]}],
            "size_px": 16.0}


class CurveContactTests(unittest.TestCase):

    def test_bar_crown_pair_recognized(self):
        pairs, diag = kc.recognize(bar())
        self.assertEqual(len(pairs), 1, diag)
        p = pairs[0]
        self.assertEqual(sorted(p["a_ctrl"]), [0, 1, 4])
        self.assertEqual(sorted(p["b_ctrl"]), [2, 3, 5])
        self.assertAlmostEqual(p["medial"][0], 2.0)
        self.assertAlmostEqual(p["medial"][1], 1.0)
        width = 2 * abs(2.5 - 1.0)
        self.assertAlmostEqual(width, 3.0)

    def test_bar_fit_free_axes_rejects_kinks(self):
        # Negative control: thinning would rotate the corner join legs,
        # so the exact tangent gate refuses delivery.
        src = up = bar()
        out = kc.fit_glyph(src, up, 16.0, REF, (False, False))
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "tangent-join-changed")
        self.assertIs(out["candidate_commands"], up)

    def test_bar_fit_native_y_reports_limitation(self):
        src = up = bar()
        out = kc.fit_glyph(src, up, 16.0, REF, (False, True))
        for before, after in zip(up, out["candidate_commands"]):
            for key in ("y", "y1"):
                if key in before:
                    self.assertEqual(before[key], after[key])
        if out["applied"]:
            w = out["widths"][0]
            self.assertLess(abs(w["candidate"] - w["upstream"]), 1e-6)
            self.assertAlmostEqual(w["effectibility_x"], 0.0, places=6)

    def test_joint_extrema_pair_recognized_and_fit(self):
        cmds = [{"op": "move_to", "x": 0.0, "y": 0.0},
                {"op": "line_to", "x": 0.0, "y": 2.0},
                {"op": "quad_to", "x1": 2.0, "y1": 4.0, "x": 4.0, "y": 4.0},
                {"op": "line_to", "x": 6.0, "y": 4.0},
                {"op": "line_to", "x": 6.0, "y": -2.0},
                {"op": "quad_to", "x1": 5.0, "y1": 0.0, "x": 4.0, "y": 0.0},
                {"op": "line_to", "x": 0.0, "y": 0.0},
                {"op": "close"}]
        pairs, diag = kc.recognize(cmds)
        self.assertEqual(len(pairs), 1, diag)
        p = pairs[0]
        self.assertEqual(p["a_t"], 1.0)
        self.assertEqual(p["b_t"], 1.0)
        self.assertAlmostEqual(p["medial"][0], 4.0)
        self.assertAlmostEqual(p["medial"][1], 2.0)
        out = kc.fit_glyph(cmds, cmds, 16.0, REF_WIDE, (False, False))
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "tangent-join-changed")
        self.assertIs(out["candidate_commands"], cmds)

    def test_disk_inside_triangle_rejected(self):
        from fractions import Fraction as F
        tri = [(F(-10), F(-10)), (F(10), F(-10)), (F(0), F(10))]
        self.assertTrue(kc._tri_clear((F(0), F(0)), F(1), tri) is False)
        far = [(F(100), F(100)), (F(110), F(100)), (F(105), F(110))]
        self.assertTrue(kc._tri_clear((F(0), F(0)), F(1), far))
        deg = [(F(0), F(5)), (F(5), F(5)), (F(10), F(5))]
        self.assertTrue(kc._tri_clear((F(0), F(0)), F(1), deg))

    def test_multi_contour_abstains(self):
        two = (bar()[:-1] + [{"op": "move_to", "x": 10.0, "y": 10.0},
                             {"op": "line_to", "x": 11.0, "y": 10.0},
                             {"op": "line_to", "x": 11.0, "y": 11.0},
                             {"op": "close"}])
        pairs, diag = kc.recognize(two)
        self.assertEqual(pairs, [])
        self.assertIn("multi-contour-unsupported", diag["rejected"])

    def test_lens_diagonal_has_no_certified_pair(self):
        pairs, diag = kc.recognize(lens())
        self.assertEqual(pairs, [])
        self.assertGreaterEqual(diag["candidates"], 0)

    def test_fit_glyph_abstains_without_pairs(self):
        src = up = lens()
        out = kc.fit_glyph(src, up, 16.0, REF, (False, False))
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-certified-pairs")
        self.assertIs(out["candidate_commands"], up)

    def test_malformed_axes_fail_closed(self):
        src = up = bar()
        out = kc.fit_glyph(src, up, 16.0, REF, (0, 1))
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "malformed-native-axes")


if __name__ == "__main__":
    unittest.main()
