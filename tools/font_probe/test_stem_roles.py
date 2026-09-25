import unittest

from stem_roles import (ANCHORED, FLOATING, role_for_feature, role_of,
                        tol_for_scale, zones_for_face)


class ZoneRoleTests(unittest.TestCase):
    # Roboto-scale design units (em 2048): baseline 0, cap mode 1476.
    ZONES = [0.0, 1476.0]
    TOL = 30.0  # overshoot scale, provisional (see stem_roles).

    def test_n_stem_stood_on_baseline_is_anchored(self):
        self.assertEqual(role_of([0.0, 1460.0], self.ZONES, self.TOL),
                         ANCHORED)

    def test_cap_hung_stem_is_anchored(self):
        self.assertEqual(role_of([200.0, 1470.0], self.ZONES, self.TOL),
                         ANCHORED)

    def test_descender_stem_merely_crossing_floats(self):
        # literata p: x-height down past the baseline to the
        # descender bottom. Neither end touches a zone, so the
        # role floats — span-crossing was tried (span-cover
        # semantics) and rejected 2-0 by oracle adjudication on
        # full-height brackets, which both witnesses keep thin.
        # p still takes the main in practice through its
        # main-class width (geometry-free lookup), not its role.
        self.assertEqual(role_of([-400.0, 1000.0], self.ZONES,
                                 self.TOL), FLOATING)

    def test_plus_arm_floating_mid_glyph_is_floating(self):
        self.assertEqual(role_of([500.0, 900.0], self.ZONES, self.TOL),
                         FLOATING)

    def test_just_outside_tolerance_floats(self):
        self.assertEqual(role_of([self.TOL + 1.0, 900.0],
                                 self.ZONES, self.TOL), FLOATING)

    def test_empty_zones_float(self):
        self.assertEqual(role_of([0.0, 1460.0], [], self.TOL), FLOATING)

    def test_zones_for_face_baseline_always_cap_when_known(self):
        self.assertEqual(zones_for_face(None), [0.0])
        self.assertEqual(zones_for_face(1476.0), [0.0, 1476.0])
        self.assertEqual(zones_for_face(0), [0.0])

    def test_tol_for_scale_is_half_pixel_in_design_units(self):
        self.assertAlmostEqual(tol_for_scale(16 / 2048), 64.0)
        self.assertIsNone(tol_for_scale(0))
        self.assertIsNone(tol_for_scale(None))


class FeatureAdapterTests(unittest.TestCase):
    ZONES = [0.0, 1476.0]
    TOL = 64.0

    def test_vertical_stem_spanning_zones_is_anchored(self):
        f = dict(kind='stem', support_direction=[0, 1],
                 support_intervals=[[0.0, 1460.0]])
        self.assertEqual(role_for_feature(f, self.ZONES, self.TOL),
                         ANCHORED)

    def test_vertical_stem_floating_mid_glyph_is_floating(self):
        f = dict(kind='stem', support_direction=[0, 1],
                 support_intervals=[[500.0, 900.0]])
        self.assertEqual(role_for_feature(f, self.ZONES, self.TOL),
                         FLOATING)

    def test_bar_reads_station_height(self):
        mid = dict(kind='bar', a=[100.0, 700.0], b=[900.0, 700.0])
        self.assertEqual(role_for_feature(mid, self.ZONES, self.TOL),
                         FLOATING)
        base = dict(kind='bar', a=[100.0, 10.0], b=[900.0, 10.0])
        self.assertEqual(role_for_feature(base, self.ZONES, self.TOL),
                         ANCHORED)

    def test_slant_and_curves_abstain(self):
        for f in (dict(kind='slant', support_direction=[1, 1],
                       support_intervals=[[0.0, 100.0]]),
                  dict(kind='arc', points=[0, 1]),
                  dict(kind='stem'),
                  dict(kind='stem', support_direction=[1, 0],
                       support_intervals=[[0.0, 100.0]]),
                  None):
            self.assertIsNone(role_for_feature(f, self.ZONES,
                                               self.TOL))


if __name__ == '__main__':
    unittest.main()
