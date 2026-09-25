"""Source-shaped global-size examples from Shamir 2003 §3.4/Table II."""
import unittest
from shamir_segment_fit import clusters


class BaselineStatisticsTests(unittest.TestCase):
    def test_adjacent_recurring_heights_remain_distinct(self):
        samples=[('top',36,'a')]*8+[('top',37,'b')]*18
        self.assertEqual(clusters(samples,2048,baseline=True),{'top':[36.,37.]})

    def test_occurrences_count_even_inside_one_character(self):
        samples=[('stem',100,'m')]*6+[('stem',120,'n')]*5
        self.assertEqual(clusters(samples,1000,baseline=True),{'stem':[100.]})

    def test_types_remain_separate_and_values_use_font_units(self):
        samples=[('black',20.2,'a')]*3+[('black',20.4,'b')]*3+[('white',20,'c')]*5
        self.assertEqual(clusters(samples,1000,baseline=True),{'black':[20.],'white':[]})

    def test_poor_richard_distinct_baselines_are_not_clustered(self):
        samples=[('bottom',v,str(v)) for v,count in [(-35,8),(-27,6),(-20,17),(-16,9),(-14,6),(-6,8)] for _ in range(count)]
        self.assertEqual(clusters(samples,2048,baseline=True),{'bottom':[-35.,-27.,-20.,-16.,-14.,-6.]})

    def test_table_two_joint_transcription_keeps_published_set(self):
        # B03 Table II close-out: the paper's transcribed multiset —
        # adjacent tops 36/37, stems, Poor Richard bottoms, black/white
        # separation with font-unit rounding — retains exactly the kept
        # set in a single clusters() call (threshold, separation and
        # rounding jointly, not aspect by aspect).
        samples = ([('top', 36, 'a')] * 8 + [('top', 37, 'b')] * 18
                   + [('stem', 100, 'm')] * 6 + [('stem', 120, 'n')] * 5
                   + [('bottom', v, str(v))
                      for v, count in [(-35, 8), (-27, 6), (-20, 17),
                                       (-16, 9), (-14, 6), (-6, 8)]
                      for _ in range(count)]
                   + [('black', 20.2, 'a')] * 3 + [('black', 20.4, 'b')] * 3
                   + [('white', 20, 'c')] * 5)
        self.assertEqual(
            clusters(samples, 2048, baseline=True),
            {'black': [20.], 'bottom': [-35., -27., -20., -16., -14., -6.],
             'stem': [100.], 'top': [36., 37.], 'white': []})

    def test_retained_set_grows_monotonically_with_repertoire(self):
        # B03 repertoire sensitivity: adding samples can only add counts,
        # so the retained shared set grows monotonically as the repertoire
        # expands; values crossing the six-occurrence line appear exactly
        # when their count reaches it.
        small = [('top', 36, 'a')] * 5 + [('top', 37, 'b')] * 6
        grown = small + [('top', 36, 'c')] + [('stem', 100, 'd')] * 6
        kept_small = clusters(small, 2048, baseline=True)
        kept_grown = clusters(grown, 2048, baseline=True)
        self.assertEqual(kept_small, {'top': [37.]})
        self.assertEqual(kept_grown, {'stem': [100.], 'top': [36., 37.]})
        for kind in kept_small:
            self.assertTrue(set(kept_small[kind]) <= set(kept_grown[kind]))

    def test_experimental_distinct_character_rule_is_preserved(self):
        samples=[('stem',100,'a'),('stem',102,'b'),('stem',104,'c')]
        self.assertEqual(clusters(samples,1000),{'stem':[102.]})
        self.assertEqual(clusters(samples,1000,baseline=True),{'stem':[]})


if __name__=='__main__':unittest.main()
