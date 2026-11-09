#!/usr/bin/env python3
# cspell:words yinyangfit bindgen
"""Export the Class-L sample-gallery spacing page (isolated, offline file:// use).

Covers all 13 canonical root-page font samples in both Mono and
Grayscale profiles, from the frozen source catalogue (cases, texts,
packed glyphs, captures, source metrics) pinned by hash before use.
The source catalogue is derived from captures plus the root catalogue
plus fonts; generated pages are never build input.

Scorer: the frozen oriented-engine runtime (``yinyangfit-oriented-engine-v1``;
stage-1 oriented fields, stage-2 multiscale combination, Class-L local
normalization ``yinyangfit-local-energy-v2``) at the default geometry
(R 12, q 2.0, tau 0.5, notebook strength, frozen normalizer 12).
Shipped tables carry one geometry column per pair: per-step Class-L
curves from the pinned calibration curves (pair domains re-verified,
missing pinned pairs rescored through the production runtime), plus
validity/support diagnostics. The interaction target never enters
geometry, so every target choice derives in the browser through the
shared TIE-v2 rule; R/q/text outside the shipped column score exactly
on demand in the page WASM worker. No B2 scorer, tables, or ranges are
used or shipped here.

The G2 Python oracle below (``score_steps``, ``score_pair_curves``,
``derive_choice``, ``line_layouts``, ``parity_spots``, ``build_case``)
remains frozen code history for the archived studies that import it;
it is not the active UI path and no G2 tables are built or shipped.
"""
import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import yinyangfit_interactive as v1
import yinyangfit_interactive_v3_ranges as vr
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
from yinyangfit_interactive_evidence import PAIRS as FIXED_PAIRS

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "apps/web/scripts/landing-samples"))
import generate as landing_generate

ENGINE = HERE / "oriented_engine"
# Placement-search identity, versioned separately from the model and the
# settings: exhaustive whole-pixel enumeration over the geometry-derived
# ordered-letter domain intersected with strictly forward pen order
# (step >= 1), TIE-v2 over supported steps only.
SEARCH_POLICY = "yinyangfit-search-v2"
PINNED_PAIRS = ["nn", "HH", "ll"]
CSTAR_SPOT_GRID = [0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 48, 64,
                   96, 128]

MODEL_IDENTITY = "yinyangfit-oriented-engine-v1"
# Fixed global display gains (display only; never enter scores).
# Slate: corpus peaks run ~0.07..0.18, so gain 6 puts typical peaks at
# visible alpha while clipping only the tallest; interaction: per-query
# peaks run ~0.0..0.74 with median ~0.25, so gain 4 puts typical peaks
# near full alpha while faint tails stay faint. Measured ranges are
# recorded in the manifest; neither gain auto-normalizes per frame.
SLATE_GAIN = 6.0
CONTRIB_GAIN = 4.0


def _sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def check_frozen_pins():
    """Frozen model/param pins the tables are built against."""
    assert yf.MODEL_IDENTITY == "yinyangfit-oriented-fields-v1"
    assert mf.MODEL_IDENTITY == "yinyangfit-multiscale-fields-v1"
    assert MODEL_IDENTITY == "yinyangfit-oriented-engine-v1"
    params_rs = (ENGINE / "src/params.rs").read_text()
    assert f'MODEL_IDENTITY: &str = "{MODEL_IDENTITY}"' in params_rs
    assert yf.DEFAULT_PARAMS.radial_exponent_q == 2.0
    assert yf.DEFAULT_PARAMS.angular_concentration_kappa == 4.0
    assert yf.DEFAULT_PARAMS.kernel_radius_px == 12
    assert yf.DEFAULT_PARAMS.denominator_eps == 1e-12
    assert yf.DEFAULT_PARAMS.n_directed == 16
    assert tuple(mf.DEFAULT_PARAMS.scale_sigmas_px) == (
        0.75, 1.0606601717798212, 1.5, 2.1213203435596424, 3.0)
    assert tuple(mf.DEFAULT_PARAMS.scale_weights) == (1.0,) * 5
    assert sc.TAU_PX == 0.5
    assert sc.G2_BOUND == 128.0
    assert sc.resolve_strength("notebook") == "confidence_notebook"
    facing = sc.facing_matrix(16)
    assert abs(float(facing.sum()) - 128.0) < 1e-9


def text_pairs(text):
    """Unique non-space adjacent pairs per line; newlines split lines."""
    found = set()
    for line in text.split("\n"):
        for left, right in zip(line, line[1:]):
            if left != " " and right != " ":
                found.add(left + right)
    return found


def cover_string(profile, cover):
    if profile == "mono":
        return "".join("1" if v > 0.0 else "0" for v in cover)
    codes = []
    for v in cover:
        code = int(round(v * 7.0))
        if not 0 <= code <= 7 or abs(v - code / 7.0) > 1e-9:
            raise ValueError(f"gray cover is not an exact delivered level: {v!r}")
        codes.append(str(code))
    return "".join(codes)


def pack_glyphs(dataset):
    packed = {}
    for codepoint, cell in dataset["cells"].items():
        packed[str(codepoint)] = {
            "w": cell["width"], "h": cell["height"],
            "left": cell["left"], "top": cell["top"],
            "cover": cover_string(dataset["profile"], cell["cover"])}
    return packed


def pack_metrics(dataset):
    """Source advances and pair-kerning adjustments for exact metric steps.

    The browser mirrors ``metric_step`` for novel preview-text pairs with
    these numbers; a pair absent from ``kern`` means no adjustment, exactly
    as the captured ``adjustments.get((left, right), 0.0)`` policy. Mono
    advances are finalized whole pixels; Gray keeps 26.6 fractions.
    """
    if dataset["profile"] == "mono":
        advances = {str(cp): float(cell["advance_px"])
                    for cp, cell in dataset["cells"].items()}
    else:
        advances = {str(cp): float(adv)
                    for cp, adv in dataset["advances"].items()}
    kern = {f"{left}/{right}": float(adj)
            for (left, right), adj in dataset["adjustments"].items()}
    return {"advances": advances, "kern": kern}


class GlyphFields:
    """Per-dataset oriented fields + notebook energies, cached per glyph."""

    def __init__(self, dataset):
        import numpy as np
        self._np = np
        self.dataset = dataset
        self.banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
        self.kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
        self.pad = int(mf.stage_pad_multiscale(mf.DEFAULT_PARAMS))
        self.fields = {}
        self.energies = {}

    def get(self, codepoint):
        hit = self.fields.get(codepoint)
        if hit is not None:
            return hit
        cell = self.dataset["cells"][codepoint]
        image = self._np.asarray(
            cell["cover"], dtype=self._np.float64).reshape(
            cell["height"], cell["width"])
        fields = mf.multiscale_glyph_fields(
            image, v1_banks=self.banks, kernels=self.kernels, pad=self.pad)
        self.fields[codepoint] = fields
        self.energies[codepoint] = sc.self_energy(fields, "notebook")
        return fields

    def energy(self, codepoint):
        self.get(codepoint)
        return self.energies[codepoint]


def slate_peak(fields, energy_vec):
    """Glyph context projection peak: max over channels/pixels of
    ``c/sqrt(E)`` (zero where E is zero/unsupported). Display
    calibration only; per-glyph fixed E, never per-frame autogain."""
    import numpy as np
    best = 0.0
    for channel in range(int(fields["supported"].shape[0])):
        energy = float(energy_vec[channel])
        if not math.isfinite(energy) or energy <= 0.0:
            continue
        sel = fields["supported"][channel]
        if not np.any(sel):
            continue
        peak = float(np.max(
            fields["confidence_notebook"][channel][sel] / math.sqrt(energy)))
        if peak > best:
            best = peak
    return best


