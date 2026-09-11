import copy
import unittest
from vtt_stem_widths import inherit_widths


class StemWidthTests(unittest.TestCase):
    def setUp(self):
        self.features=[dict(kind='slant',groups=[0,1],points=[0,2],normal=[1,.03],width=183),
                       dict(kind='stem',groups=[0,2],points=[0,3],normal=[1,0],width=192)]
        self.links=[dict(feature='align-1',point=2,sources=[3]),
                    dict(feature='align-2',point=3,sources=[4])]
        self.strokes=[dict(feature=0,cvts=[192,164])]

    def test_connected_taper_inherits_detected_stem(self):
        audit=inherit_widths(self.strokes,self.features,self.links)
        self.assertEqual(self.strokes[0]['cvts'],[192,192])
        self.assertTrue(self.strokes[0]['shared_cvt'])
        self.assertEqual(audit[0]['candidates'][0]['junction_points'],[3])

    def test_unconnected_sides_keep_their_widths(self):
        self.features[1]['points'][1]=4
        self.links[1]=dict(feature='align-2',point=4,sources=[5])
        self.assertEqual(inherit_widths(self.strokes,self.features,self.links),[])
        self.assertEqual(self.strokes[0]['cvts'],[192,164])

    def test_strong_taper_or_direction_change_is_excluded(self):
        for key,value in [('width',140),('normal',[1,1])]:
            features=copy.deepcopy(self.features);features[0][key]=value
            self.assertEqual(inherit_widths(self.strokes,features,self.links),[])

    def test_conflicting_stems_are_reported(self):
        other=copy.deepcopy(self.features[1]);other['width']=200
        self.features.append(other)
        audit=inherit_widths(self.strokes,self.features,self.links)
        self.assertEqual(audit[0]['status'],'ambiguous-width')
        self.assertEqual(self.strokes[0]['cvts'],[192,164])
