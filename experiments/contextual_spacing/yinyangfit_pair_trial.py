"""Frozen within-font pair-identity training trial for historical YinYangFit.

The original scorer, Gaussian training draws, hybrid loss and Adam settings
remain unchanged. This wrapper owns the predeclared data split and bounded
one-pass protocol. Neither the holdout nor lower loss selects another run.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import gc
import hashlib
import io
import json
import math
from pathlib import Path
import string
import subprocess
import sys
import time
import traceback

import yinyangfit_recovery as recovery
import yinyangfit_train as short


POLICY = "yinyangfit-pair-holdout-v1"
PLAN_PATH = Path(__file__).with_name("reference") / "yinyangfit-recovery" / "pair-trial.lock.json"
TrainingError = short.TrainingError


def canonical_hash(value):
    return recovery.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def validate_plan(plan):
    """Validate the locked experiment before any input is scored or updated."""
    if plan.get("schema") != "yinyangfit-pair-trial-plan-v1" or plan.get("policy") != POLICY:
        raise TrainingError("pair trial plan identity mismatch")
    if plan.get("seed") != 20261101 or plan.get("threads") != 4:
        raise TrainingError("pair trial initialization policy mismatch")
    schedule = plan.get("main_schedule")
    if (not isinstance(schedule, list) or len(schedule) != 13
            or any(not isinstance(p, str) or len(p) != 2 or any(c not in string.ascii_lowercase for c in p)
                   for p in schedule)
            or len(set(schedule)) != 13 or schedule != plan.get("training_pairs")):
        raise TrainingError("pair trial requires thirteen unique lowercase training pairs")
    if sorted("".join(schedule)) != list(string.ascii_lowercase):
        raise TrainingError("pair trial must cover each lowercase scalar exactly once")
    if plan.get("heldout_pairs") != ["ca", "nx", "os", "se"]:
        raise TrainingError("pair trial holdout identity mismatch")
    excluded = plan.get("excluded_training_pairs")
    if (not isinstance(excluded, list)
            or any(not isinstance(p, str) or len(p) != 2 or any(c not in string.ascii_lowercase for c in p)
                   for p in excluded)
            or excluded != sorted(set(excluded)) or any(p[::-1] not in excluded for p in excluded)):
        raise TrainingError("pair trial exclusion policy mismatch")
    if any(p not in excluded or p[::-1] not in excluded for p in plan["heldout_pairs"]):
        raise TrainingError("heldout pairs and reversals must be excluded from training")
    if set(schedule) & set(excluded):
        raise TrainingError("a heldout or diagnostic pair entered training")
    indices = plan.get("training_evaluation_indices")
    if indices != [0, 4, 8, 12] or plan.get("training_evaluation_pairs") != [schedule[i] for i in indices]:
        raise TrainingError("training evaluation subset differs from frozen protocol")
    selection = plan.get("selection", {})
    if selection.get("namespace") != POLICY + ":20261101":
        raise TrainingError("pair trial permutation namespace mismatch")
    nonce = selection.get("nonce")
    if type(nonce) is not int or not 0 <= nonce < 10000:
        raise TrainingError("pair trial permutation work bound exceeded")
    for candidate in range(nonce + 1):
        alphabet = sorted(string.ascii_lowercase, key=lambda c: hashlib.sha256(
            f"{selection['namespace']}:{candidate}:{c}".encode()).digest())
        pairs = [a + b for a, b in zip(alphabet[:13], alphabet[13:])]
        if not set(pairs) & set(excluded):
            if candidate != nonce or pairs != schedule:
                raise TrainingError("pair trial is not the first admissible frozen permutation")
            break
    else:
        raise TrainingError("pair trial permutation does not satisfy exclusions")
    if (plan.get("main_updates"), plan.get("replay_updates"), plan.get("replay_from_completed_step")) != (13, 1, 12):
        raise TrainingError("pair trial update/replay counts mismatch")
    optimizer = plan.get("optimizer", {})
    if optimizer.get("name") != "torch.optim.Adam" or optimizer.get("learning_rate") != short.LEARNING_RATE:
        raise TrainingError("pair trial optimizer differs from source settings")
    if plan.get("evaluation_times") != ["before", "after"]:
        raise TrainingError("pair trial evaluation times differ")
    if plan.get("resource_limits") != {"wall_seconds": 2100, "rss_gib": 24}:
        raise TrainingError("pair trial resource budget differs")
    return plan


def load_plan(path=PLAN_PATH):
    return validate_plan(json.loads(Path(path).read_text()))


def diagnostics(values):
    """Describe all candidate choices, including ties; never choose a favorable tie."""
    values = [float(v) for v in values]
    if len(values) != 5 or not all(math.isfinite(v) for v in values):
        raise TrainingError("diagnostics require five finite source costs")
    logits = [-v for v in values]
    maximum = max(logits)
    nll = values[2] + maximum + math.log(sum(math.exp(v - maximum) for v in logits))
    less = sum(v < values[2] for v in values)
    ties = sum(v == values[2] for v in values)
    best = [d for d, v in zip(recovery.DELTAS, values) if v == min(values)]
    return dict(target_cross_entropy=nll, target_rank_lower=1 + less, target_rank_upper=less + ties,
                target_rank=1 + less, target_ties=ties, best_candidate_deltas=best,
                unique_target_minimum=best == [0], boundary_minimum=any(v in (-3, 5) for v in best),
                cost_spread=max(values) - min(values))


def aggregate(pairs):
    return dict(pair_count=len(pairs),
                mean_target_cross_entropy=math.fsum(p["target_cross_entropy"] for p in pairs) / len(pairs),
                mean_target_rank_lower=math.fsum(p["target_rank_lower"] for p in pairs) / len(pairs),
                mean_target_rank_upper=math.fsum(p["target_rank_upper"] for p in pairs) / len(pairs),
                unique_target_minima=sum(p["unique_target_minimum"] for p in pairs),
                boundary_minima=sum(p["boundary_minimum"] for p in pairs),
                tied_target_positions=sum(p["target_ties"] > 1 for p in pairs),
                mean_cost_spread=math.fsum(p["cost_spread"] for p in pairs) / len(pairs))


def validate_payload(payload, hyperparameters, parameter_names, parameter_specs, plan):
    """Plan-aware state validation; frozen short-trial globals are never changed."""
    import numpy as np
    import torch
    if set(payload) != short.STATE_KEYS:
        raise TrainingError("pair-trial checkpoint field inventory mismatch")
    position = payload["position"]
    if set(position) != {"completed_steps", "schedule", "next_pair"}:
        raise TrainingError("checkpoint position fields differ")
    n = position["completed_steps"]
    schedule = plan["main_schedule"]
    if type(n) is not int or not 0 <= n <= len(schedule) or position["schedule"] != schedule:
        raise TrainingError("checkpoint schedule/step mismatch")
    if position["next_pair"] != (schedule[n] if n < len(schedule) else None):
        raise TrainingError("checkpoint next training pair mismatch")
    if set(payload["model"]) != set(parameter_names):
        raise TrainingError("checkpoint parameter field inventory mismatch")
    for name, value in payload["model"].items():
        if not isinstance(value, torch.Tensor) or (tuple(value.shape), str(value.dtype)) != parameter_specs[name]:
            raise TrainingError("checkpoint parameter shape/dtype mismatch")
    optimizer = payload["optimizer"]
    if set(optimizer) != {"state", "param_groups"} or len(optimizer["param_groups"]) != 1:
        raise TrainingError("checkpoint optimizer structure differs")
    group = dict(optimizer["param_groups"][0])
    ids = group.pop("params", None)
    if ids != list(range(len(parameter_names))) or group != hyperparameters:
        raise TrainingError("checkpoint optimizer hyperparameters/order mismatch")
    active = {i for i, name in enumerate(parameter_names) if name in short.ACTIVE_NAMES}
    if set(optimizer["state"]) != (active if n else set()):
        raise TrainingError("checkpoint optimizer active-state inventory mismatch")
    for index, state in optimizer["state"].items():
        if set(state) != {"step", "exp_avg", "exp_avg_sq"}:
            raise TrainingError("checkpoint Adam state fields differ")
        step = state["step"]
        if (not isinstance(step, torch.Tensor) or step.shape != torch.Size([])
                or step.dtype != torch.float32 or float(step) != n):
            raise TrainingError("checkpoint Adam counter mismatch")
        parameter = payload["model"][parameter_names[index]]
        for key in ("exp_avg", "exp_avg_sq"):
            if (not isinstance(state[key], torch.Tensor) or state[key].shape != parameter.shape
                    or state[key].dtype != parameter.dtype):
                raise TrainingError("checkpoint Adam tensor shape/dtype mismatch")
        if (state["exp_avg_sq"] < 0).any().item():
            raise TrainingError("checkpoint Adam squared average is negative")
    short.validate_finite_tree(payload["model"], "model")
    short.validate_finite_tree(optimizer, "optimizer")
    with short.preserve_rng(torch, np):
        short.restore_rng(payload["rng"], torch, np)


class PairTrialTrainer:
    def __init__(self, reference, inputs, plan, plan_file_sha256=None):
        import numpy as np
        import torch
        self.plan = copy.deepcopy(validate_plan(plan))
        self.reference, self.inputs = reference, inputs
        self.torch, self.np = torch, np
        self.scorer = recovery.RecoveredScorer(reference, inputs, "reference_seeded_per_pair", plan["seed"], plan["threads"])
        self.scorer.model.train()
        self.optimizer = torch.optim.Adam(self.scorer.model.parameters(), lr=short.LEARNING_RATE)
        self.parameter_names = list(dict(self.scorer.model.named_parameters()))
        self.parameter_specs = {name: (tuple(v.shape), str(v.dtype)) for name, v in self.scorer.model.named_parameters()}
        self.hyperparameters = {k: v for k, v in self.optimizer.state_dict()["param_groups"][0].items() if k != "params"}
        self.completed_steps = 0
        self.initial_model = copy.deepcopy(self.scorer.model.state_dict())
        metadata = self.scorer.metadata()
        keys = ("revision", "notebook_sha256", "adapter_sha256", "selected_ast_sha256", "input_npz_sha256",
                "input_manifest_sha256", "globals", "environment", "parameters", "fixed_tensor_state")
        self.identity = json.loads(json.dumps(dict(
            policy=POLICY, pair_trial_adapter_sha256=recovery.sha256(Path(__file__).read_bytes()),
            short_helper_sha256=recovery.sha256(Path(short.__file__).read_bytes()),
            plan_sha256=canonical_hash(plan),
            plan_file_sha256=plan_file_sha256 or recovery.sha256(PLAN_PATH.read_bytes()), plan=plan,
            recovered_source={k: metadata[k] for k in keys},
            training_rng="Continue Python/NumPy/Torch RNG after fresh recovered initialization; never reseed per pair",
            evaluation_noise_policy="noise_off", optimizer=dict(name="torch.optim.Adam", **self.hyperparameters)
        ), allow_nan=False))

    def payload(self):
        n, schedule = self.completed_steps, self.plan["main_schedule"]
        return dict(model=copy.deepcopy(self.scorer.model.state_dict()),
                    optimizer=copy.deepcopy(self.optimizer.state_dict()), rng=short.capture_rng(self.torch, self.np),
                    position=dict(completed_steps=n, schedule=schedule,
                                  next_pair=schedule[n] if n < len(schedule) else None))

    def validate(self, payload):
        validate_payload(payload, self.hyperparameters, self.parameter_names, self.parameter_specs, self.plan)

    def save(self, path, role="main"):
        return short.CheckpointStore.save(path, self.payload(), self.identity, self.validate, role)

    def restore(self, path):
        payload = short.CheckpointStore.load(path, self.identity, self.validate)
        self.scorer.model.load_state_dict(payload["model"], strict=True)
        self.optimizer.load_state_dict(payload["optimizer"])
        short.restore_rng(payload["rng"], self.torch, self.np)
        self.completed_steps = payload["position"]["completed_steps"]

    def update(self, record, changed=lambda: None):
        schedule = self.plan["main_schedule"]
        if self.completed_steps >= len(schedule):
            raise TrainingError("frozen pair schedule is complete")
        pair = schedule[self.completed_steps]
        if pair in self.plan["heldout_pairs"]:
            raise TrainingError("heldout pair entered optimizer")
        record.update(step=self.completed_steps + 1, pair=pair, optimizer_update_applied=False,
                      rng_before_sha256=short.tensor_tree_digest(short.capture_rng(self.torch, self.np)))
        self.optimizer.zero_grad(set_to_none=True)
        self.scorer.intermediates = {}
        left, right = self.scorer._pair_inputs(pair)
        start = time.perf_counter()
        penalties = self.scorer.model((left, right, [pair[0]], [pair[1]], False))
        values = penalties.detach().cpu().numpy()[0].tolist()
        record["scores"] = [v if math.isfinite(v) else str(v) for v in values]
        record["forward_seconds"] = time.perf_counter() - start
        changed()
        if not all(math.isfinite(v) for v in values) or len(set(values)) == 1:
            raise TrainingError("nonfinite or constant training costs")
        record["loss_gate"] = short.validate_loss_values(self.scorer.source, values)
        with contextlib.redirect_stdout(io.StringIO()):
            loss = self.scorer.namespace["estimate_min_loss"](penalties)
        if not self.torch.isfinite(loss).item():
            raise TrainingError("nonfinite original differentiable loss")
        record["loss"] = float(loss.detach())
        start = time.perf_counter()
        loss.backward()
        record["backward_seconds"] = time.perf_counter() - start
        record["gradients"] = short.gradient_census(self.scorer.model)
        changed()
        self.optimizer.step()
        record["optimizer_update_applied"] = True
        changed()
        short.validate_finite_tree(self.scorer.model.state_dict(), "post-update model")
        short.validate_finite_tree(self.optimizer.state_dict(), "post-update optimizer")
        self.completed_steps += 1
        self.validate(self.payload())
        for name, value in self.scorer.model.state_dict().items():
            if name not in short.ACTIVE_NAMES and not self.torch.equal(value, self.initial_model[name]):
                raise TrainingError("inactive parameter changed: " + name)
        record.update(status="update_completed", parameter_sha256=short.tensor_tree_digest(self.scorer.model.state_dict()),
                      optimizer_sha256=short.tensor_tree_digest(self.optimizer.state_dict()),
                      rng_after_sha256=short.tensor_tree_digest(short.capture_rng(self.torch, self.np)))
        return record

    def evaluate(self, changed=lambda _group, _result: None):
        before = {k: short.tensor_tree_digest(v) for k, v in self.payload().items()}
        groups = {}
        with short.preserve_rng(self.torch, self.np):
            evaluator = recovery.RecoveredScorer(self.reference, self.inputs, "noise_off",
                                                 self.plan["seed"], self.plan["threads"])
            evaluator.model.load_state_dict(self.scorer.model.state_dict(), strict=True)
            for group, key in (("training", "training_evaluation_pairs"), ("heldout", "heldout_pairs")):
                pairs = []
                for pair in self.plan[key]:
                    result = evaluator.score(pair)
                    result["loss_gate"] = short.validate_loss_values(evaluator.source, result["scores"])
                    result.update(diagnostics(result["scores"]))
                    pairs.append(result)
                    changed(group, result)
                groups[group] = dict(pairs=pairs, aggregate=aggregate(pairs))
            del evaluator
            gc.collect()
        after = {k: short.tensor_tree_digest(v) for k, v in self.payload().items()}
        if before != after:
            raise TrainingError("evaluation changed training model, optimizer, RNG or position")
        groups.update(training_rng_preserved=True, training_parameters_preserved=True,
                      training_optimizer_preserved=True, training_position_preserved=True,
                      diagnostic_precision="Python binary64 log-sum-exp on retained float32 costs")
        return groups


def summarize(report):
    result = dict(status=report["status"], policy=POLICY,
                  main_completed_steps=report.get("main_completed_steps", 0),
                  main_optimizer_updates_executed=report.get("main_optimizer_updates_executed", 0),
                  replay_optimizer_updates_executed=report.get("replay_optimizer_updates_executed", 0),
                  total_optimizer_updates_executed=report.get("total_optimizer_updates_executed", 0),
                  resume_bit_identity=report.get("resume_bit_identity", False),
                  process_peak_rss_gib=report.get("process_peak_rss_bytes", 0) / 2**30,
                  remaining=["Within-font pair holdout only, shared glyphs and incomplete role coverage",
                             "One pass does not establish convergence or optical quality",
                             "No source/size/bitdepth transfer or browser inference established"])
    if "supervisor" in report:
        result["wall_seconds"] = report["supervisor"]["wall_seconds"]
    for phase in ("before", "after"):
        evaluation = report.get("evaluation_" + phase)
        if evaluation is not None:
            result["evaluation_" + phase] = {
                group: dict(aggregate=evaluation[group]["aggregate"], pairs=[{
                    key: pair[key] for key in ("pair", "scores", "target_cross_entropy", "target_rank_lower",
                                               "target_rank_upper", "target_ties", "best_candidate_deltas",
                                               "unique_target_minimum", "boundary_minimum", "cost_spread")
                } for pair in evaluation[group]["pairs"]]) for group in ("training", "heldout")}
    if "error" in report:
        result["error"] = report["error"]
    return result


def run_worker(args):
    output = Path(args.output)
    report = dict(status="running", policy=POLICY, phases=[], main_updates=[], replay_updates=[],
                  main_completed_steps=0, evaluation_progress=[], plan_file_sha256=recovery.sha256(Path(args.plan).read_bytes()))
    path = output / "report.json"
    def flush():
        report["main_optimizer_updates_executed"] = sum(r.get("optimizer_update_applied", False) for r in report["main_updates"])
        report["replay_optimizer_updates_executed"] = sum(r.get("optimizer_update_applied", False) for r in report["replay_updates"])
        report["total_optimizer_updates_executed"] = report["main_optimizer_updates_executed"] + report["replay_optimizer_updates_executed"]
        recovery.write_json(path, report)
    def phase(name):
        report["phases"].append(name)
        flush()
    def evaluated(group, result):
        report["evaluation_progress"].append(dict(phase=report["phases"][-1], group=group, result=result))
        flush()
    flush()
    try:
        phase("validate_frozen_split_and_prepare_fresh_scorer")
        plan = load_plan(args.plan)
        trainer = PairTrialTrainer(args.reference, args.inputs, plan, report["plan_file_sha256"])
        report["identity"] = trainer.identity
        report["initial_parameter_sha256"] = short.tensor_tree_digest(trainer.scorer.model.state_dict())
        report["initialization_kind"] = "fresh recovered initialization, not prior trained state"
        phase("noise_off_evaluation_before")
        report["evaluation_before"] = trainer.evaluate(evaluated)
        trainer.save(output / "checkpoint-00")
        for _ in plan["main_schedule"]:
            record = {}
            report["main_updates"].append(record)
            phase(f"main_update:{trainer.completed_steps + 1}")
            trainer.update(record, flush)
            report["main_completed_steps"] = trainer.completed_steps
            trainer.save(output / f"checkpoint-{trainer.completed_steps:02}")
            flush()
            gc.collect()
            print(json.dumps(dict(phase="main_update_completed", step=trainer.completed_steps, pair=record["pair"])), flush=True)
        expected = trainer.payload()
        report["main_final_digests"] = {k: short.tensor_tree_digest(expected[k]) for k in short.STATE_KEYS}
        phase("noise_off_evaluation_after")
        report["evaluation_after"] = trainer.evaluate(evaluated)
        phase("resume_penultimate_checkpoint_and_replay_last_update")
        replay = PairTrialTrainer(args.reference, args.inputs, plan, report["plan_file_sha256"])
        start = plan["replay_from_completed_step"]
        replay.restore(output / f"checkpoint-{start:02}")
        while replay.completed_steps < len(plan["main_schedule"]):
            record = {}
            report["replay_updates"].append(record)
            replay.update(record, flush)
            flush()
        actual = replay.payload()
        report["replay_final_digests"] = {k: short.tensor_tree_digest(actual[k]) for k in short.STATE_KEYS}
        if report["main_final_digests"] != report["replay_final_digests"]:
            raise TrainingError("replayed final state is not bit-identical")
        replay.save(output / "replay-checkpoint-13", role="resume_replay")
        report["resume_bit_identity"] = True
        report["status"] = "pair_trial_checks_passed"
    except BaseException as error:
        report["status"] = "pair_trial_gate_failed"
        report["error"] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    report["process_peak_rss_bytes"] = recovery.peak_rss_bytes()
    report["finished_unix_seconds"] = time.time()
    flush()
    recovery.write_json(output / "summary.json", summarize(report))
    print(json.dumps({k: report[k] for k in ("status", "main_completed_steps", "total_optimizer_updates_executed")}))
    return 0 if report["status"] == "pair_trial_checks_passed" else 1


def supervise(args):
    plan = load_plan(args.plan)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    for filename, source in (("pair-trial-adapter.py", __file__), ("short-training-helper.py", short.__file__),
                             ("recovery-adapter.py", recovery.__file__), ("pair-trial.lock.json", args.plan)):
        (output / filename).write_bytes(Path(source).read_bytes())
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--_worker"]
    start, termination = time.monotonic(), None
    with (output / "stdout.log").open("w") as stdout, (output / "stderr.log").open("w") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        while child.poll() is None:
            sampled = subprocess.run(["ps", "-o", "rss=", "-p", str(child.pid)], capture_output=True, text=True)
            rss = int(sampled.stdout.strip() or 0) * 1024
            if time.monotonic() - start > plan["resource_limits"]["wall_seconds"] or rss > plan["resource_limits"]["rss_gib"] * 2**30:
                termination = "wall_time_limit" if time.monotonic() - start > plan["resource_limits"]["wall_seconds"] else "rss_limit"
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                break
            time.sleep(.25)
    path = output / "report.json"
    report = json.loads(path.read_text()) if path.exists() else dict(status="worker_failed_before_report")
    if termination:
        report.update(status="resource_gate_failed", resource_failure=termination)
    report["supervisor"] = dict(wall_seconds=time.monotonic() - start,
                                 max_seconds=plan["resource_limits"]["wall_seconds"], max_rss_gib=plan["resource_limits"]["rss_gib"],
                                 worker_exit_code=child.returncode, sampling="ps RSS every0.25s; normal exit records peak RSS")
    recovery.write_json(path, report)
    recovery.write_json(output / "summary.json", summarize(report))
    print(json.dumps(dict(status=report["status"], report=str(path))))
    return 0 if report["status"] == "pair_trial_checks_passed" and child.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("inputs")
    parser.add_argument("output", help="new isolated trial directory")
    parser.add_argument("--plan", default=str(PLAN_PATH))
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return run_worker(args) if args._worker else supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
