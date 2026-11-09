<!-- cspell:words Cozens Kosch YinYangFit AtoKern atokern kerncritic badkerndetector kerndeterminer tensorfont hdf hdf5 h5dump nntools keras Keras TensorFlow ONNX WebGPU NumPy Conv1D Conv2D MaxPooling1D MaxPooling2D SpatialDropout2D softmax tanh ReLU Nakatsuru Uchida ResNet sidebearings opsz rd ri ca bd du ff cc zz npz urllib checkpoint checkpointer FT simoncozens yinyang fontfile kernmodel leftofo leftof lcontour rcontour bigram -->

# Learned alternatives linked from YinYangFit

Research only, 2026-10-31. **No Cozens model audited here is ready to replace the current delivered-bitmap spacing
model.** There is more recoverable material than an untrained architecture: a historical AtoKern checkpoint remains in
Git, and Cozens attached another model to an issue. However, the attachment is incompatible with the current
`kerncritic` executable, while the historical checkpoint predicts source kerning classes from contour profiles. Neither
establishes a calibrated score for unchanged 16 px Mono glyphs.

This report follows the neural alternative in [YinYangFit's prior-art section][yinyang]. It supplements the
[YinYangFit audit](yinyangfit-feasibility.md) and [pair-model survey](optical-spacing-pair-models.md); it does not
revive the survey's earlier CounterSpace recommendation as a new experiment. CounterSpace has already been reproduced
and assessed in source and delivered calibration domains. The supplied task context retains concerns about `bd`/`du`,
`ff`/`cc`/`zz`, and no clear overall preference for the bitmap-cell ablation over control B. These observations are
context, not results of this audit. Current controls and placement policy remain owned by the
[contextual-spacing design](../designs/text-layout/contextual-spacing-and-healing.md).

## Identity and inspection boundary

**Observed:** the article's “kerncritic (formerly AtoKern)” link resolves to [`simoncozens/atokern`][repository]. Its
current README and executable are named `kerncritic`; there was no redirect to a separate successor. The GitHub API
returned 404 for `simoncozens/kerncritic`. Inspected HEAD is **`6a315125d2b25548eb664bbae19e57c0b6d4b1d5`**, dated
2023-09-25. The available `master` and `generator` branches contain 62 reachable commits in total; release and tag
inventories were empty. These are bounded public-source observations, not proof that no private or unadvertised
successor exists. [Identity/API evidence][identity-evidence].

An author-repository search also found `kerndeterminer`, inspected at
[`ad6ecb397116519d15d4ae2370ead53ca1d5e7d3`][kerndeterminer]. It is a separate contour-distance Rust library, not a
neural successor; its README explicitly excludes Latin kerning. It does not provide a learned optical alternative for
Literata. No successor relationship was found in the inspected links.

**Executed:** source/ref inventories, bounded downloads, gzip decompression, HDF5 metadata and numeric weight reads with
the already-installed `h5dump`, and one original preprocessing helper using an existing Python environment. **Not
executed:** neural inference, training, model conversion, browser inference, candidate-distance search or optical
assessment. No dependencies were installed. Reference source, renderer, solver and preview stayed unchanged. All scratch
material is under [`out/diagnostics/contextual-spacing/yinyang-alternatives/`][evidence].

## Current kerncritic: real code, incompatible recovered weights

### Training and inference paths

The [CLI][cli] has an actual inference path: construct `tensorfont.Font(fontfile, 50)`, render `OH` + left glyph + right
glyph + `HO`, pad to **160 × 550 × 1**, clip intensity to `[0, 1]`, and call `load_model("badkerndetector.hdf5")`. It
expects two outputs: probabilities for tight/correct/loose and a scalar correction. It reports tight/loose probabilities
above a threshold, converting the regression result to an adjustment by `-prediction * 120`. It checks existing font
placement; it does not enumerate and optimize candidate integer placements. It also collects every requested pair image
before prediction, despite using prediction batches of 16.

The [training entry point][training] and [network helper][network] are substantive, not scoring stubs:

- Two 2 × 2 Conv2D layers, each with 16 filters, ReLU and 2 × 2 max pooling, feed a flattened image representation.
  Separate classification and regression branches each have two 32-unit dense layers, batch normalization, ReLU and
  dropout. Outputs are three-way softmax and one tanh scalar. Losses are categorical cross-entropy and MSE, with
  regression loss weighted by 10. These ordinary layers require no FFT, OpenCL or YinYangFit feature pipeline.
- A generated example uses the font's designed central pair distance, optionally perturbed by **40–120 font units** in
  either direction, scaled into raster pixels. The supplied labels identify the perturbation's sign and magnitude.
  Neutral source placement is assumed correct. This is supervision from font defaults plus synthetic errors, not expert
  judgments of low-resolution spacing.
- `write_data` thresholds cached images with `> 0.5`. Its invocations are commented out; training instead immediately
  loads `in-training.npz`, `out-training.npz`, `in-validation.npz` and `out-validation.npz`. Those files and the
  `fonts/training` / `fonts/validation` corpora are absent from the inspected repository. File lists, hashes, license
  provenance, seeds and a verifiable family-level split were not recovered.

**Source inconsistency:** the generator returns the raw integer perturbation as its regression target; the batch helper
does not divide it by 120. The model's tanh output is bounded to `[-1, 1]`, while the CLI assumes a normalized
correction and multiplies by 120. The absent cached labels could have been produced differently, but the checked-in path
does not demonstrate that. Training writes `output/kernmodel-cp-val.hdf5` and `output/kernmodel-final.hdf5`, whereas
inference requests `badkerndetector.hdf5`; no mapping from a completed training run to the distributed name is recorded.
[Generator and cache path][training], [batching, outputs and checkpoint path][network].

### What actually happened to the weights

The automatic model URL in the CLI, `http://dealer.simon-cozens.org/~simon/badkerndetector.hdf5`, returned **404** on
this audit. An HTTPS probe failed hostname certificate verification; it was not bypassed. Earlier
`www.simon-cozens.org/downloads/kernmodel.hdf5` URLs returned 404 over both HTTP and HTTPS. These are recorded access
results, not claims that every possible mirror is unavailable. [Current download probes][identity-evidence],
[earlier download probes][access], [earlier download instructions][old-readme].

Crucially, [Cozens's 2023-09-25 response (UTC) in issue #8][attachment-comment] links
[`badkerndetector.hdf5.gz`][attachment]. **The attachment downloaded successfully.** Its identity is:

```text
gzip bytes:       1,925,040
gzip SHA-256:     661e4b56c181ca3b70b390bc93c0bb34284179ac8d975a7ffffd4d3c453f59eb
HDF5 bytes:       2,130,008
HDF5 SHA-256:     1b24583ff059a00017e8f987fb20f91148a801257756fe88ae3428ca447db33f
```

**Observed incompatibility:** despite the filename, its saved Keras 2.2.2 graph accepts four **100-value vectors** named
`leftofo`, `leftofH`, `r_lcontour`, `l_rcontour`. It applies input batch normalization, concatenation, two 256-unit
dense layers with batch normalization/ReLU, and a **single linear scalar output**. It has no `string_image` input, image
convolutions, three-way category output or second correction output. Its training metadata records MSE and custom error
metrics. Consequently it cannot satisfy the current CLI's input/output contract merely by saving it under the expected
filename. This conclusion follows from the saved graph, not an attempted TensorFlow load.
[Downloaded metadata and graphs][model-metadata].

Numeric inspection found **172,353 finite model-weight values**, including batch-normalization state, and an Adam
iteration counter of 36,092. That is evidence of saved numerical state, not just a topology file; it does not identify
the training corpus or validate the model. A history search for `r_lcontour`, `max_abs_error` and `percent_within_5`
found no matching checked-in Python source across the available refs. Its exact preprocessing, target units and source
revision remain unresolved. Cozens himself cautions about its usefulness in the attachment comment.
[Weight inventory][weights], [source inventory][source-inventory].

**Disposition:** the current whole-image method is a research lead with genuine train/infer code, but no compatible
trained image checkpoint was verified. The attached contour regressor must remain a separate, unidentified artifact.

## Historical AtoKern: a recoverable trained baseline

The Git inventory contains a **different checkpoint**:
[`kernmodel.hdf5` at `206672c9ffce15710a02ac3f8fb58a9ee901e167`][historical-model], dated 2017-11-20, Git blob
`50462b5c8d5e249d1c6aae43374f277a754a3749`. It was removed from the tree in
[`3a64373c241fbdc03ca387c2f1fdb03d356f89d3`][removal], but remains retrievable from history. This audit extracted and
read it successfully:

```text
HDF5 bytes:       13,325,160
HDF5 SHA-256:     63d34d7eb5e1d8f8165468ddfc6789dbea6d3a5f00fc154e0858da00f049d599
```

Its Keras 2.1.1 graph takes six **100 × 1** profiles: the facing sides of the pair plus reference sides of `n`, `o`,
`H`, `O`. Each input passes through a two-filter, two-sample Conv1D, max pooling and flattening. Concatenation feeds
four 512-unit ReLU dense layers and a 26-bin softmax. All **1,102,910 model-weight values** are finite; stored Adam
iterations are 125,396. These are metadata/weight observations, not an inference or accuracy reproduction.
[Historical graph and weight inventory][historical-evidence].

The matching [inference script][historical-inference] constructs those six inputs and decodes bins into kern values
scaled by the font's `m` advance. The [preprocessor][historical-preprocessing] renders with FreeType Mono at nominal one
pixel per font unit, samples boundary distances into 100 rows and normalizes by `m` width. It therefore uses
high-resolution exterior profiles with sidebearings, not unchanged delivered 16 px cell images or internal counters. The
neural combination can depend on both profiles, but candidate relative placement is not supplied as a composed image or
an independent distance variable. It predicts a kern correction rather than a general spatial energy curve.

The [training script][historical-training] reads font kerning dumps, inserts zero labels for trusted unkerned pairs,
bins normalized kern values, applies bigram/class weighting and noisy augmentation, and calls `fit` with a 20% sample
validation split. This is source-default supervision. It does not demonstrate a held-out-family or optical evaluation.
The builder in that commit differs from the saved graph; the script loads an existing checkpoint when present. The saved
topology is consequently essential, and the file is not proof that training afresh from that builder reproduces it.
[Settings and bin definitions][historical-settings].

**Actual preprocessing probe:** importing the original helper succeeded in the already-existing CounterSpace Python
environment, but calling `get_m_width` on `fonts/Literata.ttf` failed because `FT_Get_Name_Index()` expects a binary
string and the source supplies a Python string. No compatibility patch was applied. Neither that environment nor the
default interpreter has TensorFlow, ONNX Runtime or h5py; the HDF5 inspection used the existing system tool.
[Recorded failure][preprocessing-probe].

**Disposition:** a recoverable source-kerning baseline, with actual weights and verifiable inference inputs. It is
neither a clean-run reproduction nor an optical spacing solution. It does not replace the information lost by reducing
glyphs to exterior profiles, and no evidence establishes arbitrary-style or low-resolution generalization.

## Browser and delivered-bitmap feasibility

The app keeps uploaded fonts local and renders through Rust/WASM in a dedicated Worker; see the
[web contract](../../apps/web/CONTRACT.md), [WASM interface](../../crates/wasm/README.md) and
[Worker implementation](../../apps/web/src/app/renderer/font-worker.ts). The following are **deployment inferences and
unresolved gates**, not completed ports.

### Input domain and calibration

- **Latest image approach:** a composed candidate image could expose true pair-specific spatial interaction, unlike a
  shared wall average. But its expected x-height is 50 pixels within a 160 × 550 frame. The inspected contemporaneous
  [`tensorfont` revision `74f1a5740ee5356f425378968997f811fd478074`][tensorfont-2019] produces 0–255 grayscale samples;
  clipping to `[0, 1]` and caching `> 0.5` effectively retain nonzero raster coverage as binary ink. Do not describe
  this as training on ordinary normalized antialiasing, or as training on this project's Mono scanner. The exact
  dependency revision used for a compatible checkpoint remains unknown because the [requirements][requirements] are
  unpinned.
- **Actual delivered cells:** padding 16 px glyphs into the training frame changes occupied scale dramatically.
  Enlarging their cells preserves the small raster's shape but does not recover the high-resolution source glyph used by
  the training pipeline. Re-rendering outlines at x-height 50 changes the object being judged. None has demonstrated
  calibration parity. Font-default labels also do not identify the preferred integer placement after hinting, raster
  changes and rounding at Literata `wght=400`, `opsz=16`, 16 px.
- **Historical/attached contours:** dimensions could be filled by resampling delivered walls, but doing so changes both
  sampling statistics and the learned meaning of scale/sidebearings. The historical `m` normalization and explicit
  `n/o/H/O` references require a defined missing-glyph policy. The unidentified attachment lacks even a verified
  normalization rule. Weight availability does not justify such an adaptation.
- **Style and training:** the intended deployment is a fixed model trained across fonts, with font-specific
  preprocessing/context, rather than training a new network for every upload. No per-font fitting algorithm is supplied
  for these checkpoints. New per-font training would require labels, an optimizer and resource evaluation; training
  against the upload's defaults would still supervise source imitation. Coverage across italics, variable-axis
  locations, scripts and unusual designs is unverified. Arbitrary uploads require explicit unsupported-input fallbacks.

### Runtime, operations and caching

The recovered graphs use dense, convolution, pooling, activation, concatenation and, for the attachment,
batch-normalization operations. They require no FFT. A port is plausible in principle: TensorFlow.js documents
[Keras HDF5 conversion with operation checks][tfjs], and ONNX Runtime documents [browser WASM/WebGPU inference][ort] and
[Worker/runtime asset deployment][ort-deploy]. **No conversion or operation coverage was tested for these legacy
checkpoints.** ONNX would first require a verified export; a Rust/WASM runtime would require equivalent model and
preprocessing code. Existing font WASM does not automatically run Python/Keras.

The historical checkpoint contains 4,411,640 bytes of float32 inference weights, while the attached model contains
689,412 bytes; their larger HDF5 files also hold optimizer state. These exact tensor byte counts come from the
[inventory][weights], not browser memory measurements. Actual peak memory includes runtime, activations, inputs, copies
and optional GPU buffers. The current CLI's all-pairs image collection scales with the square of repertoire size; an
integer-candidate search would multiply inference work further. Browser startup, throughput, memory, conversion parity
and backend stability are unknown. WebGPU support must be checked on target browsers; it is not a universal substitute
for a WASM path. [Runtime provider documentation][ort].

**Possible project adaptation, not implemented:** for a recovered image classifier, compose unchanged delivered cells at
each legal integer origin step and evaluate them in a fixed reference context. A rule such as maximizing its neutral
class probability would be a new selection policy requiring validation; a diagnostic classifier does not itself provide
a calibrated optical objective. Fix evaluation mode, input composition, candidate order and tie handling, and verify
repeatability/native-export parity before relying on candidate rankings. GPU numerical differences near a tie must not
silently change integer placement.

The existing placement policy remains independent: allow contact, reject occupied-cell overlap and same-row wall
inversion, preserve fixed-pitch/tabular cases and unsupported-input fallbacks, and keep delivered pixels unchanged.
Clipping an invalid neural prediction establishes safety, not optical correctness. Preserve control B,
`hu_fitted_full_density_conserved_touch`, and keep problem pairs outside calibration.
[Policy owner](../designs/text-layout/contextual-spacing-and-healing.md#touching-clearance-candidate).

Static final-pair tables could cache successful inference for a particular font and rendering state. A shipped table for
known fonts cannot cover arbitrary uploads: those need local inference or an explicitly authorized local fitting path
before caching. Cache identity would need font bytes/face, axes, size, fitting/scanner state, model/preprocessing
version and placement policy. Changing size or axes invalidates the corresponding result. Caching reduces repeated work;
it cannot supply missing weights or demonstrate domain validity.

## Learning to Kern: comparison boundary

[Nakatsuru and Uchida, v2, 2024-04-28][learning], sections 3–4, describe ResNet18 image features and pairwise or
set-wise Transformer prediction. Their inputs are binary 256 × 256 glyph images with font-wide scaling and baseline
normalization; labels are default centre-of-ink distances, not perceptual ratings. The 2,558-font corpus is split by
family, unlike the historical sample split above. Its normalization and 52-letter set are not a demonstrated 16 px
delivered-cell pipeline. Section 6 calls for expert subjective assessment.

The inspected [v2 HTML][learning] and [arXiv record][learning-record] provide the paper and source/PDF links but no
identified author model checkpoint or executable implementation. A bounded repository-title search did not recover the
authors' artifacts; it is not an exhaustive availability proof. Fetching Uchida's linked publications page timed out, so
that avenue remains unchecked. Do not promote the paper into a ready library or transfer its font-default accuracy to a
promise of better optics. A paper license also does not establish a code/weights license.

## License, readiness and next test

The current [AtoKern README][license] supplies MIT permission for software and documentation with notice retention. The
historical checkpoint's provenance is its exact Git blob; the other checkpoint's provenance is Cozens's issue
attachment. Neither recovered model has a model card identifying the training-font corpus, hashes, label preparation or
separate weight-specific terms. The [historical README][historical-readme] has no license section. Code permission does
not by itself establish provenance and redistribution rights for every training font or resolve the precise checkpoint
terms; those remain to be clarified before shipping model assets.

Ranked by **reproduction readiness**, not optical merit:

1. **Historical AtoKern checkpoint:** best recoverable executable baseline; saved graph, weights and matching inference
   inputs exist. Needs compatible runtime/preprocessor verification and source-label provenance. It predicts kerning
   classes from profiles, so it does not meet the delivered-image scoring goal.
2. **Current kerncritic image method:** the strongest conceptual fit among these Cozens paths for spatial scoring of
   composed glyphs, but blocked by a missing compatible checkpoint/data and unresolved regression-target scaling.
   Reimplementing training is a research project, not routine integration.
3. **Issue attachment contour regressor:** numerical trained state exists, but no matching preprocessing/revision was
   recovered. Its misleading filename is insufficient to make it usable by the current CLI.

Learning to Kern remains a paper-level comparator in this audit. CounterSpace is an already-tested control;
`kerndeterminer` is not a Latin neural alternative. **None is currently recommended as a replacement.**

One concrete next test is **an original-domain recovery smoke test of the 2017 checkpoint**, before any delivered-bitmap
adaptation: in an isolated compatible environment, load the saved graph for inference without recompiling its custom
training loss; disclose the minimal string/bytes compatibility repair; generate the six original 100-row profiles from a
hashed, licensed upright font; verify finite, repeatable 26-bin outputs and bin decoding against the original inference
script. Retain the inputs and outputs as fixtures for any later browser export. Stop if the saved input contract cannot
be reproduced. This would establish a source-default control only, not pair-energy scoring, better optics or 16 px
acceptance. Prioritizing the newer image method instead first requires its actual compatible image checkpoint and
preprocessing/label provenance; renaming the issue attachment cannot satisfy that gate.

Evidence can be re-inspected without TensorFlow or any installation:

```sh
h5dump -A out/diagnostics/contextual-spacing/yinyang-alternatives/badkerndetector.hdf5
h5dump -A out/diagnostics/contextual-spacing/yinyang-alternatives/atokern-2017/kernmodel.hdf5
```

[yinyang]: https://skosch.github.io/YinYangFit/#prior-art
[repository]: https://github.com/simoncozens/atokern/tree/6a315125d2b25548eb664bbae19e57c0b6d4b1d5
[cli]: https://github.com/simoncozens/atokern/blob/6a315125d2b25548eb664bbae19e57c0b6d4b1d5/kerncritic#L28-L108
[training]: https://github.com/simoncozens/atokern/blob/6a315125d2b25548eb664bbae19e57c0b6d4b1d5/badkerndetector.py#L7-L113
[network]: https://github.com/simoncozens/atokern/blob/6a315125d2b25548eb664bbae19e57c0b6d4b1d5/nntools.py#L52-L200
[old-readme]: https://github.com/simoncozens/atokern/blob/ce5f46bea6f6b33d06b8f4c4e039e85b375c76d0/README.md
[attachment-comment]: https://github.com/simoncozens/atokern/issues/8#issuecomment-1734010948
[attachment]: https://github.com/simoncozens/atokern/files/12717156/badkerndetector.hdf5.gz
[historical-model]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/kernmodel.hdf5
[removal]: https://github.com/simoncozens/atokern/commit/3a64373c241fbdc03ca387c2f1fdb03d356f89d3
[historical-inference]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/neural-kern.py
[historical-preprocessing]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/sidebearings.py#L69-L176
[historical-training]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/atokern.keras.py#L100-L217
[historical-settings]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/settings.py
[tensorfont-2019]: https://github.com/simoncozens/tensorfont/blob/74f1a5740ee5356f425378968997f811fd478074/tensorfont/__init__.py#L145-L219
[kerndeterminer]: https://github.com/simoncozens/kerndeterminer/blob/ad6ecb397116519d15d4ae2370ead53ca1d5e7d3/README.md
[tfjs]: https://www.tensorflow.org/js/guide/conversion
[ort]: https://onnxruntime.ai/docs/get-started/with-javascript/web.html
[ort-deploy]: https://onnxruntime.ai/docs/tutorials/web/deploy.html
[learning]: https://arxiv.org/html/2402.14313v2
[learning-record]: https://arxiv.org/abs/2402.14313v2
[license]: https://github.com/simoncozens/atokern/blob/6a315125d2b25548eb664bbae19e57c0b6d4b1d5/README.md#licence
[evidence]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/
[identity-evidence]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/access-inventory.json
[access]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/extra-access-inventory.json
[model-metadata]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/model-attributes.txt
[weights]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/weight-inventory.json
[source-inventory]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/source-inventory.json
[historical-evidence]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/atokern-2017/model-attributes.txt
[preprocessing-probe]: ../../out/diagnostics/contextual-spacing/yinyang-alternatives/source-preprocessing-probe.json
[requirements]: https://github.com/simoncozens/atokern/blob/6a315125d2b25548eb664bbae19e57c0b6d4b1d5/requirements.txt
[historical-readme]: https://github.com/simoncozens/atokern/blob/206672c9ffce15710a02ac3f8fb58a9ee901e167/README.md
