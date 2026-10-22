"""Runner unit tests: curve sampling, cache identity, no upstream needed."""

import importlib.util
import os
import unittest

import numpy as np

RUNNER = os.path.join(os.path.dirname(__file__), "..", "runner", "run_extract.py")


def load_runner():
    spec = importlib.util.spec_from_file_location("run_extract", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rx = load_runner()


class FlattenTests(unittest.TestCase):
    def test_quad_chain_midpoint_joint(self):
        # on, off, off, on: implied on-curve is the off midpoint.
        a, o1, o2, b = (0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (30.0, 10.0)
        typed = [(a, "line"), (o1, None), (o2, None), (b, "line")]
        out = rx.flatten_contour(typed, "quad", curve_steps=4)
        self.assertEqual(len(out), 9)
        np.testing.assert_allclose(out[0], a)
        np.testing.assert_allclose(out[-1], b)
        np.testing.assert_allclose(out[4], (15.0, 5.0))

    def test_quad_single_triple_midpoint(self):
        a, o, b = (0.0, 0.0), (10.0, 0.0), (10.0, 10.0)
        typed = [(a, "line"), (o, None), (b, "line")]
        out = rx.flatten_contour(typed, "quad", curve_steps=2)
        self.assertEqual(len(out), 3)
        # Quadratic midpoint: (a + 2o + b) / 4.
        np.testing.assert_allclose(out[1], (7.5, 2.5))

    def test_all_offcurve_wrap(self):
        o1, o2, o3 = (0.0, 0.0), (10.0, 0.0), (10.0, 10.0)
        typed = [(o1, None), (o2, None), (o3, None)]
        out = rx.flatten_contour(typed, "quad", curve_steps=2)
        wrap = ((o3[0] + o1[0]) / 2.0, (o3[1] + o1[1]) / 2.0)
        np.testing.assert_allclose(out[0], wrap)
        np.testing.assert_allclose(out[-1], wrap)

    def test_cubic_midpoint(self):
        a, c1, c2, b = (0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (30.0, 10.0)
        typed = [(a, "line"), (c1, None), (c2, None), (b, "curve")]
        out = rx.flatten_contour(typed, "cubic", curve_steps=2)
        self.assertEqual(len(out), 3)
        np.testing.assert_allclose(
            out[1],
            ((a[0] + 3 * c1[0] + 3 * c2[0] + b[0]) / 8.0,
             (a[1] + 3 * c1[1] + 3 * c2[1] + b[1]) / 8.0),
        )

    def test_cubic_bad_run_raises(self):
        typed = [((0.0, 0.0), "line"), ((5.0, 0.0), None), ((9.0, 1.0), "line")]
        with self.assertRaises(ValueError):
            rx.flatten_contour(typed, "cubic", curve_steps=2)

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            rx.flatten_contour([], "quad")
        with self.assertRaises(ValueError):
            rx.flatten_contour([((0.0, 0.0), "line")], "quad")
        with self.assertRaises(ValueError):
            rx.flatten_contour([((float("nan"), 0.0), "line")], "quad")
        with self.assertRaises(ValueError):
            rx.flatten_contour([((0.0, 0.0), "line")], "other")


class GlyphControlTests(unittest.TestCase):
    """Actual glyf controls: flattening must reproduce the source outline."""

    def test_roboto_y_flatten_matches_glyf(self):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools unavailable")
        root = os.path.dirname(__file__)
        path = os.path.normpath(os.path.join(root, "..", "..", "..", "fonts"))
        roboto = os.path.join(path, "Roboto.ttf")
        if not os.path.exists(roboto):
            self.skipTest("Roboto.ttf not in checkout")
        font = TTFont(roboto, recalcTimestamp=False)
        glyf = font["glyf"]
        name = font.getBestCmap()[ord("y")]
        glyph = glyf[name]
        glyph.expand(glyf)
        typed = rx.collect_glyph_points(font, "y")
        # Contour count matches the expanded glyf outline.
        self.assertEqual(len(typed), len(glyph.getCoordinates(glyf)[1]))
        flat = [rx.flatten_contour(c, "quad", curve_steps=12) for c in typed]
        xs = np.concatenate([c[:, 0] for c in flat])
        ys = np.concatenate([c[:, 1] for c in flat])
        # Subdivision stays inside the control hull: no invented excursion.
        self.assertGreaterEqual(xs.min(), glyph.xMin)
        self.assertLessEqual(xs.max(), glyph.xMax)
        self.assertGreaterEqual(ys.min(), glyph.yMin)
        self.assertLessEqual(ys.max(), glyph.yMax)
        # Every typed on-curve point survives exactly in the polyline.
        for contour, poly in zip(typed, flat):
            for (p, t) in contour:
                if t is not None:
                    self.assertTrue(
                        np.any(
                            np.all(np.isclose(poly, p, atol=1e-9), axis=1)
                        ),
                        "lost on-curve %r" % (p,),
                    )


if __name__ == "__main__":
    unittest.main()