def search_domain(dataset, left, right, pad):
    """Geometry-derived ordered-letter step domain for one pair.

    Returns ``(lo, hi)`` (both inclusive, ascending) or ``(None, reason)``.
    Lower bound ``max(floor(L1 - R2), 1)`` from delivered ink extents
    excludes the reversed-order component of the full padded interval
    (italic bearings included through the true origins), intersected with
    strictly forward pen order (LTR layout admissibility: step >= 1, so no
    gap moves the pen backward or leaves equal origins); upper bound is
    the last step whose padded field lattices still overlap in x, beyond
    which both-supported pixels are impossible. Blank sides and disjoint
    padded row bands yield no domain.
    """
    left_cell, right_cell = dataset["cells"][left], dataset["cells"][right]
    spans = {}
    for tag, cell in (("l", left_cell), ("r", right_cell)):
        ox = math.trunc(cell["left"])
        xs = [ox + col for row in range(cell["height"])
              for col in range(cell["width"])
              if cell["cover"][row * cell["width"] + col] > 0.0]
        if not xs:
            return None, "blank_glyph_no_ink"
        spans[tag] = (min(xs), max(xs))
    lo = max(math.floor(spans["l"][0] - spans["r"][1]), 1)
    lox = math.trunc(left_cell["left"] - pad)
    rox = math.trunc(right_cell["left"] - pad)
    loy = math.trunc(left_cell["top"] - pad)
    roy = math.trunc(right_cell["top"] - pad)
    left_w = left_cell["width"] + 2 * pad
    if loy + left_cell["height"] + 2 * pad <= roy or \
            roy + right_cell["height"] + 2 * pad <= loy:
        return None, "row_bands_disjoint"
    hi = lox + left_w - 1 - rox
    if hi < 1:
        return None, "no_forward_step"
    return (lo, hi), None


def score_steps(store, left, right, steps):
    """Exactly evaluated G2 curves over explicit integer steps.

    Shared scoring core behind the shipped domain curves and wider
    reference scans: one fixed union canvas covers exactly the given
    steps (embedding only, so shared-step G2 is canvas-invariant).
    Validity mirrors the engine: occupied-cell overlap invalidates with
    ``occupied_cell_overlap``; face/corner contact is allowed and
    counted; blank or support-empty steps score valid ``g2 = 0`` steps
    with abstain.
    """
    dataset = store.dataset
    metric = v1.metric_step(dataset, left, right)
    left_fields = store.get(left)
    right_fields = store.get(right)
    energy_left = store.energy(left)
    energy_right = store.energy(right)
    pad = store.pad
    origin_left = sc.glyph_padded_origin(dataset["cells"][left], pad)
    origin_right = sc.glyph_padded_origin(dataset["cells"][right], pad)
    right_origins = [(origin_right[0] + step, origin_right[1])
                     for step in steps]
    canvas_origin, canvas_shape = sc.union_canvas(
        left_fields["image_shape"], origin_left,
        right_fields["image_shape"], right_origins)
    geo = {"ok": [], "inter": [], "raw": [], "fsh": [], "rfsh": [],
           "both": [], "abst": [], "why": [], "fa": [], "co": []}
    for step, right_origin in zip(steps, right_origins):
        overlaps, faces, corners = v1.contact_counts(
            dataset["cells"][left], dataset["cells"][right], step)
        if overlaps > 0:
            geo["ok"].append(False)
            geo["inter"].append(None)
            geo["raw"].append(None)
            geo["fsh"].append(None)
            geo["rfsh"].append(None)
            geo["both"].append(0)
            geo["abst"].append(False)
            geo["why"].append("occupied_cell_overlap")
            geo["fa"].append(faces)
            geo["co"].append(corners)
            continue
        out = sc.score_step(left_fields, right_fields, origin_left,
                            right_origin, canvas_origin, canvas_shape,
                            energy_left, energy_right)
        geo["ok"].append(True)
        geo["inter"].append(float(out["g2"]))
        geo["raw"].append(float(out["raw"]))
        geo["fsh"].append(float(out["floor_share"]))
        geo["rfsh"].append(float(out["raw_floor_share"]))
        geo["both"].append(int(out["both_supported_pairpx"]))
        geo["abst"].append(bool(out["raw"] == 0.0
                               and out["both_supported_pairpx"] == 0))
        geo["why"].append(None)
        geo["fa"].append(faces)
        geo["co"].append(corners)
    return {"metric": metric, "steps": steps, "geo": geo}


def score_pair_curves(store, left, right):
    """Exactly evaluated G2 curves over the whole search domain."""
    dataset = store.dataset
    metric = v1.metric_step(dataset, left, right)
    bounds, reason = search_domain(dataset, left, right, store.pad)
    if bounds is None:
        steps = [metric]
    else:
        lo, hi = bounds
        steps = list(range(lo, hi + 1))
    table = score_steps(store, left, right, steps)
    search = {"policy": SEARCH_POLICY, "lo": bounds[0] if bounds else None,
              "hi": bounds[1] if bounds else None,
              "domain_reason": reason, "exhaustive": True}
    table["search"] = search
    return table


def derive_choice(table, cstar):
    """Browser-mirror TIE-v2 derivation from stored G2 curves.

    The minimizing set holds every supported (valid, non-abstained) step
    within ``m* + 1e-9*max(1, m*)``; the pick is the lowest step index
    (never metric-nearest). Abstained steps never win, even at target 0.
    With no supported step the metric (Source) is retained with a reason.
    Returns ``(chosen, detail)`` with minimizing set, fallback flag,
    reason, target-outside flag and the attainable G2 range.
    """
    geo = table["geo"]
    eligible = [bool(ok) and not abst and g2 is not None
                and math.isfinite(g2)
                for ok, abst, g2 in zip(geo["ok"], geo["abst"],
                                       geo["inter"])]
    deviations = [abs(g2 - cstar) if ok else None
                  for ok, g2 in zip(eligible, geo["inter"])]
    supported_g2 = [g2 for ok, g2 in zip(eligible, geo["inter"]) if ok]
    attainable = ([min(supported_g2), max(supported_g2)]
                  if supported_g2 else None)
    target_outside = (attainable is not None
                      and (cstar < attainable[0] or cstar > attainable[1]))
    chosen, members, fallback = vr.tie_pick(deviations, table["steps"],
                                            table["metric"])
    if not fallback:
        return chosen, {"minimizing": members, "fallback": False,
                        "reason": None, "target_outside": target_outside,
                        "attainable": attainable}
    search = table.get("search", {})
    if search.get("domain_reason") in ("blank_glyph_no_ink",
                                       "row_bands_disjoint",
                                       "no_forward_step"):
        reason = search["domain_reason"]
    elif any(geo["ok"]):
        reason = "no_shared_support"
    else:
        reason = "occupied_cell_overlap"
    return table["metric"], {"minimizing": [], "fallback": True,
                             "reason": reason,
                             "target_outside": target_outside,
                             "attainable": attainable}


def line_layouts(dataset, tables, text, cstar):
    """Per-line experiment and captured-source layouts (presentation stacking).

    The pitch is display-only leading shared by the Source and Adjusted
    views: a single general normal-preview factor of 1.25em rounded up,
    not scorer geometry and not per-font tuning. Experiment gaps resolve
    through TIE-v2 over the stored G2 curves at the given C*.
    """
    pitch = int(math.ceil(1.25 * dataset["size_px"]))
    experiment, captured = [], []
    for line in text.split("\n"):
        origins = [0]
        gaps = []
        for left, right in zip(line, line[1:]):
            if left == " " or right == " ":
                fixed = v1.metric_step(dataset, ord(left), ord(right))
                origins.append(origins[-1] + fixed)
                gaps.append({"pair": left + right, "metric": fixed,
                             "chosen": fixed, "space": True})
                continue
            table = tables[left + right]
            chosen, detail = derive_choice(table, cstar)
            origins.append(origins[-1] + chosen)
            gaps.append({"pair": left + right, "metric": table["metric"],
                         "chosen": chosen,
                         "fallback": detail["fallback"],
                         "fallback_reason": detail["reason"],
                         "target_outside": detail["target_outside"],
                         "space": False})
        baseline = v1.captured_source_word_origins(dataset, line)
        experiment.append({"origins": origins, "gaps": gaps})
        captured.append({"origins": baseline["origins"],
                         "draw_steps": [g["draw_step"]
                                        for g in baseline["gaps"]]})
    return pitch, experiment, captured


