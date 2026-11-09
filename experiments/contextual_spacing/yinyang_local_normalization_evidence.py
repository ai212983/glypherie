#!/usr/bin/env python3
"""Evidence driver for the YinYang local-normalization repair pilot.

Research only: synthetic bar fixtures over frozen stage-1 fields, no
captures, no live changes. Writes run_output.json under the repair
research directory. REPORT.md/PROVENANCE.md are authored beside it.
"""

import hashlib
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..",
                                "out", "diagnostics", "contextual-spacing",
                                "yinyang-normalization-repair",
                                "spec-review", "oracle"))
import yinyang_oriented_fields as yf
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import norm_reference as N

RESEARCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "out", "diagnostics",
                        "contextual-spacing",
                        "yinyang-normalization-repair", "research")

P1 = yf.DEFAULT_PARAMS


def bars(w=140, x0=20, x1=22, y0=4, y1=16, extra=None):
    img = np.zeros((20, w))
    img[y0:y1, x0:x1] = 1.0
    if extra:
        img[y0:y1, extra[0]:extra[1]] = 1.0
    return img


def spearman(xs, ys):
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    return float(np.dot(rx, ry) / math.sqrt(np.dot(rx, rx) * np.dot(ry, ry)))


def stack_canvas(lf, rf, lo, ro, origin, shape, strength="notebook"):
    chans = ln._per_pair_overlays(lf, rf, lo, ro, origin, shape, strength)
    n = len(chans)
    cL = np.asarray([chans[o][0] for o in range(n)])
    dL = np.asarray([chans[o][1] for o in range(n)])
    sL = np.asarray([chans[o][2] for o in range(n)])
    cR = np.asarray([chans[o][4] for o in range(n)])
    dR = np.asarray([chans[o][5] for o in range(n)])
    sR = np.asarray([chans[o][6] for o in range(n)])
    return cL, dL, sL, cR, dR, sR


