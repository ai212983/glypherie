import unittest
import numpy as np
from vtt_serif_experiment import detect, fit


class SerifTests(unittest.TestCase):
    def setUp(self):
        self.p = np.array([(0,0),(0,50),(80,60),(100,100),(100,600),
                           (200,600),(200,100),(220,60),(300,50),(300,0)], float)

    def test_pair_detection_and_reversal(self):
        for p in (self.p, self.p[::-1]):
            halves = detect(p, [9], [1]*10, 1000)
            self.assertEqual(len(halves), 2)
            self.assertEqual({h['type'] for h in halves}, {2})
            self.assertEqual(sorted(h['extension_fu'] for h in halves), [-100,100])

    def test_stem_relative_extensions_and_unowned_coordinates(self):
        hs = detect(self.p, [9], [1]*10, 1000); before = self.p*.01
        after, audit = fit(self.p, before, hs, .01)
        owned = {i for h in hs for i in h['members']}
        for h in hs:
            self.assertEqual(after[h['stem'],0], before[h['stem'],0])
            self.assertEqual(abs(after[h['endpoint'],0]-after[h['stem'],0]),1)
            self.assertEqual(abs(after[h['upper'],1]-after[h['endpoint'],1]),1)
        self.assertTrue(all(np.array_equal(after[i], before[i]) for i in range(10) if i not in owned))

    def test_mirrored_shape_stays_mirrored(self):
        a, _ = fit(self.p, self.p*.014, detect(self.p,[9],[1]*10,1000),.014)
        p = self.p*np.array([-1,1])
        b, _ = fit(p,p*.014,detect(p,[9],[1]*10,1000),.014)
        self.assertTrue(np.allclose(a*np.array([-1,1]),b))

    def test_thick_end_is_not_a_supported_serif(self):
        p=self.p.copy();p[1,1]=200
        self.assertEqual(detect(p,[9],[1]*10,1000),[])


if __name__ == '__main__': unittest.main()
