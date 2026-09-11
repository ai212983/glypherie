"""Tests for opt-in central-upright shape bounds (experimental)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont
from central_upright_fit import fit
from central_upright_shape import shape_targets, apply_to_record
from test_central_upright import SRC, CUR, ENDS, FLAGS

HERE = Path(__file__).resolve().parent


def _record():
    def c(kind, point, normal, value, role, cid, sources=(), rnd=True):
        return dict(kind=kind, point=point, normal=list(normal),
                    sources=list(sources), value=value, round=rnd,
                    metric=True, metric_role=role, id=cid)
    return {'graph': {'constraints': [
        c('Abs', 2, (1, 0), 1.0, 'glyph-x-bound', 6),
        c('Dist', 8, (1, 0), 6.0, 'glyph-x-bound', 12, sources=[2]),
        c('Abs', 0, (0, 1), 0.0, 'glyph-y-bound', 20),
        c('Dist', 1, (0, 1), 3.0, 'baseline', 21, sources=[0]),
        dict(kind='PAbs', point=5, normal=[1, 0], sources=[], value=9.0,
             round=True, metric=False, id=30),
    ]}}


class ShapeBoundsTests(unittest.TestCase):
    def test_member_targets_source_driven_left_edge(self):
        mapped, audit = fit(SRC, ENDS, FLAGS, CUR, 1)
        self.assertEqual(audit['status'], 'candidate')
        members = audit['evidence']['member_targets']
        # Left-boundary points 2,3 have source x == A_src; moved 1 -> 2.
        kt = audit['evidence']['target_knots']
        self.assertEqual(members[2], kt[0])
        self.assertEqual(members[3], kt[0])
        self.assertEqual(kt[0], 2.0)
        targets = shape_targets(mapped, audit)
        self.assertEqual(targets[2], 2.0)
        self.assertEqual(targets[3], 2.0)

    def test_apply_replaces_exactly_with_round_false(self):
        rec, changed = apply_to_record(_record(), {2: 2.0, 8: 7.0}, 1.0)
        by_id = {c['id']: c for c in rec['graph']['constraints']}
        self.assertEqual(sorted(changed), [6, 12])
        self.assertEqual(by_id[6]['value'], 2.0)
        self.assertFalse(by_id[6]['round'])
        self.assertEqual(by_id[12]['value'], 5.0)
        self.assertFalse(by_id[12]['round'])
        # y bound, baseline, P* untouched.
        self.assertEqual(by_id[20]['value'], 0.0)
        self.assertEqual(by_id[21]['value'], 3.0)
        self.assertEqual(by_id[30]['value'], 9.0)
        # Input record unmutated (all-or-nothing copy).
        src = _record()
        self.assertEqual(src['graph']['constraints'][0]['value'], 1.0)

    def test_apply_unknown_role_holds(self):
        rec = _record()
        rec['graph']['constraints'].append(
            dict(kind='Abs', point=4, normal=[1, 0], sources=[], value=1.0,
                 round=True, metric=True, metric_role='mystery', id=99))
        with self.assertRaises(ValueError):
            apply_to_record(rec, {2: 2.0, 8: 7.0, 4: 1.0}, 1.0)

    def test_apply_missing_endpoint_holds_all(self):
        with self.assertRaises(ValueError):
            apply_to_record(_record(), {2: 2.0}, 1.0)


def _literata_plus():
    """Real prepare/reflect inputs: Literata '+' at 14px with live record."""
    from compare_shamir_pipeline import CHARS, instance
    from shamir_model import build_font
    from shamir_representative_search import representative_override
    from build_geometric_candidate import geometry as geometric_data
    job = json.loads(
        (HERE.parent / 'font_generator/examples/literata.json').read_text())
    source = (HERE.parent / 'font_generator/examples' / job['font']).resolve()
    tmp = tempfile.TemporaryDirectory()
    static = Path(tmp.name) / 'static.ttf'
    instance(source, static, {})
    experiment = Path(tmp.name) / 'experiment.ttf'
    with representative_override(256):
        model = build_font(static, experiment, CHARS,
                           profile='baseline', ppem=14)
    with TTFont(str(experiment)) as font:
        em = font['head'].unitsPerEm
        points, ends, flags = font['glyf'][
            font.getBestCmap()[ord('+')]].getCoordinates(font['glyf'])
    record = model['records']['+']
    data = geometric_data(record, points, ends, flags, 14, em)
    return tmp, data, record


@unittest.skipUnless(
    (HERE.parent / 'font_generator/examples/literata.json').exists(),
    'literata source job absent')
class PrepareReflectCenteringTests(unittest.TestCase):
    def test_prepare_applies_shape_and_reflect_agrees(self):
        import central_upright_fit as upright
        from cumulative_hinter import prepare, reflect
        tmp, data, record = _literata_plus()
        try:
            before = copy.deepcopy(record)
            base, current, audit = prepare(data, record,
                                           center_fit=upright.fit)
            shape = audit.get('central_upright_shape') or {}
            self.assertEqual(shape.get('status'), 'applied')
            self.assertTrue(shape.get('replaced_ids'))
            self.assertEqual(audit.get('status'), 'joint-fit')
            # Prepare never mutates the caller's record.
            self.assertEqual(record, before)
            final, reflection = reflect(data, record, current, audit, set())
            rshape = reflection.get('central_upright_shape') or {}
            self.assertEqual(rshape.get('status'), 'applied')
            self.assertEqual(sorted(rshape.get('replaced_ids', [])),
                             sorted(shape.get('replaced_ids')))
        finally:
            tmp.cleanup()

    def test_reflect_conflicting_owner_holds_and_preserves_current(self):
        import central_upright_fit as upright
        from cumulative_hinter import prepare, reflect
        tmp, data, record = _literata_plus()
        try:
            _, current, audit = prepare(data, record,
                                        center_fit=upright.fit)
            shape = audit.get('central_upright_shape') or {}
            self.assertEqual(shape.get('status'), 'applied')
            poisoned = copy.deepcopy(audit)
            target_point = next(iter(shape['targets']))
            poisoned.setdefault('ownership', []).append(
                dict(point=int(target_point), axis=0, value=1e6,
                     stage='conflicting-owner'))
            final, reflection = reflect(data, record, current, poisoned,
                                        set())
            # Conflict HOLDS: no superseding, upstream current preserved.
            self.assertEqual(reflection.get('status'), 'held-shape-conflict')
            np.testing.assert_array_equal(np.asarray(final),
                                          np.asarray(current))
        finally:
            tmp.cleanup()


class OwnerSemanticsTests(unittest.TestCase):
    def test_claim_conflict_raises_and_leaves_owners_unchanged(self):
        from cumulative_hinter import claim
        fitted = np.array([[0., 0.], [4., 0.]])
        owners = []
        claim(owners, [1], [0], fitted, 'first')
        snapshot = copy.deepcopy(owners)
        with self.assertRaises(ValueError):
            claim(owners, [1], [0], fitted + [[0., 0.], [9., 0.]],
                  'second')
        self.assertEqual(owners, snapshot)

    def test_claim_same_value_is_idempotent(self):
        from cumulative_hinter import claim
        fitted = np.array([[0., 0.], [4., 0.]])
        owners = []
        claim(owners, [1], [0], fitted, 'first')
        claim(owners, [1], [0], fitted, 'second')
        self.assertEqual(len(owners), 2)


if __name__ == '__main__':
    unittest.main()