def main():
    t0 = time.time()
    os.makedirs(RESEARCH, exist_ok=True)
    fa = yf.oriented_fields_for_image(bars())
    fb = yf.oriented_fields_for_image(bars())
    ft = yf.oriented_fields_for_image(bars(extra=(110, 112)))
    t_fields = time.time() - t0
    ecache, lcache = sc.EnergyCache(), ln.LocalEnergyCache()
    EA, EB, ET = (ecache.energy("a", fa), ecache.energy("b", fb),
                  ecache.energy("t", ft))
    LA, LB, LT = (lcache.maps("a", fa), lcache.maps("b", fb),
                  lcache.maps("t", ft))
    pc_tau = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])
    pc_R = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["kernel_radius"])
    PA, PB, PT = (pc_tau.maps("a", fa), pc_tau.maps("b", fb),
                  pc_tau.maps("t", ft))
    PAR, PBR = (pc_R.maps("a", fa), pc_R.maps("b", fb))

    out = {"model": ln.MODEL_IDENTITY,
           "sourced_sigmas": ln.SOURCED_SIGMAS,
           "support_frame_single_scale": int(yf.stage_pad())}

    # Far-stem strict nuisance (stem beyond 2x influence of any overlap).
    o2, sh2 = sc.union_canvas(fa["image_shape"], (0, 0),
                              fb["image_shape"], [(6, 0)])
    o3, sh3 = sc.union_canvas(ft["image_shape"], (0, 0),
                              fb["image_shape"], [(6, 0)])
    g2p = sc.score_step(fa, fb, (0, 0), (6, 0), o2, sh2, EA, EB)["g2"]
    g2t = sc.score_step(ft, fb, (0, 0), (6, 0), o3, sh3, ET, EB)["g2"]
    gop = ln.score_overlap_cosine(fa, fb, (0, 0), (6, 0), o2, sh2)
    got = ln.score_overlap_cosine(ft, fb, (0, 0), (6, 0), o3, sh3)
    glp = ln.score_local_energy(fa, fb, (0, 0), (6, 0), o2, sh2, LA, LB)
    glt = ln.score_local_energy(ft, fb, (0, 0), (6, 0), o3, sh3, LT, LB)
    gpp = ln.score_pooled(fa, fb, (0, 0), (6, 0), o2, sh2, PA, PB,
                          ln.SOURCED_SIGMAS["tau"])
    gpt = ln.score_pooled(ft, fb, (0, 0), (6, 0), o3, sh3, PT, PB,
                          ln.SOURCED_SIGMAS["tau"])
    gpR_p = ln.score_pooled(fa, fb, (0, 0), (6, 0), o2, sh2, PAR, PBR,
                            ln.SOURCED_SIGMAS["kernel_radius"])
    gpR_t = ln.score_pooled(ft, fb, (0, 0), (6, 0), o3, sh3,
                            pc_R.maps("t", ft), PBR,
                            ln.SOURCED_SIGMAS["kernel_radius"])
    out["far_stem"] = {
        "g2_pair": g2p, "g2_trio": g2t, "g2_ratio": g2t / g2p,
        "go_pair": gop["g"], "go_trio": got["g"],
        "go_reldiff": abs(got["g"] - gop["g"]) / gop["g"],
        "go_both_pair": gop["both_supported_pairpx"],
        "go_both_trio": got["both_supported_pairpx"],
        "gl_reldiff": abs(glt["g"] - glp["g"]) / glp["g"],
        "gp_tau_reldiff": abs(gpt["g"] - gpp["g"]) / gpp["g"],
        "gp_R_reldiff": abs(gpR_t["g"] - gpR_p["g"]) / gpR_p["g"],
        "conf_pair": ln.confidence_readout(fa, fb, (0, 0), (6, 0), o2, sh2),
        "conf_trio": ln.confidence_readout(ft, fb, (0, 0), (6, 0), o3, sh3)}

    # Bar sweep: distance discrimination + support-dependence across steps.
    steps = list(range(2, 13))
    ow, shw = sc.union_canvas(fa["image_shape"], (0, 0),
                              fb["image_shape"], [(s, 0) for s in steps])
    sweep = []
    for s in steps:
        g2 = sc.score_step(fa, fb, (0, 0), (s, 0), ow, shw, EA, EB)["g2"]
        go = ln.score_overlap_cosine(fa, fb, (0, 0), (s, 0), ow, shw)
        goa = ln.score_overlap_cosine(fa, fb, (0, 0), (s, 0), ow, shw,
                                      mode="all-channel")
        gl = ln.score_local_energy(fa, fb, (0, 0), (s, 0), ow, shw, LA, LB)
        gp = ln.score_pooled(fa, fb, (0, 0), (s, 0), ow, shw, PA, PB,
                             ln.SOURCED_SIGMAS["tau"])
        sweep.append({"step": s, "g2": g2, "go_per": go["g"],
                      "go_all": goa["g"], "gl": gl["g"], "gp": gp["g"],
                      "elbar": gp["ELbar"],
                      "both_union": gp["both_supported_pairpx"],
                      "go_max_term": go["max_term_cosine"]})
    out["sweep"] = sweep
    for key in ("g2", "go_per", "go_all", "gl", "gp"):
        out["spearman_%s" % key] = spearman(
            steps, [r[key] for r in sweep])

    # Oracle cross-check (independent implementation, same canvas inputs).
    cL, dL, sL, cR, dR, sR = stack_canvas(fa, fb, (0, 0), (6, 0), o2, sh2)
    ref = N.score_overlap(cL, dL, sL, cR, dR, sR)
    out["oracle_crosscheck"] = {
        "mine_per_channel": gop["g"], "oracle_overlap": ref["g2"],
        "reldiff": abs(ref["g2"] - gop["g"]) / gop["g"],
        "oracle_abstain": ref["abstain"]}
    cLt, dLt, sLt, cRt, dRt, sRt = stack_canvas(ft, fb, (0, 0), (6, 0),
                                                o3, sh3)
    reft = N.score_overlap(cLt, dLt, sLt, cRt, dRt, sRt)
    out["oracle_crosscheck_trio"] = {
        "mine_per_channel": got["g"], "oracle_overlap": reft["g2"],
        "reldiff": abs(reft["g2"] - got["g"]) / got["g"]}

    out["timing_s"] = {"fields_3x": t_fields,
                       "total": time.time() - t0}
    with open(os.path.join(RESEARCH, "run_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else "...")
                      for k, v in out.items()}, indent=2))
    print("far_stem g2_ratio %.12f go_reldiff %.3g gl_reldiff %.3g "
          "gp_tau_reldiff %.3g gp_R_reldiff %.3g"
          % (out["far_stem"]["g2_ratio"], out["far_stem"]["go_reldiff"],
             out["far_stem"]["gl_reldiff"],
             out["far_stem"]["gp_tau_reldiff"],
             out["far_stem"]["gp_R_reldiff"]))
    print("spearman g2/go_per/go_all/gl/gp:",
          ["%.4f" % out["spearman_%s" % k]
           for k in ("g2", "go_per", "go_all", "gl", "gp")])
    print("oracle reldiff pair/trio: %.3g / %.3g"
          % (out["oracle_crosscheck"]["reldiff"],
             out["oracle_crosscheck_trio"]["reldiff"]))


if __name__ == "__main__":
    main()
