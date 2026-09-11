"""Focused checks for the axis-placement diagnostic and candidate rule.

Geometry helpers stay identity-free (no character, family, or size in
their signatures); case selection lives in the adapter. Rendering checks
read the corrected ``source-bitmap-constraints-v2`` report only.
"""
import json
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CONSTRAINTS = HERE / 'out' / 'source-bitmap-constraints-v2'


def rect_samples(x0, y0, x1, y1, n=40):
    """Dense perimeter samples of an axis-aligned rectangle."""
    corners = [np.array([x0, y0]), np.array([x1, y0]),
               np.array([x1, y1]), np.array([x0, y1])]
    out = []
    for i in range(4):
        for k in range(n):
            out.append(corners[i] + (corners[(i + 1) % 4] - corners[i]) * (k / n))
    return np.asarray(out)


class GeometryFrameTests(unittest.TestCase):
    def test_ink_center_uses_bitmap_frame(self):
        from audit_axis_placement import ink_axis_center, ink_box_of, _axis_center
        # Same glyph: y-up outline box vs y-down bitmap box live in
        # different frames, so the outline y-center must never drive
        # raster mirroring.
        self.assertEqual(_axis_center([0, 10, 9, 20], 'y'), 15.0)
        self.assertEqual(ink_axis_center([0, 0, 10, 10], 'y'), 5.0)
        self.assertNotEqual(_axis_center([0, 10, 9, 20], 'y'),
                            ink_axis_center([0, 0, 10, 10], 'y'))
        self.assertEqual(ink_box_of({(2, 3)}), [2, 3, 3, 4])
        self.assertEqual(ink_axis_center([2, 3, 3, 4], 'x'), 2.5)

    def test_mirror_is_involution(self):
        from audit_axis_placement import mirror_ink
        ink = {(0, 0), (3, 0), (1, 2), (5, 4)}
        self.assertEqual(mirror_ink(mirror_ink(ink, 'x', 2.5), 'x', 2.5), ink)
        self.assertEqual(mirror_ink(mirror_ink(ink, 'y', 2.5), 'y', 2.5), ink)

    def test_offcurve_contour_closes(self):
        from audit_axis_placement import sample_closed_contour
        # All off-curve nodes: implied on-curve midpoints must close the loop.
        pts = [np.array(p, float) for p in [(0, 0), (10, 0), (10, 10), (0, 10)]]
        out = sample_closed_contour(pts, [0, 0, 0, 0], 0.25)
        self.assertGreater(len(out), 8)
        np.testing.assert_allclose(out[0], out[-1], atol=1e-9)

    def test_already_symmetric_no_op(self):
        from audit_axis_placement import symmetry_error, ink_mismatch
        square = [rect_samples(0, 0, 10, 10)]
        err = symmetry_error(square, 'x', 5.0)
        self.assertLess(err['max'], 1e-6)
        ink = {(x, y) for x in range(4) for y in range(4)}
        self.assertEqual(ink_mismatch(ink, 'x', 2.0)['mismatch'], 0)

    def test_disjoint_y_dot_stem_grouping(self):
        from audit_axis_placement import group_vertical
        stem, counter, dot = [0, 0, 10, 30], [3, 10, 7, 20], [3, 36, 7, 40]
        comps = group_vertical([stem, counter, dot], 5.0)
        self.assertEqual(len(comps), 2)
        # Counter stays with its enclosing outline; dot separates.
        grouped = sorted(c['contours'] for c in comps)
        self.assertEqual(grouped, [[0, 1], [2]])
        for comp in comps:
            self.assertEqual(comp['coaxial_offset'], 0.0)

    def test_rigid_move_preserves_shape(self):
        from audit_axis_placement import shift_coords, extent_of
        coords = np.array([[0., 0.], [10., 0.], [10., 30.], [3., 36.]])
        moved = shift_coords(coords, 0.25, 0.0)
        before = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=2)
        after = np.linalg.norm(moved[:, None, :] - moved[None, :, :], axis=2)
        np.testing.assert_allclose(before, after, atol=1e-12)
        before_box, after_box = extent_of(coords), extent_of(moved)
        self.assertAlmostEqual(after_box[2] - after_box[0], before_box[2] - before_box[0])
        self.assertAlmostEqual(after_box[3] - after_box[1], before_box[3] - before_box[1])
        np.testing.assert_allclose(moved - coords, [[0.25, 0.0]] * 4)


