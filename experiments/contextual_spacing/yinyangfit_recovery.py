"""Recover the pinned historical YinYangFit scorer without optimizer updates.

The original notebook definitions execute unchanged. This adapter supplies only
their globals, pinned original-domain inputs and explicitly named RNG policies.
It is a compatibility experiment, not a trained or accepted spacing method.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import signal
import subprocess
import sys
import time
import traceback


REVISION = "d9c7e2580f2ad4884c45e5081e8e4613b86632cf"
NOTEBOOK_SHA256 = "078e9dda8c5217bc064f1b1b09f03e83fb2be03e7322885594eb2b5d50d59ba6"
POLICY = "yinyangfit-historical-recovery-v1"
NOISE_POLICIES = ("reference_seeded_per_pair", "noise_off")
FIXED_PAIRS = ("nn", "oo", "av")
DELTAS = (-3, -1, 0, 1, 5)
SELECTED = {
    5: ("unit_pgrid", "get_sigmas", "get_v1_filter_bank", "apply_filter_bank"),
    6: ("G_filters",),
    7: ("B_G_Direct",),
    8: ("G_Targets",),
    9: ("YinYangFit",),
    11: ("apply_translations",),
    13: ("estimate_min_loss",),
}


class RecoveryError(ValueError):
    """A failed recovery gate, rather than permission to change the model."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class RecoverySource:
    raw_sha256: str
    ast_sha256: str
    module: ast.Module
    provenance: dict


def load_source(reference: Path | str) -> RecoverySource:
    """Read one exact historical notebook without changing its checkout."""
    reference = Path(reference)
    raw = (reference.read_bytes() if reference.is_file() else
           subprocess.check_output(["git", "-C", str(reference), "show", f"{REVISION}:YinYangFit.ipynb"]))
    if sha256(raw) != NOTEBOOK_SHA256:
        raise RecoveryError("historical notebook identity mismatch")
    notebook = json.loads(raw)
    nodes, provenance = [], {}
    for index, names in SELECTED.items():
        source = "".join(notebook["cells"][index]["source"])
        parsed = ast.parse(source)
        found = {node.name: node for node in parsed.body
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names}
        if set(found) != set(names):
            raise RecoveryError(f"historical definition inventory mismatch in cell {index}")
        # Selection only: no function bodies, operators, constants or branches
        # are rewritten. Notebook demonstrations/install/display calls are not
        # part of the scorer definition and are deliberately not executed.
        nodes.extend(found[name] for name in names)
        provenance[str(index)] = {name: dict(
            line=found[name].lineno,
            ast_sha256=sha256(ast.dump(found[name], include_attributes=False).encode()),
        ) for name in names}
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    return RecoverySource(sha256(raw), sha256(ast.dump(module, include_attributes=False).encode()),
                          module, provenance)


