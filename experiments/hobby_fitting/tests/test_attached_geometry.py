"""Independent ownership and coordinate-encoding controls for attached fitting."""

import copy
import json
import math
from pathlib import Path
import struct
import unittest

import numpy as np

from experiments.hobby_fitting import attached_diagonal as model
from experiments.hobby_fitting import curved_width
from experiments.hobby_fitting.real_outline import parse_commands
from experiments.hobby_fitting.tests.test_smooth_curve_geometry import (
    TOPOLOGY_BINARY_REASON,
    topology_binary_present,
)


def bits(value):
    return struct.unpack('=I', struct.pack('=f', value))[0]


def command(op, **coordinates):
    return dict(op=op, **coordinates, **{k + '_bits': bits(v) for k, v in coordinates.items()})


def translate(commands, dx, dy):
    return [command(c['op'], **{k: c[k] + (dx if k.startswith('x') else dy)
                               for k in ('x', 'x1', 'x2', 'y', 'y1', 'y2') if k in c})
            for c in commands]


def segments(commands):
    start = current = None
    result = []
    for c in commands:
        op = c['op']
        if op == 'move_to':
            start = current = (c['x'], c['y'])
        elif op in ('line_to', 'quad_to'):
            end = (c['x'], c['y'])
            if op == 'quad_to':
                result.append((op, current, (c['x1'], c['y1']), end))
            elif current != end:
                result.append((op, current, end))
            current = end
        elif op == 'close':
            if current != start:
                result.append(('line_to', current, start))
            current = start
        else:
            raise AssertionError('quadratic control only')
    return result


def reverse(commands):
    segs = segments(commands)
    start = segs[-1][-1]
    result = [command('move_to', x=start[0], y=start[1])]
    for seg in reversed(segs):
        end = seg[1]
        coordinates = dict(x=end[0], y=end[1])
        if seg[0] == 'quad_to':
            coordinates.update(x1=seg[2][0], y1=seg[2][1])
        result.append(command(seg[0], **coordinates))
    return result + [dict(op='close')]


def unoriented_geometry(commands):
    return sorted((s[0], tuple(sorted((s[1], s[-1]))), s[2] if s[0] == 'quad_to' else ())
                  for s in segments(commands))


def topology(source, upstream, candidate):
    return dict(curved_width._substitution_gate(source, upstream, candidate), supported=True)


class AttachedCoordinateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path('out/diagnostics/direct-diagonal')
        reasons = []
        missing = [str(folder / p) for p in (
            'text-review/ascii-captures/Roboto-400-16.json',
            'coverage-review/cells/Roboto_16.0_400_selective_default.json')
            if not (folder / p).is_file()]
        if missing:
            reasons.append(
                "missing optional captures %s (git-ignored corpora; "
                "regenerate the capture with "
                "experiments/hobby_fitting/text_review.py and the cell with "
                "experiments/hobby_fitting/coverage_review.py)"
                % ", ".join(missing))
        if not topology_binary_present():
            reasons.append(TOPOLOGY_BINARY_REASON)
        if reasons:
            raise unittest.SkipTest("; ".join(reasons))
        captures = json.loads((folder / 'text-review/ascii-captures/Roboto-400-16.json').read_text())[0]
        rec = next(r for r in captures['modes']['selective_default']['records'] if r['codepoint'] == 50)
        cls.source, cls.upstream = rec['source_commands'], rec['fitted_commands']
        cls.reference = json.loads((folder / 'coverage-review/cells/Roboto_16.0_400_selective_default.json').read_text())['reference']

    def fit(self, source=None, upstream=None, axes=(False, True)):
        return model.fit(source if source is not None else self.source,
                         upstream if upstream is not None else self.upstream,
                         16, self.reference, axes, topology_checker=topology)

    def test_original_upstream_ownership_and_movement(self):
        result = self.fit()
        self.assertTrue(result['applied'], result.get('reason'))
        candidate = result['candidate_commands']
        for before, after in zip(self.upstream, candidate):
            for key in ('y', 'y1', 'y2'):
                if key in before:
                    self.assertEqual(bits(before[key]), bits(after[key]))
        source, old, new = [parse_commands(c) for c in (self.source, self.upstream, candidate)]
        pts = source['oncurve']
        upright = {v for contour in source['contours'] for seg in contour
                   if seg[0] == 'line' and pts[seg[1]][0] == pts[seg[2]][0]
                   and pts[seg[1]][1] != pts[seg[2]][1] for v in (seg[1], seg[2])}
        for v in upright:
            self.assertEqual(bits(old['oncurve'][v][0]), bits(new['oncurve'][v][0]))
        peak = max(math.dist(a, b) for a, b in zip(old['oncurve'] + old['offcurve'],
                                                  new['oncurve'] + new['offcurve']))
        self.assertLess(peak, 1.2264083287553476 / 2)
        self.assertTrue(topology(self.source, self.upstream, candidate)['ok'])

    def test_rigid_translation_retains_relative_geometry(self):
        first = self.fit()
        shifted = self.fit(translate(self.source, 16, 8), translate(self.upstream, 16, 8))
        self.assertTrue(first['applied'], first.get('reason'))
        self.assertTrue(shifted['applied'], shifted.get('reason'))
        self.assertEqual(translate(first['candidate_commands'], 16, 8), shifted['candidate_commands'])

    def test_reversed_contour_retains_geometry(self):
        first = self.fit()
        reversed_fit = self.fit(reverse(self.source), reverse(self.upstream))
        self.assertTrue(first['applied'], first.get('reason'))
        self.assertTrue(reversed_fit['applied'], reversed_fit.get('reason'))
        self.assertEqual(unoriented_geometry(first['candidate_commands']),
                         unoriented_geometry(reversed_fit['candidate_commands']))

    def test_both_native_axes_abstain_identically(self):
        before = copy.deepcopy(self.upstream)
        result = self.fit(axes=(True, True))
        self.assertFalse(result['applied'])
        self.assertEqual(before, result['candidate_commands'])
        self.assertEqual(before, self.upstream)


class ConvexConstraintTests(unittest.TestCase):
    def test_dependent_equalities_and_inequalities_match_one_dimensional_optimum(self):
        rng = np.random.default_rng(20261021)
        g = np.array([[1., 1.], [2., 2.], [-3., -3.]])
        h = np.array([.2, .4, -.6])
        for _ in range(15):
            a, b = rng.normal(size=(3, 2)), rng.normal(size=3)
            direction = a[:, 0] - a[:, 1]
            target = b - .2 * a[:, 1]
            x = float(np.clip(direction @ target / (direction @ direction), -.4, .4))
            result = model._convex_qp(a, b, g, h, np.eye(2), np.array([-.4, -.2]), .8)
            self.assertIsNotNone(result)
            np.testing.assert_allclose(result[0], [x, .2 - x], atol=1e-7, rtol=0)

    def test_incompatible_inequality_abstains(self):
        result = model._convex_qp(np.eye(2), np.zeros(2), np.array([[1., 1.]]),
                                  np.array([0.]), np.array([[1., 0.]]), np.array([1.]), .5)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
