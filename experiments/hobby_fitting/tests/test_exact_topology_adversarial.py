"""Exact arrangement controls for neutral seams and boundary contacts.

CGAL arrangements retain edges that do not separate nonzero-filled ink
from white. Such edges must not create counters or erase point contacts.
These are analytic shapes, independent of fitting and rasterization.
"""
import unittest
from experiments.hobby_fitting import exact_topology as et


def rectangle(x0, y0, x1, y1, clockwise=False):
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if clockwise:
        points.reverse()
    return [{"op": "move_to", "x": points[0][0], "y": points[0][1]}] + [
        {"op": "line_to", "x": x, "y": y} for x, y in points[1:]
    ] + [{"op": "close"}]


class ArrangementControls(unittest.TestCase):
    def analyze(self, commands):
        result = et.analyze_commands(commands)
        self.assertTrue(result["supported"], result["reason"])
        return result["signature"]

    def test_cancelled_square_has_no_counter(self):
        signature = self.analyze(rectangle(0, 0, 4, 4) + rectangle(0, 0, 4, 4, True))
        self.assertEqual(signature["filled_components"], 0)
        self.assertEqual(signature["holes"], 0)

    def test_neutral_strip_does_not_split_counter(self):
        annulus = rectangle(0, 0, 10, 10) + rectangle(2, 2, 8, 8, True)
        neutral = rectangle(4, 1, 6, 9) + rectangle(4, 1, 6, 9, True)
        self.assertEqual(self.analyze(annulus)["holes"], 1)
        self.assertEqual(self.analyze(annulus + neutral)["holes"], 1)

    def test_point_contact_is_not_an_edge_connection(self):
        signature = self.analyze(rectangle(0, 0, 2, 2) + rectangle(2, 2, 4, 4))
        self.assertEqual(signature["filled_components"], 2)
        self.assertEqual(len(signature["point_contacts"]), 1)
        self.assertEqual(signature["pinch_vertices"], 1)

    def test_internal_overlap_border_may_move(self):
        before = rectangle(0, 0, 4, 4) + rectangle(2, 0, 6, 4)
        after = rectangle(0, 0, 3.5, 4) + rectangle(2.5, 0, 6, 4)
        result = et.compare_commands(before, before, after)
        self.assertTrue(result["supported"], result["reason"])
        self.assertTrue(result["ok"], result.get("diff"))


if __name__ == "__main__":
    unittest.main()