def load_inputs(directory: Path | str) -> dict:
    """Accept the fixed complete original-domain corpus, never reading prose."""
    import numpy as np

    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    raw = (directory / "inputs.npz").read_bytes()
    if manifest.get("schema_version") != "yinyangfit-original-inputs-v1" or manifest.get("status") != "complete":
        raise RecoveryError("input manifest schema or completion status mismatch")
    if manifest.get("inputs_npz_sha256") != sha256(raw):
        raise RecoveryError("input archive identity mismatch")
    lock = manifest.get("source_lock", {})
    lock_path = Path(__file__).with_name("reference") / "yinyangfit-recovery" / "inputs.lock.json"
    locked_bytes = lock_path.read_bytes()
    if manifest.get("source_lock_sha256") != sha256(locked_bytes) or lock != json.loads(locked_bytes):
        raise RecoveryError("input manifest does not match the maintained source lock")
    if (lock.get("historical_notebook_revision") != REVISION
            or lock.get("historical_notebook_sha256") != NOTEBOOK_SHA256
            or lock.get("tensorfont_revision") != "ca40a251693022a86eff63301dbae45ec27b608e"
            or lock.get("crimson_revision") != "685b5a2478a7213a806e9bbf1e36f6a9e7f5c7ef"):
        raise RecoveryError("input source identity mismatch")
    font = manifest.get("font", {})
    if (font.get("requested_x_height_px"), font.get("full_height_px"), font.get("width_px")) != (34, 80, 161):
        raise RecoveryError("input original-domain geometry declaration mismatch")
    if manifest.get("sample_distance_deltas") != list(DELTAS) or manifest.get("label_index") != 2:
        raise RecoveryError("input manifest candidate policy mismatch")
    if manifest.get("clipping") != {"source_ink": False, "candidate_ink": False}:
        raise RecoveryError("input manifest reports clipped candidates")
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    expected = {"glyph_images", "glyph_ink_widths", "codepoints", "pair_codepoints",
                "translations_left", "translations_right", "sample_distance_deltas", "labels"}
    if set(arrays) != expected:
        raise RecoveryError("input archive field inventory mismatch")
    dtypes = dict(glyph_images="float32", glyph_ink_widths="int32", codepoints="uint32", pair_codepoints="uint32",
                  translations_left="int32", translations_right="int32", sample_distance_deltas="int32", labels="int64")
    identities = manifest.get("array_identities", {})
    if set(identities) != expected:
        raise RecoveryError("input array identity inventory mismatch")
    for key, value in arrays.items():
        identity = dict(shape=list(value.shape), dtype=str(value.dtype), sha256=sha256(value.tobytes()))
        if str(value.dtype) != dtypes[key] or identities[key] != identity:
            raise RecoveryError(f"input array identity or dtype mismatch: {key}")
    images = arrays["glyph_images"]
    if images.shape != (26, 80, 161) or images.dtype != np.float32:
        raise RecoveryError("recovery requires the original 26 x 80 x 161 float32 image domain")
    if not np.isfinite(images).all() or (images < 0).any() or (images > 1).any():
        raise RecoveryError("input coverage is not finite normalized grayscale")
    if not np.array_equal(arrays["codepoints"], np.arange(97, 123, dtype=np.uint32)):
        raise RecoveryError("input scalar order is not the fixed lowercase alphabet")
    products = np.array([(a, b) for a in range(97, 123) for b in range(97, 123)], dtype=np.uint32)
    if not np.array_equal(arrays["pair_codepoints"], products):
        raise RecoveryError("pair domain is not the complete ordered lowercase Cartesian product")
    if not np.array_equal(arrays["sample_distance_deltas"], np.array(DELTAS, dtype=np.int32)):
        raise RecoveryError("candidate deltas differ from the historical domain")
    if arrays["labels"].shape != (676,) or not np.all(arrays["labels"] == 2):
        raise RecoveryError("historical target labels differ")
    widths = arrays["glyph_ink_widths"]
    if widths.shape != (26,) or not np.issubdtype(widths.dtype, np.integer) or (widths <= 0).any():
        raise RecoveryError("invalid glyph ink widths")
    for key in ("translations_left", "translations_right"):
        values = arrays[key]
        if values.shape != (676, 5) or values.dtype != np.int32 or (np.abs(values.astype(np.int64)) >= 161).any():
            raise RecoveryError("invalid candidate translation grid")
    realized = arrays["translations_right"] - arrays["translations_left"]
    if not np.all(realized - realized[:, 2:3] == np.array(DELTAS)):
        raise RecoveryError("realized candidate deltas collapsed or changed")
    for index, (left, right) in enumerate(products):
        for cp, key in ((left, "translations_left"), (right, "translations_right")):
            image = images[int(cp) - 97]
            columns = np.flatnonzero(np.any(image != 0, axis=0))
            translations = arrays[key][index]
            if not len(columns) or (columns[0] + translations < 0).any() or (columns[-1] + translations >= 161).any():
                raise RecoveryError("a historical candidate clips glyph ink")
    return dict(arrays=arrays, manifest=manifest, npz_sha256=sha256(raw),
                manifest_sha256=sha256((directory / "manifest.json").read_bytes()))


