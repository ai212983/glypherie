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

    def test_experimental_distinct_character_rule_is_preserved(self):
        samples=[('stem',100,'a'),('stem',102,'b'),('stem',104,'c')]
        self.assertEqual(clusters(samples,1000),{'stem':[102.]})
        self.assertEqual(clusters(samples,1000,baseline=True),{'stem':[]})


if __name__=='__main__':unittest.main()
