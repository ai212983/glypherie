"""Export the two-arm complete-wall geometry ablation for masked text review.

This isolated adapter reuses the existing full-outline model and placement
composition. US5768490A supplies B/C/D; representing binary cells as exact
rectangles is the declared geometry ablation, not author-code parity.
"""

import argparse
import base64
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import secrets

from density_probe import BitmapOracle
from hu_density import HuDensityModel
import hu_hersch as hu
from page import embedded_json, load_presets
from solver import Controls, IMPLEMENTATION_IDENTITY, Solver, bitmap_commands, canonical


HERE = Path(__file__).resolve().parent
CONTROL = "hu_fitted_full_density_conserved_touch"
POLICY = "complete-cell-wall-ablation-v1"
FAMILIES = ("Literata-reading", "Roboto", "RobotoFlex", "SourceSans3")


class CompleteCellModel(HuDensityModel):
    """Same calibration and construction, exact delivered-cell measurement."""

    def __init__(self, capture, samples_per_px=64):
        super().__init__(capture, samples_per_px, candidate_geometry="fitted_outline",
                         construction_policy="full_outline")
        self.identity = hashlib.sha256((self.identity + POLICY).encode() + Path(__file__).read_bytes()).hexdigest()

    @property
    def candidate_measurement_method(self):
        return POLICY

    @property
    def target_provenance(self):
        return "fixed_alphabet_source_origin_complete_binary_cells"

    def _profile(self, cp, window, geometry):
        if geometry != "fitted_outline":
            return super()._profile(cp, window, geometry)
        key = (cp, tuple(window), "complete_binary_cells")
        if key not in self._profiles:
            commands = bitmap_commands(self.glyphs[cp]["bitmap"], 1.)
            self._profiles[key] = hu.full_source_depth_profile(commands, 1., window, self.settings)
        return self._profiles[key]

    def metadata(self, evaluate=True):
        result = super().metadata(evaluate)
        result.update(candidate_geometry="complete_binary_cells", policy=POLICY,
                      calibration_geometry="source_and_complete_binary_cells")
        for record in result["classes"].values():
            record["candidate_geometry"] = "complete_binary_cells"
        return result


class CompleteCellSolver(Solver):
    """Keep the ablation out of the selectable solver models and defaults."""

    def __init__(self, capture):
        super().__init__(capture)
        self.identity = hashlib.sha256((self.identity + POLICY).encode() + Path(__file__).read_bytes()).hexdigest()
        self.cell_model = CompleteCellModel(self.capture, self.filtered_samples_per_px)

    def _hu_density_model(self, target_policy, candidate_geometry="bitmap", construction_policy="windowed"):
        if (target_policy, candidate_geometry, construction_policy) != ("source_origin", "fitted_outline", "full_outline"):
            raise ValueError("complete-cell review supports only the declared full-strength model")
        return self.cell_model

    def pair(self, left, right, controls=Controls()):
        result = super().pair(left, right, controls)
        result.update(candidate_geometry="complete_binary_cells", measurement_method=POLICY)
        if result.get("hu_hersch"):
            result["hu_hersch"]["candidate_geometry"] = "complete_binary_cells"
        return result

    def generate(self, *args, **kwargs):
        result = super().generate(*args, **kwargs)
        result["estimator"].update(candidate_geometry="complete_binary_cells", measurement_method=POLICY)
        result["experiment_adapter"] = POLICY
        return result


def schedule(font_count, preset_count, seed):
    """Equal first/second positions overall; each repeated trial reverses order.

    This is a two-stimulus counterbalance, not the full multi-stimulus ordering
    algorithm of Davison et al. (2012), doi:10.3758/s13428-011-0170-0.
    """
    result = []
    phase = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 2
    for font in range(font_count):
        for preset in range(preset_count):
            first = (font * preset_count + preset + phase) % 2
            result.append(dict(font=font, preset=preset, order=[first, 1-first]))
    return result


