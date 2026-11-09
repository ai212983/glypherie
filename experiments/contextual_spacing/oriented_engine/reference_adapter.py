#!/usr/bin/env python3
"""Separate reference harness for the Rust oriented-engine parity work.

Imports the frozen YinYang modules read-only (never modifies them) and dumps
a self-contained JSON corpus: exact capture covers, metric steps, expected
narrow-delta SCORE-v2 values, tau variants, manuscript ablation, validity,
plus custom-q/custom-R stage-1 references (defaults untouched) and novel
pairs over the 13 v3 mono captures for the TRUE-workload bench.

Output directory must be new. Frozen leaves (score-experiment-corrected,
oracles, reference-review) are only read, never rewritten.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyangfit_interactive as v1
import yinyang_oriented_score_evidence as ev

FOCUS = ["um", "og", "AV", "To"]
HELDOUT = ["nn", "oo", "HH", "il"]
NOVEL = ["ef", "ff", "ya", "ri", "ac", "Gu"]
DELTAS = (-2, -1, 0, 1, 2)
# Stratified config axes (not full Cartesian): R varies at frozen q, q varies
# at frozen R. R is the square kernel half-width ([-R, R]^2 taps, no circular
# crop); q is real precision, R integer.
R_AXIS = [4, 6, 12, 18, 24, 32]
Q_AXIS = [0.5, 1.0, 2.0, 3.0, 4.0, 10.0, 16.0]
AXES_PAIRS = {"roboto-16-mono": ["um", "og", "ef", "ya"],
              "roboto-16-gray": ["um", "og"]}
V3_MONO_CASES = ["roboto-8", "roboto-12", "roboto-16", "roboto-20",
                 "literata-8", "literata-12", "literata-16", "literata-20",
                 "roboto-italic-8", "roboto-italic-12", "roboto-italic-16",
                 "roboto-italic-20", "rouge-script-20"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def multiscale_glyph_fields_custom(image, s1params, weights, v1_banks,
                                   kernels, pad):
    """Stage-2 pipeline with q/R threaded through kernels, strength and pad.

    Same arithmetic as the frozen stage-2 module, except the radial exponent,
    denominator floor and pad come from ``s1params`` instead of the frozen
    stage-1 defaults. Verified at the default point against the frozen module
    (see adapter main: exact match required before any axis point runs).
    """
    import numpy as np
    import yinyang_oriented_fields as yf
    import yinyang_multiscale_fields as mf
    image = np.asarray(image, dtype=np.float64)
    weights = mf._validate_weights(weights)
    conv = yf.convolve_fft
    padded = np.pad(image, pad, mode="constant") if pad else image
    c_per_scale = []
    for bank in v1_banks:
        c_per_scale.append(np.abs(np.asarray(
            [conv(padded, g) for g in bank])))
    c_per_scale = np.asarray(c_per_scale)
    t_combined = mf.combine_scales(c_per_scale, weights)
    n_v1 = len(v1_banks[0])
    n_dir = int(s1params.n_directed)
    t = np.asarray([t_combined[o % n_v1] for o in range(n_dir)])
    h1, h2, mass1, mass2 = kernels
    u1 = np.asarray([conv(np.maximum(t[o], 0.0), h1[o])
                     for o in range(n_dir)])
    u2 = np.asarray([conv(np.maximum(t[o], 0.0), h2[o])
                     for o in range(n_dir)])
    u1 = np.maximum(u1, 0.0)
    u2 = np.maximum(u2, 0.0)
    q = float(s1params.radial_exponent_q)
    eps = float(s1params.denominator_eps)
    supported = np.isfinite(u1) & np.isfinite(u2) & (u2 > eps)
    distance = np.full_like(u1, np.nan)
    distance[supported] = u1[supported] / u2[supported]
    arc_strength = np.zeros_like(u1)
    arc_strength[supported] = u1[supported] * distance[supported] ** (q + 1.0)
    confidence_notebook = np.zeros_like(u1)
    confidence_notebook[supported] = (
        u1[supported] * distance[supported] ** (q - 1.0))
    return {
        "T_combined": t_combined,
        "U1": u1, "U2": u2, "distance": distance,
        "arc_strength": arc_strength,
        "confidence_notebook": confidence_notebook,
        "supported": supported,
        "params_q": q, "params_eps": eps, "pad": pad,
        "image_shape": padded.shape,
    }


def contribution_map(lf, rf, lo, ro, canvas_origin, canvas_shape, EL, ER,
                     tau, strength="notebook"):
    """Exact normalized per-pixel G2 summands (sums to the step G2).

    Independent vectorized re-derivation of the score formula for the
    adapter reference map: ``sum_{a,b} F cL cR kval/sqrt(EL ER)`` over
    both-supported pixels, zero elsewhere.
    """
    import numpy as np
    import yinyang_oriented_score as sc
    field = sc.resolve_strength(strength)
    n = int(lf["supported"].shape[0])
    F = sc.facing_matrix(n)
    out = np.zeros(canvas_shape, dtype=np.float64)
    for a in range(n):
        cLa = sc._embed_float(np.where(lf["supported"][a], lf[field][a], 0.0),
                              lo, canvas_origin, canvas_shape)
        dLa = sc._embed_float(np.where(lf["supported"][a], lf["distance"][a], 0.0),
                              lo, canvas_origin, canvas_shape)
        sLa = sc._embed_bool(lf["supported"][a], lo, canvas_origin, canvas_shape)
        for b in range(n):
            w = float(F[a, b])
            if w == 0.0:
                continue
            den = float(np.sqrt(float(EL[a]) * float(ER[b])))
            if not np.isfinite(den) or den <= 0.0:
                continue
            both = (sLa & sc._embed_bool(rf["supported"][b], ro,
                                         canvas_origin, canvas_shape))
            if not np.any(both):
                continue
            cRb = sc._embed_float(np.where(rf["supported"][b], rf[field][b], 0.0),
                                  ro, canvas_origin, canvas_shape)
            dRb = sc._embed_float(np.where(rf["supported"][b], rf["distance"][b], 0.0),
                                  ro, canvas_origin, canvas_shape)
            dd = np.abs(dLa - dRb)
            kval = np.exp(-dd[both] ** 2 / (2.0 * float(tau) * float(tau)))
            out[both] += w * cLa[both] * cRb[both] * kval / den
    return out


def slate_max_of(fields, energy_vec, strength="notebook"):
    """Glyph context projection peak: max over channels and pixels of
    ``c/sqrt(E)`` (zero where E is zero or unsupported). Exact normalized
    G2 factor per pixel, per-glyph fixed E (no per-frame autogain).
    """
    import numpy as np
    import yinyang_oriented_score as sc
    field = sc.resolve_strength(strength)
    best = 0.0
    for o in range(int(fields["supported"].shape[0])):
        e = float(energy_vec[o])
        if not np.isfinite(e) or e <= 0.0:
            continue
        sel = fields["supported"][o]
        if not np.any(sel):
            continue
        m = float(np.max(fields[field][o][sel] / np.sqrt(e)))
        if m > best:
            best = m
    return best


def main():
    outdir = Path(sys.argv[1])
    if outdir.exists():
        raise SystemExit("refusing to reuse output directory: %s" % outdir)
    outdir.mkdir(parents=True)
    repo = HERE.parents[2]
    t_start = time.perf_counter()

    prov = json.loads((repo / "out/diagnostics/contextual-spacing"
                       / "yinyang-oriented-fields/implementation"
                       / "provenance.json").read_text())
    names = list(prov["captures"].keys())
    v3cap = repo / "out/diagnostics/contextual-spacing" / \
        "yinyangfit-interactive-v3/captures"
    for case in V3_MONO_CASES:
        key = "v3mono:" + case
        if key not in names:
            names.append(key)

    s1_bank = yf.build_v1_bank(yf.DEFAULT_PARAMS)
    s1_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    s2_banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
    s2_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    energy = sc.EnergyCache()

    corpus = {
        "axes": [],
        "glyph_proj": {},
        "refmap": None,
        "frozen": {
            "oriented_fields_sha256": sha256_file(HERE.parent / "yinyang_oriented_fields.py"),
            "multiscale_fields_sha256": sha256_file(HERE.parent / "yinyang_multiscale_fields.py"),
            "oriented_score_sha256": sha256_file(HERE.parent / "yinyang_oriented_score.py"),
            "evidence_sha256": sha256_file(HERE.parent / "yinyang_oriented_score_evidence.py"),
            "tau": sc.TAU_PX,
            "cstar_grid": list(sc.CSTAR_GRID),
            "tie_tol_factor": sc.TIE_TOL_FACTOR,
            "g2_bound": sc.G2_BOUND,
            "floor_u2": sc.FLOOR_U2,
            "uncertainty": "uncertainty_not_certified",
        },
        "datasets": {},
        "study": [],
        "novel": [],
        "custom": [],
        "skipped": [],
    }

    def load_named(name):
        if name.startswith("v3mono:"):
            case = name.split(":", 1)[1]
            p = v3cap / (case + "-mono.json")
            cap = {"path": str(p.relative_to(repo)), "sha256": sha256_file(p),
                   "profile": "mono"}
            return v1.load_mono_capture(str(p)), cap
        cap = prov["captures"][name]
        p = repo / cap["path"]
        assert sha256_file(p) == cap["sha256"], "capture drift: %s" % name
        loader = (v1.load_mono_capture if cap["profile"] == "mono"
                  else v1.load_gray_capture)
        return loader(str(p)), cap

    def dump_dataset(name, ds, cap, codepoints):
        cells = {}
        for cp in sorted(codepoints):
            cell = ds["cells"][cp]
            cells[str(cp)] = {
                "w": cell["width"], "h": cell["height"],
                "left": cell["left"], "top": cell["top"],
                "cover": list(cell["cover"]),
                "advance_px": cell.get("advance_px"),
            }
        entry = {"path": cap["path"], "sha256": cap["sha256"],
                 "profile": ds["profile"], "cells": cells,
                 "adjustments": {"%d,%d" % k: v
                                 for k, v in ds.get("adjustments", {}).items()}}
        if ds["profile"] == "gray":
            entry["advances"] = {str(cp): ds["advances"][cp]
                                 for cp in sorted(codepoints)}
        corpus["datasets"][name] = entry

    def run_pairs(name, ds, cap, pairs, bucket):
        for pair in pairs:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                corpus["skipped"].append("%s:%s" % (name, pair))
                continue
            metric = v1.metric_step(ds, l, r)
            lc, lo0 = ev.glyph_cover(ds, l)
            rc, ro0 = ev.glyph_cover(ds, r)
            lf = mf.multiscale_glyph_fields(
                lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels)
            rf = mf.multiscale_glyph_fields(
                rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels)
            lo = (float(lo0[0]) - int(lf["pad"]),
                  float(lo0[1]) - int(lf["pad"]))
            ro_base = (float(ro0[0]) - int(rf["pad"]),
                       float(ro0[1]) - int(rf["pad"]))
            ELp = energy.energy((cap["sha256"], "stage2", l), lf, "notebook")
            ERp = energy.energy((cap["sha256"], "stage2", r), rf, "notebook")
            proj = corpus["glyph_proj"].setdefault(name, {})
            proj[str(l)] = slate_max_of(lf, ELp)
            proj[str(r)] = slate_max_of(rf, ERp)
            steps, (origin, shape) = ev.run_case(
                ds, pair, lf, rf, lo, ro_base, metric, DELTAS,
                energy, "stage2", (0.25, 1.0), None, None, l, r,
                capture_identity=cap["sha256"])
            dump_dataset(name, ds, cap, {l, r} |
                         {cp for c in corpus["datasets"].get(name, {})
                          .get("cells", {}) for cp in [int(c)]})
            narrow_g2 = [s["g2_primary"] for s in steps
                         if s.get("valid") and s["delta"] in DELTAS
                         and s["g2_primary"] is not None]
            narrow_steps = [s["step"] for s in steps
                            if s.get("valid") and s["delta"] in DELTAS
                            and s["g2_primary"] is not None]
            choices = {}
            for cstar in sc.CSTAR_GRID:
                if not narrow_g2:
                    choices[str(cstar)] = {"minimizing": [], "chosen": None,
                                           "fallback": True}
                    continue
                devs = [abs(g - cstar) for g in narrow_g2]
                idx, _ = sc.tie_set(devs)
                mins = [narrow_steps[i] for i in idx]
                choices[str(cstar)] = {"minimizing": mins,
                                       "chosen": min(mins), "fallback": False}
            rec = {"dataset": name, "pair": pair, "metric": metric,
                   "canvas_origin": list(origin), "canvas_shape": list(shape),
                   "choices": choices,
                   "steps": []}
            for s in steps:
                rec["steps"].append({
                    "step": s["step"], "delta": s["delta"],
                    "valid": bool(s.get("valid")),
                    "reason": s.get("reason"),
                    "faces": s.get("faces", 0), "corners": s.get("corners", 0),
                    "g2": s.get("g2_primary"),
                    "raw": s.get("g2_primary_raw"),
                    "floor_share": s.get("g2_primary_floor_share"),
                    "raw_floor_share": s.get("g2_primary_raw_floor_share"),
                    "both_pairpx": s.get("g2_primary_both_pairpx"),
                    "abstain": bool(s.get("abstain", False)),
                    "g2_a1": s.get("g2_a1"),
                    "g2_tau_0.25": s.get("g2_tau_0.25"),
                    "g2_tau_1.0": s.get("g2_tau_1.0"),
                })
            corpus[bucket].append(rec)

    for name in [n for n in names if not n.startswith("v3mono:")]:
        ds, cap = load_named(name)
        run_pairs(name, ds, cap, FOCUS + HELDOUT, "study")
    for case in V3_MONO_CASES:
        name = "v3mono:" + case
        ds, cap = load_named(name)
        run_pairs(name, ds, cap, NOVEL, "novel")

    # Custom-q / custom-R stage-2 references (generalization, defaults apart).
    # Stage-2 custom replica so the engine's custom-params path covers them;
    # the verified default replica above pins the replica to frozen semantics.
    bar = ev.bar_image()
    for tag, params in (
            ("q3", yf.OrientedFieldParams(radial_exponent_q=3.0)),
            ("r8", yf.OrientedFieldParams(kernel_radius_px=8))):
        kern = yf.build_oriented_kernels(params)
        cpad = (max(mf.support_halfwidth_for_sigma(s)
                    for s in mf.DEFAULT_PARAMS.scale_sigmas_px)
                + int(params.kernel_radius_px))
        lf = multiscale_glyph_fields_custom(
            bar, params, tuple(mf.DEFAULT_PARAMS.scale_weights),
            s2_banks, kern, cpad)
        rf = multiscale_glyph_fields_custom(
            bar, params, tuple(mf.DEFAULT_PARAMS.scale_weights),
            s2_banks, kern, cpad)
        lo = (-int(lf["pad"]), -int(lf["pad"]))
        ros = [(8 - int(lf["pad"]), -int(lf["pad"]))]
        origin, shape = sc.union_canvas(
            lf["image_shape"], lo, rf["image_shape"], ros)
        EL = sc.self_energy(lf, "notebook")
        ER = sc.self_energy(rf, "notebook")
        s = sc.score_step(lf, rf, lo, ros[0], origin, shape, EL, ER,
                          sc.TAU_PX, "notebook")
        corpus["custom"].append({
            "tag": tag, "q": params.radial_exponent_q,
            "kappa": params.angular_concentration_kappa,
            "radius": params.kernel_radius_px,
            "strength_exponent_notebook": params.radial_exponent_q - 1.0,
            "E": [float(x) for x in EL],
            "g2": s["g2"], "raw": s["raw"],
            "floor_share": s["floor_share"],
            "both_pairpx": s["both_supported_pairpx"],
        })

    # Default-point verification: custom replica must match the frozen
    # stage-2 module exactly before any axis point runs.
    import numpy as _np
    _dsm, _capm = load_named("roboto-16-mono")
    _lc, _lo0 = ev.glyph_cover(_dsm, ord("u"))
    _lf_frozen = mf.multiscale_glyph_fields(
        _lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    _kern_d = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    _lf_custom = multiscale_glyph_fields_custom(
        _lc, yf.DEFAULT_PARAMS, tuple(mf.DEFAULT_PARAMS.scale_weights),
        s2_banks, _kern_d, mf.stage_pad_multiscale())
    for _k in ("U1", "U2", "distance", "confidence_notebook",
               "arc_strength"):
        _a = _np.asarray(_lf_frozen[_k])
        _b = _np.asarray(_lf_custom[_k])
        _same = _np.array_equal(_a, _b, equal_nan=True)
        if not _same:
            raise SystemExit("custom replica diverges at default: %s" % _k)
    corpus["default_replica_exact"] = True

    # Stratified q/R axes (shared default point run once as R12/q2).
    _configs = [("R%d" % r, {"q": 2.0, "R": r}) for r in R_AXIS]
    _configs += [("q%g" % q, {"q": q, "R": 12}) for q in Q_AXIS
                 if not (q == 2.0)]
    _ax_ds = {}
    for _name in AXES_PAIRS:
        _ax_ds[_name] = load_named(_name)
    for _tag, _cfg in _configs:
        _t0 = time.perf_counter()
        _sp = yf.OrientedFieldParams(
            radial_exponent_q=float(_cfg["q"]),
            kernel_radius_px=int(_cfg["R"]))
        _kern = yf.build_oriented_kernels(_sp)
        _pad = (max(mf.support_halfwidth_for_sigma(s)
                    for s in mf.DEFAULT_PARAMS.scale_sigmas_px)
                + int(_sp.kernel_radius_px))
        _stage = "R%(R)d-q%(q)g stage2" % _cfg
        for _name, _pairs in AXES_PAIRS.items():
            _ds, _cap = _ax_ds[_name]
            for _pair in _pairs:
                _l, _r = ord(_pair[0]), ord(_pair[1])
                _metric = v1.metric_step(_ds, _l, _r)
                _lc, _lo0 = ev.glyph_cover(_ds, _l)
                _rc, _ro0 = ev.glyph_cover(_ds, _r)
                _lf = multiscale_glyph_fields_custom(
                    _lc, _sp, tuple(mf.DEFAULT_PARAMS.scale_weights),
                    s2_banks, _kern, _pad)
                _rf = multiscale_glyph_fields_custom(
                    _rc, _sp, tuple(mf.DEFAULT_PARAMS.scale_weights),
                    s2_banks, _kern, _pad)
                _lo = (float(_lo0[0]) - _pad, float(_lo0[1]) - _pad)
                _ro_base = (float(_ro0[0]) - _pad, float(_ro0[1]) - _pad)
                _steps, _ = ev.run_case(
                    _ds, _pair, _lf, _rf, _lo, _ro_base, _metric, DELTAS,
                    energy, _stage, (), None, None, _l, _r,
                    capture_identity=_cap["sha256"])
                _rec_steps = []
                for _s in _steps:
                    _rec_steps.append({
                        "step": _s["step"], "delta": _s["delta"],
                        "valid": bool(_s.get("valid")),
                        "reason": _s.get("reason"),
                        "g2": _s.get("g2_primary"),
                        "raw": _s.get("g2_primary_raw"),
                        "floor_share": _s.get("g2_primary_floor_share"),
                        "both_pairpx": _s.get("g2_primary_both_pairpx"),
                        "abstain": bool(_s.get("abstain", False)),
                        "g2_a1": _s.get("g2_a1"),
                    })
                _any_nan = any(
                    _s.get("g2") is not None and not _np.isfinite(_s["g2"])
                    for _s in _rec_steps if _s["valid"])
                corpus["axes"].append({
                    "config": _tag, "q": _cfg["q"], "R": _cfg["R"],
                    "dataset": _name, "pair": _pair, "metric": _metric,
                    "steps": _rec_steps, "any_nonfinite_g2": bool(_any_nan),
                })
        corpus["axes_seconds_%s" % _tag] = time.perf_counter() - _t0

    # Reference contribution map: roboto-16-mono um at the metric step.
    _l, _r = ord("u"), ord("m")
    _metric = v1.metric_step(_dsm, _l, _r)
    _lc, _lo0 = ev.glyph_cover(_dsm, _l)
    _rc, _ro0 = ev.glyph_cover(_dsm, _r)
    _lf = mf.multiscale_glyph_fields(
        _lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    _rf = mf.multiscale_glyph_fields(
        _rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    _lo = (float(_lo0[0]) - int(_lf["pad"]), float(_lo0[1]) - int(_lf["pad"]))
    _ro_base = (float(_ro0[0]) - int(_rf["pad"]),
                float(_ro0[1]) - int(_rf["pad"]))
    _ros = [(_ro_base[0] + _metric + _d, _ro_base[1]) for _d in DELTAS]
    _origin, _shape = sc.union_canvas(
        _lf["image_shape"], _lo, _rf["image_shape"], _ros)
    _EL = sc.self_energy(_lf, "notebook")
    _ER = sc.self_energy(_rf, "notebook")
    _ro = (_ro_base[0] + _metric, _ro_base[1])
    _sref = sc.score_step(_lf, _rf, _lo, _ro, _origin, _shape, _EL, _ER,
                          sc.TAU_PX, "notebook")
    _map = contribution_map(_lf, _rf, _lo, _ro, _origin, _shape, _EL, _ER,
                            sc.TAU_PX, "notebook")
    _map_sum = float(_np.sum(_map))
    if not (_np.isfinite(_map_sum) and abs(_map_sum - _sref["g2"]) <=
            1e-9 * max(1.0, abs(_sref["g2"]))):
        raise SystemExit("reference map does not reduce to G2")
    corpus["refmap"] = {
        "dataset": "roboto-16-mono", "pair": "um", "metric": _metric,
        "step": _metric, "g2": _sref["g2"],
        "canvas_origin": list(_origin), "canvas_shape": list(_shape),
        "map": _map.ravel().tolist(),
    }

    corpus["seconds"] = time.perf_counter() - t_start
    corpus["n_study_pairs"] = len(corpus["study"])
    corpus["n_novel_pairs"] = len(corpus["novel"])
    (outdir / "adapter.json").write_text(json.dumps(corpus) + "\n")
    print("study=%d novel=%d axes=%d replica_exact=%s skipped=%s seconds=%.1f" % (
        len(corpus["study"]), len(corpus["novel"]), len(corpus["axes"]),
        corpus["default_replica_exact"], corpus["skipped"], corpus["seconds"]))


if __name__ == "__main__":
    main()
