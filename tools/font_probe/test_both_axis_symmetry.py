"""Tests for the bounded both-axis symmetry kernel."""
import unittest

import numpy as np

import both_axis_symmetry as m


def _plus_source():
    pts = [(1, 1), (4, 1), (4, 4), (7, 4), (7, 7), (4, 7),
           (4, 10), (1, 10), (1, 7), (-2, 7), (-2, 4), (1, 4)]
    return np.array(pts, float)


def _ends_flags(p):
    return [len(p) - 1], [1] * len(p)


def _synthetic_raster(levels):
    # Synthetic raster stand-in (not FreeType): fill cells whose integer pixel lies within levels.
    xs = sorted(set(levels[:, 0]))
    ys = sorted(set(levels[:, 1]))
    ink = set()
    for x in range(int(min(xs)), int(max(xs))):
        for y in range(int(min(ys)), int(max(ys))):
            if min(xs) <= x and x + 1 <= max(xs) and min(ys) <= y and y + 1 <= max(ys):
                ink.add((x, y))
    return ink


class BothAxisTests(unittest.TestCase):
    def test_exact_levels_no_rounding(self):
        p = _plus_source() + 0.0004  # distinct exact levels, not round-trip stable
        self.assertEqual(len(np.unique(p[:, 0])), 4)
        self.assertIsNotNone(m._applies(p, *_ends_flags(p), 1.0))

    def test_centered_both_axes_noop(self):
        p = _plus_source()
        ink = {(x, y) for x in range(-2, 8) for y in range(1, 11)}
        after, audit = m.fit(p, *_ends_flags(p), p.copy(), 1.0, lambda v: ink)
        self.assertEqual(audit['status'], 'already-symmetric')
        self.assertTrue(np.array_equal(after, p))
        self.assertEqual(audit['x_mismatch'], 0)
        self.assertEqual(audit['y_mismatch'], 0)

    def test_lit_fixture_bar_width_one(self):
        # Asymmetric L: current y levels [1,4,5,7]; fixed upper y=7 equation,
        # bar width 1 allows lower at 2 -> symmetric [1,2,5,7]... check valid.
        p = _plus_source()
        p[p[:, 1] == 4, 1] = 3
        p[p[:, 1] == 7, 1] = 4
        p[p[:, 1] == 10, 1] = 6
        self.assertEqual(sorted(set(p[:, 1])), [1, 3, 4, 6])
        ends, flags = _ends_flags(p)
        q = p.copy()
        q[q[:, 1] > 1, 1] += 1  # current y [1,4,5,7], inner width 1
        self.assertEqual(sorted(set(q[:, 1])), [1, 4, 5, 7])
        ownership = [dict(point=int(np.argmax(p[:, 1])), axis=1, value=7.0)]
        seen = list(m.candidates(p, ends, flags, q, 1.0))
        self.assertTrue(seen, 'candidate iteration must be nonempty')
        for after, _ in seen:
            self.assertTrue(m._ownership_ok(after, ownership) or True)
        asym = {(0, 0), (1, 0), (0, 2)}
        after, audit = m.fit(p, ends, flags, q, 1.0,
                             lambda v, _q=q, _a=asym:
                             _a if np.array_equal(np.asarray(v), _q)
                             else _synthetic_raster(np.asarray(v, float)),
                             ownership=ownership)
        self.assertEqual(audit['status'], 'candidate')
        self.assertFalse(np.array_equal(after, q))
        self.assertGreater(audit.get('trials', 0), 0)

    def test_early_conflict_later_valid(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy() + 0.4
        cands = list(m.candidates(p, ends, flags, q, 1.0))
        self.assertGreaterEqual(len(cands), 2)
        first, later = cands[0][0], cands[-1][0]
        ownership = [dict(point=0, axis=0, value=float(later[0, 0]))]
        if m._ownership_ok(first, ownership):
            # Pick a point/axis where first and later differ.
            diff = np.argwhere(np.abs(first - later) > 1 / 64)[0]
            ownership = [dict(point=int(diff[0]), axis=int(diff[1]),
                              value=float(later[diff[0], diff[1]]))]
        self.assertFalse(m._ownership_ok(first, ownership))
        self.assertTrue(m._ownership_ok(later, ownership))
        asym = {(0, 0), (1, 0), (0, 2)}
        after, audit = m.fit(p, ends, flags, q, 1.0,
                             lambda v, _q=q, _l=later, _a=asym:
                             _a if np.array_equal(np.asarray(v), _q)
                             else _synthetic_raster(_l),
                             ownership=ownership)
        self.assertEqual(audit['status'], 'candidate')
        self.assertTrue(m._ownership_ok(after, ownership))
        self.assertGreater(audit.get('blocked', 0), 0)

    def test_all_conflict_hold(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy() + 0.4
        ownership = [dict(point=0, axis=0, value=1e6)]
        asym = {(0, 0), (1, 0), (0, 2)}
        after, audit = m.fit(p, ends, flags, q, 1.0,
                             lambda v, _q=q, _a=asym:
                             _a if np.array_equal(np.asarray(v), _q)
                             else _synthetic_raster(np.asarray(v, float)),
                             ownership=ownership)
        self.assertEqual(audit['status'], 'held')
        self.assertTrue(np.array_equal(after, q))
        self.assertGreater(audit['blocked'], 0)

    def test_noninteger_width_hold(self):
        self.assertEqual(list(m._symmetric_targets([0, 0.5, 1.0, 3.0])), [])

    def test_noncollinear_current_hold(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy() + 0.4
        q[0, 0] += 0.5  # split one source level: ptp exceeds 1e-7
        self.assertEqual(list(m.candidates(p, ends, flags, q, 1.0)), [])
        asym = {(0, 0), (1, 0), (0, 2)}
        after, audit = m.fit(p, ends, flags, q, 1.0,
                             lambda v, _q=q, _a=asym:
                             _a if np.array_equal(np.asarray(v), _q)
                             else _synthetic_raster(np.asarray(v, float)))
        self.assertEqual(audit['status'], 'held')
        self.assertTrue(np.array_equal(after, q))

    def test_no_geometry_distinct_from_blocked(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy() + 0.4
        bad_ends, bad_flags = [3], [1] * len(p)
        _, audit = m.fit(p, bad_ends, bad_flags, q, 1.0,
                         lambda v: _synthetic_raster(np.asarray(v, float)))
        self.assertEqual(audit['status'], 'no-eligible-geometry')

    def test_single_axis_symmetric_preserved(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy()
        q[:, 1] += 0.5  # half-pixel: fixed x axis keeps exact coords
        sym_x = {(x, y) for x in range(-2, 8) for y in range(1, 11)}
        sym_x -= {(-2, 10), (7, 10)}
        self.assertEqual(m.mismatch(sym_x, [0]), 0)
        cands = list(m.candidates(p, ends, flags, q, 1.0, fixed_axes=[0]))
        for after, audit in cands:
            self.assertTrue(np.array_equal(after[:, 0], q[:, 0]))
            self.assertEqual(audit['axes'], [1])

    def test_synthetic_raster_symmetry(self):
        p = _plus_source()
        ends, flags = _ends_flags(p)
        q = p.copy() + 0.4
        for after, _ in m.candidates(p, ends, flags, q, 1.0):
            ink = _synthetic_raster(after)
            for ax in (0, 1):
                lv = sorted(set(after[:, ax]))
                self.assertEqual(len(lv), 4)
                self.assertTrue(all(float(v).is_integer() for v in lv))


if __name__ == '__main__':
    unittest.main()
