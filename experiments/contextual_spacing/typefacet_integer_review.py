"""Whole-text review of the verified integer TypeFacet experiment; B unchanged."""
import argparse
import copy
import json
from pathlib import Path

from blind_review import CONTROL, HERE, write_review
from density_probe import BitmapOracle
from page import load_presets
from solver import Controls, IMPLEMENTATION_IDENTITY, Solver, canonical
from typefacet_integer import POLICY
from typefacet_density_review import CAPTURE_SHA, DOMAIN, sha


def export(output, fit_root, baseline_path):
    if Path(output).exists():
        raise ValueError("output must be new")
    fit_root = Path(fit_root)
    summary_raw = (fit_root/"summary.json").read_bytes()
    summary = json.loads(summary_raw)
    proof_raw = (fit_root/"original-predicate-verification.json").read_bytes()
    proof = json.loads(proof_raw)
    if (summary["status"] != "density_feasible" or not summary["cold_replay_identical"]
            or not summary["analytic_contact_passed"] or summary["postsolve_correction_px"] != 0
            or proof["status"] != "passed" or proof["chosen_valid_pairs"] != len(DOMAIN)):
        raise ValueError("integer verification gates are incomplete")
    original = json.loads((fit_root/"original-full/capture.json").read_text())
    if (proof.get("summary_sha256") != sha(summary_raw)
            or proof.get("profiles_sha256") != sha((fit_root/"original-full/capture.json").read_bytes())):
        raise ValueError("independent verification does not cover these inputs")
    if original["parameters"] != summary["selected"]["parameters"]:
        raise ValueError("independent original profiles use different settings")
    capture_raw = Path(summary["protocol"]["capture_path"]).read_bytes()
    if sha(capture_raw) != CAPTURE_SHA or sha(capture_raw) != summary["protocol"]["capture_sha256"]:
        raise ValueError("capture differs")
    capture = json.loads(capture_raw)
    solver = Solver(capture)
    presets = load_presets(HERE/"presets.json")
    for preset in presets:
        solver.validate_text(preset["text"])
    baseline_raw = Path(baseline_path).read_bytes()
    retained = json.loads(baseline_raw)
    if sha(canonical({k:v for k,v in retained.items() if k != "identity"}).encode()) != retained["identity"]:
        raise ValueError("retained page identity differs")
    baseline = solver.generate(Controls(spacing_model=CONTROL,preserve_tabular_spacing=False),work_limit=12000)
    if baseline["status"] != "complete":
        raise ValueError("B did not complete")
    font = copy.deepcopy(retained["fonts"][0])
    glyphs = [dict(codepoint=cp,glyphId=g["glyph_id"],advancePx=g["finalized_advance_px"],bitmap=g["bitmap"])
              for cp,g in sorted(solver.glyphs.items())]
    table_b = [int(p["automatic_adjustment_px"]) for p in baseline["pairs"]]
    if (font["glyphs"] != glyphs or font["codepoints"] != sorted(solver.glyphs) or font["tables"][0] != table_b
            or font["label"] != "Literata" or font["axes"] != capture["axes"] or font["sizePx"] != capture["size_px"]):
        raise ValueError("retained B or glyphs differ")
    selected = summary["selected"]
    steps = {tuple(map(ord,p["pair"])):p["step_px"] for p in selected["pairs"]}
    if len(selected["pairs"]) != len(DOMAIN) or set(steps) != set(DOMAIN):
        raise ValueError("integer domain incomplete")
    oracle = BitmapOracle(solver.glyphs)
    table_a, pairs = [], []
    for record in baseline["pairs"]:
        a,b = record["left"],record["right"]
        if (a,b) in steps:
            contact = oracle.contacts(a,b,steps[a,b])
            if not contact["overlap_free"] or not contact["same_row_wall_order"]:
                raise ValueError("integer output violates bitmap safety")
            adjustment = steps[a,b]-solver.glyphs[a]["finalized_advance_px"]
        else:
            adjustment = record["automatic_adjustment_px"]
        table_a.append(int(adjustment))
        pairs.append(dict(left=a,right=b,automatic_adjustment_px=adjustment))
    candidate = dict(status="complete",analysis_identity=solver.identity,controls=baseline["controls"],pairs=pairs)
    fixtures = [dict(arm=arm,preset=preset["id"],width=width,expected=solver.layout(preset["text"],result,width))
                for arm,result in enumerate((baseline,candidate)) for preset in presets for width in (160,280,400)]
    font["tables"] = [table_b,table_a]
    provenance = dict(policy=POLICY,fit_path=str(fit_root.resolve()),fit_sha256=sha(summary_raw),
        original_verification_sha256=sha(proof_raw),capture_sha256=sha(capture_raw),baseline_review_sha256=sha(baseline_raw),
        parameters=selected["parameters"],mean_emitted_px=selected["mean_emitted_px"],
        source_mean_px=summary["protocol"]["source_mean_px"],density_error_px=selected["density_error_px"],
        postsolve_correction_px=0,calibration_alternatives=summary["alternatives"],
        baseline_table_unchanged=True,glyphs_unchanged=True,adapter_sha256=sha(Path(__file__).read_bytes()))
    payload = dict(schema="masked-spacing-review-v2",fonts=[font],presets=presets,
        schedule=[dict(font=0,preset=i,order=[1,0]) for i in range(len(presets))],
        arms=["Previous spacing · control","TypeFacet · constrained integer trial"],
        controls=dict(source_kerning=1,optical=1,letter_spacing=0,word_spacing=0,preserve_tabular_spacing=False),
        implementationSha256=IMPLEMENTATION_IDENTITY,
        presentation=dict(intro="Compare A and B in this short Literata passage. A is an experimental ASCII lowercase spacing fit; all other pairs retain B. Tell me in chat which feels more natural, or if there is no clear difference.",moreLabel="Full presets (optional)"))
    manifest = dict(schema="masked-spacing-review-manifest-v2",status="pending_optical_assessment",fonts=["Literata-reading"],
        presets=[p["id"] for p in presets],**provenance)
    return write_review(output,payload,[dict(inputs=provenance,candidate_pairs=selected["pairs"])],[fixtures],manifest)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output")
    p.add_argument("--fit",default="out/diagnostics/contextual-spacing/typefacet-integer/fit-01")
    p.add_argument("--baseline",default="out/diagnostics/contextual-spacing/blinded-wall-review/underlined/review-data.json")
    args=p.parse_args()
    print(json.dumps(export(args.output,args.fit,args.baseline),indent=2))
