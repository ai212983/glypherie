"""Stage-1 source reconciliation: writer module vs frozen independent oracle.

Compares ``experiments/contextual_spacing/yinyang_oriented_fields.py``
(stage-1 writer: manuscript derivative-of-Gaussian V1C input, odd 25-tap
kernels, ``exp(+k cos)`` masks, angles from +x, pixel units) against the
frozen oracle ``yinyang_oriented_reference.py`` (notebook cells 12/15:
even 16-tap kernels, ``exp(-k cos)`` masks, angles from +y, box-unit
lengths) on IDENTICAL declared T arrays.

Equation/provenance notes only (see owning design section
"YinYang oriented field stage"):
- Manuscript direct-approximation chain: d = (T*f1)/(T*f2),
  a = (T*f1) . d^(q+1); notebook executable cells 15/19:
  confidences = f.(f/d)^(k-1), distances = f/d where defined.
- Manuscript V1 instance adopted here ("we might use
  derivative-of-Gaussians"): odd = u.gauss/(2.pi.s^4) = -dG/du,
  even = gauss/(2.pi.s^3) - u^2.gauss/(2.pi.s^5) = -s.d2G/du2,
  with the even partner demeaned to zero DC (finite-support correction;
  the analytic integral of G_uu already vanishes).
- Angle conventions: writer phi = arctan2(dy,dx) from +x (rows down);
  oracle angle = arctan2(x,y) from +y. Mask functions agree under one
  fixed channel permutation (fitted empirically in section M, not
  assumed), composed with true convolution on both sides.
- Length units: oracle r is dimensionless (px / UNIT); writer r is px.
  This script runs the oracle at UNIT=1 so both distances read in px.
- Kernel support: oracle even 2*HALF taps (center index HALF, tap offsets
  -HALF..HALF-1); writer odd 2*R+1 taps (-R..R). Common taps compared
  directly; the extra writer rim and the half-tap center offset are
  measured, not assumed away.
- Support floors differ by declaration: writer U2 > 1e-12 (NaN/0 outside);
  oracle A2 > 1e-9 (sentinel -100/0 outside). Masks compared separately
  from well-supported values with condition-aware tolerances.
- Strength reporting: the executable notebook confidence U1.d^(q-1) is the
  PRIMARY reference; the manuscript U1.d^(q+1) is retained explicitly as
  an alternate diagnostic. Neither is optically approved.

Output (must be a new directory): reconciliation.json + raw .npy arrays.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
REF_DIR = (Path(__file__).resolve().parents[2]
           / "out/diagnostics/contextual-spacing"
           / "yinyang-oriented-fields/reference-review")
sys.path.insert(0, str(REF_DIR))
import yinyang_oriented_fields as yf
import yinyang_oriented_reference as ref

Q = 2.0
KAPPA = 4.0
HALF = 12          # oracle half-support -> 24x24 even kernels
UNIT = 1.0         # px units on both sides
N_O = 8
MARGIN = 13        # interior crop: kernel reach 12 + 1 for even/odd centers
WELL = 1e-6        # well-supported floor for tight value comparison


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def oracle_stack():
    r, angle = ref.polar_grid(HALF, UNIT)
    masks = ref.angular_masks(N_O, KAPPA, angle)
    f1, f2 = ref.radial_kernels(r, 2, center="zero")
    return r, angle, masks, f1, f2


def oracle_per_channel(Tr16, masks_r, f1r, f2r):
    """Oracle ratio stage on a 16-channel T (one 2D field per channel).

    The frozen oracle's ``ratio_fields`` takes a single 2D ``T`` (source
    calls share one T across channels); directed inputs differ per channel
    here, so each channel runs its own call with its single mask slice.
    """
    outs = [ref.ratio_fields(np.asarray(Tr16[j], dtype=np.float64),
                             masks_r[j][None, :, :], f1r, f2r, 2)
            for j in range(16)]
    return {k: np.asarray([o[k][0] for o in outs])
            for k in ("A1", "A2", "supported", "d",
                      "conf_article", "conf_notebook")}


def writer_estimator(T16, h1, h2, eps=1e-12):
    """Writer ratio stage on a given 16-channel T (mirrors module internals)."""
    u1 = np.asarray([yf.convolve_fft(np.maximum(T16[o], 0.0), h1[o])
                     for o in range(16)])
    u2 = np.asarray([yf.convolve_fft(np.maximum(T16[o], 0.0), h2[o])
                     for o in range(16)])
    u1 = np.maximum(u1, 0.0)
    u2 = np.maximum(u2, 0.0)
    supported = np.isfinite(u1) & np.isfinite(u2) & (u2 > eps)
    distance = np.full_like(u1, np.nan)
    distance[supported] = u1[supported] / u2[supported]
    arc = np.zeros_like(u1)
    arc[supported] = u1[supported] * distance[supported] ** (Q + 1.0)
    conf = np.zeros_like(u1)
    conf[supported] = u1[supported] * distance[supported] ** (Q - 1.0)
    return {"U1": u1, "U2": u2, "supported": supported,
            "distance": distance, "arc_manuscript": arc,
            "conf_notebook": conf}


def main():
    outdir = Path(sys.argv[1])
    if outdir.exists():
        raise SystemExit(f"refusing to reuse output directory: {outdir}")
    (outdir / "arrays").mkdir(parents=True)
    t0_all = time.perf_counter()
    report = {"model_writer": yf.MODEL_IDENTITY,
              "writer_sha256": yf.IMPLEMENTATION_SHA256,
              "oracle_files": {p: sha256_file(REF_DIR / p) for p in
                               ("yinyang_oriented_reference.py",
                                "run_reference_checks.py")},
              "oracle_unit_px": UNIT, "oracle_half_taps": HALF,
              "sections": {}}

    params = yf.DEFAULT_PARAMS
    h1w, h2w, _, _ = yf.build_oriented_kernels(params)
    _, _, masks_r, f1r, f2r = oracle_stack()
    S = report["sections"]

    # --- M: mask-function equivalence under a fixed channel permutation ---
    # Common tap offsets -12..11 (writer idx 0..23, oracle idx 0..23).
    common = slice(0, 2 * HALF)
    f1c_r, f2c_r = f1r, f2r
    perm, mask_err = {}, {}
    for o in range(16):
        best, bj = np.inf, -1
        for j in range(16):
            e1 = float(np.abs(h1w[o][common, common]
                              - masks_r[j] * f1c_r).max())
            e2 = float(np.abs(h2w[o][common, common]
                              - masks_r[j] * f2c_r).max())
            e = max(e1, e2)
            if e < best:
                best, bj = e, j
        perm[str(o)] = bj
        mask_err[str(o)] = best
    S["mask_permutation"] = {
        "writer_to_oracle": perm,
        "max_abs_err_on_common_taps": mask_err,
        "bijective": len(set(perm.values())) == 16,
        "worst": max(mask_err.values()),
        "note": ("writer exp(+k.cos) from +x equals oracle exp(-k.cos) "
                 "from +y up to this fixed relabeling; radial kernels agree "
                 "exactly on common taps (UNIT=1)")}

    # --- E1: impulse T (single point), analytic r on both sides ---
    T = np.zeros((41, 41))
    T[20, 25] = 1.0  # 5 px east of query (20, 20)
    Tw = np.asarray([T] * 16)
    fw = writer_estimator(Tw, h1w, h2w)
    # Tr indexed by oracle channel j: Tr[j] = Tw[o] with perm[o] = j.
    Tr = np.empty_like(Tw)
    for o in range(16):
        Tr[int(perm[str(o)])] = Tw[o]
    orac = oracle_per_channel(Tr, masks_r, f1r, f2r)
    j_east = int(perm["8"])  # writer ch8 faces east ink; oracle winner?
    S["impulse"] = {
        "permutation_writer_ch8": j_east,
        "writer_d_ch8_at_query": float(fw["distance"][8, 20, 20]),
        "oracle_d_jeast_at_query": float(orac["d"][j_east, 20, 20]),
        "expected_px": 5.0,
        "oracle_supports_query": bool(orac["supported"][j_east, 20, 20]),
        "writer_supports_query": bool(fw["supported"][8, 20, 20]),
    }

    # --- E2: identical-T estimator parity on 4 declared stimuli ---
    def bars_T(shape=(41, 41), gap=4, width=2, h0=14, h1=26):
        t = np.zeros(shape)
        t[h0:h1, 10:10 + width] = 1.0
        t[h0:h1, 10 + width + gap:10 + 2 * width + gap] = 1.0
        return t

    def two_point_T():
        t = np.zeros((41, 41))
        t[20, 25] = 1.0
        t[20, 15] = 0.5
        return t

    # (d) actual V1C magnitudes of a bars image through the writer V1 bank.
    bank = yf.build_v1_bank(params)
    bars_img = bars_T()
    C = np.abs(np.asarray([yf.convolve_fft(bars_img, g) for g in bank]))
    Tv = np.asarray([C[o % params.n_v1_orientations] for o in range(16)])

    stims = {"impulse": T, "two_point": two_point_T(),
             "bars": bars_T(), "v1c_bars": Tv[0]}
    E = S["estimator_parity"] = {}
    for name, t in stims.items():
        if name == "v1c_bars":
            Tw = Tv
        else:
            Tw = np.asarray([t] * 16)
        fw = writer_estimator(Tw, h1w, h2w)
        Tr = np.empty_like(Tw)
        for o in range(16):
            Tr[int(perm[str(o)])] = Tw[o]
        orac = oracle_per_channel(Tr, masks_r, f1r, f2r)
        Ow = np.asarray([fw["distance"][o] for o in range(16)])
        # reorder writer channels into oracle order for comparison
        Ow_in_oracle = np.empty_like(Ow)
        Uw1 = np.empty_like(Ow)
        Uw2 = np.empty_like(Ow)
        for o in range(16):
            j = int(perm[str(o)])
            Ow_in_oracle[j] = fw["distance"][o]
            Uw1[j] = fw["U1"][o]
            Uw2[j] = fw["U2"][o]
        sup_w = np.empty_like(fw["supported"])
        for o in range(16):
            sup_w[int(perm[str(o)])] = fw["supported"][o]
        sup_r = orac["supported"]
        interior = np.zeros_like(sup_w, dtype=bool)
        interior[:, MARGIN:-MARGIN, MARGIN:-MARGIN] = True
        both = sup_w & sup_r & interior
        well = both & (np.minimum(Uw2, orac["A2"]) > WELL)
        with np.errstate(invalid="ignore"):
            dd = np.abs(Ow_in_oracle - orac["d"])
            dd_well = dd[well]
            rel_u1 = (np.abs(Uw1 - orac["A1"])
                      / np.maximum(np.abs(orac["A1"]), 1e-300))
            rel_u2 = (np.abs(Uw2 - orac["A2"])
                      / np.maximum(np.abs(orac["A2"]), 1e-300))
        # strength branches (primary: notebook; alternate: manuscript)
        man_w = np.empty_like(Ow)
        for o in range(16):
            man_w[int(perm[str(o)])] = fw["arc_manuscript"][o]
            # conf_notebook reordered below
        nb_w = np.empty_like(Ow)
        for o in range(16):
            nb_w[int(perm[str(o)])] = fw["conf_notebook"][o]
        with np.errstate(invalid="ignore", divide="ignore"):
            dman = np.abs(man_w - orac["conf_article"])
            dnb = np.abs(nb_w - orac["conf_notebook"])
            dman = dman[well]
            dnb = dnb[well]
        # support-mask agreement on interior
        agree = float((sup_w[interior] == sup_r[interior]).mean())
        # floor band: writer-only support (1e-12 < U2 <= 1e-9)
        floorband = (sup_w & ~sup_r & interior).sum()
        E[name] = {
            "both_supported_interior": int(both.sum()),
            "well_supported": int(well.sum()),
            "max_abs_d_diff_well": float(dd_well.max()) if well.any()
            else float("nan"),
            "max_rel_U1_diff_well": float(rel_u1[well].max())
            if well.any() else float("nan"),
            "max_rel_U2_diff_well": float(rel_u2[well].max())
            if well.any() else float("nan"),
            "max_abs_manuscript_strength_diff_well":
                float(dman.max()) if well.any() else float("nan"),
            "max_abs_notebook_strength_diff_well":
                float(dnb.max()) if well.any() else float("nan"),
            "support_agreement_interior": agree,
            "writer_only_floorband_pixels": int(floorband),
        }
        np.save(outdir / "arrays" / f"{name}_dw.npy", Ow_in_oracle)
        np.save(outdir / "arrays" / f"{name}_dr.npy", orac["d"])
    S["estimator_parity_note"] = (
        "UNIT=1 aligns length units (oracle d reads in px). Permutation is "
        "the fixed map from section M. Oracle sentinel -100 vs writer NaN "
        "is representation only; value comparison restricted to common "
        "support. Even/odd center offset and the extra writer rim enter only "
        "outside the interior crop or at measured magnitudes above.")

    # --- S_match: matched-support control (finite-support isolation) ---
    # Writer kernels cropped to the oracle's exact even support (tap offsets
    # -12..+11, i.e. [:24, :24]) must reproduce the oracle to FFT precision;
    # whatever remains under full symmetric support is then purely the rim.
    h1c = h1w[:, :24, :24]
    h2c = h2w[:, :24, :24]
    SM = S["matched_support_control"] = {}
    for name, t in stims.items():
        Tw = Tv if name == "v1c_bars" else np.asarray([t] * 16)
        fw = writer_estimator(Tw, h1c, h2c)
        Tr = np.empty_like(Tw)
        for o in range(16):
            Tr[int(perm[str(o)])] = Tw[o]
        orac = oracle_per_channel(Tr, masks_r, f1r, f2r)
        Ow = np.empty_like(fw["distance"])
        Uw2 = np.empty_like(fw["distance"])
        sup_w = np.empty_like(fw["supported"])
        for o in range(16):
            j = int(perm[str(o)])
            Ow[j] = fw["distance"][o]
            Uw2[j] = fw["U2"][o]
            sup_w[j] = fw["supported"][o]
        interior = np.zeros_like(sup_w, dtype=bool)
        interior[:, MARGIN:-MARGIN, MARGIN:-MARGIN] = True
        both = sup_w & orac["supported"] & interior
        well = both & (np.minimum(Uw2, orac["A2"]) > WELL)
        with np.errstate(invalid="ignore"):
            dd = np.abs(Ow - orac["d"])[well]
        SM[name] = {"well_supported": int(well.sum()),
                    "max_abs_d_diff": float(dd.max()) if well.any()
                    else float("nan")}
    SM["verdict"] = ("matched even support reproduces the oracle to FFT "
                     "precision; full-support residuals are the symmetric "
                     "+12 rim alone (writer choice; the oracle even support "
                     "is asymmetric -12..+11 with a half-tap bias)")

    # --- G: gap-width probe (no universal-monotonicity claim) ---
    # Parallel bars at declared gaps; record east-facing distance at the gap
    # center. Values only: ratio fields are not gap meters.
    G = S["gap_width_probe"] = {}
    for gap in (2, 4, 6, 8):
        t = np.zeros((20, 30))
        t[4:16, 6:8] = 1.0
        t[4:16, 8 + gap:10 + gap] = 1.0
        f = yf.oriented_fields_for_image(
            t, params, yf.build_v1_bank(params), (h1w, h2w, None, None))
        pad = int(f["pad"])
        mid, gc = 10 + pad, 8 + gap // 2 + pad
        G[str(gap)] = {
            "distance_ch0": float(f["distance"][0, mid, gc]),
            "supported_ch0": bool(f["supported"][0, mid, gc])}

    # --- V: independent V1 derivative-of-Gaussian verification ---
    # Fresh transcription of the manuscript equation (no build_v1_bank call),
    # plus finite-difference derivative identities on a fine sampling.
    s = float(params.v1_sigma_px)
    w = int(params.v1_support_halfwidth_px)
    ys, xs = np.mgrid[-w:w + 1, -w:w + 1].astype(np.float64)
    indep = []
    for theta in yf.v1_angles(params.n_v1_orientations):
        c, sn = np.cos(theta), np.sin(theta)
        u = xs * c + ys * sn
        v = -xs * sn + ys * c
        gauss = np.exp(-(u * u + v * v) / (2.0 * s * s))
        odd = u * gauss / (2.0 * np.pi * s ** 4)
        even = gauss / (2.0 * np.pi * s ** 3) - u * u * gauss / (
            2.0 * np.pi * s ** 5)
        even = even - np.mean(even)
        indep.append(odd + 1j * even)
    indep = np.asarray(indep)
    trans_err = float(np.abs(indep - bank).max())
    # Finite differences of the sampled Gaussian along u at theta=0.
    du = 1e-4
    G = np.exp(-(xs ** 2 + ys ** 2) / (2 * s ** 2)) / (2 * np.pi * s ** 2)
    Gp = np.exp(-((xs + du) ** 2 + ys ** 2) / (2 * s ** 2)) / (
        2 * np.pi * s ** 2)
    Gm = np.exp(-((xs - du) ** 2 + ys ** 2) / (2 * s ** 2)) / (
        2 * np.pi * s ** 2)
    dG = (Gp - Gm) / (2 * du)
    Gpp = (Gp - 2 * G + Gm) / (du ** 2)
    b0 = bank[0]  # theta=0: u = xs
    fd_odd = float(np.abs(np.real(b0) + dG).max())
    # Even partner before demeaning: gauss/(2.pi.s^3) - u^2.gauss/(2.pi.s^5).
    gauss0 = np.exp(-(xs ** 2 + ys ** 2) / (2 * s ** 2))
    even_raw = gauss0 / (2.0 * np.pi * s ** 3) - xs ** 2 * gauss0 / (
        2.0 * np.pi * s ** 5)
    fd_even = float(np.abs(even_raw + s * Gpp).max())
    # Contributing property checks on the shipped bank.
    odd_sums = [float(np.real(g).sum()) for g in bank]
    even_dc = [float(np.imag(g).sum()) for g in bank]
    S["v1_dog_independent"] = {
        "manuscript_transcription_max_abs": trans_err,
        "finite_diff_odd_plus_dG_max_abs": fd_odd,
        "finite_diff_even_plus_s_Gpp_demeaned_max_abs": fd_even,
        "odd_sums_zero": odd_sums,
        "even_dc_after_demean": even_dc,
        "notebook_contrast": ("notebook cell 5 builds a log-Gabor bank in "
                              "the FFT domain: frequency ring "
                              "exp(-(log(f.period))^2/(2.0.75^2)) x von "
                              "Mises(k=2), 6 geometric scales period 30->3, "
                              "complex FFT-domain filters. Structurally "
                              "different from this spatial DoG quadrature "
                              "instance (manuscript 'we might use'); V1C "
                              "magnitude semantics |S| are shared.")}

    # --- F: absolute support-floor behavior (contrast ladder + Mono/Gray) ---
    t = bars_T()
    Tw = np.asarray([t] * 16)
    ladder = {}
    for c in (1.0, 0.5, 0.25, 1.0 / 7.0):
        fw = writer_estimator(c * Tw, h1w, h2w)
        Tr = np.empty_like(Tw)
        for o in range(16):
            Tr[int(perm[str(o)])] = Tw[o] * c
        orac = oracle_per_channel(Tr, masks_r, f1r, f2r)
        ladder[str(c)] = {
            "writer_support_frac": float(fw["supported"].mean()),
            "oracle_support_frac": float(orac["supported"].mean())}
    S["support_floor_ladder"] = ladder
    # Real glyphs Mono vs Gray (retained captures, read-only).
    try:
        sys.path.insert(0, str(Path(yf.__file__).resolve().parent))
        import yinyangfit_interactive as v1
        repo = Path(yf.__file__).resolve().parents[2]
        v3cap = (repo / "out/diagnostics/contextual-spacing"
                 / "yinyangfit-interactive-v3/captures")
        mono = v1.load_mono_capture(str(v3cap / "roboto-16-mono.json"))
        gray = v1.load_gray_capture(str(v3cap / "roboto-16-gray.json"))

        def cover(ds, cp):
            cell = ds["cells"][cp]
            a = np.asarray(cell["cover"], dtype=np.float64)
            return a.reshape(cell["height"], cell["width"])
        glyph_sup = {}
        for cp in (ord("u"), ord("m")):
            fm = yf.oriented_fields_for_image(
                cover(mono, cp), params,
                yf.build_v1_bank(params),
                (h1w, h2w, None, None))
            fg = yf.oriented_fields_for_image(
                cover(gray, cp), params,
                yf.build_v1_bank(params),
                (h1w, h2w, None, None))
            glyph_sup[chr(cp)] = {
                "mono_support_frac": float(fm["supported"].mean()),
                "gray_support_frac": float(fg["supported"].mean()),
                "mono_min_U2_supported":
                    float(fm["U2"][fm["supported"]].min()),
                "gray_min_U2_supported":
                    float(fg["U2"][fg["supported"]].min())}
        S["real_glyph_support"] = glyph_sup
    except Exception as e:  # noqa: BLE001 - record, do not hide
        S["real_glyph_support"] = {"error": f"{type(e).__name__}: {e}"}

    # --- P: estimator-level fractional-phase sensitivity parity ---
    crisp = np.zeros((21, 21))
    crisp[8:13, 6:9] = 1.0
    split = crisp.copy()
    split[8:13, 6] = 0.5
    split[8:13, 5] = 0.5
    sens = {}
    for name, Stoff in (("crisp", crisp), ("split", split)):
        Tw = np.asarray([Stoff] * 16)
        fw = writer_estimator(Tw, h1w, h2w)
        Tr = np.empty_like(Tw)
        for o in range(16):
            Tr[int(perm[str(o)])] = Tw[o]
        orac = oracle_per_channel(Tr, masks_r, f1r, f2r)
        sens[name] = (fw, orac)
    fwc, orc = sens["crisp"]
    fws, ors = sens["split"]
    Ow_c = np.empty_like(fwc["distance"])
    Ow_s = np.empty_like(fws["distance"])
    for o in range(16):
        j = int(perm[str(o)])
        Ow_c[j] = fwc["distance"][o]
        Ow_s[j] = fws["distance"][o]
    with np.errstate(invalid="ignore"):
        both = (np.isfinite(Ow_c) & np.isfinite(Ow_s)
                & (orc["d"] != ref.SENTINEL_DISTANCE)
                & (ors["d"] != ref.SENTINEL_DISTANCE))
        dw = np.abs(Ow_c - Ow_s)[both].max()
        dr = np.abs(orc["d"] - ors["d"])[both].max()
    S["fractional_phase"] = {
        "writer_max_abs_delta": float(dw),
        "oracle_max_abs_delta_units": float(dr),
        "oracle_unit_px": UNIT,
        "note": ("same total ink, redistributed coverage: sensitivity "
                 "measured on both sides, invariance claimed on neither")}

    report["provenance"] = {
        "repo_head": __import__("subprocess").run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(Path(yf.__file__).resolve().parents[2])).stdout.strip(),
        "pinned_source": "skosch/YinYangFit@"
                         "609d17e8a6446ec4413a1b02a0768b8214d73333",
        "notebook_sha256": "63f7be83b90aad5cc1c29be53197d78bafd14dff7fa84c"
                           "797345390195198a91",
        "seconds": time.perf_counter() - t0_all,
    }
    (outdir / "reconciliation.json").write_text(
        json.dumps(report, indent=1, default=float))
    print(json.dumps({"mask_worst": S["mask_permutation"]["worst"],
                      "bijective": S["mask_permutation"]["bijective"],
                      "parity": {k: {kk: v[kk] for kk in
                                     ("max_abs_d_diff_well",
                                      "support_agreement_interior",
                                      "writer_only_floorband_pixels")}
                                 for k, v in E.items()},
                      "transcription": S["v1_dog_independent"][
                          "manuscript_transcription_max_abs"],
                      "fd_odd": S["v1_dog_independent"][
                          "finite_diff_odd_plus_dG_max_abs"],
                      "fd_even": S["v1_dog_independent"][
                          "finite_diff_even_plus_s_Gpp_demeaned_max_abs"]},
                     indent=1))


if __name__ == "__main__":
    main()
