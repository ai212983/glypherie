import unittest
import numpy as np
from vtt_terminal_links import candidates, detect


class TerminalRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([(0,5),(5,5),(8,8),(8,1),(7,0),(5,3),(0,3)])

    def test_contour_start_translation_and_scale(self):
        for shift in range(len(self.points)):
            p = np.roll(self.points, shift, axis=0)*3 + [20,70]
            roles = detect(p, [1]*len(p), [len(p)-1])
            self.assertEqual(tuple(p[roles['top']]), (44,94))
            self.assertEqual(tuple(p[roles['bottom']]), (41,70))
            self.assertEqual(tuple(p[roles['upper_arm']]), (35,85))
            self.assertEqual(tuple(p[roles['lower_arm']]), (35,79))

    def test_multiple_matches_are_exposed_and_not_silently_selected(self):
        p = np.vstack([self.points, self.points+[20,0]])
        self.assertEqual(len(candidates(p, [1]*len(p), [6,13])), 2)
        with self.assertRaises(ValueError): detect(p, [1]*len(p), [6,13])

    def test_unordered_arm_is_a_reported_near_miss(self):
        p = self.points.copy(); p[5:,1] = 6
        audit = []
        self.assertEqual(candidates(p, [1]*len(p), [6], audit), [])
        self.assertTrue(any('ordered arm' in row['reason'] for row in audit))


if __name__ == '__main__': unittest.main()
