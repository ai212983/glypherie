import unittest

from join_experiment import notches, constrain, ink


def glyph(rows, left=0, top=0):
    return dict(left=left, top=top, width=len(rows[0]), height=len(rows),
                pixels=[int(c == '#') for row in rows for c in row])


class JoinConstraintTests(unittest.TestCase):
    def test_exterior_notch_is_distinct_from_counter(self):
        self.assertEqual(notches(glyph(['#.#', '###']), 1), {(1, 0)})
        self.assertEqual(notches(glyph(['###', '#.#', '###']), 1), set())

    def test_coordinates_follow_origin_and_reflection(self):
        original = glyph(['#.###', '#####'], left=-3, top=-9)
        mirrored = glyph(['###.#', '#####'], left=-3, top=-9)
        self.assertEqual(notches(original, 1), {(-2, -9)})
        self.assertEqual(notches(mirrored, 1), {(0, -9)})

    def test_constraint_only_removes_added_notch_pixels(self):
        base = glyph(['#.#', '###'])
        grown = glyph(['###', '###'])
        result, change = constrain(base, grown, 1)
        self.assertEqual(ink(result), ink(base))
        self.assertEqual(change['removed'], [(1, 0)])
        self.assertEqual(grown['pixels'], [1]*6)


if __name__ == '__main__':
    unittest.main()
