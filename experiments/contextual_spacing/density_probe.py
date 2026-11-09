"""Probe fixed-alphabet Hu density targets without changing a preview default.

Complete ASCII Cartesian domains calibrate every model; text presets only
evaluate held-out pair frequencies. Continuous conservation, integer rounding,
full-bitmap clearance and text-distribution drift remain separate measurements.
Fitted/source-outline placement is a diagnostic composition against retained
bitmaps, never a new rasterization. Mechanical checks establish no optical verdict.
"""

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
import time
import unicodedata

import filtered_walls as walls
from hu_density import HuDensityModel
from solver import (Controls, HU_DENSITY_MODELS, IMPLEMENTATION_IDENTITY, Solver,
                    hu_clearance_policy, hu_density_geometry, pixel_round)


SCHEMA = "hu-fixed-alphabet-density-probe-v2"
POLICIES = ("source_origin", "source_alphabet")
GEOMETRIES = ("source", "bitmap", "fitted_outline")
CONTROL_MODELS = ("hu_source_calibrated", "hu_source_relative")
PRESET_IDS = ("lynx-lowercase", "lynx-uppercase", "aaron-abraham", "numbers",
              "numbers-parentheses", "currencies", "fractions")
REPORTED_PAIRS = ("01", "12", "23", "00", "11", "nn", "oo", "no", "on", "HH", "OO", "HO", "OH",
                  "ip", "pe", "ly", "yn", "nx", "tu", "uf", "ft", "fr", "ro", "og", "gs", "oe", "kh",
                  "rn", "xn", "co", "ff", "cc", "zz", "jo", "yd", "le", "pi", "te", "tp", "OE", "OR",
                  "bd", "ct", "ab", "du", "re", "Aa", "aA", "AV", "To", "Wa", "fi", "al", "ri", "ig", "en", "os", "se")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixed_domains():
    """Independent inventory; never trim these products to captured/text glyphs."""
    lower = tuple(range(ord("a"), ord("z") + 1))
    upper = tuple(range(ord("A"), ord("Z") + 1))
    digits = tuple(range(ord("0"), ord("9") + 1))
    return dict(lowercase=tuple((a, b) for a in lower for b in lower),
                uppercase=tuple((a, b) for a in upper for b in upper),
                digits=tuple((a, b) for a in digits for b in digits),
                mixed=tuple((a, b) for a in upper for b in lower) +
                      tuple((a, b) for a in lower for b in upper))


DOMAINS = fixed_domains()


def mean(values):
    values = list(values)
    return math.fsum(values) / len(values) if values else None


def distribution(values):
    values = list(values)
    if not values:
        return dict(count=0, mean_px=None, sum_px=None, min_px=None, max_px=None)
    return dict(count=len(values), mean_px=mean(values), sum_px=math.fsum(values),
                min_px=min(values), max_px=max(values), median_px=statistics.median(values),
                mean_absolute_px=mean(abs(value) for value in values))


def numeric_check(actual, expected, scale=1.):
    """Binary64 arithmetic tolerance, never an optical acceptance threshold."""
    if actual is None or expected is None:
        return dict(status="not_evaluated", actual_px=actual, expected_px=expected,
                    error_px=None, tolerance_px=None)
    tolerance = 128 * sys.float_info.epsilon * max(1., abs(actual), abs(expected), abs(scale))
    error = actual - expected
    return dict(status="passed" if abs(error) <= tolerance else "failed", actual_px=actual,
                expected_px=expected, error_px=error, tolerance_px=tolerance,
                tolerance_basis="128 times binary64 epsilon times arithmetic magnitude")


def require_check(check, description):
    if check["status"] == "failed":
        raise ValueError(f"{description}: {check}")
    return check


def text_pairs(text):
    """Spaces/punctuation stay present; explicit line boundaries have no pair."""
    return Counter((ord(a), ord(b)) for a, b in zip(text, text[1:]) if a != "\n" and b != "\n")


def load_presets(path):
    records = json.loads(Path(path).read_text())
    if not isinstance(records, list):
        raise ValueError("presets must be a JSON list")
    presets = {}
    for record in records:
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or not isinstance(record.get("text"), str) or record["id"] in presets):
            raise ValueError("preset entries require distinct string ids and string text")
        presets[record["id"]] = record["text"]
    missing = set(PRESET_IDS) - presets.keys()
    if missing:
        raise ValueError("missing assessment presets: " + ", ".join(sorted(missing)))
    return {name: presets[name] for name in PRESET_IDS}


def pair_label(pair):
    return "".join(map(chr, pair))