def build_font(request):
    capture_path, presets = request
    path = Path(capture_path)
    raw = path.read_bytes()
    capture = json.loads(raw)
    solvers = [Solver(capture), CompleteCellSolver(capture)]
    supported = set(solvers[0].glyphs) | {10}
    for preset in presets:
        if {ord(c) for c in preset["text"]} - supported:
            raise ValueError(f"uncaptured preset characters: {path}, {preset['id']}")
    options = Controls(spacing_model=CONTROL, preserve_tabular_spacing=False)
    codepoints = sorted(solvers[0].glyphs)
    if len(codepoints) ** 2 > 12000:
        raise ValueError("review capture exceeds the 12000-pair scope")
    oracle = BitmapOracle(solvers[0].glyphs)
    tables, fixtures, audit = [], [], []
    for arm, solver in enumerate(solvers):
        result = solver.generate(options, work_limit=12000)
        if result["status"] != "complete":
            raise ValueError(f"incomplete review arm: {path}, {arm}, {result['reason']}")
        active = [r for r in result["pairs"] if r["unconstrained_step_px"] is not None]
        for record in active:
            contact = oracle.contacts(record["left"], record["right"], record["resolved_step_px"])
            if not contact["overlap_free"] or not contact["same_row_wall_order"]:
                raise ValueError("active placement violates the unchanged overlap guard")
        tables.append([int(r["automatic_adjustment_px"]) for r in result["pairs"]])
        # Store every class, not merely lowercase observations from the advice.
        audit.append(dict(arm=arm, identity=solver.identity, calibration=result["calibration"],
                          active_contact_checks=len(active), pairs=result["pairs"]))
        for preset in presets:
            for width in (160, 280, 400):
                fixtures.append(dict(arm=arm, preset=preset["id"], width=width,
                                     expected=solver.layout(preset["text"], result, width)))
    metrics = capture["metrics"]
    glyphs = [dict(codepoint=cp, glyphId=g["glyph_id"], advancePx=g["finalized_advance_px"], bitmap=g["bitmap"])
              for cp, g in sorted(solvers[0].glyphs.items())]
    font = dict(label="Literata" if path.parent.name == "Literata-reading" else path.parent.name,
                sizePx=capture["size_px"], axes=capture["axes"], codepoints=codepoints, glyphs=glyphs,
                monospace=capture["monospace"], tabularDigits=capture["tabular_digits"], tables=tables,
                metricsAscent=metrics["ascent_26_6"]/64, metricsDescent=metrics["descent_26_6"]/64,
                metricsLineGap=metrics["line_gap_26_6"]/64)
    provenance = dict(capture_path=str(path.resolve()), capture_sha256=hashlib.sha256(raw).hexdigest(),
                      source_sha256=capture["source_sha256"], pipeline=capture["pipeline"],
                      adapter_identity=capture.get("adapter_identity"), arms=audit)
    print(f"{font['label']}: both arms complete, {len(fixtures)} whole-text fixtures", flush=True)
    return font, provenance, fixtures


def write_review(output, payload, audit, fixtures, manifest):
    """Shared offline presentation for the two concrete isolated comparisons."""
    output = Path(output)
    if output.exists():
        raise ValueError("review output must be new")
    payload = dict(payload)
    raw = canonical(payload).encode()
    identity = hashlib.sha256(raw).hexdigest()
    payload["identity"] = identity
    encoded = base64.b64encode(gzip.compress(canonical(payload).encode(), mtime=0)).decode()
    template = (HERE/"blind_review.html").read_text()
    html = template.replace("/* REVIEW_CSS */", (HERE/"blind_review.css").read_text())
    html = html.replace("/* SHARED_HELPERS */", (HERE/"page.js").read_text())
    html = html.replace("/* REVIEW_JS */", (HERE/"blind_review.js").read_text())
    html = html.replace("__PACKED_DATA__", encoded)
    if len(html) > 512000:
        raise ValueError("review document exceeds the inline size bound")
    output.mkdir(parents=True)
    (output/"index.html").write_text(html)
    (output/"review-data.json").write_text(embedded_json(payload)+"\n")
    (output/"verification-fixtures.json").write_text(canonical(fixtures)+"\n")
    (output/"model-audit.json").write_text(canonical(audit)+"\n")
    manifest = dict(manifest, identity=identity, html_sha256=hashlib.sha256(html.encode()).hexdigest(),
                    fixture_count=sum(len(font) for font in fixtures))
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def export(output, capture_root, seed):
    if Path(output).exists():
        raise ValueError("review output must be new")
    presets = load_presets(HERE / "presets.json")
    requests = [(str(Path(capture_root)/name/"capture.json"), presets) for name in FAMILIES]
    with ProcessPoolExecutor(max_workers=4) as pool:
        built = list(pool.map(build_font, requests))
    payload = dict(schema="masked-wall-review-v1", fonts=[entry[0] for entry in built], presets=presets,
                   schedule=schedule(len(built), len(presets), seed),
                   arms=["Complete fitted-outline walls · current control", "Complete binary-cell walls · geometry ablation"],
                   controls=dict(source_kerning=1, optical=1, letter_spacing=0, word_spacing=0,
                                 preserve_tabular_spacing=False),
                   implementationSha256=IMPLEMENTATION_IDENTITY)
    manifest = dict(schema="masked-wall-review-manifest-v1", seed=seed, fonts=FAMILIES,
                    presets=[p["id"] for p in presets], implementation_sha256=IMPLEMENTATION_IDENTITY,
                    adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), status="pending_optical_assessment")
    return write_review(output, payload, [entry[1] for entry in built], [entry[2] for entry in built], manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--capture-root", default="out/diagnostics/contextual-spacing/preset-preview/captures")
    parser.add_argument("--seed", default=None)
    args = parser.parse_args()
    print(json.dumps(export(args.output, args.capture_root, args.seed or secrets.token_hex(8)), indent=2))
