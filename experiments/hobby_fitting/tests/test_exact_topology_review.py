"""Independent reviewer controls for pair-attributed join verification.

Analytic invariant: attachment is per contour-label pair with
area/edge/point classes (arrangement adjacency, exact rational
arithmetic). A lost weld must fail even when an independent
counter and all global counts are preserved; component, hole,
seam, pinch and contact tallies alone cannot see it.
"""
import unittest
from experiments.hobby_fitting import exact_topology as et


def rect(x0, y0, x1, y1, clockwise=False):
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if clockwise:
        points.reverse()
    return ([{"op": "move_to", "x": points[0][0], "y": points[0][1]}] +
            [{"op": "line_to", "x": x, "y": y} for x, y in points[1:]] +
            [{"op": "close"}])


def pairs_of(signature):
    return {tuple(p["pair"]): p for p in signature["pairs"]}


class PairAttributionControls(unittest.TestCase):
    def test_weld_loss_visible_only_in_pairs_rejects(self):
        # Labels 0:a 1:b/point 2:bridge 3,4:counter shell/hole.
        # The (0,1) weld drops edge contact to a point hinge while
        # the bridge keeps every global count, including holes.
        counter = rect(10, 0, 14, 4) + rect(11, 1, 13, 3, True)
        before = (rect(0, 0, 4, 4) + rect(4, 0, 8, 4)
                  + rect(0, 4, 8, 8) + counter)
        after = (rect(0, 0, 4, 4) + rect(4, 4, 8, 8)
                 + rect(0, 4, 8, 8) + counter)
        result = et.compare_commands(before, before, after)
        self.assertTrue(result["supported"], result["reason"])
        up = result["upstream"]["signature"]
        cand = result["candidate"]["signature"]
        for key in ("filled_components", "holes", "seam_chains",
                    "pinch_vertices"):
            self.assertEqual(up[key], cand[key])
        self.assertEqual(len(up["point_contacts"]),
                         len(cand["point_contacts"]))
        self.assertEqual(pairs_of(up)[(0, 1)]["edge_components"], 1)
        self.assertEqual(pairs_of(cand)[(0, 1)]["edge_components"], 0)
        self.assertFalse(result["ok"], result.get("diff"))


if __name__ == "__main__":
    unittest.main()