class BitmapOracle:
    """Independent occupied-cell neighbor enumeration, without wall helpers."""

    def __init__(self, glyphs):
        self.cells = {}
        self.rows = {}
        self.cache = {}
        for cp, glyph in glyphs.items():
            bitmap = glyph["bitmap"]
            width, height = bitmap["width"], bitmap["height"]
            if (type(width) is not int or type(height) is not int or min(width, height) < 0
                    or type(bitmap["left"]) is not int or type(bitmap["top"]) is not int
                    or len(bitmap["pixels"]) != width * height
                    or any(type(value) is not int or value not in (0, 1) for value in bitmap["pixels"])):
                raise ValueError("contact oracle requires whole-pixel binary bitmaps")
            self.cells[cp] = frozenset((bitmap["left"] + x, bitmap["top"] + y)
                                       for y in range(height) for x in range(width)
                                       if bitmap["pixels"][y * width + x])
            rows = {}
            for x, y in self.cells[cp]:
                rows.setdefault(y, []).append(x)
            self.rows[cp] = rows

    def contacts(self, left, right, step):
        if isinstance(step, bool) or not math.isfinite(step) or int(step) != step:
            raise ValueError("contact oracle requires an integer origin step")
        key = (left, right, int(step))
        if key not in self.cache:
            moved = {(x + int(step), y) for x, y in self.cells[right]}
            counts = dict(overlap_pixel_pairs=0, edge_pixel_pairs=0, corner_pixel_pairs=0)
            for x, y in self.cells[left]:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if (x + dx, y + dy) in moved:
                            kind = "overlap" if dx == dy == 0 else "corner" if dx and dy else "edge"
                            counts[kind + "_pixel_pairs"] += 1
            shared_rows = self.rows[left].keys() & self.rows[right].keys()
            ordered = all(max(self.rows[left][row]) + 1 <= min(self.rows[right][row]) + int(step)
                          for row in shared_rows)
            self.cache[key] = dict(counts, overlap_free=counts["overlap_pixel_pairs"] == 0,
                                   contact_free=not any(counts.values()), same_row_wall_order=ordered)
        return copy.deepcopy(self.cache[key])


def verify_clearance(contact, policy):
    """Touching is telemetry in no-overlap mode, never a failed hard check."""
    if policy == "strict":
        valid = contact["contact_free"]
    elif policy == "no_overlap":
        valid = contact["overlap_free"] and contact["same_row_wall_order"]
    else:
        raise ValueError("unsupported diagnostic clearance policy")
    if not valid:
        raise ValueError(f"bitmap clearance contract failed for {policy}: {contact}")
    return True


def source_step(glyphs, kerns, pair):
    return glyphs[pair[0]]["source_advance_px"] + kerns.get(pair, 0.)


def compose(measured, glyphs, pair, metric_step, minimum, *, monospace=False, clearance_policy="strict"):
    """Existing full-strength signed-adjustment round then bitmap clearance.

    Fallbacks are retained as metric placement and explicitly lack an eligible
    optical result. This helper is compared with Solver for bitmap candidates.
    """
    if monospace:
        fallback = "fixed_pitch"
    elif (not any(glyphs[pair[0]]["bitmap"]["pixels"])
          or not any(glyphs[pair[1]]["bitmap"]["pixels"])):
        fallback = "empty_geometry"
    else:
        fallback = measured.get("reason")
    result = dict(eligible=False, reason=fallback, emitted_step_px=metric_step,
                  unconstrained_step_px=None, rounded_unconstrained_step_px=None,
                  rounding_delta_px=None, clearance_delta_px=None,
                  clearance_min_step_px=minimum, clearance_limited=False,
                  post_constraint_target_residual_px=None, clearance_policy=clearance_policy)
    if fallback:
        return result
    ideal = measured["optical_step_px"]
    advance = glyphs[pair[0]]["finalized_advance_px"]
    rounded = advance + pixel_round(ideal - advance)
    emitted = max(rounded, minimum) if minimum is not None else rounded
    delta = emitted - rounded
    return dict(result, eligible=True, reason="clearance_limited" if delta else None,
                unconstrained_step_px=ideal, rounded_unconstrained_step_px=rounded,
                rounding_delta_px=rounded - ideal, clearance_delta_px=delta,
                emitted_step_px=emitted, clearance_limited=bool(delta),
                post_constraint_target_residual_px=emitted + measured["offset_px"] - measured["target_px"])


def compact_measurement(measured):
    keys = ("reason", "detail", "calibration_basis", "target_provenance", "reference_pair", "target_px",
            "offset_px", "optical_step_px", "target_area_px2", "measurement_window_px", "window_height_px")
    return {key: measured[key] for key in keys if key in measured}