def default_setting():
    # Frozen G2-era seed (study value 4.0 with frozen geometry), kept
    # for the frozen oracle path only; the current build derives its
    # seed from vr.default_controls().
    return {"cstar": 4.0, "reach": 12, "falloff": 2.0}


def spot_choices(table, cstars):
    """Stored TIE-v2 choices over the C* spot grid (browser rechecks)."""
    return [derive_choice(table, float(cstar))[0] for cstar in cstars]


def parity_spots(dataset, store, tables, pair_names):
    """Pinned-pair exactness: fresh fields+score must reproduce stored G2.

    Rebuilds fields from the captures with a cold store and requires
    bitwise-equal G2/raw/shares/support counts for every pinned pair;
    any drift raises. Stored spot choices cover the C* sample grid by
    value, so the browser verifies shipped bytes without rescoring.
    The default setting is checked exhaustively for every pair through
    the same derivation the browser uses.
    """
    setting = default_setting()
    derived = {name: derive_choice(tables[name], setting["cstar"])
               for name in sorted(pair_names)}
    default_choices = {name: chosen for name, (chosen, _)
                       in derived.items()}
    default_detail = {name: detail for name, (_, detail)
                      in derived.items()}
    fresh = GlyphFields(dataset)
    compared = 0
    for name in [p for p in PINNED_PAIRS if p in tables]:
        left, right = ord(name[0]), ord(name[1])
        ref = score_pair_curves(fresh, left, right)
        stored = tables[name]
        assert ref["metric"] == stored["metric"], name
        assert ref["steps"] == stored["steps"], name
        assert ref["search"] == stored["search"], (name, "search identity")
        for key in ("inter", "raw", "fsh", "rfsh"):
            for have, want in zip(ref["geo"][key], stored["geo"][key]):
                assert (have is None and want is None) or have == want, \
                    (name, key, have, want)
        for key in ("ok", "both", "abst", "why", "fa", "co"):
            assert ref["geo"][key] == stored["geo"][key], (name, key)
        compared += 1
    pinned = {name: spot_choices(tables[name], CSTAR_SPOT_GRID)
              for name in PINNED_PAIRS if name in tables}
    return {"default_setting": setting, "default": default_choices,
            "default_detail": default_detail,
            "pinned": pinned, "pinned_checked": compared,
            "cstar_grid": list(CSTAR_SPOT_GRID)}


def load_case_dataset(case_id, profile, captures):
    path = captures / f"{case_id}-{profile}.json"
    if profile == "mono":
        dataset = v1.load_mono_capture(str(path))
    else:
        dataset = v1.load_gray_capture(str(path))
    dataset["label"] = f"{case_id}-{profile}"
    dataset["capture_path"] = str(path.relative_to(REPO))
    return dataset


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture_source_sha(relative):
    capture = json.loads((REPO / relative).read_text())
    if "source_sha256" in capture:
        return capture["source_sha256"]
    if isinstance(capture.get("font"), dict):
        return capture["font"].get("source_sha256", "")
    return ""


