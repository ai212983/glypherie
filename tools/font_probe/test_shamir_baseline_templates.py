import unittest
from shamir_baseline_templates import recognize_sequence_pool, recognize_baseline_templates, instantiate_baseline_templates, PUBLISHED_SEQUENCES


class BaselineTemplates(unittest.TestCase):
    def test_published_sequence_set_is_frozen(self):
        # B05 coverage boundary: complex-feature coverage is exactly the
        # two published sequences. Silent library expansion without a new
        # decision fails here.
        self.assertEqual(PUBLISHED_SEQUENCES, {
            'MinchoBarCap': [['HR', 'CH', 'T', 'V', 'T']],
            'RomanSerif': [['T', 'T', 'LR', 'LR', 'LR', 'LR', 'T', 'T']],
        })

    def test_unrecognized_form_falls_back_to_basic_features(self):
        # B05 fallback is total and explicit: a non-matching form yields
        # zero template constraints with unchanged coverage strings, while
        # the ordinary basic-feature path still recognizes the shape.
        import numpy as np
        from test_shamir_features import polygon
        from shamir_geometry import prepare
        from shamir_model import feature_model
        tokens = ['T', 'T', 'T']
        points = np.array([[0., 0.], [10., 0.], [10., 10.]])
        model = dict(points=[dict(id=i, categories=[token]) for i, token in enumerate(tokens)],
                     segments=[dict(start=i, end=(i + 1) % 3, control=[points[i], points[(i + 1) % 3]])
                               for i in range(3)], contours=[list(range(3))])
        result = recognize_baseline_templates(model)
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['bindings'], [])
        self.assertEqual(result['recipe_coverage'],
                         'none; complex-feature hinting unsupported')
        self.assertEqual(result['classification'], 'conservative limited coverage')
        constraints, report = instantiate_baseline_templates(
            model, {0: 0, 1: 1, 2: 2}, points)
        self.assertEqual(constraints, [])
        self.assertEqual(report['unconfigured'], [])
        self.assertEqual(report['recipe_coverage'],
                         'two published recognizers; conservative local translation recipes')
        # Categorical rejection through the real loop: five events admit
        # the MinchoBarCap machine, but wrong categories match nothing.
        long_tokens = ['T'] * 5
        long_model = dict(
            points=[dict(id=i, categories=[token]) for i, token in enumerate(long_tokens)],
            segments=[dict(start=i) for i in range(5)], contours=[list(range(5))])
        self.assertEqual(recognize_baseline_templates(long_model)['matches'], [])
        prep = prepare([polygon([(0, 0), (100, 0), (100, 700), (0, 700)])], 1000)
        rect = feature_model(prep, baseline=True)
        self.assertTrue(rect['features'])
        self.assertEqual(recognize_baseline_templates(prep)['matches'], [])

    def test_calibration_match_set_is_pinned(self):
        # B05 corpus pin: exactly these calibration glyphs match a
        # published sequence. Extraction changes moving forms in or out of
        # complex-feature coverage fail loudly here.
        from pathlib import Path
        from fontTools.ttLib import TTFont
        from compare_shamir_pipeline import CHARS
        from shamir_geometry import from_font
        root = Path(__file__).parent / 'fonts'
        expected = {'Roboto.ttf': set('BDPR69'),
                    'Literata.ttf': set('AVWYvwy'),
                    'SourceSans3.ttf': set('BDPR')}
        for filename, chars in expected.items():
            font = TTFont(str(root / filename), recalcTimestamp=False)
            matched = {}
            for char in CHARS:
                names = {h['name'] for h in
                         recognize_baseline_templates(
                             from_font(font, char, baseline=True))['matches']}
                if names:
                    matched[char] = names
            self.assertEqual(set(matched), chars, filename)
            for char, names in matched.items():
                self.assertEqual(names, {'MinchoBarCap'}, (filename, char))
    def recognize(self, text, templates):
        return recognize_sequence_pool(list(range(len(text))),
                                       {i: [c] for i, c in enumerate(text)}, templates)

    def test_acceptance_resets_other_machines(self):
        templates = {'short': {'sequences': [['A', 'B']]},
                     'long': {'sequences': [['A', 'B', 'C']]}}
        self.assertEqual([h['name'] for h in self.recognize('ABC', templates)], ['short'])

    def test_declared_subautomaton_preserves_including_machine(self):
        templates = {'short': {'sequences': [['A', 'B']]},
                     'long': {'sequences': [['A', 'B', 'C']], 'subautomata': ['short']}}
        self.assertEqual([h['name'] for h in self.recognize('ABC', templates)], ['short', 'long'])

    def test_wraparound_and_failed_prefix(self):
        templates = {'match': {'sequences': [['A', 'A', 'B']]}}
        self.assertEqual(self.recognize('ABAA', templates),
                         [dict(name='match', points=[3, 0, 1])])

    def test_unconfigured_published_example_is_reported(self):
        tokens = ['HR', 'CH', 'T', 'V', 'T']
        model = dict(points=[dict(id=i, categories=[token]) for i, token in enumerate(tokens)],
                     segments=[dict(start=i) for i in range(5)], contours=[list(range(5))])
        result = recognize_baseline_templates(model)
        self.assertEqual(result['matches'], [dict(name='MinchoBarCap', points=list(range(5)))])
        self.assertEqual(len(result['unconfigured']), 1)
        self.assertEqual(result['bindings'], [])

    def test_conservative_recipe_preserves_local_offsets(self):
        import numpy as np
        tokens = ['HR', 'CH', 'T', 'V', 'T']
        points = np.array([[2., 3.], [8., 5.], [7., 10.], [3., 12.], [1., 4.]])
        model = dict(points=[dict(id=i, categories=[token]) for i, token in enumerate(tokens)],
                     segments=[dict(start=i, end=(i+1)%5, control=[points[i], points[(i+1)%5]])
                               for i in range(5)], contours=[list(range(5))])
        constraints, report = instantiate_baseline_templates(model, dict(enumerate(range(5))), points)
        self.assertEqual(len(constraints), 10)
        self.assertEqual(report['unconfigured'], [])
        for c in constraints:
            n = np.array(c['normal'])
            if c['kind'] == 'Dist':
                self.assertFalse(c['round'])
                self.assertEqual(c['sources'], [0])
                self.assertAlmostEqual(c['value'], float((points[c['point']] - points[0]) @ n))
        self.assertEqual(report['bindings'], [])

    def test_curve_controls_and_skipped_joins_translate_with_feature(self):
        import numpy as np
        from shamir_segment_fit import prepared_glyph
        from shamir_baseline_solver import resolve_baseline, evaluate_baseline
        positions = [[3, 4], [4, 7], [8, 9], [10, 12], [5, 17], [2, 12], [-2, 2]]
        tokens = ['HR', 'CT', 'CH', 'T', 'V', 'T', 'line']
        segments = [dict(start=i, end=(i+1)%7,
                         control=[positions[i], positions[(i+1)%7]]) for i in range(7)]
        segments[0]['control'].insert(1, [5, 6])
        segments[1]['control'].insert(1, [6, 8])
        # Outgoing control after the final match must remain outside the recipe.
        segments[5]['control'].insert(1, [-1, 9])
        model = dict(points=[dict(id=i, categories=[token]) for i, token in enumerate(tokens)],
                     segments=segments, contours=[list(range(7))])
        glyph, mapping, _ = prepared_glyph(model)
        points = np.asarray(glyph.coordinates, float)
        constraints, report = instantiate_baseline_templates(model, mapping, points)
        hit = report['matches'][0]
        self.assertIn(mapping[1], hit['native_members'])
        self.assertIn(mapping[0]+1, hit['native_members'])
        self.assertNotIn(mapping[5]+1, hit['native_members'])
        members = [c for c in constraints if c.get('template_member')]
        self.assertTrue(members)
        self.assertTrue(all(c['kind'] == 'Dist' and c['sources'] == [mapping[0]] for c in members))
        graph = resolve_baseline(points, constraints)
        fitted, _ = evaluate_baseline(graph, points, 16, 1000)
        translation = fitted[mapping[0]] - points[mapping[0]]*.016
        for pid in hit['native_members']:
            np.testing.assert_allclose(fitted[pid], points[pid]*.016+translation, atol=1e-12)
        np.testing.assert_allclose(fitted[mapping[5]+1], points[mapping[5]+1]*.016, atol=1e-12)

    def test_bad_subautomaton_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, 'unknown subautomata'):
            self.recognize('A', {'x': {'sequences': [['A']], 'subautomata': ['missing']}})


if __name__ == '__main__':
    unittest.main()
