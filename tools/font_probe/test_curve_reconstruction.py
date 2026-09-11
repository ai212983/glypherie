"""Source-curve invariants for bounded width-link interpolation."""
import unittest
import numpy as np
from test_curved_width_links import ring
from shamir_geometry import prepare
from shamir_segment_fit import prepared_glyph
from curve_reconstruction import reconstruct
from curved_width_links import fit


class ReconstructionTests(unittest.TestCase):
    def test_round_top_tracks_fitted_sides_from_source_proportion(self):
        m=ring();g,mp,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        # Distort the outer width while retaining its old top x coordinate.
        extrema=[p for p in m['points'] if '0' in p['extrema']]
        for p in extrema:
            i=mp[p['id']];is_left=p['extrema']['0']=='min'
            q[i,0]=(0 if is_left else 6) if p['contour']==0 else (2 if is_left else 5)
        out,a=fit(m,q,reconstruct_curves=True)
        tops=[mp[p['id']] for p in m['points'] if '1' in p['extrema']]
        np.testing.assert_allclose(out[tops,0],3.)
        np.testing.assert_array_equal(out[:,1],q[:,1])
        self.assertTrue(all(abs(l['after_width_px']-1)<1e-9 for l in a['links']))

    def test_curve_cannot_fold_past_retained_junction(self):
        contour=[[[-100,0],[-50,50]],[[-50,50],[0,150],[50,50]],
                 [[50,50],[100,0]],[[100,0],[-100,0]]]
        m=prepare([contour],100,baseline=True);m['scale']=.01
        g,mp,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        top=next(mp[p['id']] for p in m['points'] if p['inserted'])
        with self.assertRaisesRegex(ValueError,'source arc order'):
            reconstruct(m,q,1,{top:.4},[])

    def test_unaffected_component_is_bit_exact(self):
        m=ring();g,mp,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        # Affect only the inner curve; the outer contour must not be rebuilt.
        p=next(p for p in m['points'] if p['contour']==1 and p['extrema'].get('0')=='min')
        i=mp[p['id']];q[:g.endPtsOfContours[0]+1,0]+=.037
        out,a=reconstruct(m,q,0,{i:q[i,0]-.2},[])
        np.testing.assert_array_equal(out[:g.endPtsOfContours[0]+1],q[:g.endPtsOfContours[0]+1])

class SourceGeometryTests(unittest.TestCase):
    def test_rounding_can_create_corner_but_source_classification_survives(self):
        contour=[[[0,0],[10,0],[12.5,1.5]],[[12.5,1.5],[15,3],[20,10]],
                 [[20,10],[0,0]]]
        original=prepare([contour],100,baseline=True)
        rounded=prepare([[np.rint(c).tolist() for c in contour]],100,baseline=True)
        p=next(p for p in original['points'] if p['position']==[12.5,1.5])
        q=next(p for p in rounded['points'] if p['position']==[12.,2.])
        self.assertEqual(p['kind'],'curve')
        self.assertEqual(q['kind'],'corner')
        original['scale']=.1;original['source_junctions']=True
        g,mp,_=prepared_glyph(original);current=np.asarray(g.coordinates)*.1
        # Generating rounded storage does not replace the original descriptors.
        self.assertEqual(original['points'][p['id']]['position'],[12.5,1.5])
        self.assertEqual(original['points'][p['id']]['kind'],'curve')

    def test_source_profile_keeps_link_widths_and_true_line_junctions(self):
        m=ring();m['source_junctions']=True
        g,mp,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        result,audit=fit(m,q,reconstruct_curves=True)
        for link in audit['links']:
            self.assertAlmostEqual(link['after_width_px'],link['target_width_px'])
        for a in audit['reconstruction']:
            self.assertEqual(a['max_junction_movement_px'],0.)

if __name__=='__main__':unittest.main()