def loss_analysis(penalties) -> dict:
    """Inspect the original loss branch using exact binary input rationals.

    This gate does not replace the loss. Exact normal equations identify the
    published root formula's zero cubic denominator without an epsilon policy.
    """
    values = [float(value) for value in penalties]
    if len(values) != 5 or not all(math.isfinite(value) for value in values):
        raise RecoveryError("loss requires five finite penalty values")
    comparisons = [a > b for a, b in zip(values, values[1:])]
    d0, d1, d2, d3 = comparisons
    cubic = (d0 and not d1 and not d2 and not d3) or (d0 and d1 and not d2 and not d3) or (
        d0 and d1 and d2 and not d3)
    result = dict(branch="cubic" if cubic else "categorical", comparisons=comparisons,
                  status="valid_for_original_evaluation")
    if not cubic:
        return result
    xs = [Fraction(value) for value in DELTAS]
    ys = [Fraction(value) for value in values]
    design = [[x ** 3, x ** 2, x, Fraction(1)] for x in xs]
    equations = [[sum(row[i] * row[j] for row in design) for j in range(4)] +
                 [sum(row[i] * y for row, y in zip(design, ys))] for i in range(4)]
    for i in range(4):
        pivot = next(j for j in range(i, 4) if equations[j][i])
        equations[i], equations[pivot] = equations[pivot], equations[i]
        scale = equations[i][i]
        equations[i] = [value / scale for value in equations[i]]
        for j in range(4):
            if j != i:
                scale = equations[j][i]
                equations[j] = [a - scale * b for a, b in zip(equations[j], equations[i])]
    coefficients = [row[-1] for row in equations]
    result["exact_cubic_coefficients"] = [str(value) for value in coefficients]
    if coefficients[0] == 0:
        result["status"] = "degenerate_cubic_requires_model_decision"
    return result


def observe_original_loss(reference, penalties) -> dict:
    """Observe original float32 loss independently of the exact preflight gate."""
    return observe_original_loss_from_source(load_source(reference), penalties)


def observe_original_loss_from_source(source, penalties) -> dict:
    import torch

    original = next(node for node in source.module.body if node.name == "estimate_min_loss")
    namespace = dict(T=torch, dev=torch.device("cpu"), sample_distance_deltas=list(DELTAS),
                     ce_criterion=torch.nn.CrossEntropyLoss())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])),
                 f"YinYangFit-loss@{REVISION}", "exec"), namespace)
    retained = {}
    function = namespace["estimate_min_loss"]
    previous = sys.gettrace()
    def trace(frame, event, _arg):
        if frame.f_code is function.__code__ and event == "return":
            for name in ("coeffs", "sq_a", "sq_b", "sq_c", "min_est_1", "min_est_2"):
                value = frame.f_locals.get(name)
                if isinstance(value, torch.Tensor):
                    # JSON remains strict even when the original function
                    # produces a NaN/infinity: retain its textual value.
                    retained[name] = str(value.detach().cpu().tolist())
            if "min_est_1" in frame.f_locals:
                state = frame.f_locals
                selected = state["min_est_1"] if (state["li_a"] * state["min_est_1"] + state["sq_b"]).item() > 0 else state["min_est_2"]
                retained["selected_minimum"] = float(selected) if torch.isfinite(selected).item() else str(float(selected))
        return trace
    log = io.StringIO()
    try:
        sys.settrace(trace)
        with contextlib.redirect_stdout(log):
            loss = function(torch.tensor(penalties, dtype=torch.float32)[None, :])
        finite = bool(torch.isfinite(loss).item())
        return dict(exact_preflight=loss_analysis(penalties), raw_float32_status="finite" if finite else "nonfinite",
                    raw_loss=float(loss) if finite else str(float(loss)), intermediates=retained,
                    original_stdout=log.getvalue(), torch=torch.__version__)
    finally:
        sys.settrace(previous)


class _TorchFacade:
    def __init__(self, torch, policy):
        self._torch, self._policy = torch, policy

    def __getattr__(self, name):
        return getattr(self._torch, name)

    def randn_like(self, tensor, *args, **kwargs):
        if self._policy == "noise_off":
            return self._torch.zeros_like(tensor, *args, **kwargs)
        return self._torch.randn_like(tensor, *args, **kwargs)


