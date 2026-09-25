import unittest

import numpy as np

import feature_stroke_fit as F


def raster(q):
    return {(int(round(float(a))), int(round(float(b))))
            for a, b in np.asarray(q, float).tolist()}


def filled_raster(q):
    """Native-equivalent synthetic filled-polygon pixels (set of (x, y))."""
    poly = [(float(a), float(b)) for a, b in np.asarray(q, float).tolist()]
    xs = [a for a, _ in poly]
    ys = [b for _, b in poly]
    out = set()
    for x in range(int(np.floor(min(xs))), int(np.ceil(max(xs))) + 1):
        for y in range(int(np.floor(min(ys))), int(np.ceil(max(ys))) + 1):
            inside = False
            m = len(poly)
            for k in range(m):
                x0, y0 = poly[k]
                x1, y1 = poly[(k + 1) % m]
                if (y0 > y) != (y1 > y):
                    xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                    if x <= xin:
                        inside = not inside
            if inside:
                out.add((x, y))
    return out


def rect(x0, y0, x1, y1):
    return ([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], [3])


def groups_for_rect(members_x, members_y):
    return [
        {"normal": [1, 0], "members": members_x[0]},
        {"normal": [1, 0], "members": members_x[1]},
        {"normal": [0, 1], "members": members_y[0]},
        {"normal": [0, 1], "members": members_y[1]},
    ]


def h_glyph():
    # H: left stem, right stem, crossbar. Levels x: 0,2,6,8 ; y: 0,4,5,9
    pts = [[0, 0], [2, 0], [2, 4], [6, 4], [6, 0], [8, 0], [8, 9], [6, 9],
           [6, 5], [2, 5], [2, 9], [0, 9]]
    ends = [11]
    flags = [1] * 12
    groups = [
        {"normal": [1, 0], "members": [0, 11]},
        {"normal": [1, 0], "members": [1, 2, 9, 10]},
        {"normal": [1, 0], "members": [3, 8]},
        {"normal": [1, 0], "members": [4, 7]},
        {"normal": [1, 0], "members": [5, 6]},
        {"normal": [0, 1], "members": [0, 1, 4, 5]},
        {"normal": [0, 1], "members": [2, 3]},
        {"normal": [0, 1], "members": [9, 8]},
        {"normal": [0, 1], "members": [10, 11, 6, 7]},
    ]
    feats = [
        {"kind": "stem", "groups": [0, 1], "width": 2.0, "length": 9.0},
        {"kind": "stem", "groups": [3, 4], "width": 2.0, "length": 9.0},
        {"kind": "bar", "groups": [6, 7], "width": 1.0, "length": 4.0},
    ]
    return np.array(pts, float), ends, flags, groups, feats


class L1Tests(unittest.TestCase):
    def test_noninteger_source_yields_integer_positions(self):
        pts = np.array([[0.4, 0.0], [2.6, 0.0], [2.6, 8.0], [0.4, 8.0]])
        ends, flags = [3], [1] * 4
        groups = groups_for_rect([[0, 3], [1, 2]], [[0, 1], [2, 3]])
        feats = [{"kind": "stem", "groups": [0, 1],
                  "width": 2.2, "length": 8.0}]
        cur = pts + np.array([0.1, 0.0])
        # Asymmetric current that survives int-pixel rounding (the
        # no-op gate compares rounded pixels): no exact-symmetry pin.
        cur[1, 0] += 0.9
        r = F.fit(pts, ends, flags, 1.0, groups, feats, cur, raster)
        self.assertIn(r["status"], ("ok", "no-op"))
        for b in r["audit"]["boundaries"]:
            if b["axis"] == 0:
                self.assertAlmostEqual(b["selected"], round(b["selected"]))
        xs = sorted(b["selected"] for b in r["audit"]["boundaries"]
                    if b["axis"] == 0)
        self.assertEqual(xs[1] - xs[0], 2)


PLUS_SRC = [[3.57, 1.134], [3.57, 3.878], [1.092, 3.878], [1.092, 4.732],
            [3.57, 4.732], [3.57, 7.294], [4.48, 7.294], [4.48, 4.732],
            [7.056, 4.732], [7.056, 3.878], [4.48, 3.878], [4.48, 1.134]]
PLUS_CUR = [[4, 1], [4, 4], [1, 4], [1, 5], [4, 5], [4, 7],
            [5, 7], [5, 5], [7, 5], [7, 4], [5, 4], [5, 1]]
