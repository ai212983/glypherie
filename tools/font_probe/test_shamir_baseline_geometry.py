"""Source-derived baseline preparation and interior invariants (1996 §§3–4)."""
import unittest
import numpy as np
from shamir_geometry import prepare,merge_collinear_lines
from shamir_features import Interior,recognize


def polygon(points):
    return [[a,b] for a,b in zip(points,points[1:]+points[:1])]


class BaselineGeometryTests(unittest.TestCase):
    def test_redundant_static_line_points_are_removed(self):
        contour=polygon([(0,0),(5,0),(10,0),(10,10),(0,10)])
        self.assertEqual(len(prepare([contour],1000)['points']),5)
        self.assertEqual(len(prepare([contour],1000,baseline=True)['points']),4)
        self.assertEqual(len(contour),5)

    def test_preparation_log_counts_removals_and_insertions(self):
        # B01 substitution boundary (prepare() interior): the log reports
        # exactly what the baseline merge and extremum-subdivision steps
        # remove and add. Upstream OutlinePen drops and downstream
        # recognize() discards are outside this log.
        rect = polygon([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)])
        plain = prepare([rect], 1000)
        self.assertEqual(plain['preparation_log']['removed_collinear_joins'], 0)
        self.assertEqual(plain['preparation_log']['inserted_extrema'], 0)
        merged = prepare([rect], 1000, baseline=True)
        self.assertEqual(merged['preparation_log']['removed_collinear_joins'], 1)
        self.assertEqual(merged['preparation_log']['inserted_extrema'], 0)
        # Shallow real corners survive with a zero removal count.
        shallow = polygon([(0, 0), (5, .0001), (10, 0), (10, 10), (0, 10)])
        log = prepare([shallow], 1000, baseline=True)['preparation_log']
        self.assertEqual(log['removed_collinear_joins'], 0)
        # Seam rotation must not change the removal count.
        rotated = polygon([(5, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        self.assertEqual(
            prepare([rotated], 1000, baseline=True)['preparation_log'],
            merged['preparation_log'])

    def test_preparation_log_partitions_inserted_extrema(self):
        # One quadratic arch gains exactly one inserted extremum whose
        # piece t_ranges partition [0, 1].
        arch = [[(0, 0), (50, 50), (100, 0)]]
        model = prepare([arch], 1000, baseline=True)
        self.assertEqual(model['preparation_log']['inserted_extrema'], 1)
        self.assertEqual(model['preparation_log']['removed_collinear_joins'], 0)
        ranges = sorted(tuple(s['t_range']) for s in model['segments'])
        self.assertEqual(ranges[0][0], 0)
        self.assertEqual(ranges[-1][1], 1)
        for (_, hi), (lo, _) in zip(ranges, ranges[1:]):
            self.assertEqual(hi, lo)

    def test_contour_start_does_not_hide_redundancy(self):
        contour=polygon([(5,0),(10,0),(10,10),(0,10),(0,0)])
        result=merge_collinear_lines(contour)
        self.assertEqual(len(result),4)
        self.assertEqual(result[0],[(0,0),(10,0)])

    def test_preserves_real_shallow_corners_and_backtracking(self):
        contour=polygon([(0,0),(5,.0001),(10,0),(10,10),(0,10)])
        self.assertEqual(len(merge_collinear_lines(contour)),5)
        self.assertEqual(merge_collinear_lines([[(0,0),(5,0)],[(5,0),(0,0)]]),
                         [[(0,0),(5,0)],[(5,0),(0,0)]])

    def test_segment_detects_hole_between_old_samples(self):
        outer=polygon([(0,0),(100,0),(100,100),(0,100)])
        hole=polygon([(19,40),(19,60),(21,60),(21,40)])
        a=np.array([0.,50.]);b=np.array([100.,50.])
        self.assertTrue(Interior(prepare([outer,hole],1000)).between(a,b))
        self.assertFalse(Interior(prepare([outer,hole],1000,baseline=True)).between(a,b))

    def test_quadratic_hole_intersections(self):
        outer=polygon([(0,0),(100,0),(100,100),(0,100)])
        hole=[[(19,50),(19,52),(21,50)],[(21,50),(21,48),(19,50)]]
        interior=Interior(prepare([outer,hole],1000,baseline=True))
        self.assertFalse(interior.between(np.array([0.,50.]),np.array([100.,50.])))
        self.assertTrue(interior.between(np.array([0.,70.]),np.array([100.,70.])))

    def test_endpoints_allowed_and_boundary_overlap_rejected(self):
        outer=polygon([(0,0),(100,0),(100,100),(0,100)])
        interior=Interior(prepare([outer],1000,baseline=True))
        self.assertTrue(interior.between([0,50],[100,50]))
        self.assertTrue(interior.between([0,0],[100,100]))
        self.assertFalse(interior.between([0,0],[100,0]))
        self.assertFalse(interior.between([0,0],[0,0]))

    def test_region_finds_hole_between_all_old_cross_sections(self):
        outer=polygon([(0,0),(100,0),(100,100),(0,100)])
        hole=polygon([(19,23),(19,24),(21,24),(21,23)])
        interior=Interior(prepare([outer,hole],1000,baseline=True))
        self.assertFalse(interior.region_inside([(0,0),(100,0),(100,100),(0,100)]))
        self.assertTrue(interior.region_inside([(19,23),(21,23),(21,24),(19,24)],filled=False))
        old=recognize(prepare([outer,hole],1000))
        new=recognize(prepare([outer,hole],1000,baseline=True))
        self.assertTrue(any(f['kind']=='stem' and f['width']==100 for f in old['features']))
        self.assertFalse(any(f['kind']=='stem' and f['width']==100 for f in new['features']))

    def test_region_accepts_boundary_edges_and_reversed_winding(self):
        outer=polygon([(0,0),(10,0),(10,100),(0,100)])
        interior=Interior(prepare([outer],1000,baseline=True))
        points=[(0,0),(10,0),(10,100),(0,100)]
        self.assertTrue(interior.region_inside(points))
        self.assertTrue(interior.region_inside(points[::-1]))
        self.assertFalse(interior.region_inside(points,filled=False))
        found=recognize(prepare([outer],1000,baseline=True))
        self.assertTrue(any(f['kind']=='stem' and f['width']==10 for f in found['features']))

    def test_region_quadratic_intrusion_and_invalid_footprint(self):
        outer=[[(0,0),(100,0)],[(100,0),(50,50),(100,100)],
               [(100,100),(0,100)],[(0,100),(0,0)]]
        interior=Interior(prepare([outer],1000,baseline=True))
        self.assertFalse(interior.region_inside([(0,0),(100,0),(100,100),(0,100)]))
        self.assertTrue(interior.region_inside([(0,0),(50,0),(50,100),(0,100)]))
        with self.assertRaises(ValueError):
            interior.region_inside([(0,0),(100,0),(25,25),(0,100)])


if __name__=='__main__':unittest.main()