class _NoPlots:
    def __getattr__(self, name):
        raise RecoveryError(f"unexpected upstream plotting request: {name}")


def _tensor_record(tensor) -> dict:
    array = tensor.detach().cpu().contiguous().numpy()
    return dict(shape=list(array.shape), dtype=str(array.dtype), numel=int(array.size),
                sha256=sha256(array.tobytes()))


class RecoveredScorer:
    def __init__(self, reference, inputs_dir, noise_policy="reference_seeded_per_pair", seed=20261101, threads=4):
        import numpy as np
        import torch
        import torch.nn.functional as functional

        if noise_policy not in NOISE_POLICIES:
            raise RecoveryError("unknown recovery noise policy")
        if not 1 <= threads <= 12:
            raise RecoveryError("threads must be between one and twelve")
        torch.set_num_threads(threads)
        torch.use_deterministic_algorithms(True)
        torch.set_default_dtype(torch.float32)
        self.torch, self.np = torch, np
        self.source, self.inputs = load_source(reference), load_inputs(inputs_dir)
        self.noise_policy, self.seed, self.threads = noise_policy, seed, threads
        self.filtered = {}
        self.seed_for("initialization")
        namespace = dict(T=_TorchFacade(torch, noise_policy), F=functional, np=np, pi=np.float32(np.pi),
                         math=math, dev=torch.device("cpu"), box_height=80, box_width=161,
                         n_v1_scales=10, n_b_scales=1, n_v1_orientations=8, n_v4_scales=8,
                         n_g_scales=10, scale_factor=.02, scale_base=30 ** (1 / 13),
                         batch_size=1, n_sample_distances=5, sample_distance_deltas=list(DELTAS),
                         plt=_NoPlots(), ce_criterion=torch.nn.CrossEntropyLoss())
        exec(compile(self.source.module, f"YinYangFit@{REVISION}", "exec"), namespace)
        self.namespace = namespace
        # The notebook's display-only defaults are disabled; filter math and
        # complete original dimensions are unchanged.
        with torch.no_grad():
            namespace["filter_bank"] = namespace["get_v1_filter_bank"](0, False, False)
        self.model = namespace["YinYangFit"]().to(namespace["dev"])
        self.model.eval()
        self._hooks = []
        self.intermediates = {}
        for name in ("bg_direct", "g_targets"):
            getattr(self.model, name).register_forward_hook(self._finite_hook(name))

    def _finite_hook(self, name):
        def hook(_module, _inputs, outputs):
            for i, value in enumerate(outputs):
                if not self.torch.isfinite(value).all().item():
                    raise RecoveryError(f"nonfinite upstream intermediate {name}[{i}]")
                self.intermediates.setdefault(name, {})[str(i)] = dict(shape=list(value.shape), dtype=str(value.dtype))
        return hook

    def seed_for(self, pair):
        material = f"{POLICY}:{self.seed}:{self.inputs['npz_sha256']}:{pair}".encode()
        seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") & ((1 << 63) - 1)
        self.torch.manual_seed(seed)
        self.np.random.seed(seed % (1 << 32))
        random.seed(seed)
        return seed

    def _pair_inputs(self, pair):
        if len(pair) != 2 or any(ch < "a" or ch > "z" for ch in pair):
            raise RecoveryError("recovery pair must contain two lowercase ASCII letters")
        arrays = self.inputs["arrays"]
        index = (ord(pair[0]) - 97) * 26 + ord(pair[1]) - 97
        for ch in pair:
            if ch not in self.filtered:
                with self.torch.no_grad():
                    self.filtered[ch] = self.namespace["apply_filter_bank"](
                        -arrays["glyph_images"][ord(ch) - 97], self.namespace["filter_bank"], False)
        with self.torch.no_grad():
            left = self.namespace["apply_translations"](self.filtered[pair[0]], arrays["translations_left"][index])
            right = self.namespace["apply_translations"](self.filtered[pair[1]], arrays["translations_right"][index])
        return left[None, ...], right[None, ...]

    def fixed_state(self):
        result = {"filter_bank": _tensor_record(self.namespace["filter_bank"])}
        for module_name, module in self.model.named_modules():
            for name, value in vars(module).items():
                if isinstance(value, self.torch.Tensor) and name not in module._parameters and name not in module._buffers:
                    result[f"{module_name}.{name}"] = _tensor_record(value)
        return result

    def metadata(self):
        names = {name: dict(shape=list(value.shape), numel=value.numel())
                 for name, value in self.model.named_parameters()}
        return dict(policy=POLICY, revision=REVISION, notebook_sha256=self.source.raw_sha256,
                    adapter_sha256=sha256(Path(__file__).read_bytes()),
                    selected_ast_sha256=self.source.ast_sha256, definitions=self.source.provenance,
                    input_npz_sha256=self.inputs["npz_sha256"], input_manifest_sha256=self.inputs["manifest_sha256"],
                    noise_policy=self.noise_policy, seed=self.seed, threads=self.threads,
                    rng_policy="SHA256(policy, seed, input NPZ hash, pair) resets Python/NumPy/Torch RNG before each score",
                    globals=dict(box_height=80, box_width=161, scales=10, orientations=8, phases=4,
                                 batch_size=1, candidate_deltas=list(DELTAS), scale_factor=.02, scale_base=30 ** (1 / 13)),
                    environment=dict(python=platform.python_version(), torch=self.torch.__version__, numpy=self.np.__version__,
                                     device="cpu", machine=platform.machine()), parameters=names,
                    registered_parameter_entries=sum(value["numel"] for value in names.values()),
                    fixed_tensor_state=self.fixed_state(), compatibility_changes=[
                        "Execute pinned original definitions only; notebook installs, demonstrations and plotting are excluded",
                        "Use CPU rather than notebook CUDA selection and do not execute CUDA-only cache housekeeping",
                        "Use supplied original-domain captured inputs instead of importing notebook font/UFO/Colab stack",
                        "Reset RNG by full input identity and pair; noise-off is a separately named adaptation",
                        "Reconstruct and hash plain fixed tensor attributes rather than assuming state_dict contains them",
                    ], optimizer_updates=0, limitations=[
                        "Modern Torch CPU compatibility run, not recovered 2021 environment or trained state",
                        "Initialized historical parameters only; no calibrated spacing model or optical acceptance",
                        "No delivered-bitmap adaptation, browser inference or preview change",
                    ])

    def score(self, pair, gradient=False):
        seed = self.seed_for(pair)
        left, right = self._pair_inputs(pair)
        self.intermediates = {}
        self.model.zero_grad(set_to_none=True)
        start = time.perf_counter()
        with self.torch.set_grad_enabled(gradient):
            penalties = self.model((left, right, [pair[0]], [pair[1]], False))
            values = penalties.detach().cpu().numpy()[0].tolist()
            if not all(math.isfinite(value) for value in values) or len(set(values)) == 1:
                raise RecoveryError(f"nonfinite or constant pair penalties for {pair}")
            analysis = loss_analysis(values)
            result = dict(pair=pair, input_seed=seed, noise_policy=self.noise_policy,
                          candidate_deltas=list(DELTAS), scores=values, loss_analysis=analysis,
                          forward_seconds=time.perf_counter() - start, intermediates=self.intermediates,
                          gradient_requested=gradient)
            if gradient:
                if analysis["status"] != "valid_for_original_evaluation":
                    raise RecoveryError(f"original loss gate failed: {analysis['status']}")
                observation = observe_original_loss_from_source(self.source, values)
                result["original_loss_observation"] = observation
                minimum = observation.get("intermediates", {}).get("selected_minimum")
                if observation["raw_float32_status"] != "finite" or (minimum is not None and
                        (not isinstance(minimum, (float, int)) or not DELTAS[0] <= minimum <= DELTAS[-1])):
                    raise RecoveryError("original loss has a nonfinite or out-of-domain minimum")
                # Execute the unchanged loss only after identifying the exact
                # degeneracy. Its original floating-point result must itself
                # remain finite; no replacement objective or root is inserted.
                with contextlib.redirect_stdout(io.StringIO()):
                    loss = self.namespace["estimate_min_loss"](penalties)
                if not self.torch.isfinite(loss).item():
                    raise RecoveryError("nonfinite original hybrid loss")
                result["loss"] = float(loss.detach())
                backward_start = time.perf_counter()
                loss.backward()
                result["backward_seconds"] = time.perf_counter() - backward_start
                census = {}
                for name, parameter in self.model.named_parameters():
                    grad = parameter.grad
                    if grad is not None and not self.torch.isfinite(grad).all().item():
                        raise RecoveryError(f"nonfinite parameter gradient: {name}")
                    census[name] = dict(has_gradient=grad is not None, numel=parameter.numel(),
                                        nonzero_entries=int(self.torch.count_nonzero(grad)) if grad is not None else 0)
                result["gradients"] = census
                active = {f"bg_direct.{name}" for name in (
                    "b_to_g", "G_input_weight", "ray_weight", "amplification_saturation", "k", "b")}
                active.update(f"g_targets.{name}" for name in ("general_exp", "loss_b", "loss_factor", "gain_factor"))
                missing = sorted(name for name in active if not census[name]["has_gradient"])
                unexpected = sorted(name for name in census if name not in active and census[name]["has_gradient"])
                if missing or unexpected:
                    raise RecoveryError(f"gradient reachability census mismatch: missing={missing}, unexpected={unexpected}")
                result["gradient_reachability_identity"] = True
        result["process_peak_rss_bytes"] = peak_rss_bytes()
        return result

    def save_checkpoint(self, directory: Path):
        directory.mkdir()
        path = directory / "parameters.pt"
        self.torch.save(self.model.state_dict(), path)
        manifest = self.metadata()
        manifest["parameter_file_sha256"] = sha256(path.read_bytes())
        manifest["checkpoint_kind"] = "initialized recovery state, not a trained checkpoint"
        write_json(directory / "manifest.json", manifest)
        return manifest

    def restore_checkpoint(self, directory: Path):
        manifest = json.loads((directory / "manifest.json").read_text())
        current = self.metadata()
        for key in ("policy", "revision", "notebook_sha256", "adapter_sha256", "selected_ast_sha256", "input_npz_sha256",
                    "input_manifest_sha256", "noise_policy", "seed", "threads", "globals", "fixed_tensor_state", "environment"):
            if manifest[key] != current[key]:
                raise RecoveryError(f"checkpoint recovery identity mismatch: {key}")
        raw = (directory / "parameters.pt").read_bytes()
        if sha256(raw) != manifest["parameter_file_sha256"]:
            raise RecoveryError("checkpoint parameter identity mismatch")
        self.model.load_state_dict(self.torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True), strict=True)
        return manifest


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def run_recovery(args):
    output = Path(args.output)
    report = dict(status="running", policy=POLICY, optimizer_updates=0, phases=[], results=[],
                  noise_policy=args.noise_policy, requested_pairs=args.pairs)
    path = output / "report.json"
    write_json(path, report)
    def phase(name):
        report["phases"].append(name)
        write_json(path, report)
    try:
        phase("synthetic_original_loss_observation")
        report["synthetic_loss_observations"] = {
            "categorical": observe_original_loss(args.reference, [1, 2, 3, 4, 5]),
            "nondegenerate_cubic": observe_original_loss(args.reference, [6.625, 1.875, 1, 2.125, 41.625]),
            "degenerate_quadratic": observe_original_loss(args.reference, [9, 1, 0, 1, 25]),
        }
        write_json(path, report)
        phase("prepare_full_original_domain_scorer")
        scorer = RecoveredScorer(args.reference, args.inputs, args.noise_policy, args.seed, args.threads)
        report["metadata"] = scorer.metadata()
        write_json(path, report)
        for pair in args.pairs:
            phase(f"forward:{pair}")
            result = scorer.score(pair)
            report["results"].append(result)
            write_json(path, report)
        # Repeat after another pair to exercise advancing RNG/state; per-input
        # seeding, rather than one process seed, is the declared order policy.
        phase("repeat_and_order_identity")
        repeat = scorer.score(args.pairs[0])
        if repeat["scores"] != report["results"][0]["scores"]:
            raise RecoveryError("repeated pair scores changed under the declared evaluation policy")
        report["repeat_order_identity"] = True
        phase("save_reconstruct_restore_identity")
        scorer.save_checkpoint(output / "checkpoint")
        expected = report["results"][0]["scores"]
        del scorer
        import gc
        gc.collect()
        restored = RecoveredScorer(args.reference, args.inputs, args.noise_policy, args.seed, args.threads)
        restored.restore_checkpoint(output / "checkpoint")
        after = restored.score(args.pairs[0])
        if expected != after["scores"]:
            raise RecoveryError("save/load score identity failed")
        report["checkpoint_roundtrip_identity"] = True
        if args.gradient_pair:
            phase(f"gradient_census:{args.gradient_pair}")
            report["gradient_probe"] = restored.score(args.gradient_pair, gradient=True)
        report["status"] = "recovery_checks_passed"
    except BaseException as error:
        report["status"] = "recovery_gate_failed"
        report["error"] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    report["process_peak_rss_bytes"] = peak_rss_bytes()
    report["finished_unix_seconds"] = time.time()
    write_json(path, report)
    print(json.dumps({key: report[key] for key in ("status", "optimizer_updates", "process_peak_rss_bytes")}))
    return 0 if report["status"] == "recovery_checks_passed" else 1


