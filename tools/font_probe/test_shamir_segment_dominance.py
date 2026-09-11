import unittest
from shamir_constraints import relation
from shamir_segment_dominance import dominant_relations


class DominanceTests(unittest.TestCase):
    def test_tilted_abs_cannot_survive_same_segment_width(self):
        cs = [relation('Abs', 0, [1, .03], value=4, segment_owner=7),
              relation('PDist', 0, [1, 0], [1], 1, segment_owner=7)]
        kept, audit = dominant_relations(cs)
        self.assertEqual(kept, cs[1:])
        self.assertEqual(len(audit['rejected']), 1)

    def test_distinct_segments_and_metrics_keep_their_ownership(self):
        cs = [relation('Abs', 0, [1, 0], value=4, segment_owner=7),
              relation('Dist', 0, [0, 1], [1], 1, segment_owner=8),
              relation('Abs', 0, [1, 0], value=4, metric=True)]
        self.assertEqual(dominant_relations(cs)[0], cs)

    def test_font_priority_and_explicit_ties(self):
        cs = [relation('PAbs', 0, [1, 0], value=4, segment_owner=7),
              relation('Dist', 0, [1, 0], [1], 1, segment_owner=7)]
        self.assertEqual(dominant_relations(cs)[0], cs[:1])
        cs.append(dict(cs[0], feature='duplicate'))
        self.assertEqual(len(dominant_relations(cs)[1]['warnings']), 1)


if __name__ == '__main__':
    unittest.main()
