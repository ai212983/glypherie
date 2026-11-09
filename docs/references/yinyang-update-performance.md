# YinYang update-performance investigation

Assessment: 2026-11-05. Research only; the active experiment was not changed.

This is the original research record. Subsequent implementation, measured browser results and current adoption state
are in the [owning design](../designs/text-layout/contextual-spacing-and-healing.md#yinyang-update-performance-implementation).

The recommended order is to stop redundant and superseded field work, optimize the exact scoring kernel, then address
glyph-cache capacity within a measured memory budget. A worker pool is a later option. There is no verified whole-page
speed-up factor yet.

Three Muse lenses investigated scoring, worker/cache orchestration, and field rendering. One independent Argon review
supplied additional hypotheses and a native prototype. A subsequent Muse check rejected unsupported claims and verified
a bounded subset of the prototype's numerical behavior.

## 1. Avoid field work that cannot help the current view

The default Roboto 16 text requests 94 pair-map occurrences but has 78 unique maps. Deduplicate requests by their
complete computation identity and share the result between placements. This removes 16 duplicate computations, not 17%
of the entire update. The mechanism is present in
[`requestFieldLayers`](../../experiments/contextual_spacing/yinyangfit_interactive_v3_wiring.js).

The worker receives many separate field jobs. Cancellation messages cannot interrupt a synchronous WASM call, and
superseded batches can keep calculating before those messages are processed. In a browser trace, a target change
cancelled and sent 95 field jobs again. Submit a cancellable batch instead, yield between bounded operations, coalesce
rapid changes, and check the generation before starting the next operation. Keep immediate ink updates and label fields
as updating until the current generation is painted. Do not present stale fields as current. The implementation seam is
the existing [`worker`](../../experiments/contextual_spacing/yinyangfit_interactive_v3_worker.js), not a new renderer.

Also skip field extraction while **Show fields** is off. Restore cached fields when available, otherwise calculate them
on demand. Hiding and showing an already-cached view should remain a repaint-only operation.

These changes preserve scoring and final field values. Verify actual executed jobs, superseded jobs, generation
completion, and displayed pixels; fewer posted messages alone do not establish less work.

## 2. Optimize the exact scorer

[`score_step_local`](../../experiments/contextual_spacing/oriented_engine/src/local_energy.rs) has two passes that
evaluate the same exponential. A scratch implementation combined the passes, indexed the glyph arrays directly, and
restricted traversal to the glyph-lattice intersection. Outside that intersection, at least one support mask is false.
Preserve the original contributing-pixel order, multiplication association, eligibility rules, and diagnostic outputs.

The native prototype measured 7.736 versus 3.758 ms per step on one fixture (43 steps, one timing run). Muse
independently reproduced bit-identical score fields and maps on 12 synthetic steps spanning six regimes. This supports a
small implementation experiment; it is not a measured full-page or WASM gain. Intersection bounds remove skipped
iterations; fusion, separately, removes the duplicate exponential evaluations.

The map path also repeatedly embeds arrays inside its orientation loops. Hoisting or directly indexing those inputs is a
related candidate. Preserve all diagnostics in the first implementation rather than deleting a diagnostic merely because
its ordinary inputs make it zero.

Before adoption, compare the actual changed runtime with the current one on captured Mono/Gray glyphs, boundary
settings, overlap/abstention cases, map reductions, and target/tie selection. Then measure the same complete browser
workload with the same build flags. Do not multiply independent small benchmarks into a whole-page prediction.

## 3. Address cache churn with a memory budget

The engine's [`glyph LRU`](../../experiments/contextual_spacing/oriented_engine/src/engine.rs) holds 32 entries; the
default sample uses 46 distinct glyphs. Eviction discards fields and local-energy maps. The capacity mismatch is
confirmed, but exact rebuild totals depend on request order and must be instrumented.

Do not blindly raise the limit to 128. The structural estimate is approximately 3.85 MB per entry at a representative
lattice size: about 177 MB for 46 entries or 493 MB for 128, before additional workspace and page costs. These are
analytic estimates, not measured resident memory; larger reach increases lattice sizes. Measure WASM memory and peak
scratch usage, then use a bounded byte budget and an appropriate working-set policy. Cancellation and worker restarts
must remain safe.

## 4. Consider two workers after the preceding changes

An actual-worker prototype scored eight pairs in 6.63 seconds with one worker and 3.30 seconds with two, with identical
values across 455 steps. This was one run on a loaded host; an uncontrolled larger run showed little improvement. It
does not establish full-preview scaling.

A separate engine per worker can preserve per-pair arithmetic and work with the existing offline Blob-worker deployment.
Costs include duplicated glyph data, memory, scheduling, and cancellation across workers. Measure the full workload and
memory before adopting a pool. Shared-memory WASM threads would require a different isolation/deployment contract; see
the primary [Web Workers documentation](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API) and
[shared-memory security requirements](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer#security_requirements).

## Lower priorities and rejected claims

- Canvas-loop measurements were about 11–12 ms using a recording stub, excluding browser rasterization. A single-buffer
  prototype reduced that to about 6 ms, with up to one color-level difference. It is not the principal explanation for
  minute-long updates and needs browser validation before adoption.
- The current Class L path already computes only the requested strength. The claimed unused second-strength pass, extra
  twofold saving, combined fourfold gain, and whole-update projections derived from it are rejected.
- The claimed 170 ms Gray paint slowdown confused a glyph-build outlier with painting. The proposed causal explanation
  was not established.
- Build flags, SIMD, FFT-transform reuse, and pre-normalized factors remain candidates rather than measured page
  improvements. Changing arithmetic operation order needs explicit numerical and near-tie checks.
- Non-monotone curves prevent an unproved binary-search shortcut. Do not shorten the search domain, change coverage, or
  substitute approximate scores silently.

## Evidence and identity

The live page remained `04c0cb9f4bc65e8298084222f1e01c1c9f8c6c04fbd672b6f0364def2eb4a483`; both WASM packages remained
`74f4f452de44dcc1fd5fcdb7cf7f7b0814910b834a80c358553ae9a4033a1476`. The work concerns the oriented fields, Class L
score, and search-v2 implementation. Default tables avoid recomputing scores; target-only derivation must not be
benchmarked as a fresh geometry search. Retired 0–150-step benchmarks are unsuitable for current whole-page estimates.

Detailed reports, raw measurements, prototypes, and reproduction commands:

- [Scoring lens](../../out/diagnostics/contextual-spacing/yinyang-update-performance/compute/REPORT.md)
- [Worker/cache lens](../../out/diagnostics/contextual-spacing/yinyang-update-performance/worker-cache/REPORT.md)
- [Fields/rendering lens](../../out/diagnostics/contextual-spacing/yinyang-update-performance/fields-render/REPORT.md)
- [Single Argon review](../../out/diagnostics/contextual-spacing/yinyang-update-performance/argon-review/REPORT.md)
- [Independent Muse claim check](../../out/diagnostics/contextual-spacing/yinyang-update-performance/muse-claims-check/REPORT.md)

Timings vary with workload, build, and host load. Tests establish mechanical equivalence, not optical quality. No model
or live implementation change is proposed as already completed by this investigation.
