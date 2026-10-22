"""Independent analytical controls for the joint diagonal fit.

Reflection-reversal, rigid-translation and collinear-splitting invariance,
plus parity-rule unit properties. All controls are command geometry; no
pixels, no phase search, no parameter sweep.
"""
import math
import struct
import unittest

import numpy as np

from experiments.hobby_fitting import joint_diagonal as joint
from experiments.hobby_fitting.direct_diagonal import (
    _affine_sample,
    _edge_point,
    _f32bits,
)


def f32(x):
    return struct.unpack(">f", struct.pack(">f", x))[0]


def translate_commands(commands, dx, dy):
    out = []
    for cmd in commands:
        cmd = dict(cmd)
        if "x" in cmd:
            cmd["x"] = f32(cmd["x"] + dx)
            cmd["x_bits"] = _f32bits(cmd["x"])
        if "y" in cmd:
            cmd["y"] = f32(cmd["y"] + dy)
            cmd["y_bits"] = _f32bits(cmd["y"])
        out.append(cmd)
    return out


def reverse_commands(commands):
    pts = [(c["x"], c["y"], c.get("x_bits"), c.get("y_bits"))
           for c in commands if c["op"] in ("move_to", "line_to")]
    rev = [dict(op="move_to", x=pts[-1][0], y=pts[-1][1],
                x_bits=pts[-1][2], y_bits=pts[-1][3])]
    for x, y, xb, yb in reversed(pts[:-1]):
        rev.append(dict(op="line_to", x=x, y=y, x_bits=xb, y_bits=yb))
    rev.append(dict(op="close"))
    return rev


def split_longest_edge(commands):
    pts = [(c["x"], c["y"]) for c in commands
           if c["op"] in ("move_to", "line_to")]
    n = len(pts)
    best, best_len = 0, -1.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        length = math.hypot(x1 - x0, y1 - y0)
        if length > best_len:
            best, best_len = i, length
    out, idx = [], 0
    for cmd in commands:
        if cmd["op"] == "line_to":
            x0, y0 = pts[idx]
            x1, y1 = pts[(idx + 1) % n]
            if idx == best:
                mx, my = f32((x0 + x1) / 2.0), f32((y0 + y1) / 2.0)
                out.append(dict(op="line_to", x=mx, y=my,
                                x_bits=_f32bits(mx), y_bits=_f32bits(my)))
            idx += 1
        out.append(dict(cmd))
    return out


class ParityRuleTests(unittest.TestCase):
    def test_odd_snaps_to_center(self):
        self.assertEqual(joint.parity_target(3.953125, 1.075), 3.5)
        self.assertEqual(joint.parity_target(4.2, 0.9), 4.5)

    def test_even_snaps_to_boundary(self):
        self.assertEqual(joint.parity_target(3.953125, 1.6), 4.0)
        self.assertEqual(joint.parity_target(4.2, 2.1), 4.0)

    def test_sub_half_count_is_unsupported(self):
        self.assertIsNone(joint.parity_target(3.9, 0.4))
        self.assertIsNone(joint.parity_target(3.9, 0.0))
        self.assertIsNone(joint.parity_target(3.9, -0.2))

    def test_centered_sub_one_span_covers_exactly_its_center(self):
        for width in (0.5, 0.5546, 0.9, 0.99):
            target = joint.parity_target(3.953125, width)
            self.assertEqual(target, 3.5)
            lo, hi = target - width / 2.0, target + width / 2.0
            inside = [c for c in (2.5, 3.5, 4.5, 5.5) if lo < c < hi]
            self.assertEqual(inside, [target])
            cell_lo, cell_hi = target - 0.5, target + 0.5
            self.assertAlmostEqual(lo - cell_lo, 0.5 - width / 2.0)
            self.assertAlmostEqual(cell_hi - hi, 0.5 - width / 2.0)


