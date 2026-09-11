"""Independent report validation; no preferred pixel shapes are requirements."""
import tempfile
import copy
import unittest
import types
import math
import freetype as ft
from pathlib import Path
from unittest.mock import patch
from check_shamir_baseline import graph_issues, decision_metadata_present, observation, run, coordinate_check, construction_issues


def graph():
    return dict(scheduler='point', order=[0, 1], scalar_order=[0, 1], rejected=[], constraints=[
        dict(id=0, point=0, sources=[], normal=[1, 0], value=0, depends_on=[]),
        dict(id=1, point=1, sources=[0], normal=[1, 0], value=1, depends_on=[0])])


class NativeOutline:
    units_per_EM = 1000

    def __init__(self, original, actual):
        self.original, self.actual = original, actual
        self.glyph = types.SimpleNamespace(outline=types.SimpleNamespace(points=[]))

    def set_pixel_sizes(self, x, y):
        pass

    def load_char(self, char, flags):
        self.glyph.outline.points = self.original if flags & ft.FT_LOAD_NO_SCALE else self.actual


class BaselineEvidenceTests(unittest.TestCase):
    def test_topology_independent_of_report_claim(self):
        g = graph()
        self.assertEqual(graph_issues(g), [])
        g['order'] = [1, 0]
        self.assertTrue(any('source point' in e for e in graph_issues(g)))

    def test_dependency_and_rejection_audit(self):
        g = graph()
        g['constraints'][1]['depends_on'] = [17]
        g['rejected'] = [{}]
        issues = graph_issues(g)
        self.assertTrue(any('dependency' in e for e in issues))
        self.assertTrue(any('rejection' in e for e in issues))

    def test_duplicate_execution_is_not_coverage(self):
        g = graph()
        g['scalar_order'] = [0, 1, 1]
        self.assertTrue(graph_issues(g))

    def test_decision_record_is_required_but_does_not_assert_readiness(self):
        self.assertFalse(decision_metadata_present({}))
        self.assertFalse(decision_metadata_present({'baseline_decisions': {}}))
        self.assertTrue(decision_metadata_present({'baseline_decisions': {'B01': 'unresolved'}}))

    def test_missing_experimental_recipe_is_observation(self):
        with patch('check_shamir_baseline.construction_checks', side_effect=KeyError('templates')):
            self.assertFalse(observation(None, '!', 14, {})['available'])

    def test_dense_oracle_uses_supplied_relations_and_ideal_source_coordinates(self):
        cs = [dict(point=0, normal=[1, 0], kind='Abs', value=13, round=False),
              dict(point=0, normal=[0, 1], kind='Abs', value=0),
              dict(point=1, normal=[1, 0], kind='Dist', sources=[0], value=100),
              dict(point=1, normal=[0, 1], kind='Abs', value=100),
              dict(point=2, normal=[1, 0], kind='Ratio', sources=[0, 1], value=1.5),
              dict(point=2, normal=[0, 1], kind='Abs', value=50, round=False)]
        face = NativeOutline([[0, 0], [100, 100], [150, 50]], [[8, 0], [72, 64], [104, 32]])
        report = coordinate_check(face, 'A', 10, {'constraints': cs})
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(report['expected_points'][2][0], 1.63)
        face.actual[2][0] += 1
        self.assertFalse(coordinate_check(face, 'A', 10, {'constraints': cs})['passed'])

    def test_supplied_signed_distance_and_extrapolation_override_geometry(self):
        for dist_kind in ('Dist', 'PDist'):
            for ratio_kind in ('Ratio', 'PRatio'):
                cs = [dict(point=0, normal=[1, 0], kind='Abs', value=0),
                      dict(point=0, normal=[0, 1], kind='Abs', value=0),
                      dict(point=1, normal=[1, 0], kind=dist_kind, sources=[0], value=-100),
                      dict(point=1, normal=[0, 1], kind='Abs', value=0),
                      dict(point=2, normal=[1, 0], kind=ratio_kind, sources=[0, 1], value=-2),
                      dict(point=2, normal=[0, 1], kind='Abs', value=0)]
                face = NativeOutline([[0, 0], [100, 0], [150, 0]], [[0, 0], [-64, 0], [128, 0]])
                report = coordinate_check(face, 'A', 10, {'constraints': cs})
                self.assertTrue(report['passed'], (dist_kind, ratio_kind))
                self.assertEqual(report['expected_points'], [[0., 0.], [-1., 0.], [2., 0.]])

    def test_independent_near_parallel_equations_are_checked(self):
        length = math.hypot(1, .001)
        normal = [1 / length, .001 / length]
        cs = [dict(point=0, normal=[1, 0], kind='Abs', value=100, round=False),
              dict(point=0, normal=normal, kind='Abs', value=100.2 / length, round=False)]
        face = NativeOutline([[100, 200]], [[64, 128]])
        report = coordinate_check(face, 'A', 10, {'constraints': cs})
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(report['expected_points'][0][1], 2.)

    def test_reduced_relation_survives_native_point_remapping(self):
        reduced = graph()
        reduced['constraints'][0]['kind'] = 'Abs'
        reduced['constraints'][1]['kind'] = 'Dist'
        reduced['constraints'][1]['segment_owner'] = 7
        selected = [dict(c, point=[4, 9][c['point']],
                         sources=[[4, 9][p] for p in c['sources']],
                         id=c['id'] + 20, representative_owned=True)
                    for c in reduced['constraints']]
        record = dict(representative_points=[4, 9], segment_dominance={'rejected': []},
                      reduced_graph=reduced, graph=dict(order=[4, 9], constraints=selected,
                                                       reduced_selected_relation_count=2))
        self.assertEqual(construction_issues(record), [])
        damaged = copy.deepcopy(record)
        damaged['graph']['constraints'][1]['value'] += 1
        self.assertTrue(any('missing or changed' in e for e in construction_issues(damaged)))
        damaged = copy.deepcopy(record)
        damaged['graph']['constraints'].pop()
        self.assertTrue(any('missing or changed' in e for e in construction_issues(damaged)))
        damaged = copy.deepcopy(record)
        damaged['reduced_graph']['rejected'] = [dict(reason='dependent direction', constraint=
            dict(reduced['constraints'][1], id=88))]
        self.assertTrue(any('multiple dominant' in e for e in construction_issues(damaged)))

    def test_simultaneous_member_cycle_requires_complete_record(self):
        g = graph()
        g.update(scheduler='point-representatives/member-equations', execution_phase='simultaneous-members')
        g['constraints'][0].update(sources=[1], depends_on=[1])
        self.assertEqual(graph_issues(g), [])
        ordinary = copy.deepcopy(g)
        ordinary.update(scheduler='point')
        ordinary.pop('execution_phase')
        self.assertTrue(any('source point' in e for e in graph_issues(ordinary)))
        g['constraints'][0]['depends_on'] = []
        self.assertTrue(any('incomplete simultaneous' in e for e in graph_issues(g)))

    def test_frozen_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'baseline-verification.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'empty output'):
                run(temp)


if __name__ == '__main__':
    unittest.main()
