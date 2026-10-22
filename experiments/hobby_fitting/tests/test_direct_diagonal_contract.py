"""Geometric contract for the direct-diagonal core (independent of the fitter).

These tests bind the public API only (`build_reference`, `fit_glyph`) to
source-backed analytical expectations: Hersch parallelization with the axis
target converted from normal width as w_perp / |normal[axis]|, integer grid
selection that must not read the glyph name, exact native-axis freezing, and
exact-fallback abstention. All shapes are constructed here with known answers;
no bitmap counts are asserted.
"""

import math
import unittest

from experiments.hobby_fitting import direct_diagonal as core

SQRT2 = math.sqrt(2)
# 26.6 rounding reserve propagated through a 45-degree normal projection:
# each rail vertex quantizes by at most half a quantum (1/128), and the
# normal component scales by 1/|n_x| = sqrt(2).
RESERVE = SQRT2 / 64.0

DONOR_SOURCE = [
    {"op": "move_to", "x": 20.0, "y": 0.0},
    {"op": "line_to", "x": 21.8, "y": 0.0},
    {"op": "line_to", "x": 21.8, "y": 12.0},
    {"op": "line_to", "x": 20.0, "y": 12.0},
    {"op": "close"},
]
DONOR_FITTED = [
    {"op": "move_to", "x": 20.0, "y": 0.0},
    {"op": "line_to", "x": 22.0, "y": 0.0},
    {"op": "line_to", "x": 22.0, "y": 12.0},
    {"op": "line_to", "x": 20.0, "y": 12.0},
    {"op": "close"},
]

W13 = 1.3 / SQRT2
DIAG_SOURCE = [
    {"op": "move_to", "x": 2.0, "y": 0.0},
    {"op": "line_to", "x": 10.0, "y": 8.0},
    {"op": "line_to", "x": 10.0 - W13, "y": 8.0 + W13},
    {"op": "line_to", "x": 2.0 - W13, "y": W13},
    {"op": "close"},
]


def donor_record(codepoint=73, label="donor"):
    return {
        "codepoint": codepoint,
        "label": label,
        "source_commands": DONOR_SOURCE,
        "fitted_commands": DONOR_FITTED,
    }


def diag_record(codepoint=75, label="diag"):
    return {
        "codepoint": codepoint,
        "label": label,
        "source_commands": DIAG_SOURCE,
        "fitted_commands": [dict(c) for c in DIAG_SOURCE],
    }


def coords(commands):
    return [(c.get("x"), c.get("y")) for c in commands if "x" in c]


def rail_widths(commands):
    """Perpendicular distances of rail-B vertices from rail-A (vertex order)."""
    pts = [c for c in commands if "x" in c]
    (ax, ay), (bx, by) = (pts[0]["x"], pts[0]["y"]), (pts[1]["x"], pts[1]["y"])
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    out = []
    for p in pts[2:4]:
        out.append(abs(dy * p["x"] - dx * p["y"] + bx * ay - by * ax) / norm)
    return out


def signed_area(commands):
    pts = [(c["x"], c["y"]) for c in commands if "x" in c]
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2.0


def fit_diag(**kwargs):
    params = {
        "source": DIAG_SOURCE,
        "fitted": [dict(c) for c in DIAG_SOURCE],
        "size": 16,
        "native_axes": (False, True),
        "grid": True,
    }
    params.update(kwargs)
    reference = core.build_reference([donor_record()], params.pop("ref_size", 16))
    return core.fit_glyph(
        params["source"], params["fitted"], params["size"], reference,
        params["native_axes"], params["grid"],
    )


class AxisTargetTests(unittest.TestCase):
    def test_grid_selects_integer_axis(self):
        # Anchor ratio 2/1.8 scales desired normal 1.3 to 1.4444; the axis
        # target 1.4444/|n_x| = 2.0428 rounds to integer 2, i.e. normal 2/sqrt(2).
        result = fit_diag()
        self.assertTrue(result["applied"], result.get("reason"))
        cand = result["candidate_commands"]
        self.assertEqual([c["op"] for c in cand], [c["op"] for c in DIAG_SOURCE])
        for got, want in zip(coords(cand), coords(DIAG_SOURCE)):
            self.assertEqual(got[1], want[1])
            # DStroke controls line separation, not absolute endpoint X.
            # Moved coordinates retain the scanner's 26.6 precision.
            self.assertAlmostEqual(got[0] * 64, round(got[0] * 64), places=9)
        widths = rail_widths(cand)
        for w in widths:
            self.assertAlmostEqual(w, SQRT2, delta=RESERVE)
        self.assertLessEqual(abs(widths[0] - widths[1]), RESERVE)

    def test_width_only_approaches_target(self):
        result = fit_diag(grid=False)
        self.assertTrue(result["applied"], result.get("reason"))
        widths = rail_widths(result["candidate_commands"])
        for w in widths:
            self.assertGreater(w, 1.3)
            self.assertLess(w, 1.445 + RESERVE)