PLUS_ENDS = [11]
PLUS_FLAGS = [1] * 12
PLUS_GROUPS = [
    {"normal": [1, 0], "members": [2, 3]},
    {"normal": [1, 0], "members": [0, 1, 4, 5]},
    {"normal": [1, 0], "members": [6, 7, 10, 11]},
    {"normal": [1, 0], "members": [8, 9]},
    {"normal": [0, 1], "members": [0, 11]},
    {"normal": [0, 1], "members": [1, 2, 9, 10]},
    {"normal": [0, 1], "members": [3, 4, 7, 8]},
    {"normal": [0, 1], "members": [5, 6]},
]
PLUS_FEATS = [
    {"kind": "stem", "groups": [1, 2], "width": 0.91, "length": 6.0},
    {"kind": "bar", "groups": [5, 6], "width": 0.854, "length": 6.0},
]


class SymmetryTests(unittest.TestCase):
    def test_h_supports_x_t_not_y(self):
        pts, ends, flags, groups, feats = h_glyph()
        cur = pts.copy()
        # Break y-symmetry pixel-visibly so the solver runs; the
        # x-support assertion below needs relationships, which the
        # symmetric-current no-op gate would preempt.
        cur[2, 1] += 0.6
        r = F.fit(pts, ends, flags, 1.0, groups, feats, cur, raster)
        sym = [x["axis"] for x in r["audit"]["relationships"]
               if x.get("type") == "symmetry"]
        self.assertIn(0, sym)
        # Asymmetric T: top bar shifted right only on one side
        t = np.array([[0, 8], [9, 8], [9, 9], [3, 9], [3, 0],
                      [2, 0], [2, 9], [0, 9]], float)
        ends, flags = [7], [1] * 8
        tg = [{"normal": [1, 0], "members": [5, 6]},
              {"normal": [1, 0], "members": [4, 3]},
              {"normal": [0, 1], "members": [0, 1]},
              {"normal": [0, 1], "members": [2, 7]}]
        tf = [{"kind": "stem", "groups": [0, 1], "width": 1.0, "length": 9.0},
              {"kind": "bar", "groups": [2, 3], "width": 1.0, "length": 9.0}]
        r2 = F.fit(t, ends, flags, 1.0, tg, tf, t.copy(), raster)
        sym2 = [x["axis"] for x in r2["audit"]["relationships"]
                if x.get("type") == "symmetry"]
        self.assertNotIn(1, sym2)


class OwnershipTests(unittest.TestCase):
    def test_ownership_conflict_holds(self):
        pts = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 8.0], [0.0, 8.0]])
        ends, flags = [3], [1] * 4
        groups = groups_for_rect([[0, 3], [1, 2]], [[0, 1], [2, 3]])
        feats = [{"kind": "stem", "groups": [0, 1],
                  "width": 2.0, "length": 8.0}]
        own = {(0, 0): 0.0, (1, 0): 5.0}  # forces width 5 vs target 2
        # Pixel-asymmetric current so the fit runs far enough to
        # meet the ownership conflict (a symmetric current takes
        # the no-op gate first); the width-5-vs-2 conflict stands.
        cur = pts.copy()
        cur[3, 1] += 0.7
        r = F.fit(pts, ends, flags, 1.0, groups, feats, cur,
                  raster, ownership=own)
        self.assertEqual(r["status"], "held")
        self.assertIn("protected", r["reason"])


class TransposeTests(unittest.TestCase):
    def test_transpose_swaps_axes(self):
        pts = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0]])
        ends, flags = [3], [1] * 4
        groups = groups_for_rect([[0, 3], [1, 2]], [[0, 1], [2, 3]])
        feats = [{"kind": "bar", "groups": [2, 3], "width": 1.0, "length": 4.0}]
        r = F.fit(pts, ends, flags, 1.0, groups, feats, pts.copy(), raster)
        self.assertEqual(r["status"], "no-op")
        t = pts[:, ::-1].copy()
        tg = [{"normal": [1, 0], "members": [0, 1]},
              {"normal": [1, 0], "members": [2, 3]},
              {"normal": [0, 1], "members": [0, 3]},
              {"normal": [0, 1], "members": [1, 2]}]
        tf = [{"kind": "stem", "groups": [0, 1], "width": 1.0, "length": 4.0}]
        r2 = F.fit(t, ends, flags, 1.0, tg, tf, t.copy(), raster)
        self.assertEqual(r2["status"], "no-op")


class LevelsTests(unittest.TestCase):
    def test_h_many_levels_actual_fit(self):
        pts, ends, flags, groups, feats = h_glyph()
        cur = pts.copy()
        # Split current on inner left boundary, pixel-visibly (0.3
        # rounds back to symmetric and takes the no-op gate).
        cur[1, 0] += 0.6
        r = F.fit(pts, ends, flags, 1.0, groups, feats, cur, raster)
        # split current on pinned axis must hold, not silently fit
        if r["status"] == "held":
            self.assertEqual(r["reason"], "current-split-conflict")
        else:
            q = r["coords"]
            self.assertTrue(np.all(np.abs(q - np.round(q)) < 1e-6))
            self.assertGreater(len(r["audit"]["boundaries"]), 4)


if __name__ == "__main__":
    unittest.main()
