import unittest

from analyze_features import detect, filled, visible_boundary


class SourceFeatureTests(unittest.TestCase):
    def test_convex_boundary_has_no_inward_turn(self):
        self.assertEqual(detect([[(0,0),(3,0),(3,3),(0,3)]]), [])

    def test_inward_turn_follows_translation_and_reflection(self):
        shape=[(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]
        for sx,dx,dy in [(1,0,0),(-1,7,-9)]:
            features=detect([[(sx*x+dx,y+dy) for x,y in shape]])
            self.assertEqual(len(features),1)
            x,y=features[0]['point']
            self.assertAlmostEqual(x,sx+dx,delta=0.05)
            self.assertAlmostEqual(y,1+dy,delta=0.05)

    def test_union_exposes_junction_hidden_in_overlapping_contours(self):
        shapes=[[(0,0),(1,0),(1,3),(0,3)],
                [(0,0),(3,0),(3,1),(0,1)]]
        self.assertEqual(detect(shapes),[])
        boundary=visible_boundary(shapes)
        self.assertEqual(len(detect(boundary)),1)
        self.assertTrue(filled((0.5,0.5),boundary))

    def test_union_preserves_counter(self):
        shapes=[[(0,0),(4,0),(4,4),(0,4)],
                [(1,1),(1,3),(3,3),(3,1)]]
        boundary=visible_boundary(shapes)
        self.assertTrue(filled((0.5,0.5),boundary))
        self.assertFalse(filled((2,2),boundary))


if __name__=='__main__': unittest.main()