def supervise(args):
    """Bound a single full-size worker's time and RSS without changing its math."""
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "recovery-adapter.py").write_bytes(Path(__file__).read_bytes())
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--_worker"]
    start = time.monotonic()
    limit = args.max_rss_gib * 2 ** 30
    termination = None
    with (output / "stdout.log").open("w") as stdout, (output / "stderr.log").open("w") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        while child.poll() is None:
            elapsed = time.monotonic() - start
            sampled = subprocess.run(["ps", "-o", "rss=", "-p", str(child.pid)], capture_output=True, text=True)
            rss = int(sampled.stdout.strip() or 0) * 1024
            if elapsed > args.max_seconds or rss > limit:
                termination = "wall_time_limit" if elapsed > args.max_seconds else "rss_limit"
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                break
            time.sleep(.25)
    report_path = output / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
    else:
        report = dict(status="worker_failed_before_report", optimizer_updates=0)
    if termination is not None:
        report["status"] = "resource_gate_failed"
        report["resource_failure"] = termination
    report["supervisor"] = dict(wall_seconds=time.monotonic() - start, max_seconds=args.max_seconds,
                                 max_rss_gib=args.max_rss_gib, worker_exit_code=child.returncode,
                                 sampling="ps RSS every 0.25s; process peak RSS recorded separately when worker exits normally")
    write_json(report_path, report)
    print(json.dumps(dict(status=report["status"], report=str(report_path))))
    return 0 if report["status"] == "recovery_checks_passed" and child.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", help="pinned upstream Git checkout or exact historical notebook")
    parser.add_argument("inputs", help="original-domain inputs directory")
    parser.add_argument("output", help="new isolated recovery output directory")
    parser.add_argument("--pairs", nargs="+", default=list(FIXED_PAIRS), choices=FIXED_PAIRS)
    parser.add_argument("--noise-policy", choices=NOISE_POLICIES, default=NOISE_POLICIES[0])
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gradient-pair", choices=FIXED_PAIRS)
    parser.add_argument("--max-seconds", type=float, default=240)
    parser.add_argument("--max-rss-gib", type=float, default=24)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or not 1 <= args.max_seconds <= 900:
        parser.error("max-seconds must be finite and between one and 900")
    if not math.isfinite(args.max_rss_gib) or not 1 <= args.max_rss_gib <= 32:
        parser.error("max-rss-gib must be finite and between one and 32")
    return run_recovery(args) if args._worker else supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
