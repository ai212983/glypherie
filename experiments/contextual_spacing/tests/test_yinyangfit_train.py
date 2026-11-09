"""Independent optimizer/checkpoint gates, without full YinYangFit forwards.

The small stochastic Adam model exercises the checkpoint/RNG seam. It does not
establish the historical scorer's training behavior or optical acceptance.
"""
import copy
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyangfit_train as training
import yinyangfit_recovery as recovery

try:
    import numpy as np
    import torch
except ModuleNotFoundError:
    np = torch = None


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "out/diagnostics/contextual-spacing/yinyangfit/recovery-sources/YinYangFit.ipynb"
SCHEDULE = ["nn", "oo", "av"]


@unittest.skipUnless(torch is not None and np is not None, "isolated Torch recovery environment required")
class TrainingStateTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        random.seed(717)
        np.random.seed(818)
        torch.manual_seed(919)
        # Retain cached Gaussian values as well as the underlying generators.
        random.gauss(0, 1)
        np.random.normal()

    def test_rng_roundtrip_restores_all_three_streams_and_cached_gaussians(self):
        state = training.capture_rng(torch, np)
        expected = (random.gauss(0, 1), random.random(), np.random.normal(), np.random.random(), torch.randn(9))
        training.restore_rng(state, torch, np)
        actual = (random.gauss(0, 1), random.random(), np.random.normal(), np.random.random(), torch.randn(9))
        self.assertEqual(expected[:4], actual[:4])
        self.assertTrue(torch.equal(expected[4], actual[4]))

    def test_invalid_rng_state_is_rejected_before_global_stream_mutation(self):
        original = training.capture_rng(torch, np)
        invalid = copy.deepcopy(original)
        invalid["python"] = (original["python"][0], original["python"][1], math.nan)
        with self.assertRaises(training.TrainingError):
            training.restore_rng(invalid, torch, np)
        self.assertEqual(training.tensor_tree_digest(original),
                         training.tensor_tree_digest(training.capture_rng(torch, np)))

    def test_evaluation_rng_context_restores_after_seed_changes_and_exception(self):
        before = training.tensor_tree_digest(training.capture_rng(torch, np))
        with self.assertRaisesRegex(RuntimeError, "evaluation failed"):
            with training.preserve_rng(torch, np):
                random.seed(1)
                np.random.seed(2)
                torch.manual_seed(3)
                random.gauss(0, 1)
                np.random.normal(size=17)
                torch.nn.Linear(7, 3)
                raise RuntimeError("evaluation failed")
        self.assertEqual(before, training.tensor_tree_digest(training.capture_rng(torch, np)))

    def test_trainer_evaluation_preserves_training_state_even_when_constructor_reseeds(self):
        if not REFERENCE.is_file():
            self.skipTest("run original-domain input preparation first")
        source = recovery.load_source(REFERENCE)
        trainer = training.Trainer.__new__(training.Trainer)
        trainer.torch, trainer.np = torch, np
        trainer.reference, trainer.inputs = REFERENCE, Path("unused-by-evaluation-fake")
        model = torch.nn.Linear(2, 1)
        trainer.scorer = type("TrainingScorer", (), {"model": model, "seed": 123, "threads": 1})()
        trainer.optimizer = torch.optim.Adam(model.parameters(), lr=0.0011)
        for parameter in model.parameters():
            parameter.grad = torch.ones_like(parameter)
        trainer.optimizer.step()

        class EvaluationScorer:
            fail = False
            def __init__(self, _reference, _inputs, noise_policy, _seed, _threads):
                if noise_policy != "noise_off":
                    raise AssertionError("evaluation reused stochastic training noise")
                random.seed(1)
                np.random.seed(2)
                torch.manual_seed(3)
                self.model = torch.nn.Linear(2, 1)
                self.source = source
            def score(self, pair):
                random.gauss(0, 1)
                np.random.normal()
                torch.randn(5)
                if self.fail and pair == "oo":
                    raise training.TrainingError("evaluation probe failed")
                return {"pair": pair, "scores": [5., 4., 3., 2., 1.]}

        def state():
            return {"model": model.state_dict(), "optimizer": trainer.optimizer.state_dict(),
                    "rng": training.capture_rng(torch, np)}
        before = training.tensor_tree_digest(state())
        with mock.patch.object(recovery, "RecoveredScorer", EvaluationScorer):
            result = trainer.evaluate()
            self.assertEqual([v["pair"] for v in result["pairs"]], SCHEDULE)
            self.assertTrue(result["training_rng_preserved"])
            self.assertTrue(result["training_parameters_preserved"])
            self.assertEqual(before, training.tensor_tree_digest(state()))
            EvaluationScorer.fail = True
            with self.assertRaisesRegex(training.TrainingError, "evaluation probe failed"):
                trainer.evaluate()
            self.assertEqual(before, training.tensor_tree_digest(state()))

    def test_semantic_digest_preserves_tensor_values_shape_and_dtype(self):
        matrix = torch.tensor([[1., 2.], [3., 4.]])
        view = matrix.t().contiguous().t()
        self.assertFalse(view.is_contiguous())
        a = {"weights": matrix, "optimizer": {3: [0.1, 0.9]}}
        b = {"optimizer": {3: [0.1, 0.9]}, "weights": view}
        self.assertEqual(training.tensor_tree_digest(a), training.tensor_tree_digest(b))
        for different in (matrix.to(torch.float64), matrix.reshape(4), matrix + 1):
            self.assertNotEqual(training.tensor_tree_digest(matrix), training.tensor_tree_digest(different))

    def test_nested_nonfinite_model_or_optimizer_values_are_rejected(self):
        valid = {"state": {0: {"step": torch.tensor(3.), "exp_avg": torch.ones(2)}}, "lr": 0.0011}
        training.validate_finite_tree(valid, "optimizer")
        for value in (math.nan, math.inf, -math.inf, torch.tensor([1., math.nan]), torch.tensor(math.inf)):
            with self.subTest(value=str(value)), self.assertRaises(training.TrainingError):
                training.validate_finite_tree({"nested": [0, {"bad": value}]}, "state")

    def test_stochastic_adam_checkpoint_replays_without_reseeding_each_pair(self):
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.0011)
        identity = {"protocol": "independent-tiny-replay-v1", "schedule": SCHEDULE, "source": "pinned"}

        def step(current, opt, position):
            # These independent stochastic inputs make a missing RNG component
            # change the update even when model and Adam state are restored.
            noise = random.gauss(0, 1) + float(np.random.normal()) + float(torch.randn(()))
            x = torch.tensor([[1., noise], [noise, -1.]])
            target = torch.tensor([[0.25 * (position + 1)], [-0.5]])
            opt.zero_grad(set_to_none=True)
            loss = ((current(x) - target) ** 2).sum()
            loss.backward()
            opt.step()

        def validator(payload):
            position = payload["position"]["completed_steps"]
            next_pair = SCHEDULE[position] if position < 3 else None
            if (position not in (1, 2, 3) or payload["position"]["schedule"] != SCHEDULE
                    or payload["position"]["next_pair"] != next_pair):
                raise training.TrainingError("invalid independent replay position")

        step(model, optimizer, 0)
        state = {"model": copy.deepcopy(model.state_dict()), "optimizer": copy.deepcopy(optimizer.state_dict()),
                 "rng": training.capture_rng(torch, np),
                 "position": {"completed_steps": 1, "schedule": SCHEDULE, "next_pair": "oo"}}
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "step-1"
            training.CheckpointStore.save(checkpoint, state, identity, validate=validator)
            for position in (1, 2):
                step(model, optimizer, position)
            expected = {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                        "rng": training.capture_rng(torch, np)}
            expected_digest = training.tensor_tree_digest(expected)
            # Construction intentionally consumes Torch RNG; restoration must
            # take place after constructing and loading both stateful objects.
            restored = torch.nn.Linear(2, 1)
            restored_optimizer = torch.optim.Adam(restored.parameters(), lr=0.0011)
            payload = training.CheckpointStore.load(checkpoint, identity, validate=validator)
            restored.load_state_dict(payload["model"], strict=True)
            restored_optimizer.load_state_dict(payload["optimizer"])
            training.restore_rng(payload["rng"], torch, np)
            for position in (1, 2):
                step(restored, restored_optimizer, position)
            actual = {"model": restored.state_dict(), "optimizer": restored_optimizer.state_dict(),
                      "rng": training.capture_rng(torch, np)}
            self.assertEqual(expected_digest, training.tensor_tree_digest(actual))
            for name, value in expected["model"].items():
                self.assertTrue(torch.equal(value, actual["model"][name]))
            self.assertEqual(expected["optimizer"]["param_groups"], actual["optimizer"]["param_groups"])
            for index, state in expected["optimizer"]["state"].items():
                for name, value in state.items():
                    self.assertTrue(torch.equal(value, actual["optimizer"]["state"][index][name]))
            self.assertEqual(expected["rng"]["python"], actual["rng"]["python"])
            self.assertEqual(expected["rng"]["numpy"], actual["rng"]["numpy"])
            self.assertTrue(torch.equal(expected["rng"]["torch"], actual["rng"]["torch"]))
            self.assertTrue(all(float(value["step"]) == 3 for value in restored_optimizer.state.values()))

    def test_checkpoint_identity_or_validator_failure_does_not_change_rng(self):
        identity = {"source": "pinned", "inputs": "fixed", "environment": {"torch": torch.__version__}}
        payload = {"weights": torch.tensor([2.]), "rng": training.capture_rng(torch, np),
                   "position": {"completed_steps": 1, "schedule": SCHEDULE, "next_pair": "oo"}}
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "checkpoint"
            training.CheckpointStore.save(checkpoint, payload, identity)
            before = training.tensor_tree_digest(training.capture_rng(torch, np))
            for field in identity:
                changed = copy.deepcopy(identity)
                changed[field] = "changed"
                with self.subTest(field=field), self.assertRaises(training.TrainingError):
                    training.CheckpointStore.load(checkpoint, changed)
            def reject(_payload):
                raise training.TrainingError("rejected by protocol")
            with self.assertRaisesRegex(training.TrainingError, "rejected by protocol"):
                training.CheckpointStore.load(checkpoint, identity, validate=reject)
            self.assertEqual(before, training.tensor_tree_digest(training.capture_rng(torch, np)))

    def test_failed_checkpoint_validation_never_publishes_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "checkpoint"
            def reject(_payload):
                raise training.TrainingError("invalid step")
            with self.assertRaisesRegex(training.TrainingError, "invalid step"):
                training.CheckpointStore.save(checkpoint, {"weights": torch.ones(1)}, {"source": "pinned"},
                                              validate=reject)
            self.assertFalse(checkpoint.exists())

    def protocol_state(self):
        """Small named tensors exercise real Adam schema without visual fields."""
        model = torch.nn.Module()
        model.bg_direct = torch.nn.Module()
        model.g_targets = torch.nn.Module()
        bg = {"b_to_g": 400, "G_input_weight": 10, "ray_weight": 10,
              "amplification_saturation": 160, "k": 10, "b": 10}
        inactive = ["target_a", "target_b", "target_c", "target_d", "target_s",
                    "tolerance_a", "tolerance_b", "tolerance_c", "tolerance_d", "tolerance_s",
                    "loss_original_exponent", "gain_k", "traw", "gain_exponent", "pars"]
        for name, count in bg.items():
            model.bg_direct.register_parameter(name, torch.nn.Parameter(torch.ones(count)))
        for name in ["general_exp", "loss_b", "loss_factor", "gain_factor"] + inactive:
            model.g_targets.register_parameter(name, torch.nn.Parameter(torch.ones(96 if name == "pars" else 40)))
        active = {"bg_direct." + name for name in bg}
        active.update("g_targets." + name for name in ["general_exp", "loss_b", "loss_factor", "gain_factor"])
        optimizer = torch.optim.Adam(model.parameters(), lr=0.0011)
        for name, parameter in model.named_parameters():
            parameter.grad = torch.ones_like(parameter) if name in active else None
        optimizer.step()
        names = list(dict(model.named_parameters()))
        specs = {name: (tuple(value.shape), str(value.dtype)) for name, value in model.named_parameters()}
        payload = {"model": copy.deepcopy(model.state_dict()), "optimizer": copy.deepcopy(optimizer.state_dict()),
                   "rng": training.capture_rng(torch, np),
                   "position": {"completed_steps": 1, "schedule": SCHEDULE, "next_pair": "oo"}}
        hyperparameters = {k: v for k, v in payload["optimizer"]["param_groups"][0].items() if k != "params"}
        validator = lambda value: training.validate_training_payload(value, hyperparameters, names, specs)
        return model, payload, validator

    def test_declared_training_payload_rejects_schedule_optimizer_and_tensor_corruption(self):
        _model, payload, validator = self.protocol_state()
        validator(payload)
        active_id = next(iter(payload["optimizer"]["state"]))
        mutations = [
            lambda p: p["position"].update(completed_steps=2, next_pair="av"),
            lambda p: p["position"].update(schedule=list(reversed(SCHEDULE))),
            lambda p: p["position"].update(next_pair="av"),
            lambda p: p["optimizer"]["param_groups"][0].update(lr=0.01),
            lambda p: p["optimizer"]["param_groups"][0]["params"].reverse(),
            lambda p: p["optimizer"]["state"][active_id].update(step=torch.tensor(2.)),
            lambda p: p["optimizer"]["state"][active_id].update(exp_avg=torch.ones(1)),
            lambda p: p["optimizer"]["state"][active_id]["exp_avg_sq"].fill_(-1),
            lambda p: p["model"].update({next(iter(p["model"])): torch.ones(1, dtype=torch.float64)}),
            lambda p: p["model"][next(iter(p["model"]))].fill_(math.nan),
        ]
        before_rng = training.tensor_tree_digest(training.capture_rng(torch, np))
        for mutate in mutations:
            changed = copy.deepcopy(payload)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(training.TrainingError):
                validator(changed)
        self.assertEqual(before_rng, training.tensor_tree_digest(training.capture_rng(torch, np)))

    def test_checkpoint_semantic_validation_runs_even_with_consistent_checksums(self):
        _model, payload, validator = self.protocol_state()
        identity = {"source": "pinned", "schedule": SCHEDULE}
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "checkpoint"
            training.CheckpointStore.save(checkpoint, payload, identity, validate=validator)
            payload["position"]["completed_steps"] = 2
            payload["position"]["next_pair"] = "av"
            torch.save(payload, checkpoint / "state.pt")
            manifest = json.loads((checkpoint / "manifest.json").read_text())
            manifest.update(position=payload["position"],
                            state_sha256=recovery.sha256((checkpoint / "state.pt").read_bytes()),
                            semantic_state_sha256=training.tensor_tree_digest(payload))
            (checkpoint / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(training.TrainingError, "step counter"):
                training.CheckpointStore.load(checkpoint, identity, validate=validator)

    def test_checkpoint_type_and_payload_bytes_are_not_silently_accepted(self):
        _model, payload, validator = self.protocol_state()
        identity = {"source": "pinned"}
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "checkpoint"
            training.CheckpointStore.save(checkpoint, payload, identity, validate=validator)
            manifest_path = checkpoint / "manifest.json"
            original = json.loads(manifest_path.read_text())
            for field, value in (("artifact_kind", "untrained"), ("role", "unknown")):
                changed = dict(original)
                changed[field] = value
                manifest_path.write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(training.TrainingError):
                    training.CheckpointStore.load(checkpoint, identity, validate=validator)
            manifest_path.write_text(json.dumps(original))
            path = checkpoint / "state.pt"
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaisesRegex(training.TrainingError, "file identity"):
                training.CheckpointStore.load(checkpoint, identity, validate=validator)

    def test_gradient_census_rejects_nonfinite_missing_or_unexpected_paths(self):
        model, _payload, _validator = self.protocol_state()
        census = training.gradient_census(model)
        self.assertEqual(sum(v["numel"] for v in census.values() if v["has_gradient"]), 760)
        self.assertEqual(sum(v["numel"] for v in census.values() if not v["has_gradient"]), 656)
        model.g_targets.loss_b.grad = None
        with self.assertRaisesRegex(training.TrainingError, "reachability"):
            training.gradient_census(model)
        model.g_targets.loss_b.grad = torch.ones_like(model.g_targets.loss_b)
        model.g_targets.pars.grad = torch.ones_like(model.g_targets.pars)
        with self.assertRaisesRegex(training.TrainingError, "reachability"):
            training.gradient_census(model)
        model.g_targets.pars.grad = None
        model.g_targets.loss_b.grad[0] = math.inf
        with self.assertRaisesRegex(training.TrainingError, "nonfinite gradient"):
            training.gradient_census(model)

    def test_original_loss_guards_do_not_replace_the_objective(self):
        if not REFERENCE.is_file():
            self.skipTest("run original-domain input preparation first")
        source = recovery.load_source(REFERENCE)
        for penalties in ([1., 2., 3., 4., 5.], [6.625, 1.875, 1., 2.125, 41.625]):
            actual = training.validate_loss_values(source, penalties)
            self.assertEqual(actual["analysis"]["status"], "valid_for_original_evaluation")
            observed = recovery.observe_original_loss_from_source(source, penalties)
            self.assertEqual(actual["observation"]["raw_loss"], observed["raw_loss"])
        with self.assertRaises(training.TrainingError):
            training.validate_loss_values(source, [9., 1., 0., 1., 25.])
        for penalties in ([1., 2., math.nan, 4., 5.], [1., 2., math.inf, 4., 5.]):
            with self.assertRaises(training.TrainingError):
                training.validate_loss_values(source, penalties)


if __name__ == "__main__":
    unittest.main()