class TransformTests(unittest.TestCase):
    def base_candidate(self):
        return fit_diag()["candidate_commands"]

    def test_integer_translation_exact(self):
        base = self.base_candidate()
        shifted = [{**c, **({"x": c["x"] + 7.0, "y": c["y"] + 3.0} if "x" in c else {})}
                   for c in DIAG_SOURCE]
        result = fit_diag(source=shifted, fitted=[dict(c) for c in shifted])
        self.assertTrue(result["applied"], result.get("reason"))
        for got, want in zip(coords(result["candidate_commands"]), coords(base)):
            self.assertEqual(got, (want[0] + 7.0, want[1] + 3.0))

    def test_reflection_preserves_normal(self):
        base_widths = rail_widths(self.base_candidate())
        mirrored = [{**c, **({"x": -c["x"]} if "x" in c else {})} for c in DIAG_SOURCE]
        result = fit_diag(source=mirrored, fitted=[dict(c) for c in mirrored])
        self.assertTrue(result["applied"], result.get("reason"))
        for got, want in zip(rail_widths(result["candidate_commands"]), base_widths):
            self.assertAlmostEqual(got, want, delta=RESERVE)


class AbstentionTests(unittest.TestCase):
    def test_both_native_abstains_exact(self):
        result = fit_diag(native_axes=(True, True))
        self.assertFalse(result["applied"])
        self.assertTrue(result.get("reason"))
        self.assertEqual(result["candidate_commands"], DIAG_SOURCE)

    def test_crossing_strips_safe(self):
        strip_b = [
            {"op": "move_to", "x": 10.0, "y": 0.0},
            {"op": "line_to", "x": 2.0, "y": 8.0},
            {"op": "line_to", "x": 2.0 + W13, "y": 8.0 + W13},
            {"op": "line_to", "x": 10.0 + W13, "y": W13},
            {"op": "close"},
        ]
        source = DIAG_SOURCE + strip_b
        fitted = [dict(c) for c in source]
        result = fit_diag(source=source, fitted=fitted)
        if result["applied"]:
            self.assertTrue(result.get("validity"))
            self.assertLessEqual(result["movement"], result["bound"])
            for got, want in zip(coords(result["candidate_commands"]), coords(source)):
                self.assertEqual(got[1], want[1])
            areas_src = [signed_area(source[:5]), signed_area(source[5:])]
            areas_got = [signed_area(result["candidate_commands"][:5]),
                         signed_area(result["candidate_commands"][5:])]
            for a, b in zip(areas_src, areas_got):
                self.assertEqual(math.copysign(1.0, a), math.copysign(1.0, b))
        else:
            self.assertTrue(result.get("reason"))
            self.assertEqual(result["candidate_commands"], fitted)

    def test_small_taper_contract(self):
        # Slightly tapered pure-straight quad: feasibility is the model's
        # call, but either branch must honor the contract exactly.
        taper = [
            {"op": "move_to", "x": 2.0, "y": 0.0},
            {"op": "line_to", "x": 10.0, "y": 8.0},
            {"op": "line_to", "x": 10.0 - W13, "y": 8.0 + W13},
            {"op": "line_to", "x": 2.0 - W13 + 0.1, "y": W13},
            {"op": "close"},
        ]
        result = fit_diag(source=taper, fitted=[dict(c) for c in taper])
        if result["applied"]:
            self.assertTrue(result.get("validity"))
            self.assertLessEqual(result["movement"], result["bound"])
            for got, want in zip(coords(result["candidate_commands"]), coords(taper)):
                self.assertEqual(got[1], want[1])
        else:
            self.assertTrue(result.get("reason"))
            self.assertEqual(result["candidate_commands"], taper)

    def test_name_independent_selection(self):
        first = fit_diag()
        self.assertTrue(first["applied"], first.get("reason"))
        reference = core.build_reference([donor_record(88, "other")], 16)
        second = core.fit_glyph(
            [dict(c) for c in DIAG_SOURCE], [dict(c) for c in DIAG_SOURCE],
            16, reference, (False, True), True,
        )
        self.assertEqual(
            coords(first["candidate_commands"]), coords(second["candidate_commands"]))


if __name__ == "__main__":
    unittest.main()
