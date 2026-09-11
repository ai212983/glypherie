import unittest

from correct_pixels import remove, stable_runs, valid


def glyph(rows):
    return dict(left=0,top=0,width=len(rows[0]),height=len(rows),
                pixels=[int(c=='#') for row in rows for c in row])


class PixelGuardTests(unittest.TestCase):
    def test_repeated_stroke_runs_are_protected(self):
        g=glyph(['##..##']*3)
        self.assertEqual(len(stable_runs(g)),12)
        self.assertEqual(valid(g,remove(g,[0]),[0],stable_runs(g)),'stable stroke')

    def test_opening_counter_is_rejected(self):
        g=glyph(['###','#.#','###'])
        self.assertEqual(valid(g,remove(g,[1]),[1],set()),'ink/counter topology')

    def test_new_diagonal_only_join_is_rejected(self):
        g=glyph(['##','.#'])
        self.assertEqual(valid(g,remove(g,[1]),[1],set()),'new diagonal-only join')

    def test_safe_corner_removal_keeps_input(self):
        g=glyph(['##','##'])
        changed=remove(g,[0])
        self.assertIsNone(valid(g,changed,[0],set()))
        self.assertEqual(g['pixels'],[1,1,1,1])


if __name__=='__main__':unittest.main()
