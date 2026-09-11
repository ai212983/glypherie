import unittest

from compare_join_repairs import connectivity_reason
from correct_pixels import remove


def glyph(rows):
    return dict(width=len(rows[0]),height=len(rows),left=0,top=0,
                pixels=[int(c=='#') for row in rows for c in row])


class RepairGuardsTests(unittest.TestCase):
    def test_only_thin_arm_permits_new_diagonal_contact(self):
        before=glyph(['##','.#']);after=remove(before,[1])
        self.assertIsNone(connectivity_reason(before,after,'thin'))
        self.assertEqual(connectivity_reason(before,after,'move'),'new diagonal-only connection')

    def test_both_arms_reject_opened_counter(self):
        before=glyph(['###','#.#','###']);after=remove(before,[1])
        for mode in ('thin','move'):
            self.assertEqual(connectivity_reason(before,after,mode),'ink/counter topology')

    def test_relocated_pixel_can_restore_edge_connection(self):
        before=glyph(['##','.#']);after=glyph(['#.','##'])
        self.assertIsNone(connectivity_reason(before,after,'move'))
        self.assertEqual(sum(before['pixels']),sum(after['pixels']))


if __name__=='__main__':unittest.main()
