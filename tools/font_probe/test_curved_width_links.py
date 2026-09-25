"""Curve pairing and width links without calibration glyph identities."""
import unittest
import numpy as np
from shamir_geometry import prepare
from shamir_segment_fit import prepared_glyph
from curved_width_links import detect,fit
from curved_pair_support import pairs
from shamir_features import Interior


def oval(x0,y0,x1,y1):
    cx=(x0+x1)/2;cy=(y0+y1)/2
    return [[[x0,cy],[x0,y1],[cx,y1]],[[cx,y1],[x1,y1],[x1,cy]],
            [[x1,cy],[x1,y0],[cx,y0]],[[cx,y0],[x0,y0],[x0,cy]]]


def ring(reverse=False,start=0):
    contours=[oval(0,0,500,500),[s[::-1] for s in oval(100,100,400,440)[::-1]]]
    if reverse:contours=[[s[::-1] for s in c[::-1]] for c in contours]
    contours=[c[start:]+c[:start] for c in contours]
    m=prepare(contours,1000,baseline=True);m['scale']=.014
    return m


class CurvedWidthTests(unittest.TestCase):
    def test_displaced_extrema_are_recognized_in_both_windings_and_starts(self):
        for reverse in (False,True):
            for start in range(4):
                fs=[f for f in detect(ring(reverse,start)) if f['axis']==0]
                self.assertEqual(len(fs),2)
                self.assertTrue(all(f['new'] for f in fs))
                self.assertEqual(sorted(f['width'] for f in fs),[100,100])

    def test_counter_is_never_recognized_as_black_stroke(self):
        m=ring()
        for axis in (0,1):
            for a,b in pairs(m,axis,Interior(m)):
                self.assertNotEqual(a['contour'],b['contour'])

    def test_links_fix_opposing_widths_preserving_outer_and_other_axis(self):
        m=ring();g,mapping,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        fs=[f for f in detect(m) if f['axis']==0]
        outers=[]
        for f in fs:
            a,b=f['points'];pa,pb=m['points'][a],m['points'][b]
            sign=1 if pa['extrema']['0']=='min' else -1
            if sign*(pa['position'][0]-pb['position'][0])>0:a,b=b,a
            outer,inner=mapping[a],mapping[b];outers.append(outer)
            q[inner,0]=q[outer,0]+sign*(2 if sign==1 else 1)
        result,audit=fit(m,q)
        self.assertTrue(audit['links'])
        np.testing.assert_array_equal(result[:,1],q[:,1])
        np.testing.assert_array_equal(result[outers],q[outers])
        self.assertTrue(all(l['after_width_px']==1 for l in audit['links']))

    def test_owned_inner_coordinate_conflict_is_explicit(self):
        m=ring();g,mapping,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        f=next(f for f in detect(m) if f['axis']==0)
        inner=next(mapping[i] for i in f['points'] if m['points'][i]['contour']==1)
        with self.assertRaisesRegex(ValueError,'owned coordinate'):
            fit(m,q,[dict(point=inner,axis=0,value=q[inner,0])])

    def test_straddling_sides_take_shared_stem_target(self):
        # Literata O/Q sides: a 106u/109u pair straddles the pixel
        # boundary (1.484/1.526px at 14px); the local mean (1.505px)
        # rounds up to 2px, but the pair falls in the 1px stem class
        # and must take its target (Shamir 2003 sections 3.4-3.5, 5).
        outer = oval(0, 0, 500, 500)
        inner = [s[::-1] for s in oval(106, 100, 391, 440)[::-1]]
        m = prepare([outer, inner], 1000, baseline=True)
        m['scale'] = .014
        table = {'ppem': 14, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 99.0, 'members': [],
             'target_px': 1, 'reason': 'stem test class'}]}
        g, _, _ = prepared_glyph(m)
        q = np.asarray(g.coordinates) * m['scale']
        _, audit = fit(m, q, (), width_table=table)
        sides = [l for l in audit['links'] if l['axis'] == 0]
        self.assertEqual(len(sides), 2)
        self.assertTrue(all(l['target_width_px'] == 1 for l in sides))

    def test_hold_or_widen_never_narrows_fitted(self):
        # Horizontal bands hold or widen but never narrow the fitted
        # width: sides fitted at 1.7px take a shared 2px target even
        # though it exceeds the design mean (literata-16 O,
        # literata-18 0: the moved outlines feed the bytecode).
        outer = oval(0, 0, 500, 500)
        inner = [s[::-1] for s in oval(121, 100, 376, 440)[::-1]]
        m = prepare([outer, inner], 1000, baseline=True)
        m['scale'] = .014
        table = {'ppem': 14, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 110.0, 'members': [],
             'target_px': 2, 'reason': 'stem test class'}]}
        g, _, _ = prepared_glyph(m)
        q = np.asarray(g.coordinates) * m['scale']
        _, audit = fit(m, q, (), width_table=table)
        sides = [l for l in audit['links'] if l['axis'] == 0]
        self.assertEqual(len(sides), 2)
        self.assertTrue(all(l['target_width_px'] == 2 for l in sides))

    def test_narrowing_link_holds_solver_width(self):
        # Literata-16 m/n regression (bow probe, 2026-09-15): arch
        # sides at 1.12px design take a unanimous 1px shared target
        # while the solver honestly fits 2.0px — and both oracle
        # witnesses agree at 2px (m W=5 C=35, n W=3 C=20,
        # settled REJECTs of the 1px program). The old
        # above-14px outright-claim rule narrowed these sides to
        # the target; its two foundations are gone — v1 parity
        # (the census tripwire, never a judge since the
        # evaluation protocol of 2026-09-15) and the scaler
        # claim (literata-16 O/Q and roboto-16 8, cited for the
        # old rule, all probe UNSETTLED at W=17/29/14: no
        # established target anywhere). The link layer therefore
        # holds or widens like the solver layer
        # (``standardize_hard_widths`` widen-only) and never
        # narrows a fitted width, at every size. The production
        # table keeps the (now link-ignored) ``arc_sharing``
        # key, which the joint solver still consults.
        outer = oval(0, 0, 500, 500)
        inner = [s[::-1] for s in oval(70, 100, 427, 440)[::-1]]
        m = prepare([outer, inner], 1000, baseline=True)
        m['scale'] = .016
        table = {'ppem': 16, 'em': 1000, 'cut_in_px': 1.0,
                 'arc_sharing': False,
                 'clusters': [
                     {'design_mean_units': 71.5, 'members': [],
                      'target_px': 1, 'reason': 'thin test class'}]}
        g, mapping, _ = prepared_glyph(m)
        q = np.asarray(g.coordinates) * m['scale']
        for f in [f for f in detect(m) if f['axis'] == 0]:
            a, b = f['points']
            pa, pb = m['points'][a], m['points'][b]
            sign = 1 if pa['extrema']['0'] == 'min' else -1
            if sign * (pa['position'][0] - pb['position'][0]) > 0:
                a, b = b, a
            outer_i, inner_i = mapping[a], mapping[b]
            q[inner_i, 0] = q[outer_i, 0] + sign * 2.0
        _, audit = fit(m, q, (), width_table=table)
        sides = [l for l in audit['links'] if l['axis'] == 0]
        self.assertEqual(sides, [])

    def test_narrowing_fitted_width_skips(self):
        # The same cluster withholds when the shared target would
        # narrow an honestly wider fitted band (literata-18 p bowl:
        # 3px fitted keeps the solver fit, never starves to 2px).
        outer = oval(0, 0, 500, 500)
        inner = [s[::-1] for s in oval(121, 100, 376, 440)[::-1]]
        m = prepare([outer, inner], 1000, baseline=True)
        m['scale'] = .014
        table = {'ppem': 14, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 110.0, 'members': [],
             'target_px': 2, 'reason': 'stem test class'}]}
        g, mapping, _ = prepared_glyph(m)
        q = np.asarray(g.coordinates) * m['scale']
        for f in [f for f in detect(m) if f['axis'] == 0]:
            a, b = f['points']
            pa, pb = m['points'][a], m['points'][b]
            sign = 1 if pa['extrema']['0'] == 'min' else -1
            if sign * (pa['position'][0] - pb['position'][0]) > 0:
                a, b = b, a
            outer_i, inner_i = mapping[a], mapping[b]
            q[inner_i, 0] = q[outer_i, 0] + sign * 3.0
        _, audit = fit(m, q, (), width_table=table)
        sides = [l for l in audit['links'] if l['axis'] == 0]
        self.assertEqual(sides, [])

    def test_straddling_sides_keep_local_rounding_without_table(self):
        # No width table: the local mean straddles 1.5px and would round
        # up to 2px, but curved sharing never thickens (Shamir 2003 §3.5
        # thins only), so the cluster is skipped and the solver fit stands.
        outer = oval(0, 0, 500, 500)
        inner = [s[::-1] for s in oval(106, 100, 391, 440)[::-1]]
        m = prepare([outer, inner], 1000, baseline=True)
        m['scale'] = .014
        g, _, _ = prepared_glyph(m)
        q = np.asarray(g.coordinates) * m['scale']
        _, audit = fit(m, q)
        sides = [l for l in audit['links'] if l['axis'] == 0]
        self.assertEqual(sides, [])

    def test_subdivision_does_not_change_pairing(self):
        from fontTools.misc.bezierTools import splitQuadraticAtT
        m=ring();contours=[]
        for loop in m['contours']:
            contours.append([part for sid in loop for part in splitQuadraticAtT(*m['segments'][sid]['control'],.5)])
        finer=prepare(contours,1000,baseline=True)
        a=sorted((f['axis'],round(f['width'],8)) for f in detect(m))
        b=sorted((f['axis'],round(f['width'],8)) for f in detect(finer))
        self.assertEqual(a,b)

if __name__=='__main__':unittest.main()
