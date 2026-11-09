"""Density invariants and the retained integer/contact policy, not optics."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typefacet_density_review import DOMAIN, center_steps, place_pair


class TypeFacetDensityTests(unittest.TestCase):
    def test_conservation_preserves_pair_differences_and_does_not_mutate_inputs(self):
        raw = {p: (p[0]-96)*.125+(p[1]-96)*.03125 for p in DOMAIN}
        source = {p: (p[0]-96)*.25 for p in DOMAIN}
        original = copy.deepcopy((raw, source))
        centered, metadata = center_steps(raw, source)
        self.assertAlmostEqual(math.fsum(centered.values()), math.fsum(source.values()), places=10)
        for p in DOMAIN:
            self.assertAlmostEqual(centered[p]-centered[DOMAIN[0]], raw[p]-raw[DOMAIN[0]])
        self.assertEqual((raw, source), original)
        self.assertEqual(metadata["count"], 676)

    def test_uniform_raw_offset_cancels_without_changing_source_density(self):
        raw = {p: (p[0]-p[1])*.125 for p in DOMAIN}
        source = dict.fromkeys(DOMAIN, 6.25)
        a, _ = center_steps(raw, source)
        b, _ = center_steps({p: v+3.125 for p, v in raw.items()}, source)
        self.assertEqual(a, b)

    def test_incomplete_or_nonfinite_domains_are_rejected(self):
        raw = dict.fromkeys(DOMAIN, 4.)
        source = dict(raw)
        del raw[DOMAIN[0]]
        with self.assertRaises(ValueError):
            center_steps(raw, source)
        raw[DOMAIN[0]] = math.nan
        with self.assertRaises(ValueError):
            center_steps(raw, source)

    def test_signed_adjustment_rounding_and_touching_permitted_guard(self):
        glyph = dict(finalized_advance_px=2, bitmap=dict(left=0, top=0, width=1, height=1, pixels=[1]))
        # At a negative half adjustment, the existing ties-away rule selects
        # step 1 (face contact), rather than absolute-step rounding to 2.
        placed = place_pair(glyph, glyph, 2., -.5)
        self.assertEqual(placed["rounded_step_px"], 1)
        self.assertEqual(placed["emitted_step_px"], 1)
        self.assertEqual(placed["guard_displacement_px"], 0)
        overlap = place_pair(glyph, glyph, 0., 0.)
        self.assertEqual(overlap["rounded_step_px"], 0)
        self.assertEqual(overlap["emitted_step_px"], 1)
        self.assertEqual(overlap["guard_displacement_px"], 1)


if __name__ == "__main__":
    unittest.main()
