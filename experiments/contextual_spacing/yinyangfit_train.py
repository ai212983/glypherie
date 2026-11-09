"""Bounded original-objective YinYangFit optimizer and checkpoint experiment.

The pinned historical scorer/loss execute unchanged through the recovery module.
This wrapper owns a three-item schedule, numerical stop gates, continuing RNG,
Adam updates, deterministic evaluation and state-complete resume verification.
It is not a trained optical-spacing product or the original full training run.
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
import random
import shutil
import struct
import subprocess
import sys
import time
import traceback

import yinyangfit_recovery as recovery


POLICY = "yinyangfit-short-training-v1"
SCHEDULE = ("nn", "oo", "av")
LEARNING_RATE = 0.0011
ACTIVE_NAMES = frozenset(
    [f"bg_direct.{name}" for name in (
        "b_to_g", "G_input_weight", "ray_weight", "amplification_saturation", "k", "b")]
    + [f"g_targets.{name}" for name in ("general_exp", "loss_b", "loss_factor", "gain_factor")]
)
STATE_KEYS = {"model", "optimizer", "rng", "position"}


class TrainingError(ValueError):
    """The declared experiment stopped, without changing its objective."""


def capture_rng(torch, np):
    algorithm, keys, position, has_gauss, cached_gaussian = np.random.get_state()
    return dict(python=random.getstate(), torch=torch.get_rng_state().clone(), numpy=dict(
        algorithm=algorithm, keys=keys.tolist(), position=int(position),
        has_gauss=int(has_gauss), cached_gaussian=float(cached_gaussian)))


def restore_rng(state, torch, np):
    if set(state) != {"python", "numpy", "torch"}:
        raise TrainingError("RNG field inventory mismatch")
    n = state["numpy"]
    if set(n) != {"algorithm", "keys", "position", "has_gauss", "cached_gaussian"}:
        raise TrainingError("NumPy RNG field inventory mismatch")
    if (n["algorithm"] != "MT19937" or len(n["keys"]) != 624
            or not all(type(v) is int and 0 <= v < 2**32 for v in n["keys"])
            or type(n["position"]) is not int or not 0 <= n["position"] <= 624
            or type(n["has_gauss"]) is not int or n["has_gauss"] not in (0, 1)
            or not math.isfinite(n["cached_gaussian"])):
        raise TrainingError("invalid NumPy RNG state")
    if not isinstance(state["python"], tuple) or len(state["python"]) != 3 or state["python"][0] != 3:
        raise TrainingError("invalid Python RNG state")
    cached_python_gaussian = state["python"][2]
    if cached_python_gaussian is not None and (
            type(cached_python_gaussian) not in (int, float) or not math.isfinite(cached_python_gaussian)):
        raise TrainingError("invalid cached Python Gaussian RNG value")
    if not isinstance(state["torch"], torch.Tensor) or state["torch"].dtype != torch.uint8 or state["torch"].ndim != 1:
        raise TrainingError("invalid Torch CPU RNG state")
    numpy_state = (n["algorithm"], np.asarray(n["keys"], dtype=np.uint32), n["position"],
                   n["has_gauss"], n["cached_gaussian"])
    # Validate every generator on temporary objects before mutating globals.
    random.Random().setstate(state["python"])
    np.random.RandomState().set_state(numpy_state)
    torch.Generator(device="cpu").set_state(state["torch"])
    random.setstate(state["python"])
    np.random.set_state(numpy_state)
    torch.set_rng_state(state["torch"])


@contextlib.contextmanager
def preserve_rng(torch, np):
    state = capture_rng(torch, np)
    try:
        yield
    finally:
        restore_rng(state, torch, np)


def tensor_tree_digest(value):
    """Hash tensor bits, dtypes/shapes and exact primitive state, not pickle bytes."""
    import torch
    h = hashlib.sha256()
    def visit(v):
        if isinstance(v, torch.Tensor):
            v = v.detach().cpu().contiguous()
            h.update(b"tensor:")
            h.update(str(v.dtype).encode())
            h.update(json.dumps(list(v.shape)).encode())
            h.update(v.reshape(-1).view(torch.uint8).numpy().tobytes())
        elif isinstance(v, dict):
            h.update(b"dict:")
            for key in sorted(v, key=lambda k: (type(k).__name__, str(k))):
                visit(key)
                visit(v[key])
            h.update(b"enddict")
        elif isinstance(v, (tuple, list)):
            h.update(b"tuple:" if isinstance(v, tuple) else b"list:")
            for item in v:
                visit(item)
            h.update(b"endsequence")
        elif isinstance(v, float):
            h.update(b"float:" + struct.pack("!d", v))
        elif isinstance(v, (str, int, bool)) or v is None:
            h.update(type(v).__name__.encode() + b":" + json.dumps(v).encode() + b";")
        else:
            raise TrainingError(f"unsupported checkpoint value type: {type(v).__name__}")
    visit(value)
    return h.hexdigest()


def validate_finite_tree(value, label="state"):
    import torch
    if isinstance(value, torch.Tensor):
        if not torch.isfinite(value).all().item():
            raise TrainingError(f"nonfinite {label}")
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_finite_tree(item, f"{label}.{key}")
    elif isinstance(value, (tuple, list)):
        for i, item in enumerate(value):
            validate_finite_tree(item, f"{label}[{i}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise TrainingError(f"nonfinite {label}")


def validate_loss_values(source, values):
    try:
        analysis = recovery.loss_analysis(values)
    except recovery.RecoveryError as error:
        raise TrainingError(str(error)) from error
    if analysis["status"] != "valid_for_original_evaluation":
        raise TrainingError("original loss gate: " + analysis["status"])
    observation = recovery.observe_original_loss_from_source(source, values)
    selected = observation.get("intermediates", {}).get("selected_minimum")
    if observation["raw_float32_status"] != "finite":
        raise TrainingError("original loss is nonfinite")
    if selected is not None and (not isinstance(selected, (int, float)) or
                                 not recovery.DELTAS[0] <= selected <= recovery.DELTAS[-1]):
        raise TrainingError("original selected minimum is outside candidate domain")
    return dict(analysis=analysis, observation=observation)


def gradient_census(model):
    import torch
    result = {}
    for name, parameter in model.named_parameters():
        grad = parameter.grad
        if grad is not None and not torch.isfinite(grad).all().item():
            raise TrainingError("nonfinite gradient: " + name)
        if (name in ACTIVE_NAMES) != (grad is not None):
            raise TrainingError("gradient reachability mismatch: " + name)
        result[name] = dict(numel=parameter.numel(), has_gradient=grad is not None,
                            nonzero_entries=int(torch.count_nonzero(grad)) if grad is not None else 0)
    if set(result) & ACTIVE_NAMES != ACTIVE_NAMES:
        raise TrainingError("missing declared active parameter field")
    return result


def validate_training_payload(payload, expected_hyperparameters, parameter_names, parameter_specs=None):
    """Validate trajectory/protocol before model, optimizer or RNG restoration."""
    import torch
    if set(payload) != STATE_KEYS:
        raise TrainingError("training checkpoint field inventory mismatch")
    p = payload["position"]
    if set(p) != {"completed_steps", "schedule", "next_pair"}:
        raise TrainingError("checkpoint position field inventory mismatch")
    steps = p["completed_steps"]
    if type(steps) is not int or not 0 <= steps <= len(SCHEDULE) or p["schedule"] != list(SCHEDULE):
        raise TrainingError("checkpoint schedule/step mismatch")
    if p["next_pair"] != (SCHEDULE[steps] if steps < len(SCHEDULE) else None):
        raise TrainingError("checkpoint next pair mismatch")
    if set(payload["model"]) != set(parameter_names):
        raise TrainingError("checkpoint model field inventory mismatch")
    if parameter_specs is not None:
        for name, value in payload["model"].items():
            if not isinstance(value, torch.Tensor) or (tuple(value.shape), str(value.dtype)) != parameter_specs[name]:
                raise TrainingError("checkpoint model tensor shape/dtype mismatch")
    o = payload["optimizer"]
    if set(o) != {"state", "param_groups"} or len(o["param_groups"]) != 1:
        raise TrainingError("checkpoint optimizer structure mismatch")
    group = dict(o["param_groups"][0])
    ids = group.pop("params", None)
    if ids != list(range(len(parameter_names))) or group != expected_hyperparameters:
        raise TrainingError("checkpoint optimizer hyperparameters/order mismatch")
    active_ids = {i for i, name in enumerate(parameter_names) if name in ACTIVE_NAMES}
    expected_ids = active_ids if steps else set()
    if set(o["state"]) != expected_ids:
        raise TrainingError("checkpoint optimizer active-state inventory mismatch")
    for index, state in o["state"].items():
        if set(state) != {"step", "exp_avg", "exp_avg_sq"}:
            raise TrainingError("checkpoint Adam state inventory mismatch")
        step = state["step"]
        if (not isinstance(step, torch.Tensor) or step.shape != torch.Size([])
                or step.dtype != torch.float32 or float(step) != steps):
            raise TrainingError("checkpoint Adam step counter mismatch")
        parameter = payload["model"][parameter_names[index]]
        if any(state[key].shape != parameter.shape or state[key].dtype != parameter.dtype
               for key in ("exp_avg", "exp_avg_sq")):
            raise TrainingError("checkpoint Adam tensor shape/dtype mismatch")
        if (state["exp_avg_sq"] < 0).any().item():
            raise TrainingError("checkpoint Adam squared-average state is negative")
    validate_finite_tree(payload["model"], "model")
    validate_finite_tree(o, "optimizer")
    # Temporary validation restores the outer RNG even if state is invalid.
    import numpy as np
    with preserve_rng(torch, np):
        restore_rng(payload["rng"], torch, np)


class CheckpointStore:
    @staticmethod
    def save(path, payload, identity, validate=None, role="main"):
        import torch
        if role not in ("main", "resume_replay"):
            raise TrainingError("unknown training checkpoint role")
        path = Path(path)
        if path.exists():
            raise TrainingError("checkpoint output already exists")
        if validate is not None:
            validate(payload)
        temporary = path.with_name(path.name + ".tmp")
        temporary.mkdir(parents=True, exist_ok=False)
        try:
            data_path = temporary / "state.pt"
            torch.save(payload, data_path)
            with data_path.open("rb") as stream:
                import os
                os.fsync(stream.fileno())
            manifest = dict(schema="yinyangfit-training-checkpoint-v1", artifact_kind="short_optimizer_probe_state",
                            role=role, identity=identity, position=payload["position"],
                            state_sha256=recovery.sha256(data_path.read_bytes()),
                            semantic_state_sha256=tensor_tree_digest(payload))
            recovery.write_json(temporary / "manifest.json", manifest)
            temporary.rename(path)
            return manifest
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    @staticmethod
    def load(path, identity, validate=None):
        import torch
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text())
        if (manifest.get("schema") != "yinyangfit-training-checkpoint-v1"
                or manifest.get("artifact_kind") != "short_optimizer_probe_state"
                or manifest.get("role") not in ("main", "resume_replay")
                or manifest.get("identity") != identity):
            raise TrainingError("checkpoint identity mismatch")
        raw = (path / "state.pt").read_bytes()
        if recovery.sha256(raw) != manifest.get("state_sha256"):
            raise TrainingError("checkpoint file identity mismatch")
        payload = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
        if tensor_tree_digest(payload) != manifest.get("semantic_state_sha256") or payload.get("position") != manifest.get("position"):
            raise TrainingError("checkpoint semantic identity mismatch")
        if validate is not None:
            validate(payload)
        return payload


class Trainer:
    def __init__(self, reference, inputs, seed=20261101, threads=4):
        import torch
        import numpy as np
        self.scorer = recovery.RecoveredScorer(reference, inputs, "reference_seeded_per_pair", seed, threads)
        self.reference, self.inputs = reference, inputs
        self.scorer.model.train()
        self.torch, self.np = torch, np
        self.optimizer = torch.optim.Adam(self.scorer.model.parameters(), lr=LEARNING_RATE)
        self.parameter_names = list(dict(self.scorer.model.named_parameters()))
        self.parameter_specs = {name: (tuple(value.shape), str(value.dtype))
                                for name, value in self.scorer.model.named_parameters()}
        self.hyperparameters = {k: v for k, v in self.optimizer.state_dict()["param_groups"][0].items() if k != "params"}
        self.completed_steps = 0
        meta = self.scorer.metadata()
        identity_keys = ("revision", "notebook_sha256", "adapter_sha256", "selected_ast_sha256", "input_npz_sha256",
                         "input_manifest_sha256", "globals", "environment", "parameters", "fixed_tensor_state")
        self.identity = dict(policy=POLICY, training_adapter_sha256=recovery.sha256(Path(__file__).read_bytes()),
                             recovered_source={k: meta[k] for k in identity_keys},
                             schedule=list(SCHEDULE), seed=seed, threads=threads,
                             training_rng="Continue Python/NumPy/Torch CPU RNG after recovered initialization; no per-pair reseeding",
                             evaluation_noise_policy="noise_off", optimizer=dict(name="torch.optim.Adam", **self.hyperparameters))
        self.identity = json.loads(json.dumps(self.identity, allow_nan=False))

    def payload(self):
        n = self.completed_steps
        return dict(model=copy.deepcopy(self.scorer.model.state_dict()),
                    optimizer=copy.deepcopy(self.optimizer.state_dict()), rng=capture_rng(self.torch, self.np),
                    position=dict(completed_steps=n, schedule=list(SCHEDULE),
                                  next_pair=SCHEDULE[n] if n < len(SCHEDULE) else None))

    def validate(self, payload):
        validate_training_payload(payload, self.hyperparameters, self.parameter_names, self.parameter_specs)

    def save(self, path, role="main"):
        return CheckpointStore.save(path, self.payload(), self.identity, self.validate, role)

    def restore(self, path):
        payload = CheckpointStore.load(path, self.identity, self.validate)
        self.scorer.model.load_state_dict(payload["model"], strict=True)
        self.optimizer.load_state_dict(payload["optimizer"])
        restore_rng(payload["rng"], self.torch, self.np)
        self.completed_steps = payload["position"]["completed_steps"]

    def update(self, record, changed=lambda: None):
        if self.completed_steps >= len(SCHEDULE):
            raise TrainingError("declared main schedule is complete")
        pair = SCHEDULE[self.completed_steps]
        record.update(step=self.completed_steps + 1, pair=pair, optimizer_update_applied=False,
                      rng_before_sha256=tensor_tree_digest(capture_rng(self.torch, self.np)))
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
            raise TrainingError("nonfinite or constant training scores")
        record["loss_gate"] = validate_loss_values(self.scorer.source, values)
        with contextlib.redirect_stdout(io.StringIO()):
            loss = self.scorer.namespace["estimate_min_loss"](penalties)
        if not self.torch.isfinite(loss).item():
            raise TrainingError("nonfinite original differentiable loss")
        record["loss"] = float(loss.detach())
        start = time.perf_counter()
        loss.backward()
        record["backward_seconds"] = time.perf_counter() - start
        record["gradients"] = gradient_census(self.scorer.model)
        changed()
        self.optimizer.step()
        record["optimizer_update_applied"] = True
        changed()
        validate_finite_tree(self.scorer.model.state_dict(), "post-update model")
        validate_finite_tree(self.optimizer.state_dict(), "post-update optimizer")
        self.completed_steps += 1
        self.validate(self.payload())
        record.update(status="update_completed", parameter_sha256=tensor_tree_digest(self.scorer.model.state_dict()),
                      optimizer_sha256=tensor_tree_digest(self.optimizer.state_dict()),
                      rng_after_sha256=tensor_tree_digest(capture_rng(self.torch, self.np)))
        return record

    def evaluate(self):
        before = tensor_tree_digest(capture_rng(self.torch, self.np))
        model_before = tensor_tree_digest(self.scorer.model.state_dict())
        results = []
        with preserve_rng(self.torch, self.np):
            evaluator = recovery.RecoveredScorer(self.reference, self.inputs,
                                                 "noise_off", self.scorer.seed, self.scorer.threads)
            evaluator.model.load_state_dict(self.scorer.model.state_dict(), strict=True)
            for pair in SCHEDULE:
                result = evaluator.score(pair)
                values = result["scores"]
                gate = validate_loss_values(evaluator.source, values)
                scores = self.torch.tensor([values], dtype=self.torch.float32)
                result["target_cross_entropy"] = float(self.torch.nn.functional.cross_entropy(-scores, self.torch.tensor([2])))
                result["target_rank"] = 1 + sum(v < values[2] for v in values)
                result["target_ties"] = sum(v == values[2] for v in values)
                result["best_candidate_deltas"] = [d for d, v in zip(recovery.DELTAS, values) if v == min(values)]
                result["original_loss"] = gate["observation"]["raw_loss"]
                results.append(result)
            del evaluator
            gc.collect()
        after = tensor_tree_digest(capture_rng(self.torch, self.np))
        if before != after or model_before != tensor_tree_digest(self.scorer.model.state_dict()):
            raise TrainingError("evaluation changed training RNG or parameters")
        return dict(pairs=results, training_rng_preserved=True, training_parameters_preserved=True)


def run_worker(args):
    output = Path(args.output)
    report = dict(policy=POLICY, status="running", schedule=list(SCHEDULE), main_completed_steps=0,
                  main_updates=[], replay_updates=[], phases=[],
                  limitations=["Three-item optimizer/replay probe, not a shuffled 676-pair epoch or calibrated optical model",
                               "Original grayscale Crimson domain; no delivered-small-bitmap, held-out or browser assessment"])
    path = output / "report.json"
    def flush():
        report["main_optimizer_updates_executed"] = sum(r.get("optimizer_update_applied", False) for r in report["main_updates"])
        report["replay_optimizer_updates_executed"] = sum(r.get("optimizer_update_applied", False) for r in report["replay_updates"])
        report["total_optimizer_updates_executed"] = report["main_optimizer_updates_executed"] + report["replay_optimizer_updates_executed"]
        recovery.write_json(path, report)
    def phase(name):
        report["phases"].append(name)
        flush()
    flush()
    try:
        phase("prepare_original_scorer_and_Adam")
        trainer = Trainer(args.reference, args.inputs, args.seed, args.threads)
        report["identity"] = trainer.identity
        report["initial_parameter_sha256"] = tensor_tree_digest(trainer.scorer.model.state_dict())
        phase("noise_off_evaluation_before")
        report["evaluation_before"] = trainer.evaluate()
        trainer.save(output / "checkpoint-00")
        for _ in SCHEDULE:
            record = {}
            report["main_updates"].append(record)
            phase(f"main_update:{trainer.completed_steps + 1}")
            trainer.update(record, flush)
            report["main_completed_steps"] = trainer.completed_steps
            trainer.save(output / f"checkpoint-{trainer.completed_steps:02}")
            flush()
            gc.collect()
        expected = trainer.payload()
        report["main_final_digests"] = {k: tensor_tree_digest(expected[k]) for k in STATE_KEYS}
        phase("noise_off_evaluation_after")
        report["evaluation_after"] = trainer.evaluate()
        phase("resume_checkpoint_01_and_replay_updates_2_3")
        replay = Trainer(args.reference, args.inputs, args.seed, args.threads)
        replay.restore(output / "checkpoint-01")
        while replay.completed_steps < len(SCHEDULE):
            record = {}
            report["replay_updates"].append(record)
            phase(f"replay_update:{replay.completed_steps + 1}")
            replay.update(record, flush)
            flush()
            gc.collect()
        actual = replay.payload()
        report["replay_final_digests"] = {k: tensor_tree_digest(actual[k]) for k in STATE_KEYS}
        if report["main_final_digests"] != report["replay_final_digests"]:
            raise TrainingError("resume/replay final state is not bit-identical")
        replay.save(output / "replay-checkpoint-03", role="resume_replay")
        report["resume_bit_identity"] = True
        report["status"] = "short_training_checks_passed"
    except BaseException as error:
        report["status"] = "short_training_gate_failed"
        report["error"] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    report["process_peak_rss_bytes"] = recovery.peak_rss_bytes()
    report["finished_unix_seconds"] = time.time()
    flush()
    print(json.dumps({k: report[k] for k in ("status", "main_completed_steps", "total_optimizer_updates_executed", "process_peak_rss_bytes")}))
    return 0 if report["status"] == "short_training_checks_passed" else 1


def supervise(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "training-adapter.py").write_bytes(Path(__file__).read_bytes())
    (output / "recovery-adapter.py").write_bytes(Path(recovery.__file__).read_bytes())
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--_worker"]
    start, termination = time.monotonic(), None
    with (output / "stdout.log").open("w") as stdout, (output / "stderr.log").open("w") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        while child.poll() is None:
            elapsed = time.monotonic() - start
            sampled = subprocess.run(["ps", "-o", "rss=", "-p", str(child.pid)], capture_output=True, text=True)
            rss = int(sampled.stdout.strip() or 0) * 1024
            if elapsed > args.max_seconds or rss > args.max_rss_gib * 2**30:
                termination = "wall_time_limit" if elapsed > args.max_seconds else "rss_limit"
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
    report["supervisor"] = dict(wall_seconds=time.monotonic() - start, max_seconds=args.max_seconds,
                                 max_rss_gib=args.max_rss_gib, worker_exit_code=child.returncode,
                                 sampling="ps RSS every0.25s; normal worker exit records process peak RSS")
    recovery.write_json(path, report)
    print(json.dumps(dict(status=report["status"], report=str(path))))
    return 0 if report["status"] == "short_training_checks_passed" and child.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("inputs")
    parser.add_argument("output", help="new isolated output directory")
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-seconds", type=float, default=1200)
    parser.add_argument("--max-rss-gib", type=float, default=24)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or not 1 <= args.max_seconds <= 1800:
        parser.error("max-seconds must be finite and between one and1800")
    if not math.isfinite(args.max_rss_gib) or not 1 <= args.max_rss_gib <= 32:
        parser.error("max-rss-gib must be finite and between one and32")
    return run_worker(args) if args._worker else supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