class PhaseRuleTests(unittest.TestCase):
    def test_trials_are_horizontal_only(self):
        from audit_axis_placement import _trial_deltas, PHASES
        deltas = _trial_deltas()
        self.assertEqual([dx for dx, _ in deltas], list(PHASES))
        self.assertTrue(all(dy == 0.0 for _, dy in deltas))

    def test_ownership_gate(self):
        from audit_axis_placement import _ownership_hold
        current = np.array([[0., 0.], [4., 0.]])
        owned = [{'point': 0, 'axis': 0, 'value': 0.0, 'stage': 's'}]
        held, worst = _ownership_hold(current + [[0.25, 0.], [0.25, 0.]], current, owned)
        self.assertTrue(held)
        self.assertEqual(worst, 0.25)
        held, _ = _ownership_hold(current, current, owned)
        self.assertFalse(held)
        # Unowned axes may move; empty ownership never holds.
        held, _ = _ownership_hold(current + [[0., 0.5], [0., 0.5]], current, owned)
        self.assertFalse(held)
        held, _ = _ownership_hold(current + [[0.5, 0.], [0.5, 0.]], current, [])
        self.assertFalse(held)

    def test_percentage_is_deferred(self):
        from audit_axis_placement import _is_deferred
        self.assertTrue(_is_deferred('%'))
        for char in ('+', 'T', '!', 'A', ' '):
            self.assertFalse(_is_deferred(char))

    def test_eligibility_needs_coaxial_symmetry(self):
        from audit_axis_placement import _eligible_components
        stem = rect_samples(0, 0, 10, 30)
        dot = rect_samples(3, 36, 7, 40)
        ends = [len(stem) - 1, len(stem) + len(dot) - 1]
        source_px = np.vstack([stem, dot])
        qualified = _eligible_components(source_px, ends, [stem, dot], 5.0)
        self.assertEqual(len(qualified), 2)
        # Shifted dot breaks coaxiality and reflection: no longer eligible.
        far = rect_samples(30, 36, 34, 40)
        source_px = np.vstack([stem, far])
        qualified = _eligible_components(source_px, ends, [stem, far], 5.0)
        self.assertEqual([c['contours'] for c in qualified], [[0]])

    def test_whole_unit_needs_source_symmetry(self):
        from audit_axis_placement import _candidate_units
        stem = rect_samples(0, 0, 10, 30)
        dot = rect_samples(3, 36, 7, 40)
        ends = [len(stem) - 1, len(stem) + len(dot) - 1]
        source_px = np.vstack([stem, dot])
        units, _, whole_ok, _ = _candidate_units(
            source_px, ends, [stem, dot], 5.0)
        self.assertTrue(whole_ok)
        self.assertIn('whole', [u for u, _ in units])
        # Asymmetric source (far dot) can never get a whole-shift unit.
        far = rect_samples(30, 36, 34, 40)
        source_px = np.vstack([stem, far])
        units, _, whole_ok, _ = _candidate_units(
            source_px, ends, [stem, far], 17.0)
        self.assertFalse(whole_ok)
        self.assertNotIn('whole', [u for u, _ in units])

    def test_component_qualifies_without_whole(self):
        from audit_axis_placement import _candidate_units
        # Symmetric foot plus a coaxial-but-internally-asymmetric top
        # (unequal arm heights): the whole outline is asymmetric, so no
        # whole-shift unit, while the foot still qualifies on its own.
        foot = rect_samples(-5, 0, 5, 4)
        left = rect_samples(-5, 36, -1, 38)
        right = rect_samples(1, 36, 5, 40)
        ends = [len(foot) - 1, len(foot) + len(left) - 1,
                len(foot) + len(left) + len(right) - 1]
        source_px = np.vstack([foot, left, right])
        units, _, whole_ok, _ = _candidate_units(
            source_px, ends, [foot, left, right], 0.0)
        self.assertFalse(whole_ok)
        self.assertEqual([u for u, _ in units], ['component@0'])

    def test_order_preserved_hold(self):
        from audit_axis_placement import _order_preserved_hold
        current = np.array([[0., 0.], [4., 0.], [0., 6.], [4., 6.]])
        relations = [{'a': 0, 'b': 2, 'axis': 0, 'value': 0.0,
                      'stage': 'contour-order'}]
        # Cross-component shift moves the pair difference: held.
        moved = current.copy()
        moved[2] += [0.25, 0.0]
        held, worst, rel = _order_preserved_hold(moved, current, relations)
        self.assertTrue(held)
        self.assertEqual(worst, 0.25)
        self.assertEqual((rel['a'], rel['b'], rel['axis']), (0, 2, 0))
        # Unmoved and sub-tolerance candidates pass; empty never holds.
        held, _, _ = _order_preserved_hold(current, current, relations)
        self.assertFalse(held)
        held, _, _ = _order_preserved_hold(current + 0.01, current, relations)
        self.assertFalse(held)
        held, _, _ = _order_preserved_hold(moved, current, [])
        self.assertFalse(held)
        # Rigid whole shifts preserve every difference: pass.
        held, _, _ = _order_preserved_hold(current + [0.5, 0.0], current,
                                           relations)
        self.assertFalse(held)


@unittest.skipUnless((CONSTRAINTS / 'report.json').exists(),
                     'constraints-v2 report absent')