def build_case(entry, captures, cases_parent):
    """One catalogue case in both profiles with default-geometry G2 tables."""
    case_id = entry["id"]
    text = entry.get("text") or landing_generate.DEFAULT_TEXT
    font_path = (cases_parent / entry["font"]).resolve()
    if not font_path.is_file():
        raise ValueError(f"missing font for {case_id}: {font_path}")
    font_sha = sha_file(font_path)
    if entry.get("font_url"):
        if font_sha != entry["font_sha256"]:
            raise ValueError(f"pinned font identity mismatch for {case_id}")
    case = {"id": case_id, "family_id": entry["family_id"],
            "family_label": entry["family_label"],
            "size_px": entry["size_px"], "axes": entry["axes"],
            "font_file": font_path.name,
            "font_sha256": font_sha, "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "line_pitch": 0, "profiles": {}, "tables": {}}
    names = text_pairs(text) | {p for p in FIXED_PAIRS}
    seed = default_setting()["cstar"]
    for profile in ("mono", "gray"):
        dataset = load_case_dataset(case_id, profile, captures)
        # Provenance guard: the selected font must be the font the capture
        # was made from, before any geometry is built.
        source_sha = capture_source_sha(dataset["capture_path"])
        if not source_sha:
            raise ValueError(
                f"{case_id} {profile}: capture {dataset['capture_path']} "
                "is missing required source font identity")
        if source_sha != font_sha:
            raise ValueError(
                f"{case_id} {profile}: selected font {font_path.name} "
                f"({font_sha}) does not match capture source ({source_sha})")
        repertoire = set(dataset["cells"])
        missing = {c for c in text if c != "\n" and ord(c) not in repertoire}
        if missing:
            raise ValueError(
                f"{case_id} {profile}: sample text outside repertoire: "
                + " ".join(f"U+{ord(c):04X}" for c in sorted(missing)))
        pair_names = sorted(p for p in names
                            if ord(p[0]) in repertoire and ord(p[1]) in repertoire)
        label = f"{case_id}-{profile}"
        store = GlyphFields(dataset)
        started = time.time()
        tables = {}
        for name in pair_names:
            tables[name] = score_pair_curves(
                store, ord(name[0]), ord(name[1]))
        seconds = round(time.time() - started, 3)
        print(f"  {label}: {len(tables)} pairs in {seconds}s", flush=True)
        slate_peaks = {}
        for codepoint in sorted(dataset["cells"]):
            slate_peaks[str(codepoint)] = round(
                slate_peak(store.get(codepoint),
                           store.energy(codepoint)), 6)
        spot = parity_spots(dataset, store, tables, pair_names)
        packed = pack_glyphs(dataset)
        pitch, experiment, captured = line_layouts(
            dataset, tables, text, seed)
        space_metrics = {}
        for line in experiment:
            for gap in line["gaps"]:
                if gap.get("space"):
                    space_metrics[gap["pair"]] = gap["metric"]
        expected_space = {a + b for line in text.split("\n")
                          for a, b in zip(line, line[1:])
                          if a == " " or b == " "}
        if set(space_metrics) != expected_space:
            raise ValueError(
                f"{case_id} {profile}: space metrics incomplete: "
                f"{sorted(expected_space - set(space_metrics))}")
        case["line_pitch"] = pitch
        case["profiles"][profile] = {
            "label": dataset["label"], "capture": dataset["capture_path"],
            "capture_sha256": sha_file(REPO / dataset["capture_path"]),
            "source_sha256": capture_source_sha(dataset["capture_path"]),
            "glyphs": packed, "lines": text.split("\n"),
            "captured": captured,
            "preview": experiment,
            "space_metrics": space_metrics}
        metrics = pack_metrics(dataset)
        case["tables"][profile] = {
            "label": dataset["label"], "profile": profile,
            "size_px": dataset["size_px"],
            "geometry": {"reach": vr.DEFAULT_REACH,
                         "falloff": vr.DEFAULT_FALLOFF,
                         "tau": sc.TAU_PX, "strength": "notebook"},
            "search_policy": SEARCH_POLICY,
            "pairs": tables, "slate_peaks": slate_peaks, "spot": spot,
            "uncertainty": "uncertainty_not_certified",
            "advances": metrics["advances"], "kern": metrics["kern"],
            "seconds": seconds}
    return case


def transform_wasm_glue(source):
    """ESM wasm-bindgen glue to a classic script exposing window.YYWasmRT.

    The worker and the main-thread fallback run from Blob/classic
    scripts with no fetch: both instantiate from inlined bytes via
    ``initSync({module: bytes})``. Every ESM-only form must go: export
    keywords, the ``import.meta``-based default wasm URL (replaced with
    an explicit error; the fetch path is never used), while the
    ``initSync({module})`` bytes path stays byte-identical.
    """
    out = source.replace("export class YinYangEngine {",
                         "class YinYangEngine {")
    out = out.replace(
        "module_or_path = new URL('yinyang_oriented_engine_bg.wasm', import.meta.url);",
        "throw new Error('wasm fetch path disabled: pass {module} bytes to initSync');")
    out = out.replace("export { initSync, __wbg_init as default };",
                      "self.YYWasmRT = { initSync: initSync, "
                      "YinYangEngine: YinYangEngine };")
    if "import.meta" in out:
        raise ValueError("glue transform left import.meta behind")
    for token in ("\nimport ", "\nexport "):
        if token in out:
            raise ValueError(f"glue transform left ESM behind: {token!r}")
    if "self.YYWasmRT" not in out or "function initSync(module)" not in out:
        raise ValueError("glue transform lost the bytes init path")
    return out


def wasm_build_inputs():
    """Pinned browser runtime inputs: glue source, wasm bytes, versions."""
    glue_path = ENGINE / "pkg-web" / "yinyang_oriented_engine.js"
    wasm_path = ENGINE / "pkg-web" / "yinyang_oriented_engine_bg.wasm"
    glue = glue_path.read_text()
    wasm_bytes = wasm_path.read_bytes()
    pkg_version = ""
    for line in (ENGINE / "Cargo.toml").read_text().splitlines():
        if line.startswith("version"):
            pkg_version = line.split("=")[1].strip().strip('"')
            break
    return {"glue": transform_wasm_glue(glue),
            "glue_sha256": sha_file(glue_path),
            "wasm_bytes": wasm_bytes,
            "wasm_sha256": sha_file(wasm_path),
            "pkg_version": pkg_version}


# ---------------------------------------------------------------------------
# Current Class-L staging build path.
#
# Tables come from the pinned target-calibration Class-L curves
# (frozen default geometry, production runtime) after per-dataset
# identity/capture/domain/record-schema checks, with pinned pairs absent
# from the sample texts rescored through the same production runtime.
# The G2 oracle above stays frozen history; nothing here builds G2.
# ---------------------------------------------------------------------------

REPAIR = REPO / ("out/diagnostics/contextual-spacing/"
                 "yinyang-normalization-repair")
CURVES = REPAIR / "target-calibration/curves"
HELPER = HERE / "yinyang_classl_rescore.mjs"

# Explicit frozen build input: a source-site directory holding
# catalogue.json (cases, texts, packed glyphs, source advances/kerning,
# captures and font pins). Derived from captures plus the root catalogue
# plus fonts; generated pages are never build input. Pinned by hash;
# the staged freeze tests (not the builder) assert live pages unchanged.
SOURCE_FORMAT = "yinyangfit-interactive-v3-source-catalogue/1"
SOURCE_SITE = HERE / "yinyangfit_interactive_v3_source"
SOURCE_CATALOGUE_SHA = ("71e374ca218d75cf7657b7e008fc16f437165affe3ca27937330c8c"
                        "fb3a9a6ec")
DEFAULT_CAPTURES = (REPO / "out/diagnostics/contextual-spacing"
                    / "yinyangfit-interactive-v3/captures")
# Shipping production bytes the staged site embeds. Current runtime is
# the accepted wave-2 combination on the frozen model: FFT spectrum/scratch
# reuse within one glyph build (identical padded dimensions, plans,
# association, scaling and crop) plus the 256 MiB soft owned-payload
# target with 32-entry keep-floor and 512-entry ceiling (soft: the most
# recent 32 entries stay resident past the target; overshoot is reported,
# never hidden). Bit-identical fields/scores/maps/pixels; no model,
# setting, search, table or catalogue change.
# Adopted 2026-11-05: wave-2 C2 candidate (FFT reuse + cache policy).
SHIP_WASM_SHA = ("c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f"
                 "855")

SCORE_MODEL = vr.SCORE_MODEL
EXPECTED_ENGINE_VERSION = {
    "model": MODEL_IDENTITY,
    "score_model": SCORE_MODEL,
    "search": SEARCH_POLICY,
    "frozen_normalization_radius": 12,
}
TAU = 0.5
STRENGTH = "notebook"
NORM_RADIUS = 12
# Curve step-row columns, in order (see the curve exporter).
COL_STEP, COL_VALID, COL_GL, COL_BOTH, COL_WEAK, COL_ABST, COL_REASON, \
    COL_SKIP, COL_SHORT, COL_BOUND, COL_FACES, COL_CORNERS, \
    COL_MAXCOS = range(13)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def check(value, what):
    if not value:
        raise ValueError(f"staging refused: {what}")


def pixel_round(value):
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def metric_step(advances, kern, left, right):
    adv = advances[str(left)]
    adj = kern.get(f"{left}/{right}", 0.0)
    return pixel_round(adv + adj)


def run_node(args):
    proc = subprocess.run(["node", str(HELPER)] + args,
                          capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        raise ValueError(f"rescore helper failed ({args[0]}): "
                         f"{proc.stderr.strip()[:1500]}")
    return proc.stdout


def dump_source_catalogue(catalogue):
    """Canonical bytes for the frozen source catalogue (reproducible)."""
    return json.dumps(catalogue, sort_keys=True,
                      separators=(",", ":")) + "\n"


def build_source_catalogue(entries, captures, cases_parent):
    """Frozen build input from captures plus root catalogue plus fonts.

    Never reads generated pages: packed glyphs, source advances/kerning,
    captured-source layouts, space metrics, and capture/font pins derive
    from the capture files, the root catalogue entries, and the font
    bytes. Font/source-identity and repertoire guards mirror ``build_case``;
    space completeness is exact by construction (every space-adjacent
    pair of the sample text gets its source metric step).
    """
    cases = []
    for entry in entries:
        case_id = entry["id"]
        font_path = (cases_parent / entry["font"]).resolve()
        if not font_path.is_file():
            raise ValueError(f"missing font for {case_id}: {font_path}")
        font_sha = sha_file(font_path)
        text = entry.get("text") or landing_generate.DEFAULT_TEXT
        case = {"id": case_id, "family_id": entry["family_id"],
                "family_label": entry["family_label"],
                "size_px": entry["size_px"], "axes": entry["axes"],
                "font_file": font_path.name,
                "font_sha256": font_sha, "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "line_pitch": int(math.ceil(1.25 * entry["size_px"])),
                "profiles": {}}
        for profile in ("mono", "gray"):
            dataset = load_case_dataset(case_id, profile, captures)
            source_sha = capture_source_sha(dataset["capture_path"])
            if not source_sha:
                raise ValueError(
                    f"{case_id} {profile}: capture "
                    f"{dataset['capture_path']} is missing required "
                    "source font identity")
            if source_sha != font_sha:
                raise ValueError(
                    f"{case_id} {profile}: selected font {font_path.name} "
                    f"({font_sha}) does not match capture source "
                    f"({source_sha})")
            repertoire = set(dataset["cells"])
            missing = {c for c in text if c != "\n"
                       and ord(c) not in repertoire}
            if missing:
                raise ValueError(
                    f"{case_id} {profile}: sample text outside repertoire: "
                    + " ".join(f"U+{ord(c):04X}" for c in sorted(missing)))
            metrics = pack_metrics(dataset)
            expected_space = {a + b for line in text.split("\n")
                              for a, b in zip(line, line[1:])
                              if a == " " or b == " "}
            space_metrics = {}
            for pair in sorted(expected_space):
                space_metrics[pair] = metric_step(
                    metrics["advances"], metrics["kern"],
                    ord(pair[0]), ord(pair[1]))
            captured = []
            for line in text.split("\n"):
                baseline = v1.captured_source_word_origins(dataset, line)
                captured.append(
                    {"origins": baseline["origins"],
                     "draw_steps": [g["draw_step"]
                                    for g in baseline["gaps"]]})
            case["profiles"][profile] = {
                "label": dataset["label"],
                "capture": dataset["capture_path"],
                "capture_sha256": sha_file(REPO / dataset["capture_path"]),
                "source_sha256": source_sha,
                "glyphs": pack_glyphs(dataset),
                "lines": text.split("\n"),
                "captured": captured,
                "advances": metrics["advances"], "kern": metrics["kern"],
                "space_metrics": space_metrics}
        cases.append(case)
    return {
        "format": SOURCE_FORMAT,
        "root_catalogue": {
            "path": ("apps/web/scripts/landing-samples/main-page.json"),
            "sha256": sha_file(REPO / "apps/web/scripts/landing-samples"
                               / "main-page.json")},
        "landing_default_text_sha256": hashlib.sha256(
            landing_generate.DEFAULT_TEXT.encode()).hexdigest(),
        "cases": cases,
        "derived_by": ("yinyangfit_interactive_v3.py "
                       "--write-source-catalogue: captures plus root "
                       "catalogue plus fonts; no generated-page reads")}


def curve_geo(rows):
    """Staged table entry arrays from calibration-curve step rows."""
    geo = {"ok": [], "gl": [], "both": [], "abst": [], "why": [],
           "areason": [], "weak": [], "skip": [], "short": [],
           "bound": [], "fa": [], "co": []}
    for row in rows:
        valid = bool(row[COL_VALID])
        geo["ok"].append(valid)
        geo["gl"].append(float(row[COL_GL]) if valid else None)
        geo["both"].append(int(row[COL_BOTH]))
        abst = bool(row[COL_ABST])
        geo["abst"].append(abst)
        geo["why"].append(None if valid else "occupied_cell_overlap")
        geo["areason"].append(row[COL_REASON] if abst else None)
        geo["weak"].append(row[COL_WEAK] if valid else None)
        geo["skip"].append(int(row[COL_SKIP]))
        geo["short"].append(float(row[COL_SHORT]))
        geo["bound"].append(row[COL_BOUND] if valid else None)
        geo["fa"].append(int(row[COL_FACES]))
        geo["co"].append(int(row[COL_CORNERS]))
    return geo


def derive_choice_classl(table, target):
    """Browser-mirror TIE-v2 derivation from stored Class-L curves.

    The minimizing set holds every supported (valid, non-abstained)
    step within ``m* + 1e-9*max(1, m*)``; the pick is the lowest step
    index (never metric-nearest). Abstained steps never win, even at
    target 0. With no supported step the metric (Source) is retained
    with a reason. Returns ``(chosen, detail)`` with minimizing set,
    fallback flag, reason, target-outside flag and the attainable
    Class-L range.
    """
    geo, steps = table["geo"], table["steps"]
    eligible = [bool(ok) and not abst and gl is not None
                and math.isfinite(gl)
                for ok, abst, gl in zip(geo["ok"], geo["abst"],
                                       geo["gl"])]
    deviations = [abs(gl - target) if ok else None
                  for ok, gl in zip(eligible, geo["gl"])]
    supported = [gl for ok, gl in zip(eligible, geo["gl"]) if ok]
    attainable = ([min(supported), max(supported)]
                  if supported else None)
    outside = (attainable is not None
               and (target < attainable[0] or target > attainable[1]))
    chosen, members, fallback = vr.tie_pick(
        deviations, steps, table["metric"])
    if not fallback:
        return chosen, {"minimizing": members, "fallback": False,
                        "reason": None, "target_outside": outside,
                        "attainable": attainable}
    search = table.get("search", {})
    if search.get("domain_reason") in ("blank_glyph_no_ink",
                                       "row_bands_disjoint",
                                       "no_forward_step"):
        reason = search["domain_reason"]
    elif any(geo["ok"]):
        # The pair has valid steps but no eligible (non-abstained)
        # score: distinct from the engine abstain reasons.
        reason = "no_supported_score"
    else:
        reason = "occupied_cell_overlap"
    return table["metric"], {"minimizing": [], "fallback": True,
                             "reason": reason, "target_outside": outside,
                             "attainable": attainable}


def line_layouts_classl(tables, text, target, space_metrics):
    """Per-line experiment layout over stored Class-L curves.

    Experiment gaps resolve through TIE-v2 at the given target; space
    gaps keep their source metric advance exactly (no ink on one side
    to score), verified complete against the text by the caller.
    """
    experiment = []
    for line in text.split("\n"):
        origins = [0]
        gaps = []
        for left, right in zip(line, line[1:]):
            if left == " " or right == " ":
                fixed = space_metrics.get(left + right)
                if fixed is None:
                    raise ValueError("space metrics incomplete")
                origins.append(origins[-1] + fixed)
                gaps.append({"pair": left + right, "metric": fixed,
                             "chosen": fixed, "space": True})
                continue
            table = tables[left + right]
            chosen, detail = derive_choice_classl(table, target)
            origins.append(origins[-1] + chosen)
            gaps.append({"pair": left + right, "metric": table["metric"],
                         "chosen": chosen,
                         "fallback": detail["fallback"],
                         "fallback_reason": detail["reason"],
                         "target_outside": detail["target_outside"],
                         "space": False})
        experiment.append({"origins": origins, "gaps": gaps})
    return experiment


def build_dataset_tables(catalogue, catalogue_path, label, case_id,
                         profile, work):
    """Class-L table for one dataset: curves + rescored pinned pairs."""
    t0 = time.time()
    curve_path = CURVES / f"{label}.json"
    check(curve_path.is_file(), f"missing curve file for {label}")
    curve = json.loads(curve_path.read_text())
    check(curve.get("normalization_radius") == NORM_RADIUS,
          f"{label}: normalizer drift")
    check(abs(curve.get("tau", -1) - TAU) < 1e-12, f"{label}: tau drift")
    check(curve.get("strength") == STRENGTH, f"{label}: strength drift")
    check(curve.get("gray", None) == (profile == "gray"),
          f"{label}: profile drift")
    version = curve.get("engine_version", {})
    for key, want in EXPECTED_ENGINE_VERSION.items():
        check(version.get(key) == want,
              f"{label}: engine identity drift ({key})")
    check(version.get("params", {}).get("q") == 2.0 and
          version.get("params", {}).get("radius") == 12,
          f"{label}: frozen geometry drift")
    check(version.get("params_hash") == "0011825cbfb05845",
          f"{label}: params hash drift")
    prof = next(c for c in catalogue["cases"]
                if c["id"] == case_id)["profiles"][profile]
    check(curve.get("capture_sha256") == prof["capture_sha256"],
          f"{label}: capture drift")
    domain_out = run_node(["domains", str(catalogue_path),
                           str(curve_path)])
    domain_check = json.loads(domain_out)
    check(not domain_check["mismatched"], f"{label}: domain mismatch")
    pairs = dict(curve["pairs"])
    reused = sorted(pairs)
    names = set()
    for line in prof["lines"]:
        for a, b in zip(line, line[1:]):
            if a != " " and b != " ":
                names.add(a + b)
    repertoire = {int(cp) for cp in prof["glyphs"]}
    for fixed in PINNED_PAIRS:
        if ord(fixed[0]) in repertoire and ord(fixed[1]) in repertoire:
            names.add(fixed)
    missing = sorted(n for n in names if n not in pairs)
    recomputed = []
    if missing:
        want = {}
        advances = prof["advances"]
        kern = prof.get("kern", {})
        for name in missing:
            step = metric_step(advances, kern, ord(name[0]),
                               ord(name[1]))
            want[name] = {"metric": step}
        tmp = work / f"want-{label}.json"
        tmp.write_text(json.dumps(want))
        scored = json.loads(run_node(
            ["rescore", str(catalogue_path), case_id, profile,
             str(tmp), str(work / f"rescored-{label}.json")]))
        check(scored["pairs"] == len(missing),
              f"{label}: rescore shortfall")
        fresh = json.loads(
            (work / f"rescored-{label}.json").read_text())
        for name, rec in fresh.items():
            if rec.get("metric_source") == "preview":
                rec["metric_source"] = "metric_step"
            pairs[name] = rec
            recomputed.append(name)
        tmp.unlink()
    peaks_out = run_node(["peaks", str(catalogue_path), case_id,
                          profile, str(work / f"peaks-{label}.json"),
                          "slate"])
    peaks = json.loads(
        (work / f"peaks-{label}.json").read_text())
    check(json.loads(peaks_out)["codepoints"] == len(prof["glyphs"]),
          f"{label}: peak coverage")
    tables = {}
    for name in sorted(names):
        rec = pairs[name]
        if rec.get("lo") is None:
            steps = [rec["metric"]]
            rows = rec["steps"]
            search = {"policy": SEARCH_POLICY, "lo": None, "hi": None,
                      "domain_reason": rec.get("domain_reason",
                                               "no_forward_step"),
                      "exhaustive": True}
        else:
            steps = list(range(rec["lo"], rec["hi"] + 1))
            rows = rec["steps"]
            check([r[COL_STEP] for r in rows] == steps,
                  f"{label} {name}: step window mismatch")
            search = {"policy": SEARCH_POLICY, "lo": rec["lo"],
                      "hi": rec["hi"], "domain_reason": None,
                      "exhaustive": True}
        tables[name] = {"metric": rec["metric"], "steps": steps,
                        "search": search, "geo": curve_geo(rows),
                        "metric_source": rec.get("metric_source")}
    seconds = round(time.time() - t0, 3)
    return {"tables": tables, "reused": reused, "recomputed": recomputed,
            "peaks": {cp: info["peak"] for cp, info in peaks.items()},
            "seconds": seconds}


def spot_checks(tables, default_target):
    """Default choices plus pinned pairs over the staged spot grid."""
    derived = {name: derive_choice_classl(table, default_target)
               for name, table in tables.items()}
    pinned = {name: [derive_choice_classl(tables[name], float(target))[0]
                     for target in vr.TARGET_SPOT_GRID]
              for name in PINNED_PAIRS if name in tables}
    return {"default_target": default_target,
            "default": {name: chosen for name, (chosen, _)
                        in derived.items()},
            "default_detail": {name: detail for name, (_, detail)
                               in derived.items()},
            "pinned": pinned,
            "target_grid": list(vr.TARGET_SPOT_GRID)}


def verify_case_fonts(case, font_relpath, cases_parent):
    """Font/source/capture guard for the staging path: the selected font
    file must hash to the catalogue pin, every capture file must hash to
    its recorded capture pin, and every capture must record that same
    source hash. Mirrors the frozen ``build_case`` guard without
    rebuilding geometry from captures.
    """
    candidates = sorted((REPO / "fonts").glob(case["font_file"]))
    if font_relpath:
        candidates.append((cases_parent / font_relpath).resolve())
    font_path = next((p for p in candidates if p.is_file()), None)
    if font_path is None:
        raise ValueError(f"missing font for {case['id']}")
    font_sha = sha_file(font_path)
    if font_sha != case["font_sha256"]:
        raise ValueError(f"pinned font identity mismatch for {case['id']}")
    for profile in ("mono", "gray"):
        prof = case["profiles"][profile]
        if sha_file(REPO / prof["capture"]) != prof["capture_sha256"]:
            raise ValueError(
                f"{case['id']} {profile}: capture content "
                f"({prof['capture']}) does not match recorded "
                "capture_sha256")
        if prof.get("source_sha256") != font_sha:
            raise ValueError(
                f"{case['id']} {profile}: capture source "
                f"({prof.get('source_sha256')}) does not match selected "
                f"font {font_path.name} ({font_sha})")


def provenance_text(manifest):
    lines = [
        "# Class-L staging provenance",
        "",
        "Staged integration of the YinYang normalization repair:",
        "default Class-L curves at the frozen geometry with the staged",
        "navigation settings. Not adoption: the live reviewed site is",
        "untouched and this output is for independent staged review only.",
        "",
        "## Identities",
        "",
        f"- model: {manifest['model']}",
        f"- score_model: {manifest['score_model']}",
        f"- search: {SEARCH_POLICY}",
        f"- settings: {manifest['settings_version']}",
        f"- wasm: {manifest['implementation']['wasm_sha256']}",
        f"- glue: {manifest['implementation']['glue_sha256']}",
        "",
        "## Source catalogue (frozen build input)",
        "",
        (f"- source catalogue `{manifest['source']['catalogue']}` "
         f"({manifest['source']['catalogue_sha256']}, "
         f"{manifest['source']['format']}): cases, texts, packed glyphs, "
         "source advances/kerning, captures and font pins, derived from "
         "captures plus the root catalogue plus fonts "
         "(`yinyangfit_interactive_v3.py --write-source-catalogue`); "
         "generated pages are never build input. Font bytes, capture "
         "bytes, and capture source hashes re-verified per case."),
        "",
        "## Table sources",
        "",
        ("- Default-geometry Class-L curves reused from "
         "target-calibration/curves/ after per-dataset checks: score "
         "identity, frozen normalizer 12, tau 0.5, notebook strength, "
         "frozen R12/q2 params hash, capture SHA match, and full "
         "pair-domain re-verification against the shipping engine."),
        ("- Pinned pairs absent from the sample texts rescored through "
         "the shipping production runtime (node rescore helper, "
         "`score_pair_local`, frozen normalizer 12):"),
    ]
    for entry in manifest["pairs_recomputed"]:
        lines.append(f"  - {entry['dataset']}: "
                     f"{', '.join(entry['pairs'])} "
                     "(metric_source metric_step)")
    lines += [
        ("- slate letter-context peaks through the shipping runtime "
         "(`glyph_component` slate per codepoint, per dataset)."),
        ("- Only the preview (choices at the staged default) is "
         "derived here; every other catalogue field arrives pinned "
         "from the source catalogue above."),
        "",
        "## Curve pins reused",
        "",
    ]
    for label in sorted(manifest["curves_reused"]):
        rec = manifest["curves_reused"][label]
        lines.append(f"- {rec['curve']}: {rec['sha256']} "
                     f"({rec['reused_pairs']} pairs)")
    lines += [
        "",
        "## Navigation settings (staged)",
        "",
        ("- Interaction target slider 0..20 step 0.02 (navigation "
         "precision only), initial/reset 8.0; exact finite >= 0 "
         "accepted, no clamp, no snap; overflow/non-finite/negative "
         "rejected; zero usable exact."),
        ("- Reach slider 4..24 integer, exact 1..32; falloff slider "
         "0.5..10 step 0.5, exact 0.25..16."),
        "- Normalizer frozen at 12, never user-controlled.",
    ]
    return "\n".join(lines) + "\n"


def assemble_page(template, app_js, wiring_js, worker_js, visual_js,
                  coupling_js, wasmx, payload):
    """Single-file page from owner sources plus a compact boot payload.

    Shared by full builds and `--rebundle`: same guards, same
    replacements, so a rebundle with unchanged sources reproduces the
    built bytes exactly. No scores, tables, or captures are touched.
    """
    for name, content in (("template", template), ("app", app_js),
                          ("wiring", wiring_js), ("worker", worker_js),
                          ("visual", visual_js), ("coupling", coupling_js),
                          ("glue", wasmx["glue"])):
        if "title=" in content.replace("aria-", ""):
            raise ValueError(f"native title tooltips forbidden ({name})")
    for name, content in (("wiring", wiring_js), ("worker", worker_js),
                          ("visual", visual_js), ("coupling", coupling_js),
                          ("glue", wasmx["glue"])):
        if "</script" in content:
            raise ValueError(f"raw script terminator in {name}")
    for placeholder in ("__YY_BOOT__", "__YY_APP_JS__", "__YY_WIRING_JS__",
                        "__YY_WASM_GLUE__", "__YY_WORKER_SRC__",
                        "__YY_WASM_B64__", "__YY_VISUAL_JS__",
                        "__YY_COUPLING_JS__"):
        if placeholder not in template:
            raise ValueError(f"template placeholder missing: {placeholder}")
    for stale in ("__YY_COMPUTE_JS__", "__YY_COMPUTE_SRC__",
                  "YYCompute", "yinyangfit_interactive_b2"):
        if stale in template or stale in wiring_js:
            raise ValueError(f"old-model residue forbidden: {stale}")
    for name, content in (("wiring", wiring_js), ("worker", worker_js),
                          ("app", app_js), ("coupling", coupling_js),
                          ("visual", visual_js)):
        # `("slate", 0, 0)` pins the old single-kind G2 accessor shape;
        # the Class-L `glyph_component(..., "slate", 0, 0)` kind argument
        # stays allowed (display projection from the shipping runtime).
        for stale in ("score_pair(", "contribution_map(",
                      "entry.inter", ".formatG2(", '("slate", 0, 0'):
            if stale in content:
                raise ValueError(f"G2 residue forbidden "
                                 f"({name}: {stale})")
    page = template.replace("__YY_BOOT__", payload)
    page = page.replace("__YY_APP_JS__", app_js)
    page = page.replace("__YY_VISUAL_JS__", visual_js)
    page = page.replace("__YY_COUPLING_JS__", coupling_js)
    page = page.replace("__YY_WIRING_JS__", wiring_js)
    page = page.replace("__YY_WASM_GLUE__", wasmx["glue"])
    worker_src = worker_js.replace("__YY_WASM_GLUE__", wasmx["glue"])
    if "__YY_WASM_GLUE__" in worker_src:
        raise ValueError("worker glue placeholder unfilled")
    page = page.replace("__YY_WORKER_SRC__", worker_src)
    page = page.replace("__YY_WASM_B64__",
                        base64.b64encode(wasmx["wasm_bytes"]).decode())
    return page


def rebundle_page(main_dir):
    """Re-embed owner sources into an existing main page, no rescoring.

    Reads ``boot.json`` (identity-checked) and rewrites ``index.html``
    through the shared ``assemble_page`` path, then refreshes the
    manifest ``page_bytes``. Boot, tables, captures, and WASM bytes are
    never modified; a foreign boot identity is refused.
    """
    boot = json.loads((main_dir / "boot.json").read_text())
    check(boot.get("model") == MODEL_IDENTITY, "foreign boot model")
    check(boot.get("score_model") == SCORE_MODEL,
          "foreign boot score model")
    check(boot.get("search_policy") == SEARCH_POLICY,
          "foreign boot search policy")
    check(boot.get("settings_version") == vr.RANGES_VERSION,
          "foreign boot settings")
    check(boot["implementation"]["wasm_sha256"] == SHIP_WASM_SHA,
          "foreign boot engine bytes")
    wasmx = wasm_build_inputs()
    check(wasmx["wasm_sha256"] == SHIP_WASM_SHA, "shipping wasm moved")
    root = HERE
    page = assemble_page(
        (root / "yinyangfit_interactive_v3_template.html").read_text(),
        (root / "yinyangfit_interactive_v3_app.js").read_text(),
        (root / "yinyangfit_interactive_v3_wiring.js").read_text(),
        (root / "yinyangfit_interactive_v3_worker.js").read_text(),
        (root / "yinyangfit_interactive_v3_visual.js").read_text(),
        (root / "yinyangfit_interactive_v3_coupling.js").read_text(),
        wasmx,
        json.dumps(boot, separators=(",", ":"), allow_nan=False))
    (main_dir / "index.html").write_text(page)
    manifest_path = main_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["page_bytes"] = len(page.encode())
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"index.html": sha_bytes(page.encode()),
                      "page_bytes": manifest["page_bytes"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?",
                        help="new output directory (required unless "
                             "--write-source-catalogue)")
    parser.add_argument("--cases", type=Path,
                        default=REPO / "apps/web/scripts/landing-samples"
                        / "main-page.json")
    parser.add_argument("--only", action="append", default=None,
                        help="restrict to these case ids (debugging)")
    parser.add_argument("--source-site", type=Path, default=SOURCE_SITE,
                        help="explicit frozen source-catalogue input "
                             "directory (catalogue.json); generated pages "
                             "are never build input")
    parser.add_argument("--captures", type=Path, default=DEFAULT_CAPTURES,
                        help="capture inputs for --write-source-catalogue")
    parser.add_argument("--write-source-catalogue", type=Path, default=None,
                        metavar="PATH",
                        help="derive the frozen source catalogue from "
                             "captures plus root catalogue plus fonts, "
                             "write it to PATH, and exit")
    parser.add_argument("--rebundle", type=Path, default=None,
                        metavar="MAIN_DIR",
                        help="re-embed owner sources into MAIN_DIR/index.html "
                             "from its boot.json without rescoring; refresh "
                             "manifest page_bytes, then exit")
    args = parser.parse_args()
    if args.rebundle is not None:
        rebundle_page(args.rebundle)
        return
    cases_parent = args.cases.parent
    entries = json.loads(args.cases.read_text())
    if len(entries) != 13:
        raise ValueError("root catalogue must hold all 13 cases")
    if args.write_source_catalogue:
        if args.write_source_catalogue.exists():
            parser.error("--write-source-catalogue target must be new")
        catalogue = build_source_catalogue(entries, args.captures,
                                           cases_parent)
        args.write_source_catalogue.write_text(
            dump_source_catalogue(catalogue))
        print(json.dumps(
            {"catalogue": str(args.write_source_catalogue),
             "sha256": sha_bytes(
                 dump_source_catalogue(catalogue).encode()),
             "cases": len(catalogue["cases"])}))
        return
    if args.output is None:
        parser.error("output is required without --write-source-catalogue")
    if args.output.exists():
        parser.error("output must be new")
    source_cat_path = args.source_site / "catalogue.json"
    check(source_cat_path.is_file(),
          "missing source catalogue (see --write-source-catalogue)")
    source_text = source_cat_path.read_text()
    check(sha_bytes(source_text.encode()) == SOURCE_CATALOGUE_SHA,
          "source catalogue moved; regenerate with "
          "--write-source-catalogue")
    source = json.loads(source_text)
    check(source.get("format") == SOURCE_FORMAT,
          "source catalogue format drift")
    check(len(source["cases"]) == 13, "catalogue must hold 13 cases")
    if args.only:
        source["cases"] = [c for c in source["cases"]
                           if c["id"] in args.only]
        if not source["cases"]:
            raise ValueError("no catalogue entries match --only")
    wasmx = wasm_build_inputs()
    check(wasmx["wasm_sha256"] == SHIP_WASM_SHA, "shipping wasm moved")
    check(wasmx["pkg_version"] == "0.0.0", "engine pkg drift")
    fontmap = {e["id"]: e.get("font") for e in entries}
    out = args.output
    work = out / "recompute"
    work.mkdir(parents=True, exist_ok=False)
    default = vr.default_controls()
    boot = {"model": MODEL_IDENTITY,
            "score_model": SCORE_MODEL,
            "search_policy": SEARCH_POLICY,
            "settings_version": vr.RANGES_VERSION,
            "implementation": {
                "engine_pkg": wasmx["pkg_version"],
                "wasm_sha256": wasmx["wasm_sha256"],
                "glue_sha256": wasmx["glue_sha256"],
                "settings_version": vr.RANGES_VERSION},
            "controls": {"target": list(vr.TARGETS),
                         "reach": list(vr.REACHES),
                         "falloff": list(vr.FALLOFFS),
                         "default": default},
            "numeric": {"target": [vr.TARGET_MIN, None],
                        "reach": list(vr.REACH_BOUNDS),
                        "falloff": list(vr.FALLOFF_BOUNDS)},
            "fast_geometry": {"reach": vr.FAST_GEOMETRY[0],
                              "falloff": vr.FAST_GEOMETRY[1]},
            "gains": {"slate": SLATE_GAIN, "contrib": CONTRIB_GAIN},
            "default_setting": default, "cases": []}
    tables_out = {}
    reuse_index, recompute_index = {}, []
    peak_lo, peak_hi = math.inf, 0.0
    for case in source["cases"]:
        verify_case_fonts(case, fontmap.get(case["id"]), cases_parent)
        staged = {"id": case["id"],
                  "family_id": case["family_id"],
                  "family_label": case["family_label"],
                  "size_px": case["size_px"], "axes": case["axes"],
                  "font_file": case["font_file"],
                  "font_sha256": case["font_sha256"],
                  "text": case["text"],
                  "text_sha256": case["text_sha256"],
                  "line_pitch": case["line_pitch"], "profiles": {}}
        for profile in ("mono", "gray"):
            label = f"{case['id']}-{profile}"
            src_prof = case["profiles"][profile]
            built = build_dataset_tables(source, source_cat_path, label,
                                         case["id"], profile, work)
            reuse_index[label] = {"curve": (CURVES / f"{label}.json").name,
                                  "sha256": sha_file(CURVES /
                                                     f"{label}.json"),
                                  "reused_pairs": len(built["reused"])}
            if built["recomputed"]:
                recompute_index.append(
                    {"dataset": label,
                     "pairs": sorted(built["recomputed"])})
            for peak in built["peaks"].values():
                peak_lo = min(peak_lo, peak)
                peak_hi = max(peak_hi, peak)
            experiment = line_layouts_classl(
                built["tables"], case["text"], default["target"],
                src_prof["space_metrics"])
            staged["profiles"][profile] = {
                "label": src_prof["label"],
                "capture": src_prof["capture"],
                "capture_sha256": src_prof["capture_sha256"],
                "source_sha256": src_prof["source_sha256"],
                "glyphs": src_prof["glyphs"], "lines": src_prof["lines"],
                "captured": src_prof["captured"],
                "preview": experiment,
                "space_metrics": src_prof["space_metrics"]}
            table = {
                "label": label, "profile": profile,
                "size_px": case["size_px"],
                "geometry": {"reach": 12, "falloff": 2.0, "tau": TAU,
                             "strength": STRENGTH,
                             "normalization_radius": NORM_RADIUS},
                "score_model": SCORE_MODEL,
                "search_policy": SEARCH_POLICY,
                "pairs": {name: {k: rec[k] for k in
                                 ("metric", "steps", "search", "geo")}
                          for name, rec in built["tables"].items()},
                "pair_metric_source": {
                    name: rec.get("metric_source", "preview")
                    for name, rec in built["tables"].items()},
                "slate_peaks": built["peaks"],
                "spot": spot_checks(built["tables"], default["target"]),
                "uncertainty": "uncertainty_not_certified",
                "advances": src_prof["advances"],
                "kern": src_prof.get("kern", {}),
                "seconds": built["seconds"]}
            tables_out[label] = table
            print(f"  {label}: {len(table['pairs'])} pairs "
                  f"({len(built['recomputed'])} rescored) "
                  f"in {built['seconds']}s", flush=True)
        boot["cases"].append(staged)
    root = HERE
    template = (root / "yinyangfit_interactive_v3_template.html"
                ).read_text()
    app_js = (root / "yinyangfit_interactive_v3_app.js").read_text()
    wiring_js = (root / "yinyangfit_interactive_v3_wiring.js"
                 ).read_text()
    worker_js = (root / "yinyangfit_interactive_v3_worker.js"
                 ).read_text()
    visual_js = (root / "yinyangfit_interactive_v3_visual.js"
                 ).read_text()
    coupling_js = (root / "yinyangfit_interactive_v3_coupling.js"
                   ).read_text()
    payload = json.dumps(boot, separators=(",", ":"), allow_nan=False)
    page = assemble_page(template, app_js, wiring_js, worker_js,
                         visual_js, coupling_js, wasmx, payload)
    (out / "index.html").write_text(page)
    data_dir = out / "data"
    data_dir.mkdir()
    for label, table in tables_out.items():
        (data_dir / f"{label}.js").write_text(
            "window.YY_TABLES = window.YY_TABLES || {};\n"
            f"window.YY_TABLES[{label!r}] = "
            + json.dumps(table, separators=(",", ":"), allow_nan=False)
            + ";\n")
    boot_path = out / "boot.json"
    boot_path.write_text(json.dumps(boot, indent=2) + "\n")
    manifest = {"model": boot["model"], "score_model": boot["score_model"],
                "implementation": boot["implementation"],
                "settings_version": vr.RANGES_VERSION,
                "cases": [c["id"] for c in boot["cases"]],
                "datasets": sorted(tables_out),
                "slider_stops": {"target": len(vr.TARGETS),
                                 "reach": len(vr.REACHES),
                                 "falloff": len(vr.FALLOFFS)},
                "numeric": boot["numeric"],
                "fast_geometry": boot["fast_geometry"],
                "gains": boot["gains"],
                "slate_peak_range": [peak_lo, peak_hi],
                "curves_reused": reuse_index,
                "pairs_recomputed": recompute_index,
                "source": {"catalogue": "catalogue.json",
                           "catalogue_sha256": sha_bytes(
                               source_text.encode()),
                           "format": SOURCE_FORMAT},
                "table_pairs": sum(len(t["pairs"]) for t in
                                   tables_out.values()),
                "page_bytes": len(page.encode())}
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    inputs = out / "build-inputs"
    inputs.mkdir()
    for name in ("yinyangfit_interactive_v3_ranges.py",
                 "yinyangfit_interactive_v3.py",
                 "yinyang_classl_rescore.mjs",
                 "yinyangfit_interactive_v3_template.html",
                 "yinyangfit_interactive_v3_app.js",
                 "yinyangfit_interactive_v3_wiring.js",
                 "yinyangfit_interactive_v3_worker.js",
                 "yinyangfit_interactive_v3_visual.js",
                 "yinyangfit_interactive_v3_coupling.js"):
        (inputs / name).write_text((root / name).read_text())
    (out / "PROVENANCE.md").write_text(provenance_text(manifest))
    print(json.dumps({k: manifest[k] for k in
                      ("score_model", "settings_version", "table_pairs",
                       "slate_peak_range")}))


if __name__ == "__main__":
    main()
