"""Focused checks for the consolidated source-to-bitmap pipeline.

Frozen specimens under ``out/`` are test references only: the runtime
generator (``build_source_bitmap.py``) may never read them, which these
tests enforce both statically and at runtime. Tests may identify glyphs;
the geometry API under test stays identity-free.
"""
import inspect
import json
import unittest
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
FROZEN = HERE / 'out/cumulative-hinter-v7'
FRESH = HERE / 'out/source-bitmap-v1'

# Historical output checkpoints: never generation inputs.
CHECKPOINT_DIRS = (
    'cumulative-hinter-v6', 'component-symmetry-v2', 'round-symmetry-v4',
    'curved-width-links-v2', 'source-junctions-v1', 'stem-relative-terminals-v1',
    'curved-stroke-recovery-v1', 'cumulative-hinter-v7', 'geometric-candidate-v3',
    'shamir-representative-comparison', 'shamir-controlled', 'shamir-baseline-v6',
)


class StageOrderTests(unittest.TestCase):
    def test_only_approved_stages(self):
        from build_source_bitmap import STAGE_ORDER
        self.assertIn('curved-stroke-recovery', STAGE_ORDER)
        for banned in ('axis-consistency', 'axis_consistency', 'junction-terminals',
                       'endpoint-cap', 'junction_terminals'):
            self.assertNotIn(banned, ' '.join(STAGE_ORDER))

    def test_no_checkpoint_imports_or_paths(self):
        import re
        import build_source_bitmap
        source = Path(build_source_bitmap.__file__).read_text()
        self.assertIsNone(
            re.search(r'^\s*(from|import)\s+cumulative_inputs\b', source, re.M))
        self.assertNotIn('axis_consistency', source)
        self.assertIsNone(
            re.search(r'^\s*(from|import)\s+junction_terminal_fit\b', source, re.M))
        for name in CHECKPOINT_DIRS:
            self.assertNotIn(name, source)

    def test_geometry_api_is_identity_free(self):
        from geometric_candidate import Geometry, correct
        from cumulative_hinter import finalize
        import curved_width_links
        import stem_relative_terminals
        import repeated_component_symmetry
        import round_component_fit
        fields = set(Geometry.__dataclass_fields__)
        self.assertEqual(fields, {'points', 'ends', 'flags', 'ppem', 'em',
                                  'constraints', 'members'})
        for fn in (correct, finalize, curved_width_links.fit,
                   stem_relative_terminals.fit, repeated_component_symmetry.fit,
                   round_component_fit.fit):
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(params & {'char', 'font', 'face', 'face_name', 'glyph',
                                       'glyph_id', 'codepoint', 'family', 'key'},
                             (fn.__module__, params))


class InputGuardTests(unittest.TestCase):
    def test_historical_outputs_are_forbidden(self):
        import tempfile
        from build_source_bitmap import Pipeline, ForbiddenInput
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'fresh'
            out.mkdir()
            pipeline = Pipeline.__new__(Pipeline)
            from build_source_bitmap import HERE as H
            pipeline.output = out
            pipeline.work = Path(tmp)
            pipeline.inputs = {}
            pipeline._resolved = {}
            pipeline.provenance = {}
            for name in CHECKPOINT_DIRS:
                with self.assertRaises(ForbiddenInput, msg=name):
                    pipeline.use_input(H / 'out' / name / 'report.json')
            with self.assertRaises(ForbiddenInput):
                pipeline.use_input(H / 'out/shamir-controlled/roboto-16-source.ttf')
            # Genuine inputs pass: source fonts, job configuration, own output.
            pipeline.use_input(H / 'fonts/Roboto.ttf')
            target = out / 'wrote.ttf'
            target.write_bytes(b'x')
            pipeline.use_input(target)

    def test_fresh_report_inputs_are_reusable(self):
        report = json.loads((FRESH / 'report.json').read_text())
        blob = json.dumps(report['inputs']) + json.dumps(report['provenance'])
        for marker in ('/Users/', '/tmp/', '/var/', '\\Users\\', 'source-bitmap-'):
            self.assertNotIn(marker, blob, marker)
        self.assertNotIn('resolved_inputs', report['provenance'])
        for display in report['inputs']:
            self.assertFalse(Path(display).is_absolute(), display)
            if display.endswith('.py'):
                continue
            target = Path(__file__).resolve().parents[2] / display
            self.assertTrue(target.exists(), display)
            self.assertFalse(
                target.is_relative_to((HERE / 'out').resolve())
                and target.parent.name != FRESH.name,
                display)
        for field in ('python', 'freetype', 'fonttools', 'numpy', 'pillow'):
            self.assertIn(field, report['provenance']['environment'])
        keys = sorted({r['key'] for r in report['cases']})
        self.assertEqual(sorted(report['provenance']['exports']['bitmaps']),
                         [f'{k}-bitmap.json' for k in keys])
        self.assertEqual(sorted(p.name for p in FRESH.glob('*-bitmap.json')),
                         [f'{k}-bitmap.json' for k in keys])