class ZeroShiftTests(unittest.TestCase):
    def test_zero_shift_reproduces_all_records(self):
        import freetype as ft
        from audit_axis_placement import _load_inputs, _render_shifted
        from audit_terminal_coverage import coords
        report, admitted, faces, records, outlines = _load_inputs(CONSTRAINTS)
        self.assertEqual(len(admitted), 832)
        bad = []
        for case in admitted:
            key, char = case['key'], case['char']
            with self.subTest(key=key, char=char):
                size = int(key.rsplit('-', 1)[1])
                record = records[key][char]
                fitted = np.asarray(record['native_points_px'], float)
                glyph, ink = _render_shifted(faces[key], char, size, fitted, (0.0, 0.0))
                self.assertEqual(ink, {(x, y) for x, y in record['ink']})
                self.assertEqual(glyph['advance_26_6'], record['advance_26_6'])
                np.testing.assert_array_max_ulp(
                    coords(faces[key], char, size), fitted, maxulp=0)
                if ink != {(x, y) for x, y in record['ink']}:  # pragma: no cover
                    bad.append((key, char))
        self.assertEqual(bad, [])


@unittest.skipUnless((CONSTRAINTS / 'report.json').exists(),
                     'constraints-v2 report absent')
class ExportVerificationTests(unittest.TestCase):
    def _first_case(self):
        from audit_axis_placement import _load_inputs
        report, admitted, faces, records, outlines = _load_inputs(CONSTRAINTS)
        case = admitted[0]
        key, char = case['key'], case['char']
        points, ends, flags, em, size = outlines[(key, char)]
        return faces, records, key, char, points, em, size

    def _verify(self, tmp, dx):
        from audit_axis_placement import (_counters, _render_shifted,
                                          _verify_candidate_export)
        faces, records, key, char, points, em, size = self._first_case()
        record = records[key][char]
        fitted = np.asarray(record['native_points_px'], float)
        source_px = np.asarray(points, float) * (size / em)
        moved = fitted.copy() + np.array([dx, 0.0])
        selected_glyph, selected_ink = _render_shifted(
            faces[key], char, size, moved, (0.0, 0.0))
        _, base_ink = _render_shifted(
            faces[key], char, size, fitted, (0.0, 0.0))
        base_info = _counters(base_ink, fitted, source_px)
        base_dims = [base_info['bbox'][2] - base_info['bbox'][0],
                     base_info['bbox'][3] - base_info['bbox'][1]]
        target = Path(tmp) / 'candidate.ttf'
        proof = _verify_candidate_export(
            CONSTRAINTS / f'{key}-candidate.ttf', char, size, points, em,
            moved, selected_glyph, selected_ink, base_info, base_dims,
            target)
        return proof, selected_ink

    def test_export_zero_shift_agrees(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proof, _ = self._verify(tmp, 0.0)
            self.assertTrue(proof['verified'], proof.get('reason'))
            self.assertTrue(proof['bitmap_exact'])
            self.assertEqual(proof['bitmap_delta'], 0)
            self.assertLessEqual(proof['native_drift_px'], 1 / 128)
            self.assertTrue(proof['advance_unchanged'])
            self.assertTrue(proof['hmtx_unchanged'])

    def test_export_shifted_matches_selected_raster(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proof, selected_ink = self._verify(tmp, 0.25)
            self.assertTrue(proof['verified'], proof.get('reason'))
            self.assertTrue(proof['bitmap_exact'])
            self.assertLessEqual(proof['native_drift_px'], 1 / 128)
            self.assertTrue(proof['advance_unchanged'])
            self.assertTrue(proof['hmtx_unchanged'])


@unittest.skipUnless(
    (HERE / 'out' / 'axis-placement-candidate-v2' / 'report.json').exists(),
    'candidate-v2 report absent')
class CandidateV2ExportAgreementTests(unittest.TestCase):
    def test_every_accepted_row_has_export_proof(self):
        from audit_axis_placement import NATIVE_TOL_PX
        payload = json.loads(
            (HERE / 'out' / 'axis-placement-candidate-v2'
             / 'report.json').read_text())
        accepted = [c for c in payload['cases']
                    if c['status'] == 'accepted']
        for row in accepted:
            with self.subTest(key=row['key'], char=row['char']):
                self.assertTrue(row.get('export_verified'), row)
                proof = row.get('export_proof', {})
                self.assertTrue(proof.get('bitmap_exact'), proof)
                self.assertEqual(proof.get('bitmap_delta'), 0)
                self.assertLessEqual(proof.get('native_drift_px', 9),
                                     NATIVE_TOL_PX)
                self.assertTrue(proof.get('advance_unchanged'), proof)
                self.assertTrue(proof.get('hmtx_unchanged'), proof)
                self.assertEqual(proof.get('raster_mismatch'), 0)


if __name__ == '__main__':
    unittest.main()
