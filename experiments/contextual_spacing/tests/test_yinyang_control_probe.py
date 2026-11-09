"""Focused tests for the YinYang-only control-design probe.

Mechanical gates only: choice-rule parity with the shipped v3 spot
defaults, the recorded og skip, Source identity at zero strength,
full-strength endpoint parity, per-pair monotone direction under the
fixed-endpoint blend, and the Gray fractional-pen identities that
distinguish absolute from correction-delta endpoints. Response-shape
verdicts live in docs/references/yinyang-only-control-design.md.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import yinyang_control_probe as P

BOOT = json.loads((P.SITE / "boot.json").read_text())


def case_text(case_id):
    return next(c for c in BOOT["cases"] if c["id"] == case_id)["text"]


class ProbeTest(unittest.TestCase):
    def test_choice_matches_shipped_spot_default(self):
        # Independent check: probe replication of choose_from_costs over
        # shipped curves reproduces the shipped default answer exactly.
        for label in ("roboto-16-mono", "roboto-16-gray",
                      "literata-16-mono", "roboto-8-mono"):
            table = P.load_table(label)
            sfi = P.sf_index(table)
            spot = table["spot"]["default"]
            for pair, entry in table["pairs"].items():
                self.assertEqual(
                    P.choose(entry["steps"], entry["geo"][str(sfi)]["inter"],
                             entry["geo"][str(sfi)]["ok"], 1.1, entry["metric"]),
                    spot[pair], f"{label} {pair}")

    def test_og_skip_reproduced(self):
        # Prior finding: metric-8 og picks 9 at cohesion 1.1 then 7 at
        # 1.2, skipping 8 (interior extremum reorders nearest branch).
        table = P.load_table("roboto-16-mono")
        entry = table["pairs"]["og"]
        sfi = P.sf_index(table)
        path = [P.choose(entry["steps"], entry["geo"][str(sfi)]["inter"],
                         entry["geo"][str(sfi)]["ok"], c, entry["metric"])
                for c in P.COHESION_GRID]
        self.assertEqual(path[P.COHESION_GRID.index(1.1)], 9)
        self.assertEqual(path[P.COHESION_GRID.index(1.2)], 7)

    def test_zero_strength_is_source(self):
        # Explicit bypass: both policies return exact Source at o=0.
        for label in ("roboto-16-mono", "roboto-16-gray"):
            table, cap = P.load_table(label), P.load_capture(label)
            text = case_text("roboto-16").split("\n")[0]
            gaps, src = P.line_gaps(table, cap, text), P.source_origins(cap, text)
            self.assertEqual(P.blend_origins(gaps, src, "per_pair", 0.0), src)
            self.assertEqual(P.blend_origins(gaps, src, "fractional_pen", 0.0), src)

    def test_full_strength_matches_absolute_endpoint(self):
        # P1 at o=1 accumulates the fixed YinYang chosen steps exactly.
        for label in ("roboto-16-mono", "roboto-16-gray"):
            table, cap = P.load_table(label), P.load_capture(label)
            text = case_text("roboto-16").split("\n")[2]
            gaps, src = P.line_gaps(table, cap, text), P.source_origins(cap, text)
            full = P.blend_origins(gaps, src, "per_pair", 1.0)
            expect = [src[0]]
            for gap in gaps:
                expect.append(expect[-1] + gap["d1"])
            self.assertEqual(full, expect)

    def test_per_pair_monotone_direction(self):
        # Rounding and the clearance floor are monotone maps: each pair's
        # blended step moves only toward its own endpoint (plateaus only).
        table, cap = P.load_table("roboto-16-mono"), P.load_capture("roboto-16-mono")
        text = case_text("roboto-16").split("\n")[2]
        gaps = P.line_gaps(table, cap, text)
        fine = [round(i * 0.01, 2) for i in range(101)]
        for gap in gaps:
            steps = [P.pixel_round(gap["m_frac"] + o * gap["delta"]) for o in fine]
            diffs = [b - a for a, b in zip(steps, steps[1:])]
            if gap["delta"] >= 0:
                self.assertTrue(all(d >= 0 for d in diffs), gap["pair"])
            else:
                self.assertTrue(all(d <= 0 for d in diffs), gap["pair"])

    def test_gray_fractional_pen_zero_is_source_without_bypass(self):
        # Gray Source advances are fractional, so the fractional pen
        # without any bypass already draws Source exactly at o=0; the
        # per-pair-rounded policy cannot (residue snap is nonzero).
        label = "roboto-16-gray"
        table, cap = P.load_table(label), P.load_capture(label)
        text = case_text("roboto-16").split("\n")[2]
        gaps, src = P.line_gaps(table, cap, text), P.source_origins(cap, text)
        self.assertEqual(
            P.blend_origins(gaps, src, "fractional_pen", 0.0, bypass=False), src)
        snap = max(abs(a - b) for a, b in
                   zip(P.blend_origins(gaps, src, "per_pair", 0.0, bypass=False), src))
        self.assertGreater(snap, 0)


if __name__ == "__main__":
    unittest.main()