@unittest.skipUnless((HERE / 'out/shamir-controlled/roboto-16-source.ttf').exists(),
                     'frozen source reference absent')
class SourceRegenerationTests(unittest.TestCase):
    def test_instantiation_reproduces_frozen_static(self):
        import tempfile
        from check_shamir_baseline import digest
        from compare_shamir_pipeline import instance
        job = json.loads((HERE.parent / 'font_generator/examples/roboto.json').read_text())
        source = (HERE.parent / 'font_generator/examples' / job['font']).resolve()
        self.assertEqual(digest(source), job['provenance']['expected_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / 'static.ttf'
            instance(source, dst, {'wght': 400, 'wdth': 100})
            self.assertEqual(
                digest(dst),
                digest(HERE / 'out/shamir-controlled/roboto-16-source.ttf'))

    def test_baseline_model_matches_frozen_record(self):
        from compare_shamir_pipeline import CHARS
        from shamir_model import build_font, constraints_for, feature_model
        from shamir_representative_search import representative_override
        import tempfile
        frozen = json.loads(
            (HERE / 'out/shamir-representative-comparison/roboto-16-model.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / 'experiment.ttf'
            with representative_override(256):
                model = build_font(HERE / 'out/shamir-controlled/roboto-16-source.ttf',
                                   dst, CHARS, profile='baseline', ppem=16)
            live = model['records']['A']['graph']
            # New glyph-bound labels (this task's metadata) are asserted
            # explicitly at the expected extrema, then stripped on copies
            # before comparing the numerical graph to the frozen record.
            bound = [c for c in live['constraints']
                     if c.get('metric_role') in ('glyph-x-bound', 'glyph-y-bound')]
            self.assertEqual(
                sorted(c.get('metric_role') for c in bound),
                ['glyph-x-bound', 'glyph-x-bound', 'glyph-y-bound'])
            for c in bound:
                self.assertTrue(c.get('metric'))
            self.assertEqual(
                [c['kind'] for c in bound if c['metric_role'] == 'glyph-x-bound'],
                ['Abs', 'Dist'])
            self.assertFalse(any(
                c.get('metric_role') in ('glyph-x-bound', 'glyph-y-bound')
                for c in frozen['records']['A']['graph']['constraints']))
            live_copy = json.loads(json.dumps(live))
            frozen_copy = json.loads(json.dumps(frozen['records']['A']['graph']))
            for c in live_copy['constraints']:
                if c.get('metric_role') in ('glyph-x-bound', 'glyph-y-bound'):
                    del c['metric_role']
            self.assertEqual(
                json.dumps(live_copy, sort_keys=True),
                json.dumps(frozen_copy, sort_keys=True))


class ExportAuditTests(unittest.TestCase):
    """Exported rows carry their own character's upstream owners/order."""

    def test_upstream_audit_associates_own_character(self):
        from build_source_bitmap import _export_row_status
        live = {
            'A': {'audit': {'ownership': [{'point': 1, 'sentinel': 'A'}],
                            'order_relations': ['A-order']}},
            'B': {'audit': {'ownership': [{'point': 2, 'sentinel': 'B'}],
                            'order_relations': ['B-order']}},
        }
        fitted = np.array([[0., 0.], [4., 0.], [0., 6.]])
        rows = {}
        for char in ('A', 'B'):
            row = {}
            delta = _export_row_status(
                char, live, row, fitted, {(0, 0)}, fitted, (100, 0),
                {'stage': 's'}, fitted, {(0, 0)}, (100, 0))
            self.assertEqual(delta, 0)
            self.assertEqual(row['status'], 'retained')
            rows[char] = row
        # Distinct sentinels prove per-character association (a loop-leftover
        # binding would stamp both rows with the last character's audit).
        for char in ('A', 'B'):
            owners = rows[char]['upstream_audit']['ownership']
            self.assertEqual([o['sentinel'] for o in owners], [char])
            self.assertEqual(rows[char]['upstream_audit']['order_relations'],
                             [f'{char}-order'])
        self.assertNotEqual(rows['A']['upstream_audit'],
                            rows['B']['upstream_audit'])

    def test_upstream_audit_is_a_copy(self):
        from build_source_bitmap import _export_row_status
        live = {'A': {'audit': {'ownership': [{'point': 1}]}}}
        fitted = np.array([[0., 0.], [4., 0.], [0., 6.]])
        row = {}
        _export_row_status('A', live, row, fitted, {(0, 0)}, fitted, (100, 0),
                           {'stage': 's'}, fitted, {(0, 0)}, (100, 0))
        self.assertIsNot(row['upstream_audit'], live['A']['audit'])
        row['upstream_audit']['ownership'].append({'point': 9})
        self.assertEqual(live['A']['audit'], {'ownership': [{'point': 1}]})


def iter_admitted(report):
    return [(r['key'], r['char']) for r in report['cases'] if r['status'] != 'upstream-rejected']


def render_ink(face, char, size):
    from compare_paper_prototypes import render, pixels
    return pixels(render(face, char, size, hinted=True))


@unittest.skipUnless(FRESH.exists() and FROZEN.exists(), 'specimen directories absent')
class ParityTests(unittest.TestCase):
    def test_summary_and_coverage(self):
        fresh = json.loads((FRESH / 'report.json').read_text())
        frozen = json.loads((FROZEN / 'report.json').read_text())
        self.assertEqual(fresh['summary'], {'retained': 825, 'upstream-rejected': 49, 'changed': 7})
        fresh_cases = {(r['key'], r['char']) for r in fresh['cases']}
        frozen_cases = {(r['key'], r['char']) for r in frozen['cases']}
        self.assertEqual(fresh_cases, frozen_cases)
        self.assertEqual(len(iter_admitted(fresh)), 832)
        rejected = sorted(k for k, r in
                          [((r['key'], r['char']), r) for r in fresh['cases']]
                          if r['status'] == 'upstream-rejected')
        frozen_rejected = sorted(k for k, r in
                                 [((r['key'], r['char']), r) for r in frozen['cases']]
                                 if r['status'] == 'upstream-rejected')
        self.assertEqual(rejected, frozen_rejected)
        self.assertEqual(len(rejected), 49)

    def test_full_bitmap_advance_and_coordinate_parity(self):
        from audit_terminal_coverage import coords
        fresh = json.loads((FRESH / 'report.json').read_text())
        frozen = json.loads((FROZEN / 'report.json').read_text())
        frozen_status = {(r['key'], r['char']): r for r in frozen['cases']}
        keys = sorted({k for k, _ in iter_admitted(fresh)})
        for key in keys:
            size = int(key.rsplit('-', 1)[1])
            with TTFont(FRESH / f'{key}-candidate.ttf') as a, \
                    TTFont(FROZEN / f'{key}-candidate.ttf') as b:
                self.assertEqual(set(a.getBestCmap()), set(b.getBestCmap()), key)
                fa, fb = ft.Face(str(FRESH / f'{key}-candidate.ttf')), \
                    ft.Face(str(FROZEN / f'{key}-candidate.ttf'))
                for code in sorted(set(a.getBestCmap())):
                    char = chr(code)
                    with self.subTest(key=key, char=char):
                        self.assertEqual(render_ink(fa, char, size),
                                         render_ink(fb, char, size))
                        self.assertEqual(a['hmtx'][a.getBestCmap()[code]],
                                         b['hmtx'][b.getBestCmap()[code]])
                        np.testing.assert_array_max_ulp(
                            coords(fa, char, size), coords(fb, char, size), maxulp=0)
                        row = next(r for r in fresh['cases']
                                   if r['key'] == key and r['char'] == char)
                        self.assertEqual(row['status'], frozen_status[(key, char)]['status'])
                        self.assertEqual(row.get('changed_pixels'),
                                         frozen_status[(key, char)].get('changed_pixels'))


def face_bitmap_pairs(root=None):
    """(key, bitmap JSON, TTF) triples where the export exists."""
    from build_source_bitmap import FACES
    from compare_shamir_pipeline import SIZES
    pairs = []
    for name in FACES:
        for size in SIZES:
            key = f'{name}-{size}'
            face_json, ttf = (root or FRESH) / f'{key}-bitmap.json', \
                (root or FRESH) / f'{key}-candidate.ttf'
            if face_json.exists() and ttf.exists():
                pairs.append((key, face_json, ttf))
    return pairs


@unittest.skipUnless(FRESH.exists(), 'fresh specimen directory absent')
class ExportAgreementTests(unittest.TestCase):
    """Exported bitmap/metric JSON agrees with rendering the exported TTF."""

    def test_exported_records_match_ttf_render(self):
        import source_bitmap_output as output_mod
        pairs = face_bitmap_pairs()
        self.assertTrue(pairs, 'no exported bitmap JSON; regenerate the specimen')
        for key, face_json, ttf in pairs:
            with self.subTest(key=key):
                self.assertEqual(output_mod.check_face_agreement(face_json, ttf), [])

    def test_exported_records_carry_bitmap_and_metrics(self):
        pairs = face_bitmap_pairs()
        self.assertTrue(pairs, 'no exported bitmap JSON; regenerate the specimen')
        for key, face_json, _ in pairs:
            data = json.loads(face_json.read_text())
            self.assertEqual(data['key'], key)
            admitted = {c for k, c in iter_admitted(
                json.loads((FRESH / 'report.json').read_text())) if k == key}
            self.assertEqual(set(data['glyphs']), admitted)
            for char, record in data['glyphs'].items():
                with self.subTest(key=key, char=char):
                    for field in ('width', 'height', 'left', 'top', 'advance_26_6',
                                  'advance_hmtx', 'pixels', 'ink', 'native_points_px'):
                        self.assertIn(field, record)
                    self.assertEqual(len(record['pixels']),
                                     record['width'] * record['height'])

    def test_specimen_pngs_are_reviewable(self):
        from PIL import Image
        import source_bitmap_output as output_mod
        pairs = face_bitmap_pairs()
        self.assertTrue(pairs, 'no exported bitmap JSON; regenerate the specimen')
        for key, face_json, _ in pairs:
            data = json.loads(face_json.read_text())
            page = (FRESH / f'{key}.html').read_text()
            for char, record in data['glyphs'].items():
                code = f'u{ord(char):04x}'
                native = FRESH / f'img/{key}-{code}-native.png'
                large = FRESH / f'img/{key}-{code}-x{output_mod.ENLARGE}.png'
                with self.subTest(key=key, char=char):
                    self.assertTrue(native.exists())
                    self.assertTrue(large.exists())
                    with Image.open(native) as a, Image.open(large) as b:
                        self.assertEqual(
                            b.size, (a.size[0] * output_mod.ENLARGE,
                                     a.size[1] * output_mod.ENLARGE))
                    self.assertIn(f'{key}-{code}-native.png', page)
                    self.assertIn(f'{key}-{code}-x{output_mod.ENLARGE}.png', page)


if __name__ == '__main__':
    unittest.main()