class ReencodeTests(unittest.TestCase):
    def test_reversed_match_preserves_affine_endpoints(self):
        coords = [(0.0, 1.0), (1.0, 4.0), (4.0, 1.0), (3.0, 4.0)]
        o = dict(pair=1, p0=(3.0, 4.0), p1=(4.0, 1.0), i0=3, i1=2,
                 t0=0.0, t1=1.0)
        r = joint._reencode(o, True)
        self.assertEqual((r["i0"], r["i1"]), (2, 3))
        self.assertEqual((r["t0"], r["t1"]), (0.0, 1.0))
        self.assertEqual(r["p0"], (4.0, 1.0))
        self.assertEqual(r["p1"], (3.0, 4.0))
        e0 = _edge_point(r, 0.0, coords)
        e1 = _edge_point(r, 1.0, coords)
        self.assertEqual(tuple(e0), (4.0, 1.0))
        self.assertEqual(tuple(e1), (3.0, 4.0))

    def test_reversed_mirror_pair_gives_residual_rows(self):
        from experiments.hobby_fitting.prototype import System
        points = [(0.0, 1.0), (1.0, 4.0), (4.0, 1.0), (3.0, 4.0)]
        system = System(points, 16.0)
        s = dict(pair=0, p0=(0.0, 1.0), p1=(1.0, 4.0), i0=0, i1=1,
                 t0=0.0, t1=1.0)
        o = dict(pair=1, p0=(3.0, 4.0), p1=(4.0, 1.0), i0=3, i1=2,
                 t0=0.0, t1=1.0)
        rows = joint._symmetry_rows(system, [(s, joint._reencode(o, True),
                                              0.0)], 2.0, 4.0, 16.0)
        self.assertEqual(len(rows), 2)
        delta = np.zeros(8)
        for row, constant in rows:
            self.assertAlmostEqual(float(row @ delta + constant), 0.0)


class WaistSelectionTests(unittest.TestCase):
    @staticmethod
    def commands_of(points):
        cmds = [dict(op="move_to", x=points[0][0], y=points[0][1],
                     x_bits=_f32bits(points[0][0]),
                     y_bits=_f32bits(points[0][1]))]
        for x, y in points[1:]:
            cmds.append(dict(op="line_to", x=x, y=y,
                             x_bits=_f32bits(x), y_bits=_f32bits(y)))
        cmds.append(dict(op="close"))
        return cmds

    def test_single_stem_neck_is_outside_crossing_slice(self):
        from experiments.hobby_fitting.real_outline import parse_commands
        pts = [(3.0, 0.0), (5.0, 0.0), (4.2, 4.0), (5.0, 8.0), (3.0, 8.0),
               (3.8, 4.0)]
        waist = joint._waist_from_slabs(
            parse_commands(self.commands_of(pts)))
        self.assertIsNone(waist)

    def test_silhouette_tip_is_not_a_crossing_neck(self):
        from experiments.hobby_fitting.real_outline import parse_commands
        pts = [(0.0, 0.0), (8.0, 0.0), (8.0, 1.0), (0.7, 1.0), (0.7, 3.0),
               (0.2, 3.0), (0.2, 1.0), (0.0, 1.0)]
        waist = joint._waist_from_slabs(
            parse_commands(self.commands_of(pts)))
        self.assertIsNone(waist)

    def test_crossing_neck_survives_contour_reencoding(self):
        from experiments.hobby_fitting.real_outline import parse_commands
        points = [(-2., 4.), (0., 1.), (2., 4.), (3., 4.), (1., 0.),
                  (3., -4.), (2., -4.), (0., -1.), (-2., -4.), (-3., -4.),
                  (-1., 0.), (-3., 4.)]
        original = self.commands_of(points)
        expected = joint._waist_from_slabs(parse_commands(original))
        self.assertEqual(expected, dict(width=2., mid=0., level=0.))
        split = self.commands_of([points[0], (-1., 2.5), *points[1:]])
        for commands in [reverse_commands(original), split]:
            self.assertEqual(joint._waist_from_slabs(parse_commands(commands)), expected)


if __name__ == "__main__":
    unittest.main()
