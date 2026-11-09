# cspell:words fullwindow yinyangfit
"""Focused tests for the full-window candidate scorer (ARM-B2).

Covers the experimental model ``yinyangfit-interactive-b2-fullwindow-v1``
only; the frozen v1 tests in ``test_yinyangfit_interactive.py`` keep the
historical reference. Fixtures are the existing delivered captures. Optical
acceptance stays pending by policy: these tests pin the repaired mechanism
and its guardrails, not optical quality.
"""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyangfit_interactive as v1
import yinyangfit_interactive_b2 as b2
import yinyangfit_interactive_v3_ranges as vr

REPO = Path(__file__).resolve().parents[3]
CAPTURES = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
            / "captures")
REPAIR_CORPUS = (REPO / "out/diagnostics/contextual-spacing/yinyang-model-repair"
                 / "results_corpus.json")

# Raw predeclared B2 records (full precision) for the motivating pair.
UM_B2 = [1.6942272887755012, 1.5470271899757264, 1.260502031742517,
         0.9876503288342128, 0.7813397450539757]


class B2IdentityTest(unittest.TestCase):
    def test_model_identity_is_new_and_explicit(self):
        self.assertEqual(b2.MODEL_IDENTITY,
                         "yinyangfit-interactive-b2-fullwindow-v1")
        self.assertNotEqual(b2.MODEL_IDENTITY, v1.MODEL_IDENTITY)
        self.assertNotEqual(b2.IMPLEMENTATION_SHA256,
                             v1.IMPLEMENTATION_SHA256)

    def test_settings_identity_covers_new_model(self):
        self.assertNotEqual(
            b2.settings_identity(b2.DEFAULT_CONTROLS),
            v1.settings_identity(v1.DEFAULT_CONTROLS))

    def test_shared_controls_and_policies_unchanged(self):
        self.assertEqual(float(b2.DEFAULT_CONTROLS.cohesion), 1.10)
        self.assertEqual(float(b2.DEFAULT_CONTROLS.feature_scale), 2.0)
        self.assertEqual(float(b2.DEFAULT_CONTROLS.proximity_falloff), 2.0)
        self.assertIs(b2.CANDIDATE_DELTAS, v1.CANDIDATE_DELTAS)
        self.assertEqual(b2.TIE_TOLERANCE, v1.TIE_TOLERANCE)


class B2UmRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = CAPTURES / "roboto-16-mono.json"
        if not path.exists():
            raise unittest.SkipTest(f"missing retained capture {path}")
        dataset = v1.load_mono_capture(str(path))
        cls.dataset = dataset
        cls.scorer = b2.PairScorer(dataset)
        cls.metric = v1.metric_step(dataset, ord("u"), ord("m"))
        if not REPAIR_CORPUS.exists():
            raise unittest.SkipTest(f"missing repair corpus {REPAIR_CORPUS}")

    def test_metric_is_eight(self):
        self.assertEqual(self.metric, 8)

    def test_um_matches_predeclared_b2_records(self):
        ev = self.scorer.evaluate_pair(ord("u"), ord("m"),
                                       b2.DEFAULT_CONTROLS)
        self.assertEqual([c["step"] for c in ev["candidates"]],
                         [6, 7, 8, 9, 10])
        for candidate, want in zip(ev["candidates"], UM_B2):
            self.assertTrue(candidate["valid"])
            self.assertAlmostEqual(candidate["interaction"], want, delta=1e-12)

    def test_um_chooses_source_plus_one_not_contact(self):
        ev = self.scorer.evaluate_pair(ord("u"), ord("m"),
                                       b2.DEFAULT_CONTROLS)
        self.assertEqual(ev["chosen"], 9)
        chosen = next(c for c in ev["candidates"]
                      if c["step"] == ev["chosen"])
        self.assertEqual(chosen["overlaps"], 0)

    def test_um_path_is_monotone(self):
        interactions = []
        for candidate in self.scorer.evaluate_pair(
                ord("u"), ord("m"), b2.DEFAULT_CONTROLS)["candidates"]:
            interactions.append(candidate["interaction"])
        for earlier, later in zip(interactions, interactions[1:]):
            self.assertGreater(earlier, later)

    def test_contact_step_stays_valid_with_contacts_reported(self):
        record = self.scorer.score_geometry(ord("u"), ord("m"), 6, 2.0, 2.0)
        self.assertTrue(record["valid"])
        self.assertGreater(record["faces"], 0)
        self.assertEqual(record["overlaps"], 0)

    def test_b2_valid_superset_of_v1_valid(self):
        other = v1.PairScorer(self.dataset)
        for step in range(6, 11):
            old = other.score_geometry(ord("u"), ord("m"), step, 2.0, 2.0)
            new = self.scorer.score_geometry(ord("u"), ord("m"), step,
                                             2.0, 2.0)
            if old["valid"]:
                self.assertTrue(new["valid"])
            self.assertEqual(new["faces"], old["faces"])
            self.assertEqual(new["corners"], old["corners"])


