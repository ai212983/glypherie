import math
import unittest

from fontTools.ttLib import TTFont
from analyze_features import ROOT,FlattenPen,visible_boundary,detect
from classify_junctions import classify


class JunctionClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font=TTFont(ROOT/'tools/font_probe/fonts/Roboto.ttf')
        cls.gs=cls.font.getGlyphSet(location={'wght':400,'wdth':100})
        cls.cmap=cls.font.getBestCmap()

    def boundary(self,char,size):
        pen=FlattenPen(self.gs,size/self.font['head'].unitsPerEm)
        self.gs[self.cmap[ord(char)]].draw(pen)
        return visible_boundary(pen.contours)

    def test_straight_intersections_excluded_at_all_test_sizes(self):
        for size in (14,16,18,20):
            for char in 'HX':
                boundary=self.boundary(char,size);features=detect(boundary)
                self.assertEqual(len(features),4)
                self.assertTrue(all(not classify(f,boundary,size)['eligible'] for f in features))

    def test_reviewed_curved_entries_remain_eligible(self):
        for char in 'bhmnpdq':
            boundary=self.boundary(char,16);features=detect(boundary)
            self.assertTrue(features)
            self.assertTrue(all(classify(f,boundary,16)['eligible'] for f in features),char)

    def test_rigid_transform_preserves_classification(self):
        boundary=self.boundary('b',16)
        theta=0.7
        def transform(p):
            x,y=p
            return x*math.cos(theta)-y*math.sin(theta)+4,x*math.sin(theta)+y*math.cos(theta)-3
        moved=[[transform(p) for p in poly] for poly in boundary]
        for feature in detect(boundary):
            transformed=dict(feature,point=transform(feature['point']))
            self.assertEqual(classify(feature,boundary,16)['eligible'],classify(transformed,moved,16)['eligible'])


if __name__=='__main__':unittest.main()
