import unittest
import numpy as np
from curve_gridfit import samples,fit_curves
from paper_gridfit import load,fit,generate
from stem_gridfit import fit_stems
import test_source_constraints as fixtures


class CurveGridFitTests(unittest.TestCase):
    def test_curve_sample_weights_and_tangents(self):
        source=np.array([[0.,0.],[2.,4.],[4.,0.]])
        result=samples(source,[1,0,1],[2])
        self.assertTrue(result)
        for weights,point,tangent in result:
            self.assertAlmostEqual(sum(weights),1)
            self.assertAlmostEqual(np.linalg.norm(tangent),1)
            np.testing.assert_allclose(weights@(source+[7,9]),point+[7,9])

    def test_width_residual_reduces_with_bounded_movement(self):
        for name,char,size in [('roboto','6',18),('literata','g',20)]:
            face,d,v=fixtures.SourceConstraintTests().face_and_tables(name,size)
            source,hinted,tags,ends=load(face,char,size)
            hinted,_=fit_stems(source,hinted,tags,ends,size,v,True)
            points,_=fit(source,hinted,tags,ends,size,d);current=points/64
            result,info=fit_curves(source,current,tags,ends,size,v)
            self.assertEqual(info['status'],'curved stroke constrained')
            self.assertLess(info['residual_after'],info['residual_before'])
            self.assertLessEqual(np.max(np.abs(result-current)),.5)
            extreme=(source[:,1]==source[:,1].min())|(source[:,1]==source[:,1].max())
            np.testing.assert_array_equal(result[extreme,1],current[extreme,1])
            g,diagnostics=generate(face,char,size,d,v,True,True,True)
            self.assertEqual(diagnostics['source_constraints']['selected']['defect_count'],0)

    def test_approved_mixed_stem_glyphs_stay_unchanged(self):
        for size in (16,18):
            face,d,v=fixtures.SourceConstraintTests().face_and_tables('roboto',size)
            for char in 'bhmnpdqX':
                before,_=generate(face,char,size,d,v,True,True)
                after,_=generate(face,char,size,d,v,True,True,True)
                self.assertEqual(before,after,(char,size))

    def test_straight_diagonals_preserve_serif_x(self):
        face,d,v=fixtures.SourceConstraintTests().face_and_tables('literata',20)
        before,_=generate(face,'X',20,d,v,True,True)
        after,info=generate(face,'X',20,d,v,True,True,True)
        self.assertEqual(before,after)
        self.assertEqual(info['curve_constraints']['status'],'long straight diagonals; retained outline')

    def test_cubic_curves_are_explicitly_outside_sampler(self):
        self.assertEqual(samples(np.array([[0.,0.],[1.,2.],[2.,2.],[3.,0.]]),[1,2,2,1],[3]),[])


if __name__=='__main__':unittest.main()