class B2GuardrailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = CAPTURES / "roboto-16-mono.json"
        if not path.exists():
            raise unittest.SkipTest(f"missing retained capture {path}")
        cls.dataset = v1.load_mono_capture(str(path))

    def test_offgrid_and_wide_settings_stay_finite(self):
        scorer = b2.PairScorer(self.dataset)
        for scale, falloff in [(0.25, 0.5), (12.0, 16.0), (2.0, 4.0),
                               (2.0, 10.0), (4.0, 10.0), (6.0, 12.0),
                               (2.7, 3.3)]:
            for cohesion in (0.0, 2.0):
                ev = vr.evaluate_pair(scorer, ord("o"), ord("g"),
                                      cohesion, scale, falloff)
                for candidate in ev["candidates"]:
                    if candidate["valid"]:
                        self.assertTrue(math.isfinite(
                            candidate["interaction"]))
                        self.assertTrue(math.isfinite(candidate["cost"]))

    def test_reach_quarter_and_falloff_sixteen_finite(self):
        scorer = b2.PairScorer(self.dataset)
        record = vr.score_geometry(scorer, ord("u"), ord("m"), 8,
                                   0.25, 16.0)
        if record["valid"]:
            self.assertTrue(math.isfinite(record["interaction"]))

    def test_tie_rule_shared_with_v1(self):
        steps = [6, 7, 8, 9, 10]
        costs = [1.0, 0.5, 0.5, 0.75, 1.25]
        chosen, minimizing, _ = b2.choose_from_costs(
            steps, costs, [True] * 5, 8)
        self.assertEqual(minimizing, [7, 8])
        self.assertEqual(chosen, 8)


class B2RepairCorpusSpotTest(unittest.TestCase):
    """Pinned real-pair spot checks against the predeclared B2 records."""

    PAIRS = ["um", "og", "rt", "Th", "AV", "To", "vv", "nn", "mm", "ll", "oo"]

    @classmethod
    def setUpClass(cls):
        if not REPAIR_CORPUS.exists():
            raise unittest.SkipTest("missing repair corpus")
        cls.records = json.loads(REPAIR_CORPUS.read_text())["results"]
        cls.datasets = sorted(cls.records)
        if not cls.datasets:
            raise unittest.SkipTest("empty repair corpus")

    def test_spot_pairs_match_predeclared_b2(self):
        checked = 0
        for dataset_name in self.datasets:
            capture = CAPTURES / f"{dataset_name}.json"
            if not capture.exists():
                continue
            profile = "gray" if "gray" in dataset_name else "mono"
            load = (v1.load_gray_capture if profile == "gray"
                    else v1.load_mono_capture)
            dataset = load(str(capture))
            scorer = b2.PairScorer(dataset)
            for name in self.PAIRS:
                rec = self.records[dataset_name].get(name)
                if not rec or rec.get("missing") or rec.get("error"):
                    continue
                if rec.get("fallback"):
                    continue
                left, right = ord(name[0]), ord(name[1])
                if left not in dataset["cells"] or \
                        right not in dataset["cells"]:
                    continue
                ev = scorer.evaluate_pair(left, right,
                                          b2.DEFAULT_CONTROLS)
                for candidate, want in zip(ev["candidates"],
                                           rec["B2_inter"]):
                    if want is None:
                        self.assertFalse(candidate["valid"])
                    else:
                        self.assertTrue(candidate["valid"])
                        self.assertAlmostEqual(candidate["interaction"],
                                               want, delta=1e-9)
                    checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