def summarize_records(records, weights=None):
    """Uniform alphabet and text-frequency summaries use the same pair records."""
    weights = weights if weights is not None else {pair: 1 for pair in records}
    present = [(record, weights.get(pair, 0)) for pair, record in records.items() if weights.get(pair, 0)]
    total = sum(weights.values())
    captured = sum(count for record, count in present if record["captured"])
    eligible = [(record, count) for record, count in present if record.get("composition", {}).get("eligible")]
    continuous = [(record, count) for record, count in present if record.get("optical_step_px") is not None]

    def samples(items, get):
        return (get(record) for record, count in items for _ in range(count))

    source = distribution(samples([(r, n) for r, n in present if r["captured"]], lambda r: r["source_step_px"]))
    bounded = bool(eligible) and all(r["composition"]["clearance_min_step_px"] is not None for r, _ in eligible)
    minimum_mean = mean(samples(eligible, lambda r: r["composition"]["clearance_min_step_px"])) if bounded else None
    eligible_source_mean = mean(samples(eligible, lambda r: r["source_step_px"])) if eligible else None
    budget_check = numeric_check(minimum_mean, eligible_source_mean)
    return dict(pair_occurrences=total, unique_pairs=len(weights), captured_pair_occurrences=captured,
                missing_pair_occurrences=total - captured,
                eligible_optical_occurrences=sum(count for _, count in eligible),
                continuous_solved_occurrences=sum(count for _, count in continuous),
                fallback_reasons=dict(Counter({reason: sum(count for record, count in present
                    if record.get("composition", {}).get("reason") == reason and
                    not record.get("composition", {}).get("eligible"))
                    for reason in {r.get("composition", {}).get("reason") for r, _ in present}
                    if reason is not None})),
                missing_pairs={pair_label(pair): weights[pair] for pair, record in records.items()
                               if weights.get(pair) and not record["captured"]},
                source_origin_steps=source,
                eligible_source_origin_steps=distribution(samples(eligible, lambda r: r["source_step_px"])),
                continuous_origin_steps=distribution(samples(continuous, lambda r: r["optical_step_px"])),
                continuous_source_step_drift=distribution(samples(continuous, lambda r: r["optical_step_px"] - r["source_step_px"])),
                rounding_delta=distribution(samples(eligible, lambda r: r["composition"]["rounding_delta_px"])),
                clearance_delta=distribution(samples(eligible, lambda r: r["composition"]["clearance_delta_px"])),
                post_constraint_target_residual=distribution(samples(eligible, lambda r: r["composition"]["post_constraint_target_residual_px"])),
                eligible_composed_source_step_drift=distribution(samples(eligible,
                    lambda r: r["composition"]["emitted_step_px"] - r["source_step_px"])),
                metric_source_step_drift=distribution(samples([(r, n) for r, n in present if r["captured"]],
                    lambda r: r["metric_step_px"] - r["source_step_px"])),
                composed_metric_step_drift=distribution(samples([(r, n) for r, n in present if r["captured"]],
                    lambda r: r["composition"]["emitted_step_px"] - r["metric_step_px"])),
                composed_source_step_drift=distribution(samples([(r, n) for r, n in present if r["captured"]],
                    lambda r: r["composition"]["emitted_step_px"] - r["source_step_px"])),
                clearance_limited_occurrences=sum(count for record, count in eligible if record["composition"]["clearance_limited"]),
                contact_verified_occurrences=sum(count for record, count in eligible if record["composition"]["contact_check"]["contact_free"]),
                contact_free_occurrences=sum(count for record, count in eligible if record["composition"]["contact_check"]["contact_free"]),
                overlap_free_occurrences=sum(count for record, count in eligible if record["composition"]["contact_check"]["overlap_free"]),
                clearance_verified_occurrences=sum(count for record, count in eligible
                    if (record["composition"]["contact_check"]["contact_free"]
                        if record["composition"].get("clearance_policy", "strict") == "strict" else
                        record["composition"]["contact_check"]["overlap_free"] and
                        record["composition"]["contact_check"]["same_row_wall_order"])),
                same_row_ordered_occurrences=sum(count for record, count in eligible if record["composition"]["contact_check"]["same_row_wall_order"]),
                edge_contact_occurrences=sum(count for record, count in eligible if record["composition"]["contact_check"]["edge_pixel_pairs"]),
                corner_only_contact_occurrences=sum(count for record, count in eligible
                    if record["composition"]["contact_check"]["corner_pixel_pairs"] and not record["composition"]["contact_check"]["edge_pixel_pairs"]),
                edge_and_corner_contact_occurrences=sum(count for record, count in eligible
                    if record["composition"]["contact_check"]["edge_pixel_pairs"] and record["composition"]["contact_check"]["corner_pixel_pairs"]),
                overlap_pixel_pairs=sum(count * record["composition"]["contact_check"]["overlap_pixel_pairs"] for record, count in eligible),
                edge_pixel_pairs=sum(count * record["composition"]["contact_check"]["edge_pixel_pairs"] for record, count in eligible),
                corner_pixel_pairs=sum(count * record["composition"]["contact_check"]["corner_pixel_pairs"] for record, count in eligible),
                clearance_policy_counts=dict(Counter({policy: sum(count for record, count in eligible
                    if record["composition"].get("clearance_policy", "strict") == policy)
                    for policy in {record["composition"].get("clearance_policy", "strict") for record, _ in eligible}})),
                eligible_bitmap_budget=dict(mean_minimum_feasible_step_px=minimum_mean,
                    mean_source_step_px=eligible_source_mean,
                    minimum_minus_source_px=minimum_mean-eligible_source_mean if bounded else None,
                    infeasible_source_mean_budget=(minimum_mean > eligible_source_mean + budget_check["tolerance_px"] if bounded else None),
                    scope="only eligible occurrence weights; conservative facing-order bitmap bound"),
                scope="adjacent origin steps, excluding line breaks; terminal advances and wrapping are not part of these means",
                optical_acceptance="not established")


