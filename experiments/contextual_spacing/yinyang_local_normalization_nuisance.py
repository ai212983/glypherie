#!/usr/bin/env python3
"""Nuisance / multiplicity supplement on real glyphs (multiscale fields).

Field-level addition (outside every both-set AND every pool window) must
leave scores exact; image-level edits inside convolution support are
quantified change, not invariance. mm/ll multiplicity is record-only.
Research only: writes corpus/nuisance.json.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import yinyangfit_interactive as v1

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORPUS = REPO / "out" / "diagnostics" / "contextual-spacing" \
    / "yinyang-normalization-repair" / "corpus"


def glyph_cover(ds, codepoint):
    cell = ds["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    return (np.asarray(cell["cover"], dtype=np.float64).reshape(h, w),
            (float(cell["left"]), float(cell["top"])))


def main():
    CORPUS.mkdir(parents=True, exist_ok=True)
    prov = json.loads((REPO / "out/diagnostics/contextual-spacing"
                       / "yinyang-oriented-fields/implementation"
                       / "provenance.json").read_text())
    out = {}
    s2_banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
    s2_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)

    def ms_fields(img):
        return mf.multiscale_glyph_fields(
            img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels)

    for name in ("roboto-16-mono", "roboto-16-gray"):
        cap = prov["captures"][name]
        loader = (v1.load_mono_capture if cap["profile"] == "mono"
                  else v1.load_gray_capture)
        ds = loader(str(REPO / cap["path"]))
        lc, lo0 = glyph_cover(ds, ord("u"))
        rc, ro0 = glyph_cover(ds, ord("m"))
        lf, rf = ms_fields(lc), ms_fields(rc)
        lo = (float(lo0[0]) - int(lf["pad"]),
              float(lo0[1]) - int(lf["pad"]))
        ro_base = (float(ro0[0]) - int(rf["pad"]),
                   float(ro0[1]) - int(rf["pad"]))
        step = v1.metric_step(ds, ord("u"), ord("m"))
        ro = (ro_base[0] + step, ro_base[1])
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], [ro])
        EL = sc.self_energy(lf, "notebook")
        ER = sc.self_energy(rf, "notebook")
        LL = ln.LocalEnergyCache().maps("n", lf)
        LR = ln.LocalEnergyCache().maps("n", rf)
        base = {"g2": sc.score_step(lf, rf, lo, ro, origin, shape,
                                    EL, ER)["g2"],
                "go": ln.score_overlap_cosine(
                    lf, rf, lo, ro, origin, shape)["g"],
                "gl": ln.score_local_energy(
                    lf, rf, lo, ro, origin, shape, LL, LR)["g"]}
        # Field-level: blob far outside both-sets and pool windows.
        W = lc.shape[1] + 120
        wide = np.zeros((lc.shape[0], W))
        wide[:, :lc.shape[1]] = lc
        blob_val = float(np.median(lc[lc > 0])) if np.any(lc > 0) else 1.0
        wide[4:9, lc.shape[1] + 80:lc.shape[1] + 85] = blob_val
        lfW = ms_fields(wide)
        loW = (float(lo0[0]) - int(lfW["pad"]),
               float(lo0[1]) - int(lfW["pad"]))
        oW, shW = sc.union_canvas(lfW["image_shape"], loW,
                                  rf["image_shape"], [ro])
        ELW = sc.self_energy(lfW, "notebook")
        LLW = ln.LocalEnergyCache().maps("nw", lfW)
        fld = {"g2": sc.score_step(lfW, rf, loW, ro, oW, shW,
                                   ELW, ER)["g2"],
               "go": ln.score_overlap_cosine(
                   lfW, rf, loW, ro, oW, shW)["g"],
               "gl": ln.score_local_energy(
                   lfW, rf, loW, ro, oW, shW, LLW, LR)["g"]}
        # Image-level: adjacent stem inside frame (legitimate change).
        adj = lc.copy()
        x1 = lc.shape[1]
        adjPad = np.zeros((lc.shape[0], x1 + 6))
        adjPad[:, :x1] = lc
        adjPad[4:16, x1 + 2:x1 + 4] = 1.0
        lfA = ms_fields(adjPad)
        loA = (float(lo0[0]) - int(lfA["pad"]),
               float(lo0[1]) - int(lfA["pad"]))
        oA, shA = sc.union_canvas(lfA["image_shape"], loA,
                                  rf["image_shape"], [ro])
        ELA = sc.self_energy(lfA, "notebook")
        LLA = ln.LocalEnergyCache().maps("na", lfA)
        img = {"g2": sc.score_step(lfA, rf, loA, ro, oA, shA,
                                   ELA, ER)["g2"],
               "go": ln.score_overlap_cosine(
                   lfA, rf, loA, ro, oA, shA)["g"],
               "gl": ln.score_local_energy(
                   lfA, rf, loA, ro, oA, shA, LLA, LR)["g"]}
        out[name] = {
            "base": base,
            "field_blob_reldiff": {k: abs(fld[k] - base[k]) / base[k]
                                   for k in base},
            "image_stem_relmove": {k: abs(img[k] - base[k]) / base[k]
                                   for k in base}}
    # mm vs ll multiplicity, record-only.
    cap = prov["captures"]["roboto-16-mono"]
    ds = v1.load_mono_capture(str(REPO / cap["path"]))
    mm = {}
    for pair in ("mm", "ll"):
        l, r = ord(pair[0]), ord(pair[1])
        li, lo0 = glyph_cover(ds, l)
        ri, ro0 = glyph_cover(ds, r)
        fl, fr = ms_fields(li), ms_fields(ri)
        loB = (float(lo0[0]) - int(fl["pad"]),
               float(lo0[1]) - int(fl["pad"]))
        roB = (float(ro0[0]) - int(fr["pad"]),
               float(ro0[1]) - int(fr["pad"]))
        st = v1.metric_step(ds, l, r)
        o, sh = sc.union_canvas(fl["image_shape"], loB, fr["image_shape"],
                                [(roB[0] + st, roB[1])])
        ro = (roB[0] + st, roB[1])
        EL = sc.self_energy(fl, "notebook")
        ER = sc.self_energy(fr, "notebook")
        LL = ln.LocalEnergyCache().maps("m" + pair, fl)
        LR = ln.LocalEnergyCache().maps("r" + pair, fr)
        mm[pair] = {
            "g2": sc.score_step(fl, fr, loB, ro, o, sh, EL, ER)["g2"],
            "gl": ln.score_local_energy(
                fl, fr, loB, ro, o, sh, LL, LR)["g"],
            "go": ln.score_overlap_cosine(
                fl, fr, loB, ro, o, sh)["g"]}
    out["multiplicity_mm_ll"] = mm
    with open(CORPUS / "nuisance.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(out, indent=2)[:2000])


if __name__ == "__main__":
    main()
