"""Independent split, diagnostics and state checks; no full network execution."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import string
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyangfit_pair_trial as trial
import yinyangfit_recovery as recovery
import yinyangfit_train as short

try:
    import numpy as np
    import torch
except ModuleNotFoundError:
    np = torch = None


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "experiments/contextual_spacing/reference/yinyangfit-recovery/pair-trial.lock.json"
REFERENCE = ROOT / "out/diagnostics/contextual-spacing/yinyangfit/recovery-sources/YinYangFit.ipynb"
PLAN_SHA256 = "7973d86f40ebef0ce9a30e568e526d0ee5ad142a9be0082160813c1d5121d705"
TRAINING = ["qs", "ea", "gf", "oz", "xw", "nh", "ur", "ty", "bm", "vi", "cd", "pl", "jk"]
HELDOUT = ["ca", "nx", "os", "se"]


class FrozenSplitAndDiagnosticsTests(unittest.TestCase):
    def test_split_is_the_predeclared_first_valid_permutation_without_scores(self):
        self.assertEqual(hashlib.sha256(PLAN.read_bytes()).hexdigest(), PLAN_SHA256)
        plan = json.loads(PLAN.read_text())
        excluded = set(plan["excluded_training_pairs"])
        namespace = "yinyangfit-pair-holdout-v1:20261101"
        admissible = []
        for nonce in range(7):
            letters = sorted(string.ascii_lowercase,
                             key=lambda c: hashlib.sha256(f"{namespace}:{nonce}:{c}".encode()).digest())
            pairs = [letters[i] + letters[i + 13] for i in range(13)]
            if all(pair not in excluded for pair in pairs):
                admissible.append((nonce, pairs))
        self.assertEqual(admissible, [(6, TRAINING)])
        self.assertEqual(trial.load_plan()["main_schedule"], TRAINING)
        self.assertEqual(sorted("".join(TRAINING)), list(string.ascii_lowercase))
        self.assertEqual(plan["training_pairs"], TRAINING)
        self.assertEqual(plan["training_evaluation_pairs"], [TRAINING[i] for i in (0, 4, 8, 12)])
        self.assertEqual(plan["heldout_pairs"], HELDOUT)
        for pair in HELDOUT:
            self.assertIn(pair, excluded)
            self.assertIn(pair[::-1], excluded)
            self.assertNotIn(pair, TRAINING)
            self.assertNotIn(pair[::-1], TRAINING)
        self.assertEqual(short.SCHEDULE, ("nn", "oo", "av"))

    def test_invalid_split_counts_order_exclusions_and_budget_are_rejected(self):
        plan = trial.load_plan()
        mutations = [
            lambda p: p.update(seed=1),
            lambda p: p.update(main_updates=12),
            lambda p: p.update(replay_from_completed_step=11),
            lambda p: p.update(heldout_pairs=["qs", "nx", "os", "se"]),
            lambda p: p["main_schedule"].reverse(),
            lambda p: p["training_pairs"].pop(),
            lambda p: p["excluded_training_pairs"].remove("ac"),
            lambda p: p["training_evaluation_pairs"].__setitem__(0, "ca"),
            lambda p: p["selection"].update(nonce=7),
            lambda p: p["optimizer"].update(learning_rate=0.01),
            lambda p: p["resource_limits"].update(rss_gib=64),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(plan)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(trial.TrainingError):
                trial.validate_plan(changed)
        self.assertEqual(short.SCHEDULE, ("nn", "oo", "av"))

    def test_rank_intervals_and_argmin_sets_do_not_turn_ties_into_success(self):
        d = trial.diagnostics([2., 0., 0., 1., 0.])
        self.assertEqual(d["best_candidate_deltas"], [-1, 0, 5])
        self.assertEqual((d["target_rank_lower"], d["target_rank_upper"]), (1, 3))
        self.assertEqual(d["target_ties"], 3)
        self.assertFalse(d["unique_target_minimum"])
        self.assertTrue(d["boundary_minimum"])
        self.assertEqual(d["cost_spread"], 2.)
        self.assertAlmostEqual(d["target_cross_entropy"], math.log(3 + math.exp(-1) + math.exp(-2)))
        all_tied = trial.diagnostics([0.] * 5)
        self.assertEqual(all_tied["best_candidate_deltas"], [-3, -1, 0, 1, 5])
        self.assertEqual((all_tied["target_rank_lower"], all_tied["target_rank_upper"]), (1, 5))
        self.assertFalse(all_tied["unique_target_minimum"])
        correct = trial.diagnostics([4., 3., 0., 2., 1.])
        self.assertEqual(correct["best_candidate_deltas"], [0])
        self.assertTrue(correct["unique_target_minimum"])
        self.assertFalse(correct["boundary_minimum"])

    def test_diagnostic_loss_is_stable_and_loss_reduction_is_not_distance_movement(self):
        costs = [5., 4., 3., 2., 1.]
        old = trial.diagnostics(costs)
        reduced = trial.diagnostics([v / 10 for v in costs])
        self.assertLess(reduced["target_cross_entropy"], old["target_cross_entropy"])
        self.assertEqual(reduced["best_candidate_deltas"], old["best_candidate_deltas"])
        self.assertEqual(reduced["target_rank_lower"], old["target_rank_lower"])
        self.assertAlmostEqual(trial.diagnostics([10000 + v for v in costs])["target_cross_entropy"],
                               old["target_cross_entropy"])
        for values in ([1, 2, 3, 4], [1, 2, math.nan, 4, 5], [1, 2, math.inf, 4, 5]):
            with self.subTest(values=values), self.assertRaises(trial.TrainingError):
                trial.diagnostics(values)
        aggregate = trial.aggregate([old, reduced])
        self.assertEqual(aggregate["unique_target_minima"], 0)
        self.assertEqual(aggregate["boundary_minima"], 2)
        self.assertAlmostEqual(aggregate["mean_target_cross_entropy"],
                               (old["target_cross_entropy"] + reduced["target_cross_entropy"]) / 2)


@unittest.skipUnless(torch is not None and np is not None, "isolated Torch recovery environment required")
class PairTrialStateTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        random.seed(147)
        np.random.seed(258)
        torch.manual_seed(369)
        random.gauss(0, 1)
        np.random.normal()
        self.plan = trial.load_plan()

    def tiny_trainer(self):
        # Small named tensors implement the real schema, without visual fields.
        model = torch.nn.Module()
        model.bg_direct, model.g_targets = torch.nn.Module(), torch.nn.Module()
        bg = {"b_to_g": 400, "G_input_weight": 10, "ray_weight": 10,
              "amplification_saturation": 160, "k": 10, "b": 10}
        inactive = ["target_a", "target_b", "target_c", "target_d", "target_s", "tolerance_a", "tolerance_b",
                    "tolerance_c", "tolerance_d", "tolerance_s", "loss_original_exponent", "gain_k", "traw",
                    "gain_exponent", "pars"]
        for name, count in bg.items():
            model.bg_direct.register_parameter(name, torch.nn.Parameter(torch.ones(count)))
        for name in ["general_exp", "loss_b", "loss_factor", "gain_factor"] + inactive:
            model.g_targets.register_parameter(name, torch.nn.Parameter(torch.ones(96 if name == "pars" else 40)))
        # Deliberately consume every RNG during construction before a restore.
        random.random(); np.random.random(); torch.randn(3)
        t = trial.PairTrialTrainer.__new__(trial.PairTrialTrainer)
        t.torch, t.np, t.plan = torch, np, copy.deepcopy(self.plan)
        t.scorer = type("Scorer", (), {"model": model})()
        t.optimizer = torch.optim.Adam(model.parameters(), lr=0.0011)
        t.parameter_names = list(dict(model.named_parameters()))
        t.parameter_specs = {name: (tuple(v.shape), str(v.dtype)) for name, v in model.named_parameters()}
        t.hyperparameters = {k: v for k, v in t.optimizer.state_dict()["param_groups"][0].items() if k != "params"}
        t.completed_steps = 0
        t.identity = {"policy": "independent-tiny-pair-trial-v1", "plan": copy.deepcopy(self.plan)}
        return t

    @staticmethod
    def tiny_step(t):
        noise = random.gauss(0, 1) + float(np.random.normal()) + float(torch.randn(()))
        t.optimizer.zero_grad(set_to_none=True)
        loss = sum(((v - (noise + t.completed_steps / 20)) ** 2).sum()
                   for name, v in t.scorer.model.named_parameters() if name in short.ACTIVE_NAMES)
        loss.backward()
        t.optimizer.step()
        t.completed_steps += 1

    def test_plan_aware_state_accepts_twelve_and_thirteen_and_rejects_leaks_or_corruption(self):
        t = self.tiny_trainer()
        for _ in range(12):
            self.tiny_step(t)
        good = t.payload()
        t.validate(good)
        active_id = next(iter(good["optimizer"]["state"]))
        mutations = [
            lambda p: p["position"].update(completed_steps=3, next_pair=TRAINING[3]),
            lambda p: p["position"].update(next_pair="ca"),
            lambda p: p["position"]["schedule"].__setitem__(12, "se"),
            lambda p: p["optimizer"]["param_groups"][0].update(lr=0.01),
            lambda p: p["optimizer"]["state"][active_id].update(step=torch.tensor(13.)),
            lambda p: p["optimizer"]["state"][active_id].update(exp_avg=torch.ones(1)),
            lambda p: p["model"][next(iter(p["model"]))].fill_(math.nan),
        ]
        rng = short.tensor_tree_digest(short.capture_rng(torch, np))
        for mutate in mutations:
            changed = copy.deepcopy(good)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(trial.TrainingError):
                t.validate(changed)
        self.assertEqual(rng, short.tensor_tree_digest(short.capture_rng(torch, np)))
        self.tiny_step(t)
        t.validate(t.payload())
        self.assertIsNone(t.payload()["position"]["next_pair"])
        self.assertEqual(short.SCHEDULE, ("nn", "oo", "av"))

    def test_thirteenth_stochastic_update_replays_exact_model_adam_rng_and_position(self):
        t = self.tiny_trainer()
        for _ in range(12):
            self.tiny_step(t)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint-12"
            t.save(path)
            self.tiny_step(t)
            expected = t.payload()
            restored = self.tiny_trainer()
            restored.restore(path)
            self.tiny_step(restored)
            actual = restored.payload()
            self.assertEqual(short.tensor_tree_digest(expected), short.tensor_tree_digest(actual))
            for key in short.STATE_KEYS:
                self.assertEqual(short.tensor_tree_digest(expected[key]), short.tensor_tree_digest(actual[key]))
            self.assertTrue(all(float(s["step"]) == 13 for s in actual["optimizer"]["state"].values()))
            self.assertEqual(actual["position"]["completed_steps"], 13)
            self.assertEqual(short.SCHEDULE, ("nn", "oo", "av"))

    def test_plan_mismatch_and_recomputed_checksum_position_corruption_fail_before_resume(self):
        t = self.tiny_trainer()
        for _ in range(12):
            self.tiny_step(t)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint-12"
            t.save(path)
            other = self.tiny_trainer()
            other.identity["plan"]["heldout_pairs"] = ["ca", "nx", "os", "re"]
            before = short.tensor_tree_digest(other.payload())
            with self.assertRaises(trial.TrainingError):
                other.restore(path)
            self.assertEqual(before, short.tensor_tree_digest(other.payload()))
            payload = t.payload()
            payload["position"].update(completed_steps=11, next_pair=TRAINING[11])
            torch.save(payload, path / "state.pt")
            manifest = json.loads((path / "manifest.json").read_text())
            manifest.update(position=payload["position"], state_sha256=recovery.sha256((path / "state.pt").read_bytes()),
                            semantic_state_sha256=short.tensor_tree_digest(payload))
            (path / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(trial.TrainingError, "counter"):
                short.CheckpointStore.load(path, t.identity, t.validate)

    def test_actual_update_uses_only_training_schedule_and_continuing_rng(self):
        if not REFERENCE.is_file():
            self.skipTest("run original input preparation first")
        t = self.tiny_trainer()
        t.initial_model = copy.deepcopy(t.scorer.model.state_dict())
        t.scorer.source = recovery.load_source(REFERENCE)
        t.scorer.namespace = {"estimate_min_loss": lambda p: torch.nn.functional.cross_entropy(
            -p, torch.tensor([2]))}
        def forbidden_reseed(*_args):
            raise AssertionError("training reused recovery evaluation's per-pair seeding")
        t.scorer.seed_for = forbidden_reseed
        requested, draws = [], []
        def inputs(pair):
            self.assertNotIn(pair, HELDOUT)
            requested.append(pair)
            return None, None
        t.scorer._pair_inputs = inputs
        def forward(_inputs):
            noise = (random.gauss(0, 1), float(np.random.normal()), float(torch.randn(())))
            draws.append(noise)
            coefficient = sum(v.mean() for name, v in t.scorer.model.named_parameters()
                              if name in short.ACTIVE_NAMES) + sum(noise) / 100
            return coefficient * torch.tensor([[5., 4., 3., 2., 1.]])
        t.scorer.model.forward = forward
        original_rng = short.capture_rng(torch, np)
        expected = [(random.gauss(0, 1), float(np.random.normal()), float(torch.randn(())))
                    for _ in TRAINING]
        short.restore_rng(original_rng, torch, np)
        records = []
        for _ in TRAINING:
            record = {}
            t.update(record)
            records.append(record)
        self.assertEqual(requested, TRAINING)
        self.assertEqual(draws, expected)
        self.assertEqual(t.completed_steps, 13)
        self.assertTrue(all(r["optimizer_update_applied"] for r in records))
        self.assertEqual([r["pair"] for r in records], TRAINING)
        self.assertEqual([r["rng_after_sha256"] for r in records[:-1]],
                         [r["rng_before_sha256"] for r in records[1:]])
        self.assertEqual(short.SCHEDULE, ("nn", "oo", "av"))

    def test_actual_update_blocks_a_heldout_before_inputs_or_optimizer(self):
        t = self.tiny_trainer()
        t.plan["main_schedule"][0] = "ca"
        before = short.tensor_tree_digest(t.payload())
        with self.assertRaisesRegex(trial.TrainingError, "heldout"):
            t.update({})
        self.assertEqual(before, short.tensor_tree_digest(t.payload()))

    def test_evaluation_keeps_roles_disjoint_and_restores_every_training_state(self):
        if not REFERENCE.is_file():
            self.skipTest("run original input preparation first")
        source = recovery.load_source(REFERENCE)
        t = self.tiny_trainer()
        self.tiny_step(t)
        t.reference, t.inputs = REFERENCE, Path("unused-by-fake")
        t.scorer.seed, t.scorer.threads = 20261101, 1
        constructor = self.tiny_trainer
        seen = []

        class FakeEvaluationScorer:
            fail = False
            def __init__(self, _reference, _inputs, policy, _seed, _threads):
                if policy != "noise_off":
                    raise AssertionError("heldout evaluation used noisy training policy")
                # Constructor changes all RNGs as the full scorer does.
                random.seed(1); np.random.seed(2); torch.manual_seed(3)
                self.model = constructor().scorer.model
                self.source = source
            def score(self, pair):
                seen.append(pair)
                random.gauss(0, 1); np.random.normal(); torch.randn(5)
                if self.fail and pair == "nx":
                    raise trial.TrainingError("heldout evaluation failed")
                return {"pair": pair, "scores": [5., 4., 3., 2., 1.]}

        before = short.tensor_tree_digest(t.payload())
        with mock.patch.object(recovery, "RecoveredScorer", FakeEvaluationScorer):
            result = t.evaluate()
        self.assertEqual(before, short.tensor_tree_digest(t.payload()))
        expected_training = [TRAINING[i] for i in (0, 4, 8, 12)]
        self.assertEqual(seen, expected_training + HELDOUT)
        self.assertEqual([r["pair"] for r in result["training"]["pairs"]], expected_training)
        self.assertEqual([r["pair"] for r in result["heldout"]["pairs"]], HELDOUT)
        self.assertTrue(result["training_optimizer_preserved"])
        self.assertEqual(result["heldout"]["aggregate"]["unique_target_minima"], 0)
        FakeEvaluationScorer.fail = True
        with mock.patch.object(recovery, "RecoveredScorer", FakeEvaluationScorer):
            with self.assertRaisesRegex(trial.TrainingError, "heldout evaluation failed"):
                t.evaluate()
        self.assertEqual(before, short.tensor_tree_digest(t.payload()))


if __name__ == "__main__":
    unittest.main()
