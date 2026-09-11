"""Architectural guardrails for the current identity-free correction boundary."""
import ast
import inspect
from pathlib import Path
import unittest
from geometric_candidate import Geometry, equation, correct, STAGES


class BoundaryTests(unittest.TestCase):
    def test_identity_and_arbitrary_provenance_do_not_cross_boundary(self):
        raw=dict(kind='Abs',point=0,normal=[1,0],sources=[],value=3,
                 char='E',glyph_name='E',family='Literata',feature='special-E',default_reason='E only')
        data=Geometry(((0,0),),(0,),(1,),16,1000,(raw,),())
        self.assertEqual(data.constraints[0],dict(kind='Abs',point=0,normal=[1,0],sources=[],value=3))
        with self.assertRaises(TypeError):
            Geometry(((0,0),),(0,),(1,),16,1000,(),(),char='E')

    def test_numeric_segment_provenance_survives(self):
        self.assertEqual(equation(dict(feature='align-7')),dict(feature='align-7'))
        self.assertEqual(equation(dict(feature='segment-17')),dict(feature='segment-17'))

    def test_no_correction_overrides_or_identity_parameters(self):
        self.assertEqual(list(inspect.signature(correct).parameters),['data','center_fit'])
        self.assertEqual(STAGES,('reorientation','parent-anchor','serifs','coordinated-terminals','paired-terminal'))
        with self.assertRaises(TypeError):correct({'char':'E'})

    def test_boundary_has_no_identity_or_io_access(self):
        tree=ast.parse(Path(inspect.getfile(correct)).read_text())
        forbidden={'char','character','glyph','glyph_name','family','font_name','codepoint',
                   'ord','chr','open','eval','exec','__import__'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Name):self.assertNotIn(node.id,forbidden)
            if isinstance(node,ast.Constant) and isinstance(node.value,str):self.assertNotIn(node.value,forbidden)
        allowed={'dataclasses','re','numpy','shamir_reorientation','shamir_parent_anchor',
                 'vtt_serif_experiment','vtt_terminal_links','shamir_constraints','shamir_baseline_solver','opposing_terminals'}
        for node in tree.body:
            if isinstance(node,ast.ImportFrom):self.assertIn(node.module,allowed)
            if isinstance(node,ast.Import):
                for alias in node.names:self.assertIn(alias.name,allowed)


class CenterFitWiringTests(unittest.TestCase):
    def test_known_translation_reaches_preterminal(self):
        import numpy as np
        import geometric_candidate as gc
        pts = ((0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0))
        data = Geometry(pts, (3,), (1, 1, 1, 1), 16, 1000, (), ())
        shift = np.array([[1.5, -2.5]] * 4)
        def fake_center_fit(points, ends, flags, current, scale):
            return np.asarray(current, float) + shift, dict(status='candidate')
        # Isolate wiring: passthrough unrelated stages.
        orig_proto, orig_exp = gc.prototype, gc.experiment
        orig_roles, orig_fit = gc.serif_roles, gc.fit_serifs
        orig_cand, orig_opp = gc.candidates, gc.opposing_roles
        gc.prototype = lambda record: dict(removed=[])
        gc.experiment = lambda oriented, points, ppem, em, flag: dict(
            graph=dict(baseline_execution=dict(model_points_px=np.asarray(points, float).tolist())),
            changes=[])
        gc.serif_roles = lambda *a: []
        gc.fit_serifs = lambda points, before, halves, scale: (np.asarray(before, float), [])
        gc.candidates = lambda *a: []
        gc.opposing_roles = lambda *a: []
        try:
            out = gc.correct(data, center_fit=fake_center_fit)
            plain = gc.correct(data)
        finally:
            gc.prototype, gc.experiment = orig_proto, orig_exp
            gc.serif_roles, gc.fit_serifs = orig_roles, orig_fit
            gc.candidates, gc.opposing_roles = orig_cand, orig_opp
        pre = np.asarray(out['preterminal'], float)
        base = np.asarray(plain['preterminal'], float)
        self.assertTrue(np.allclose(pre, base + shift))
        self.assertEqual(out.get('central_upright'), dict(status='candidate'))
        self.assertNotIn('central_upright', plain)


if __name__=='__main__':unittest.main()
