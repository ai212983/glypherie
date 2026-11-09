"""Frozen TypeFacet redistribution with a fixed lowercase density constraint.

TypeFacet supplies the raw pair selector. The mean-step constraint is the
project adaptation in docs/references/fixed-alphabet-spacing-density.md,
grounded in source horizontal advances, not an upstream TypeFacet formula.
It is applied before existing signed rounding and bitmap overlap protection.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from blind_review import CONTROL, HERE, write_review
from density_probe import BitmapOracle
from filtered_walls import clearance_min_step_no_overlap
from page import load_presets
from solver import Controls, IMPLEMENTATION_IDENTITY, Solver, canonical, pixel_round


POLICY = "typefacet-fixed-lowercase-density-v1"
DOMAIN = tuple((a, b) for a in range(97, 123) for b in range(97, 123))
CAPTURE_SHA = "ffcc3b3b4fcadfa6e5eb2814704e82d74eb7ce888209baeb45d0886aa93e8967"
REFERENCE_SHA = "c3c091f37501f69133936a75e03a16b542d673fca3939bfe77eff9016c472417"
FROZEN_PARAMETERS = dict(min_distance_ems=.055, max_distance_ems=.17, intrusion_tolerance_ems=.05625,
                         max_x_extrema_overlap_ems=.0375, precision_ems=.005)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def center_steps(raw, source):
    """Complete fixed alphabet only; no text or selected-pair weighting."""
    if set(raw) != set(DOMAIN) or set(source) != set(DOMAIN):
        raise ValueError("density requires all 676 ASCII lowercase pairs")
    if not all(math.isfinite(v) for v in (*raw.values(), *source.values())):
        raise ValueError("nonfinite pair step")
    raw_mean = math.fsum(raw[p] for p in DOMAIN)/len(DOMAIN)
    source_mean = math.fsum(source[p] for p in DOMAIN)/len(DOMAIN)
    shift = source_mean-raw_mean
    centered = {p: raw[p]+shift for p in DOMAIN}
    return centered, dict(domain="complete ASCII lowercase Cartesian product", count=len(DOMAIN),
                          mean_raw_px=raw_mean, mean_source_px=source_mean, shift_px=shift,
                          mean_continuous_px=math.fsum(centered.values())/len(DOMAIN))


def place_pair(left, right, raw, shift):
    continuous = raw+shift
    advance = left["finalized_advance_px"]
    rounded = advance+pixel_round(continuous-advance)
    minimum = clearance_min_step_no_overlap(left["bitmap"], right["bitmap"])
    step = max(rounded, minimum) if minimum is not None else rounded
    return dict(raw_typefacet_px=raw, density_shift_px=shift, continuous_step_px=continuous,
                rounded_step_px=rounded, clearance_min_step_px=minimum, emitted_step_px=step,
                rounding_residual_px=rounded-continuous, guard_displacement_px=step-rounded,
                automatic_adjustment_px=step-advance)


def export(output, capture_path, reference_path, baseline_path):
    if Path(output).exists():
        raise ValueError("review output must be new")
    capture_raw, reference_raw, baseline_raw = [Path(p).read_bytes() for p in (capture_path, reference_path, baseline_path)]
    if sha(capture_raw) != CAPTURE_SHA or sha(reference_raw) != REFERENCE_SHA:
        raise ValueError("the trial requires its frozen capture and original TypeFacet output")
    capture, reference, retained = map(json.loads, (capture_raw, reference_raw, baseline_raw))
    if (reference["schema"] != "typefacet-reference-capture-v1" or reference["parameters"] != FROZEN_PARAMETERS
            or reference["units_per_em"] != capture["units_per_em"]):
        raise ValueError("reference settings or coordinates differ")
    if sha(canonical({k: v for k, v in retained.items() if k != "identity"}).encode()) != retained["identity"]:
        raise ValueError("retained page identity differs")
    solver = Solver(capture)
    if capture["monospace"]:
        raise ValueError("the bounded trial requires its proportional capture")
    presets = load_presets(HERE/"presets.json")
    for preset in presets:
        solver.validate_text(preset["text"])
    controls = Controls(spacing_model=CONTROL, preserve_tabular_spacing=False)
    baseline = solver.generate(controls, work_limit=12000)
    if baseline["status"] != "complete":
        raise ValueError("control generation did not complete")
    font = copy.deepcopy(retained["fonts"][0])
    glyphs = [dict(codepoint=cp, glyphId=g["glyph_id"], advancePx=g["finalized_advance_px"], bitmap=g["bitmap"])
              for cp, g in sorted(solver.glyphs.items())]
    if (font["label"] != "Literata" or font["glyphs"] != glyphs or font["codepoints"] != sorted(solver.glyphs)
            or font["sizePx"] != capture["size_px"] or font["axes"] != capture["axes"]):
        raise ValueError("retained glyphs or font identity differ")
    table_b = [int(p["automatic_adjustment_px"]) for p in baseline["pairs"]]
    if table_b != font["tables"][0]:
        raise ValueError("regenerated B differs from the retained control")
    factor = capture["size_px"]/capture["units_per_em"]
    raw = {(ord(p["left"]), ord(p["right"])): p["selected_advance"]*factor for p in reference["pairs"]
           if len(p["left"]) == len(p["right"]) == 1 and (ord(p["left"]), ord(p["right"])) in DOMAIN}
    source = {(a, b): solver.glyphs[a]["source_advance_px"]+solver.source_pairs.get((a, b), 0.) for a, b in DOMAIN}
    centered, density = center_steps(raw, source)
    oracle = BitmapOracle(solver.glyphs)
    rows, pairs, table_a = [], [], []
    for control in baseline["pairs"]:
        pair = control["left"], control["right"]
        if pair in centered:
            a, b = pair
            record = dict(left=a, right=b, source_step_px=source[pair], control_step_px=control["resolved_step_px"],
                          **place_pair(solver.glyphs[a], solver.glyphs[b], raw[pair], density["shift_px"]))
            contact = oracle.contacts(a, b, record["emitted_step_px"])
            if not contact["overlap_free"] or not contact["same_row_wall_order"]:
                raise ValueError("candidate overlaps or inverts walls")
            record["contacts"] = contact
            adjustment = int(record["automatic_adjustment_px"])
            rows.append(record)
        else:
            adjustment = int(control["automatic_adjustment_px"])
        table_a.append(adjustment)
        pairs.append(dict(left=pair[0], right=pair[1], automatic_adjustment_px=adjustment))
    density.update(mean_rounded_px=math.fsum(p["rounded_step_px"] for p in rows)/len(DOMAIN),
                   mean_emitted_px=math.fsum(p["emitted_step_px"] for p in rows)/len(DOMAIN),
                   mean_rounding_residual_px=math.fsum(p["rounding_residual_px"] for p in rows)/len(DOMAIN),
                   mean_guard_displacement_px=math.fsum(p["guard_displacement_px"] for p in rows)/len(DOMAIN),
                   guard_clamped_pairs=sum(p["guard_displacement_px"] != 0 for p in rows))
    # Solver.layout verifies the frozen glyph/metric context; this minimal
    # result does not claim that the candidate was solved by the Hu estimator.
    candidate = dict(status="complete", analysis_identity=solver.identity, controls=baseline["controls"], pairs=pairs)
    font["tables"] = [table_b, table_a]
    fixtures = []
    for arm, result in enumerate((baseline, candidate)):
        for preset in presets:
            for width in (160, 280, 400):
                fixtures.append(dict(arm=arm, preset=preset["id"], width=width,
                                     expected=solver.layout(preset["text"], result, width)))
    inputs = dict(capture_path=str(Path(capture_path).resolve()), capture_sha256=sha(capture_raw),
                  original_output_path=str(Path(reference_path).resolve()), original_output_sha256=sha(reference_raw),
                  baseline_review_path=str(Path(baseline_path).resolve()), baseline_review_sha256=sha(baseline_raw),
                  parameters=FROZEN_PARAMETERS, policy=POLICY, density=density,
                  baseline_table_unchanged=True, glyphs_unchanged=True,
                  adapter_sha256=sha(Path(__file__).read_bytes()), implementation_sha256=IMPLEMENTATION_IDENTITY)
    payload = dict(schema="masked-spacing-review-v2", fonts=[font], presets=presets,
                   schedule=[dict(font=0, preset=i, order=[1, 0]) for i in range(len(presets))],
                   arms=["Previous spacing · control", "TypeFacet · fixed lowercase density"],
                   controls=dict(source_kerning=1, optical=1, letter_spacing=0, word_spacing=0, preserve_tabular_spacing=False),
                   implementationSha256=IMPLEMENTATION_IDENTITY,
                   presentation=dict(intro="Compare A and B in this short Literata passage. This trial changes ASCII lowercase pairs only; all other pairs retain the previous spacing. Tell me in chat which feels more natural, or if there is no clear difference.",
                                     moreLabel="Full presets (optional)"))
    manifest = dict(schema="masked-spacing-review-manifest-v2", fonts=["Literata-reading"],
                    presets=[p["id"] for p in presets], status="pending_optical_assessment", **inputs)
    manifest = write_review(output, payload, [dict(inputs=inputs, candidate_pairs=rows)], [fixtures], manifest)
    print(json.dumps(dict(identity=manifest["identity"], density=density, candidate_pairs=len(rows),
                          fixture_count=manifest["fixture_count"], status=manifest["status"]), indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--capture", default="out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json")
    parser.add_argument("--reference", default="out/diagnostics/contextual-spacing/typefacet-calibration/fit-03/full-cells/capture.json")
    parser.add_argument("--baseline", default="out/diagnostics/contextual-spacing/blinded-wall-review/underlined/review-data.json")
    args = parser.parse_args()
    export(args.output, args.capture, args.reference, args.baseline)
