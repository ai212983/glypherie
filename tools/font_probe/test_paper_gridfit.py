import unittest
from pathlib import Path
import numpy as np
from paper_gridfit import ft,load,pairs,width_table,fit,generate


class GridFitTests(unittest.TestCase):
    def setUp(self):
        self.face=ft.Face(str(Path(__file__).parent/'fonts/Roboto.ttf'))
        self.face.set_var_design_coords([400,100])
        self.face.set_pixel_sizes(0,16)

    def test_diagonal_strip_has_constant_integer_width(self):
        source=np.array([(0.,0.),(2.,0.),(6.,8.),(4.,8.)])
        hinted=source.copy();hinted[2,0]+=.2
        points,d=fit(source,hinted,[1]*4,[3],16,width_table([2]))
        self.assertEqual(d['status'],'outline constrained')
        self.assertEqual(points[1,0]-points[0,0],128)
        self.assertEqual(points[2,0]-points[3,0],128)
        np.testing.assert_array_equal(points[:,1],hinted[:,1]*64)

    def test_impossible_displacement_reports_native_fallback(self):
        source=np.array([(0.,0.),(2.,0.),(6.,8.),(4.,8.)])
        points,d=fit(source,source,[1]*4,[3],16,[dict(source=2,target=8)])
        self.assertIn('fallback',d['status'])
        np.testing.assert_array_equal(points,source*64)

    def test_curved_contour_is_not_treated_as_straight_edges(self):
        source,hinted,tags,ends=load(self.face,'b',16)
        self.assertEqual(pairs(source,tags,ends,16),[])

    def test_x_symmetry_metrics_and_repeatability(self):
        for size in (14,16,18,20):
            self.face.set_pixel_sizes(0,size)
            source,hinted,tags,ends=load(self.face,'X',size)
            advance=self.face.glyph.advance.x
            table=width_table([p['width'] for p in pairs(source,tags,ends,size)])
            glyph,d=generate(self.face,'X',size,table)
            self.assertEqual(glyph['advance_26_6'],advance)
            self.assertLessEqual(d['max_displacement_px'],1)
            self.assertLessEqual(d['quantized_constraint_residual_px'],1/32)
            rows=np.array(glyph['pixels']).reshape(glyph['height'],glyph['width'])
            np.testing.assert_array_equal(rows,rows[:,::-1])
            self.assertEqual((glyph,d),generate(self.face,'X',size,table))

    def test_width_references_are_shared(self):
        table=width_table([1.7,1.75,1.8])
        self.assertEqual(len(table),1)
        self.assertEqual(table[0]['target'],2)
        self.assertEqual(table[0]['count'],3)

    def test_vertical_stems_exclude_counter(self):
        from stem_gridfit import stems
        points=np.array([(0.,0.),(0.,8.),(6.,8.),(6.,0.),(1.,1.),(5.,1.),(5.,7.),(1.,7.)])
        detected=stems(points,[1]*8,[3,7],16)
        self.assertEqual(len(detected),2)
        self.assertTrue(all(p['width']==1 for p in detected))

    def test_m_three_stems_share_width_and_curves_move(self):
        from stem_gridfit import stems,fit_stems
        source,hinted,tags,ends=load(self.face,'m',16)
        detected=stems(source,tags,ends,16)
        self.assertEqual(len(detected),3)
        table=width_table([p['width'] for p in detected])
        result,info=fit_stems(source,hinted,tags,ends,16,table)
        self.assertEqual(info['status'],'stem outlines constrained')
        widths=[]
        for p in detected:
            widths.append(result[p['right'][0],0]-result[p['left'][0],0])
        self.assertEqual(len(set(widths)),1)
        self.assertEqual(widths[0],round(widths[0]))
        self.assertTrue(any(abs(result[i,0]-hinted[i,0])>.01 for i,t in enumerate(tags) if t==0))
        np.testing.assert_array_equal(result[:,1],hinted[:,1])

    def test_stem_extension_preserves_x_at_all_sizes(self):
        for size in (14,16,18,20):
            self.face.set_pixel_sizes(0,size)
            source,_,tags,ends=load(self.face,'X',size)
            table=width_table([p['width'] for p in pairs(source,tags,ends,size)])
            before,_=generate(self.face,'X',size,table)
            after,info=generate(self.face,'X',size,table,[])
            self.assertEqual(before,after)
            self.assertEqual(info['vertical_stems']['status'],'no vertical stems')

    def test_bowl_supports_share_stem_target(self):
        from bowl_gridfit import bowl_pairs
        from stem_gridfit import stems,fit_stems
        for char in 'bpdq':
            source,hinted,tags,ends=load(self.face,char,16)
            self.assertEqual(len(bowl_pairs(source,tags,ends,16)),1)
            table=width_table([p['width'] for p in stems(source,tags,ends,16)])
            result,info=fit_stems(source,hinted,tags,ends,16,table,True)
            self.assertEqual(info['status'],'stem outlines constrained')
            for pair in info['curved_sides']:
                self.assertEqual(result[pair['right'][0],0]-result[pair['left'][0],0],info['stems'][0]['target'])
            np.testing.assert_array_equal(result[:,1],hinted[:,1])

    def test_bowl_extension_preserves_x(self):
        for size in (14,16,18,20):
            self.face.set_pixel_sizes(0,size)
            source,_,tags,ends=load(self.face,'X',size)
            table=width_table([p['width'] for p in pairs(source,tags,ends,size)])
            before,_=generate(self.face,'X',size,table,[])
            after,_=generate(self.face,'X',size,table,[],True)
            self.assertEqual(before,after)

    def test_counter_loss_retains_baseline_and_candidate_evidence(self):
        import json
        job=json.loads((Path(__file__).parent.parent/'font_generator/examples/literata.json').read_text())
        font=(Path(__file__).parent.parent/'font_generator/examples'/job['font']).resolve()
        face=ft.Face(str(font));face.set_pixel_sizes(0,16)
        face.set_var_design_coords([{'wght':400,'opsz':16}.get(a.tag,a.default) for a in face.get_variation_info().axes])
        from stem_gridfit import stems
        import string
        widths=[]
        for char in string.ascii_uppercase+string.ascii_lowercase+string.digits:
            source,_,tags,ends=load(face,char,16)
            widths.extend(p['width'] for p in stems(source,tags,ends,16))
        table=width_table(widths)
        before,_=generate(face,'a',16,[],table)
        after,info=generate(face,'a',16,[],table,True)
        self.assertEqual(before,after)
        self.assertIn('bowl_topology_rejection',info)
        self.assertNotEqual(info['bowl_topology_rejection']['candidate_glyph'],after)


if __name__=='__main__':unittest.main()