def evaluate_capture(capture, capture_path, label, presets, samples_per_px=64):
    started = time.perf_counter()
    solver = Solver(capture, filtered_samples_per_px=samples_per_px)
    glyphs = solver.glyphs
    kerns = solver.source_pairs
    oracle = BitmapOracle(glyphs)
    clearance = {}
    no_overlap_clearance = {}
    metric = {}

    def base(pair):
        if any(cp not in glyphs for cp in pair):
            return dict(pair=pair_label(pair), codepoints=list(pair), captured=False, reason="missing_capture_glyph")
        if pair not in clearance:
            clearance[pair] = walls.clearance_min_step(*(glyphs[cp]["bitmap"] for cp in pair))
            no_overlap_clearance[pair] = walls.clearance_min_step_no_overlap(*(glyphs[cp]["bitmap"] for cp in pair))
            metric[pair] = glyphs[pair[0]]["finalized_advance_px"] + solver.metric_on.get(pair, 0.)
        return dict(pair=pair_label(pair), codepoints=list(pair), captured=True,
                    source_step_px=source_step(glyphs, kerns, pair), metric_step_px=metric[pair])

    all_pairs = set(pair for domain in DOMAINS.values() for pair in domain)
    corpus_counts = {name: text_pairs(text) for name, text in presets.items()}
    all_pairs.update(pair for counts in corpus_counts.values() for pair in counts)
    all_pairs.update(tuple(map(ord, pair)) for pair in REPORTED_PAIRS)
    all_pairs = sorted(all_pairs)
    bases = {pair: base(pair) for pair in all_pairs}
    output = dict(font=label, capture_path=str(Path(capture_path).resolve()),
                  capture_sha256=sha256(capture_path), source_sha256=capture["source_sha256"],
                  size_px=capture["size_px"], axes=capture.get("axes", {}), pipeline=capture.get("pipeline"),
                  analysis_identity=solver.identity, solver_implementation_sha256=IMPLEMENTATION_IDENTITY,
                  source_metric_quantization=capture.get("source_metric_quantization"),
                  source_coordinate_units="source_commands design units scaled by size_px / units_per_em",
                  fitted_coordinate_units="produced_commands already physical pixels, y-up; scale factor 1",
                  bitmap_coordinate_units="full binary pixel cells, baseline left/top y-down",
                  placement_policy=dict(source_kerning=1., optical=1., preserve_tabular_spacing=False,
                                        letter_spacing=0., word_spacing=0.,
                                        fitted_outline="diagnostic same signed adjustment rounding and actual bitmap clearance; no new rasterization",
                                        source="measurement control; diagnostic bitmap composition is not source-font rendering"),
                  models={}, controls={}, checks={}, budgets={}, clearance_budgets={})
    source_models = {}
    model_records = {}
    model_identities = set()
    decomposition_checks = []
    for geometry in GEOMETRIES:
        for policy in POLICIES:
            name = geometry + ":" + policy
            model = HuDensityModel(capture, samples_per_px=samples_per_px,
                                   target_policy=policy, candidate_geometry=geometry)
            metadata = model.metadata()
            if metadata["identity"] in model_identities:
                raise ValueError("density model identity does not distinguish geometry and target policy")
            model_identities.add(metadata["identity"])
            records = {}
            for pair in all_pairs:
                record = dict(bases[pair])
                if record["captured"]:
                    measured = model.pair(*pair)
                    record.update(compact_measurement(measured))
                    composed = compose(measured, glyphs, pair, metric[pair], clearance[pair],
                                       monospace=capture["monospace"])
                    if composed["eligible"]:
                        composed["contact_check"] = oracle.contacts(*pair, composed["emitted_step_px"])
                        verify_clearance(composed["contact_check"], "strict")
                        decomposition = numeric_check(composed["emitted_step_px"] - record["source_step_px"],
                            measured["optical_step_px"] - record["source_step_px"] +
                            composed["rounding_delta_px"] + composed["clearance_delta_px"],
                            scale=max(abs(composed["emitted_step_px"]), abs(record["source_step_px"])))
                        require_check(decomposition, f"drift decomposition {label}/{name}/{pair_label(pair)}")
                        decomposition_checks.append(decomposition)
                    else:
                        composed["contact_check"] = None
                    record["composition"] = composed
                records[pair] = record
            classes = {}
            for basis, domain in DOMAINS.items():
                domain_records = {pair: records[pair] for pair in domain}
                class_meta = metadata.get("classes", {}).get(basis, {})
                advertised = class_meta.get("pair_domain", {})
                expanded = [(a, b) for product in advertised.get("products", [])
                            for a in product.get("left_codepoints", []) for b in product.get("right_codepoints", [])]
                if (len(expanded) != len(domain) or set(expanded) != set(domain)
                        or advertised.get("ordered_pairs") != len(domain)
                        or class_meta.get("pair_count") != len(domain)):
                    raise ValueError(f"model changed the fixed calibration domain: {label}/{name}/{basis}")
                complete = all(record.get("optical_step_px") is not None for record in domain_records.values())
                source_mean = mean(r["source_step_px"] for r in domain_records.values()) if all(r["captured"] for r in domain_records.values()) else None
                candidate_mean = mean(r["optical_step_px"] for r in domain_records.values()) if complete else None
                intercept_mean = mean(r["offset_px"] for r in domain_records.values()) if complete else None
                targets = [r["target_px"] for r in domain_records.values() if r.get("target_px") is not None]
                target = targets[0] if complete else None
                if complete:
                    for value in targets:
                        require_check(numeric_check(value, target), f"target differs within {label}/{name}/{basis}")
                    for key, actual in (("mean_source_step_px", source_mean),
                                        ("mean_candidate_offset_px", intercept_mean),
                                        ("target_px", target), ("continuous_mean_step_px", candidate_mean)):
                        require_check(numeric_check(actual, class_meta[key]), f"metadata {key} mismatch {label}/{name}/{basis}")
                check = numeric_check(candidate_mean, source_mean)
                expected_identity = geometry == "source" or policy == "source_origin"
                if expected_identity:
                    require_check(check, f"continuous conservation {label}/{name}/{basis}")
                elif check["status"] != "not_evaluated":
                    check = dict(check, numerical_equality=check["status"] == "passed", status="not_required",
                                 scope="source-score anchor control does not constrain candidate mean origin step")
                classes[basis] = dict(metadata=class_meta, declared_pairs=len(domain), complete=complete,
                    mean_source_step_px=source_mean, mean_candidate_offset_px=intercept_mean,
                    target_px=target, continuous_mean_step_px=candidate_mean,
                    continuous_mean_source_drift_px=(candidate_mean-source_mean if complete and source_mean is not None else None),
                    mean_conservation_expected=expected_identity, conservation_check=check,
                    summary=summarize_records(domain_records))
            model_records[name] = records
            if geometry == "source":
                source_models[policy] = (metadata, records)
            output["models"][name] = dict(metadata=dict(metadata, clearance_policy="strict"), classes=classes,
                presets={preset: summarize_records(records, counts) for preset, counts in corpus_counts.items()},
                reported_pairs=[records[tuple(map(ord, pair))] for pair in REPORTED_PAIRS],
                pair_records=list(records.values()))

    # Hold each measurement fixed while composing its no-overlap counterpart.
    # Fitted walls use their own source-origin target; the delivered bitmap
    # supplies the same clearance bound in both geometries.
    for geometry in ("bitmap", "fitted_outline"):
        strict_name = geometry + ":source_origin"
        touching_name = strict_name + ":no_overlap"
        touching_records = {}
        for pair, original in model_records[strict_name].items():
            record = copy.deepcopy(original)
            if record["captured"]:
                composed = compose(record, glyphs, pair, metric[pair], no_overlap_clearance[pair],
                                   monospace=capture["monospace"], clearance_policy="no_overlap")
                if composed["eligible"]:
                    composed["contact_check"] = oracle.contacts(*pair, composed["emitted_step_px"])
                    verify_clearance(composed["contact_check"], "no_overlap")
                    strict_composed = original["composition"]
                    if composed["rounded_unconstrained_step_px"] != strict_composed["rounded_unconstrained_step_px"]:
                        raise ValueError("clearance arm changed the rounded unconstrained placement")
                    decomposition = numeric_check(composed["emitted_step_px"] - record["source_step_px"],
                        record["optical_step_px"] - record["source_step_px"] +
                        composed["rounding_delta_px"] + composed["clearance_delta_px"],
                        scale=max(abs(composed["emitted_step_px"]), abs(record["source_step_px"])))
                    require_check(decomposition, f"no-overlap drift decomposition {label}/{record['pair']}")
                    decomposition_checks.append(decomposition)
                else:
                    composed["contact_check"] = None
                record["composition"] = composed
            touching_records[pair] = record
        model_records[touching_name] = touching_records
        touching_metadata = copy.deepcopy(output["models"][strict_name]["metadata"])
        touching_metadata.update(clearance_policy="no_overlap", measurement_identity=touching_metadata["identity"])
        touching_metadata["identity"] = hashlib.sha256(canonical(dict(
            measurement_identity=touching_metadata["measurement_identity"], clearance_policy="no_overlap",
            solver_implementation_sha256=IMPLEMENTATION_IDENTITY, probe_sha256=sha256(__file__))).encode()).hexdigest()
        output["models"][touching_name] = dict(metadata=touching_metadata,
            classes={basis: dict(copy.deepcopy(output["models"][strict_name]["classes"][basis]),
                                summary=summarize_records({pair: touching_records[pair] for pair in domain}))
                     for basis, domain in DOMAINS.items()},
            presets={preset: summarize_records(touching_records, counts) for preset, counts in corpus_counts.items()},
            reported_pairs=[touching_records[tuple(map(ord, pair))] for pair in REPORTED_PAIRS],
            pair_records=list(touching_records.values()))

    # Source branches must be the same model on the complete fixed domains.
    arm_checks = {}
    for basis, domain in DOMAINS.items():
        pairs = [pair for pair in domain if all(source_models[p][1][pair].get("optical_step_px") is not None for p in POLICIES)]
        checks = [numeric_check(source_models[POLICIES[0]][1][pair]["optical_step_px"],
                                source_models[POLICIES[1]][1][pair]["optical_step_px"]) for pair in pairs]
        for check in checks:
            require_check(check, f"source arms differ {label}/{basis}")
        arm_checks[basis] = dict(status="passed" if len(pairs) == len(domain) else "unavailable",
            checked_pairs=len(pairs), declared_pairs=len(domain), max_abs_difference_px=max((abs(c["error_px"]) for c in checks), default=None))
    output["checks"]["source_arms_coincide"] = arm_checks

    # The source-alphabet arm is a source-score anchor even when the candidate
    # geometry changes. This does not require its bitmap origin mean to match.
    anchor_checks = {}
    for geometry in GEOMETRIES:
        for basis in DOMAINS:
            source_class = output["models"]["source:source_alphabet"]["classes"][basis]
            candidate_class = output["models"][geometry + ":source_alphabet"]["classes"][basis]
            check = numeric_check(candidate_class["target_px"], source_class["target_px"])
            require_check(check, f"source-score anchor changed {label}/{geometry}/{basis}")
            anchor_checks[geometry + ":" + basis] = check
    output["checks"]["source_alphabet_anchor_geometry_identity"] = anchor_checks

    # Assert Solver composition on the retained actual bitmaps for each mode;
    # source geometry remains an explicitly labelled diagnostic control.
    solver_checks = {}
    for mode, policy in HU_DENSITY_MODELS.items():
        controls = Controls(spacing_model=mode, preserve_tabular_spacing=False)
        clearance_policy = hu_clearance_policy(mode)
        geometry = hu_density_geometry(mode)
        model_name = geometry + ":" + policy + (":no_overlap" if clearance_policy == "no_overlap" else "")
        records = model_records[model_name]
        checked = 0
        for pair, record in records.items():
            if not record["captured"]:
                continue
            actual = solver.pair(*pair, controls)
            composed = record["composition"]
            if actual["resolved_step_px"] != composed["emitted_step_px"]:
                raise ValueError(f"solver/probe composition mismatch: {label}/{mode}/{record['pair']}")
            eligible = actual.get("unconstrained_step_px") is not None and actual.get("optical_adjustment_px") is not None
            if eligible != composed["eligible"]:
                raise ValueError(f"solver/probe eligibility mismatch: {label}/{mode}/{record['pair']}")
            if actual["reason"] != composed["reason"]:
                raise ValueError(f"solver/probe fallback or guard reason mismatch: {label}/{mode}/{record['pair']}")
            if actual["clearance_policy"] != clearance_policy:
                raise ValueError(f"solver/probe clearance policy mismatch: {label}/{mode}/{record['pair']}")
            if eligible:
                for key, expected in (("rounded_unconstrained_step_px", composed["rounded_unconstrained_step_px"]),
                                      ("clearance_adjustment_px", composed["clearance_delta_px"])):
                    if actual[key] != expected:
                        raise ValueError(f"solver/probe {key} mismatch: {label}/{mode}/{record['pair']}")
            checked += 1
        solver_checks[mode] = dict(status="passed", checked_pairs=checked, clearance_policy=clearance_policy,
                                   candidate_geometry=geometry)
    output["checks"]["bitmap_solver_composition"] = solver_checks

    # Old generic-source-reference and source-pair-relative candidates remain
    # measured controls, including their own unsupported fallbacks.
    for mode in CONTROL_MODELS:
        controls = Controls(spacing_model=mode, preserve_tabular_spacing=False)
        records = {}
        for pair in all_pairs:
            record = dict(bases[pair])
            if record["captured"]:
                actual = solver.pair(*pair, controls)
                eligible = actual.get("unconstrained_step_px") is not None and actual.get("optical_adjustment_px") is not None
                record.update(reason=actual["reason"], target_px=actual.get("target_separation_px"),
                              optical_step_px=actual.get("unconstrained_step_px"),
                              calibration_basis=actual.get("calibration_basis"))
                record["composition"] = dict(eligible=eligible, reason=actual["reason"],
                    emitted_step_px=actual["resolved_step_px"],
                    unconstrained_step_px=actual.get("unconstrained_step_px"),
                    rounded_unconstrained_step_px=actual.get("rounded_unconstrained_step_px"),
                    rounding_delta_px=(actual["rounded_unconstrained_step_px"] - actual["unconstrained_step_px"] if eligible else None),
                    clearance_delta_px=actual.get("clearance_adjustment_px") if eligible else None,
                    clearance_min_step_px=actual.get("clearance_min_step_px"),
                    clearance_limited=actual.get("clearance_limited", False),
                    post_constraint_target_residual_px=actual.get("target_error_px") if eligible else None,
                    clearance_policy="strict",
                    contact_check=oracle.contacts(*pair, actual["resolved_step_px"]) if eligible else None)
                if eligible:
                    verify_clearance(record["composition"]["contact_check"], "strict")
            records[pair] = record
        output["controls"][mode] = dict(metadata=solver.calibration_metadata(spacing_model=mode),
            classes={basis: summarize_records({pair: records[pair] for pair in domain}) for basis, domain in DOMAINS.items()},
            presets={preset: summarize_records(records, counts) for preset, counts in corpus_counts.items()},
            reported_pairs=[records[tuple(map(ord, pair))] for pair in REPORTED_PAIRS], pair_records=list(records.values()))

    for basis, domain in DOMAINS.items():
        captured = all(bases[pair]["captured"] for pair in domain)
        bounded = captured and all(clearance[pair] is not None for pair in domain)
        source_mean = mean(bases[pair]["source_step_px"] for pair in domain) if captured else None
        minimum_mean = mean(clearance[pair] for pair in domain) if bounded else None
        check = numeric_check(minimum_mean, source_mean)
        output["budgets"][basis] = dict(declared_pairs=len(domain), captured_pairs=sum(bases[pair]["captured"] for pair in domain),
            bounded_pairs=sum(bases[pair]["captured"] and clearance[pair] is not None for pair in domain),
            source_mean_step_px=source_mean, mean_minimum_feasible_bitmap_step_px=minimum_mean,
            minimum_minus_source_px=minimum_mean-source_mean if bounded else None,
            infeasible_source_mean_budget=(minimum_mean > source_mean + check["tolerance_px"] if bounded else None),
            constraint="retained conservative facing-order closed-cell clearance, including corner contact; not a proof about all possible interlocks")
    output["clearance_budgets"]["strict"] = copy.deepcopy(output["budgets"])
    for basis, domain in DOMAINS.items():
        captured = all(bases[pair]["captured"] for pair in domain)
        bounded = captured and all(no_overlap_clearance[pair] is not None for pair in domain)
        source_mean = output["budgets"][basis]["source_mean_step_px"]
        minimum_mean = mean(no_overlap_clearance[pair] for pair in domain) if bounded else None
        check = numeric_check(minimum_mean, source_mean)
        output["clearance_budgets"].setdefault("no_overlap", {})[basis] = dict(
            declared_pairs=len(domain), captured_pairs=sum(bases[pair]["captured"] for pair in domain),
            bounded_pairs=sum(bases[pair]["captured"] and no_overlap_clearance[pair] is not None for pair in domain),
            source_mean_step_px=source_mean, mean_minimum_feasible_bitmap_step_px=minimum_mean,
            minimum_minus_source_px=minimum_mean-source_mean if bounded else None,
            infeasible_source_mean_budget=(minimum_mean > source_mean + check["tolerance_px"] if bounded else None),
            constraint="same-row facing wall order without occupied-cell overlap; edge and corner contact permitted")
    output["runtime_seconds"] = time.perf_counter() - started
    output["checks"]["contact_oracle"] = dict(status="passed", unique_integer_pair_placements=len(oracle.cache),
        policies=dict(strict="no occupied-cell overlap, edge or corner contact", no_overlap="no occupied-cell overlap plus same-row facing order; touching is telemetry"),
        method="direct occupied-pixel neighbor enumeration and same-row extrema; zero tracking; eligible optical placements only")
    output["checks"]["preset_capture_coverage"] = dict(
        status="passed" if all(bases[pair]["captured"] for counts in corpus_counts.values() for pair in counts) else "incomplete",
        presets={name: dict(declared_pair_occurrences=sum(counts.values()),
                           missing_pair_occurrences=sum(count for pair, count in counts.items() if not bases[pair]["captured"]))
                 for name, counts in corpus_counts.items()})
    output["checks"]["drift_decomposition"] = dict(status="passed", checked_pairs=len(decomposition_checks),
        max_absolute_error_px=max((abs(check["error_px"]) for check in decomposition_checks), default=None),
        formula="emitted-source = (continuous-source) + rounding + clearance; eligible pair records only")
    return output


def summarize_font(font):
    return dict(font=font["font"], size_px=font["size_px"], axes=font["axes"], source_sha256=font["source_sha256"],
                capture_sha256=font["capture_sha256"], analysis_identity=font["analysis_identity"],
                models={name: dict(identity=model["metadata"]["identity"], clearance_policy=model["metadata"]["clearance_policy"],
                                   classes=model["classes"], presets=model["presets"],
                                   reported_pairs=model["reported_pairs"])
                        for name, model in font["models"].items()},
                controls={name: dict(classes=model["classes"], presets=model["presets"]) for name, model in font["controls"].items()},
                budgets=font["budgets"], clearance_budgets=font["clearance_budgets"],
                checks=font["checks"], runtime_seconds=font["runtime_seconds"])


def helper_paths():
    directory = Path(__file__).resolve().parent
    return [directory / name for name in ("density_probe.py", "hu_density.py", "solver.py", "hu_hersch.py",
            "hu_calibration.py", "hu_source_relative.py", "filtered_walls.py", "calibration.py", "estimator.py")]


IMPORTED_HELPER_HASHES = {str(path.resolve()): sha256(path) for path in helper_paths()}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run_probe(output_directory, capture_paths, presets_path=None, *, samples_per_px=64):
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    paths = list(map(Path, capture_paths))
    if not paths:
        raise ValueError("provide at least one capture")
    presets_path = Path(presets_path) if presets_path is not None else Path(__file__).with_name("presets.json")
    presets = load_presets(presets_path)
    labels = [path.parent.name if path.stem == "capture" else path.stem for path in paths]
    keys = [unicodedata.normalize("NFC", label).casefold() for label in labels]
    if (len(set(keys)) != len(keys) or len({path.resolve() for path in paths}) != len(paths)
            or any(not label or len(label.encode()) > 200 or key in {"summary", "identities"} for label, key in zip(labels, keys))):
        raise ValueError("capture output labels must be bounded, distinct and not reserved")
    inputs = [*paths, presets_path, *helper_paths()]
    hashes = {str(path.resolve()): sha256(path) for path in inputs}
    if any(hashes[path] != digest for path, digest in IMPORTED_HELPER_HASHES.items()):
        raise ValueError("helpers changed after import; restart probe to avoid stale loaded code")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    reserved = False
    try:
        fonts = []
        for label, path in zip(labels, paths):
            capture = json.loads(path.read_text())
            font = evaluate_capture(capture, path, label, presets, samples_per_px)
            write_json(stage / f"{label}.json", font)
            fonts.append(summarize_font(font))
            print(f"density probe: {label}: {font['runtime_seconds']:.2f}s", file=sys.stderr, flush=True)
        changed = [str(path) for path in inputs if sha256(path) != hashes[str(path.resolve())]]
        if changed:
            raise ValueError("inputs/helpers changed during probe; refusing stale identities: " + ", ".join(changed))
        summary = dict(schema=SCHEMA, status="completed_diagnostic", samples_per_px=samples_per_px,
            calibration_domains={basis: dict(pair_count=len(domain), pairs=[pair_label(pair) for pair in domain],
                codepoint_pairs=[list(pair) for pair in domain]) for basis, domain in DOMAINS.items()},
            geometries=list(GEOMETRIES), target_policies=list(POLICIES), assessed_presets=list(presets),
            clearance_policies=["strict", "no_overlap"],
            no_overlap_scope="bitmap and fitted_outline source_origin; six original geometry/policy controls retain strict clearance",
            source_pair_policy="full source kerning, independent of runtime source-kerning strength",
            findings_status="mechanical diagnostic; optical acceptance and browser-candidate decision remain pending",
            fonts=fonts, runtime=dict(python=sys.version, platform=platform.platform()),
            helper_hashes={path.name: hashes[str(path.resolve())] for path in helper_paths()})
        write_json(stage / "summary.json", summary)
        identities = dict(schema="hu-density-probe-identities-v1", inputs=hashes,
            tool_and_helpers={str(path.resolve()): hashes[str(path.resolve())] for path in helper_paths()},
            captures={str(path.resolve()): hashes[str(path.resolve())] for path in paths},
            presets=dict(path=str(presets_path.resolve()), sha256=hashes[str(presets_path.resolve())]),
            outputs={path.name: sha256(path) for path in stage.glob("*.json")})
        write_json(stage / "identities.json", identities)
        output.mkdir()
        reserved = True
        os.replace(stage, output)
        reserved = False
        return summary
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if reserved:
            output.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("captures", metavar="CAPTURE", type=Path, nargs="+")
    parser.add_argument("--presets", type=Path, default=Path(__file__).with_name("presets.json"))
    args = parser.parse_args(argv)
    try:
        summary = run_probe(args.output_directory, args.captures, args.presets)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(dict(status=summary["status"], captures=len(summary["fonts"]), output_directory=str(args.output_directory))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
