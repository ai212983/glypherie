<!-- cspell:words YinYangFit yinyangfit Kosch Colab PyTorch CUDA OpenCL MPS gputools tensorfont nptyping torchdiffeq cufft ipynb pth loggabor softplus Gabor randn randn_like einsum numel bdsophw bdgophw atemplate traw pars sigmas skimage uharfbuzz fontParts booleanOperations defcon ufo extractor ufo2ft float32 complex64 int64 fft ifft fftshift pinverse cu101 nn Bokeh logits state_dict register_buffer map_location safetensors xheight skosch simoncozens ca40a torchvision symref ppem sidebearings Harf pseudoinverse backpropagates ckpt onnx lockfiles hyperparameters autograd odeint dtypes nonconstancy nonfinite predeclared freqs Mises -->

# YinYangFit training requirements for Glypherie

Research only, 2026-11-01. **Do not start training or adapt the preview yet.** The smallest defensible next step is a
pinned, isolated recovery of the historical Torch scorer, with a numerical and deterministic-inference gate before an
optimizer run. Training the current JAX notebook is not a specified task: it lacks a scalar objective, loss and export.
Recovering the historical model would imitate one font's designed spacing, not establish an optical spacing oracle.

This report supplements [the feasibility audit](yinyangfit-feasibility.md), which owns the existing feasibility decision
and approved baseline. No renderer, solver, preview, dependency, existing research note or retained upstream checkout
was changed. No training, dependency installation, full model execution or hardware benchmark was performed. The host
independently checked the local hardware inventory and the principal tensor-size arithmetic below.

## Evidence and source identity

**Verified** means directly read in pinned primary source, fresh remote metadata, or reproduced by the stated static
probe. **Inference** means derived requirements or estimates, not execution evidence. **Unknown** means unresolved; in
particular no mechanical result here establishes optical acceptance under [the evaluation rules](../evaluation.md).
Notebook cell numbers below are zero-based.

- Fresh `git ls-remote --symref` returned HEAD and the only branch, `master`, at
  `609d17e8a6446ec4413a1b02a0768b8214d73333`, no tags, and six pull-request refs. The GitHub pull metadata and file
  lists identify all six as merged dependency updates changing only `web/static/js/yarn.lock`. They provide no training
  recovery. The releases API returned an empty list. These observations are time-specific; they do not cover forks,
  deleted/unadvertised refs, local author files or external storage. See [the pinned tree][head] and local evidence.
- Historical source is **only** [d9c7e2580f2ad4884c45e5081e8e4613b86632cf, `YinYangFit.ipynb`][torch]. It was extracted
  with `git show`, without checkout mutation. Its SHA-256 is
  `078e9dda8c5217bc064f1b1b09f03e83fb2be03e7322885594eb2b5d50d59ba6`. HEAD's notebook SHA-256 is
  `63f7be83b90aad5cc1c29be53197d78bafd14dff7fa84c797345390195198a91`.
- The primary written reference is Kosch's provisional, unfinished article, whose [abstract and status][frontmatter]
  explicitly describe fitting to existing hand-fitted fonts. Its [pinned algorithm section][algorithms] proposes a
  neighboring-cost training loss, while the historical notebook implements a different hybrid loss. These are distinct
  specifications. No separate completed YinYangFit training paper or reproducibility package was established by this
  bounded search. Neuroscience citations in the article do not supply a trained spacing model.
- The [current notebook][jax], cells 5–23, computes features; cells 24–25 translate glyph fields and plot distance and
  orientation agreement for the final pair of `test`. It has six V1 scales, eight axes and 29 glyphs. There is no scalar
  scoring reduction, gradient training or checkpoint export. **Do not substitute the historical sum/loss into JAX, sum
  the displayed mask, or blend its scales with the Torch model and call that reproduction.**

Diagnostic evidence is confined to
[`out/diagnostics/contextual-spacing/yinyangfit/training-audit/`](../../out/diagnostics/contextual-spacing/yinyangfit/training-audit/):
`remote-refs.txt`, GitHub metadata/file lists, original notebook copies, cell-source and retained-output extracts,
`git-objects.txt`, pinned dependency-source copies, `static_probe.py` and `static-probe.json`. The probe uses Python's
standard library, AST inspection, exact rational algebra and shape arithmetic; it never imports the model. Retained
notebook outputs are author-produced historical evidence, not execution reproduced here.

## Minimum original-domain reproduction

### Inputs, images and labels

**Verified, historical cells 3–5 and 10–12:**

1. Download Crimson Roman OTF and use `Font("CrimsonRoman.otf", 34 * factor)`, with `factor = 1`. Crimson Italic is also
   downloaded but is not used by this dataset. Active glyphs are exactly lowercase ASCII `a`–`z`; ordered Cartesian
   pairs include identical pairs, giving 676 training items. Other fonts and uppercase glyphs in comments are not
   training coverage. The download URLs target mutable `master`, with no recorded font hash. [Source][torch]
2. `34` is a requested **x-height**, not 34 ppem or a 34-pixel image height. The candidate historical tensorfont source
   sets an em pixel size using a monochrome rendering of `x`, then renders glyphs through FreeType. It places grayscale
   coverage in an ascender/descender box, divides by 255, pads each glyph horizontally using ceiling/floor half-padding,
   and the notebook converts to float32. The retained notebook reports **80 × 161 pixels**. This is not a 1-bit
   delivered-bitmap corpus. [Tensorfont sizing/rendering][tensorfont-old]
3. The notebook negates normalized glyph images before V1 filtering, uses a complex64 filter bank on a zero-padded **160
   × 322** FFT domain, then crops the responses to 80 × 161. It caches responses for all 26 individual glyphs. Pair
   generation shifts these filtered responses horizontally with integer offsets and zero fill; it does not rasterize a
   newly shaped pair at every candidate. This ordering, cropping, baseline and sign are part of the model input and must
   survive recovery. [Cells 5, 11–12][torch]
4. Define the font-relative center as `d0 = int(f.pair_distance(left, right) + f.minimum_ink_distance(left, right))`.
   Five candidates are **pixel deltas `[-3, -1, 0, 1, 5]` around `d0`**, with class index **2** designated correct. The
   declared multiplicative candidates `[0.8, 1, 2]` are unused by the training dataset. Left/right translations split
   candidate distance with ceiling/floor and account for both ink widths and minimum ink distance. Persist the actual
   integer translations, metric terms and rounding, not just the nominal deltas. [Cells 4, 10–12][torch]
5. In the candidate historical tensorfont implementation, `pair_distance` adds rendered sidebearings and optional
   kerning; `minimum_ink_distance` uses facing contours. Kerning uses FreeType when available and otherwise the HarfBuzz
   difference between enabled/disabled kerning. API prose calls some quantities font units, while the implementation
   combines pixel-scale metrics. **Validate units and shaping for the recovered font/dependency build; do not interpret
   this as a universal outline-distance label.** [Source][tensorfont-old]

**Unknown:** the exact OTF bytes and tensorfont wheel used in the recorded run. The latest tensorfont repository commit
not later than 2021-04-01 is `ca40a251693022a86eff63301dbae45ec27b608e` (declares version 0.0.8); Crimson's
corresponding candidate commit is `685b5a2478a7213a806e9bbf1e36f6a9e7f5c7ef`. These are recovery candidates, not
recovered execution provenance. [Tensorfont][tensorfont-old-setup], [Crimson tree][crimson]

**Inference:** the training signal is imitation of the rasterized source font's designed spacing, including whatever
kerning that dependency computes. It contains neither reader preferences nor independent judgments of the optimum for
small delivered bitmaps. A low training loss proves neither new-font generalization nor optical correctness.

### Features, scalar penalty and optimization target

**Verified, cells 4–9:** ten V1 scales and eight orientation axes; B responses double orientations to 16 and separate
four rectified real/imaginary sign phases. G has ten scales and four phases. Batch is one pair with five candidates.
`scale_factor = 0.02`, `scale_base = 30 ** (1/13)`, V1 scale values are `0.02 * scale_base ** s`, `s = 0..9`
(approximately 0.0200–0.2107). The V1 grid normalizes its axes by box height/width, uses a fixed log-Gabor expression,
low-pass cutoff 0.9, bandwidth constant 0.75 and angular concentration 8. G ring and ray masks use triangular radial
profiles from the same scale progression, angular concentration 16 and reversed scale order. `n_b_scales` and
`n_v4_scales` declarations do not add trainable layers. These are historical implementation choices; do not replace the
filter formula with another conventional log-Gabor expression during reproduction. [Source][torch]

For each candidate the model recomputes B/G responses for the left glyph, right glyph and their sum. G outputs are
scaled by `1/50` and transformed using learned saturation/exponent fields. The score adds positive learned weights times
(1) losses of either separate response relative to the pair and (2) pair response above the maximum separate response.
It sums over G scales, phases, height and width to return `[batch, 5]` scalar penalties. The variables called gain and
loss here are score terms, distinct from the optimizer loss. [Cells 7–9][torch]

**Verified, cell 13:** the optimizer loss branches on strict comparisons of the five penalties in row zero. For three
single-valley sign patterns, it fits a cubic by pseudoinverse to the five `(delta, penalty)` samples, computes the two
stationary roots and squares the selected positive-curvature root's displacement from zero. Otherwise it uses
cross-entropy of **negative penalties** with target index 2. There is no single standard regression/MSE objective to
substitute; the curvature branch and class branch have different meanings and units. The article's maximum difference
between center and neighbor costs is a proposal, not this implementation. [Notebook][torch], [article][algorithms]

**Verified, cell 14:** shuffled `DataLoader`, batch size 1, default worker settings, Adam with learning rate **0.0011**
and other settings left to the installed PyTorch defaults. Up to **5,500 epochs**, 676 optimizer steps per epoch: a full
loop would be **3,718,000 steps**, with **18,590,000 candidate presentations**. Each step evaluates the three separate/
paired branches, backpropagates once and updates once. There is no scheduler, validation split, early stopping or
periodic checkpoint. Plotting/Colab clearing occurs every ten batches; the 2,000-batch reporting branch cannot fire
inside a 676-batch epoch. Retained output ends in `KeyboardInterrupt`, not completed training. The epoch count is a loop
limit, not an evidence-backed convergence requirement. [Source and retained outputs][torch]

### Parameters and gradients

**Verified declarations and inferred score reachability:** `static-probe.json` enumerates each constructor declaration.
There are **1,416 registered scalar parameter entries**, of which **760 enter the returned score** by source tracing.
This is an AST/math count, not a measured `numel()` or verified backward pass.

| Module/fields                                                                                                | Shape/entries                    | Role                                           |
| ------------------------------------------------------------------------------------------------------------ | -------------------------------- | ---------------------------------------------- |
| B/G `b_to_g`                                                                                                 | `[10,10,4]`, 400                 | Scale/phase mixing, softplus and normalization |
| B/G `G_input_weight`, `ray_weight`, `k`, `b`                                                                 | 10 each, 40 total                | Input/ray weighting and divisive normalization |
| B/G `amplification_saturation`                                                                               | `[10,16,1,1,1]`, 160             | Feedback exponent                              |
| G targets `general_exp`, `loss_b`, `loss_factor`, `gain_factor`                                              | `[10,4,1,1]`, 40 each, 160 total | Active nonlinear score fields                  |
| G targets `target_*`, `tolerance_*` (five each), `loss_original_exponent`, `gain_k`, `traw`, `gain_exponent` | 14 fields × 40, 560 total        | No path into returned penalty in this revision |
| G targets `pars`                                                                                             | `[3,1,1,1,4,1,1,8]`, 96          | Unused                                         |

`traw` participates in a computed `tp` that is unused. `target_a` and `tolerance_a` wrap the same initial `atemplate`
storage as separate Parameter objects; both are inactive. Preserve this distinction when inspecting old state rather
than using comments' stale parameter counts. Filters, radial scales and V1 preprocessing are fixed, not learned. Require
a later gradient census: all expected active fields have finite gradients; all inactive fields are explicitly accounted
for. A score path alone does not prove a nonzero derivative on every sample. [Cells 5–9][torch]

The active initial values are: scale mixing is an identity matrix replicated across four phases; G input weights 1, ray
weights 0.2, amplification saturation 0.7, normalization `k=0.25` and `b=0.55`; the latter two and G input weights are
multiplied by 10 in forward. Active target fields initialize `general_exp=3.5`, `loss_b=0.1`, `loss_factor=0.1` and
`gain_factor=0.1`, all per scale/phase. Most positive constraints use softplus with beta 1000; amplification uses
beta 100. These are initializations, not recovered trained values. [Cells 7–8][torch]

For exact fixed-filter recovery, retain the source expression `exp(-log(unit_freqs / sigma)**2) / (2*log(0.75)**2)` with
DC zeroed, the low-pass factor `1 / (1 + (unit_freqs/0.9)**20)` and angular von Mises factor of concentration 8. G
radial breakpoints are `r[i] = 0.02 * scale_base**i`; each ring triangle uses `(r[i], r[i+1], r[i+2])`, each ray
triangle uses `(r[i], r[i+3], r[i+4])`. Their angular concentration is 16, with opposed half-orientation fragments; each
fragment is normalized across orientation/spatial dimensions with multiplier 4 and epsilon `1e-10`, clipped to `±1e12`,
then reordered by scale. V1 uses a grid normalized by height and width; G uses height for both axes. These differing
normalizations matter for rectangular boxes. [Cells 5–6][torch]

## Randomness and evaluation

**Verified:** imports call Python `random.seed()` without a fixed seed; there is no recorded PyTorch or NumPy seed.
Shuffling changes the pair order. B/G forward adds detached Gaussian perturbations proportional to positive activity or
parameters: B activation `/36`, G input weight `/36`, amplification saturation `/48`, and normalization exponent/offset
`/46`. Normalization draws separately for actual and pretend-zero-competition responses. The left, right and paired
branches each draw again. No `self.training` condition exists: **`eval()` alone does not disable this noise**.
[Cells 2, 7, 14][torch]

**Required policy, not an upstream result:** record Python/NumPy/Torch CPU and accelerator RNG states, the shuffle
source, operation determinism settings, dependency/device versions and resume state. PyTorch explicitly limits
reproducibility across versions/platforms. [Pinned PyTorch guidance][randomness]

Separate faithful stochastic reproduction from useful deterministic scoring. Removing forward noise or replacing it by a
fixed seeded Monte Carlo average changes evaluation; disclose and compare that choice before adoption. A single fixed
global seed still gives order-dependent outputs as the RNG advances. Browser inference needs a noise-free policy or an
exactly specified per-input seeded protocol, plus repeated-call and pair-order tests. Never select a favorable seed
using the held-out pairs.

## Repairs and prerequisites before any gradient step

These are requirements for a separately authorized recovery experiment; no repair was made here.

1. **Select/pin one model and recover inputs.** Extract the historical code into an isolated maintained experiment only
   after authorization, remove notebook magics/Colab-only display assumptions from execution, and lock font bytes,
   libraries and rasterizer. Either demonstrate the historical environment or record a compatibility port with input/
   score parity boundaries. Do not run the mixed later notebook or the package engine as the trainer. [Notebook][torch]
2. **Make the chosen device path executable.** Guard/remove CUDA housekeeping on CPU. Training unconditionally invokes
   `T.backends.cuda.cufft_plan_cache.clear()`, whose implementation resolves a CUDA device; selecting `dev='cpu'` does
   not prevent that call. Register fixed tensors as buffers or reconstruct them explicitly on the selected device; plain
   tensor attributes do not acquire reliable migration/serialization merely by wrapping the object in a module.
   [Notebook][torch], [cuFFT implementation][cufft], [state serialization][serialization]
3. **Resolve old dependency API incompatibilities.** The candidate tensorfont imports `skimage.util.pad` and uses
   `np.float`; scikit-image 0.18 deprecates that import for removal in 0.19, and NumPy 1.24 no longer supplies that
   alias. Pin compatible versions or make separately documented compatibility edits with raster/metric parity. Current
   tensorfont HEAD has substantial kerning and variation changes; installing it silently is not a historical recovery.
   [Historical implementation][tensorfont-old], [padding transition][skimage], [NumPy source][numpy],
   [current implementation][tensorfont-new]
4. **Gate the cubic loss numerically.** Exact rational fitting of penalties `[9,1,0,1,25]` at the prescribed deltas
   gives the valid quadratic `x²`, enters `inv2`, and yields zero cubic coefficient: the notebook's root formula divides
   by zero. Floating-point rounding may instead produce a tiny coefficient and unstable roots. There are also no guards
   for discriminant, finite roots, near-zero curvature or roots outside the candidate range. Add detection and stop
   diagnostics first; selecting a fallback or changing loss requires an explicit model decision, not a hidden fix. This
   audit proves the algebraic missing guard, not that a real first pair necessarily triggers it. [Cell 13][torch]
5. **Keep batch size one until the loss is redesigned.** Cubic fitting reads only `p[0]`; the fallback constructs a
   one-item target. Increasing the batch declaration is not supported training. Disabling extensive plotting/logging is
   an operational change; retain diagnostic records. [Cells 13–14][torch]
6. **Audit suspicious semantics before claiming correctness.** The ray-convolution code rolls a six-dimensional
   `[batch,distance,scale,orientation,height,width]` FFT tensor on dimension `-4`, which is **scale**, despite nearby
   orientation language. Preserve the operation for a faithful run or declare a model correction and evaluate it
   separately. Do not silently repair it to improve output. Likewise enforce no unintended clipping, all five distinct
   realized placements and finite intermediate scores before backward. [Cell 7][torch]

The current package engine has an additional zero-field stub and early selector break, documented by the feasibility
audit. Those are not blockers to the self-contained historical notebook, nor does repairing them create the JAX loss.
[Engine][engine]

## Save/load, recovery and deterministic browser inference

**Verified:** cell 14 saves only `yinyangfit.state_dict()` to `./yinyangfit.pth`, after the entire epoch loop. There is
no checkpoint-loading path, optimizer/RNG save or interruption recovery. Its retained `KeyboardInterrupt` does not
establish that this save executed. The local `git rev-list --objects --all` path inventory contains no conventional
`.pth`, `.pt`, `.ckpt`, `.pkl`, `.pickle`, `.npz`, `.npy`, `.h5`, `.safetensors` or `.onnx` checkpoint. Fresh public
releases are empty; advertised PR refs change web lockfiles only. **No usable historical state was recovered.** This is
a bounded negative search, not proof that the author has none. [Notebook][torch]

A historical `.pth`, if supplied later, must match this architecture, parameter names/shapes and input provenance. Its
plain tensor attributes (G masks, FFTs, grids and unused `g_scales`) are not registered buffers. A state dictionary
alone therefore does not contain the full executable scorer configuration; rebuild fixed tensors with identical globals
and verify golden inputs/scores. Load trusted state with explicit device mapping and the applicable restricted weight
loader, rather than assuming an arbitrary pickle is a safe portable artifact. [Serialization][serialization]

**Required for new runs:** periodic atomic checkpoints containing weights, optimizer state, epoch/batch position,
shuffle/RNG state, hyperparameters, data/split hashes, model/source hash and evaluation-noise policy; a round-trip test
must reproduce scores under the declared policy. A completed or resumed run needs a stopping rule and its actual
outcome. Printed losses/parameter plots cannot reconstruct missing weights.

**Inference:** deterministic browser deployment is a separate project. There is no demonstrated Torch-to-browser export
here. The implementation uses complex FFTs, large spatial tensors, global geometry and stochastic forward operations; do
not assume ONNX or a browser backend supports the complete graph. A port needs a versioned input/coordinate contract,
hashed learned and fixed state, bounded distance search, candidate-order/tie behavior, precision tolerances, noise
policy, and native/browser golden parity. Alternatively, a frozen offline pair-distance artifact can be deterministic,
but only for its declared font/size/axes/profile and does not constitute a general live scorer. Neither route bypasses
Glypherie's contact/overlap constraints or authorizes preview publication.

## Platform and dependency evidence

| Path                  | Verified evidence                                                                                                                                                          | Remaining boundary                                                                                         |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Historical Torch/CUDA | Retained imports report Python 3.7, Torch `1.8.1+cu101`, NumPy `1.19.5`, torchdiffeq `0.2.1`, fonttools `4.22.0`, booleanOperations `0.9.0`. GPU/Colab calls are explicit. | Partial environment snapshot, not a lock or measured completed run; no recovered GPU identity/runtime.     |
| Historical Torch/CPU  | `dev` selects CUDA if available, otherwise CPU; FFT/scorer code uses Torch rather than gputools.                                                                           | CUDA cache calls must be guarded; chosen versions and full forward/backward need a smoke test.             |
| Apple MPS             | The historical selector never selects `mps`. Later PyTorch documents explicit MPS availability/build checks and device placement.                                          | No evidence that this complex-FFT/autograd graph works on MPS; CPU fallback must be explicit and measured. |
| Package/OpenCL        | `engine/filter_bank.py` imports gputools and calls its OpenCL arrays/FFT.                                                                                                  | Separate implementation with stubbed scoring; OpenCL is not required by the self-contained Torch notebook. |
| Current JAX           | Uses JAX, nptyping, SciPy, NumPy, plotting/Colab; no defined training objective.                                                                                           | A backend installation does not supply the missing algorithm; no training recipe to benchmark.             |

Sources: [historical notebook][torch], [OpenCL filters][filters], [current notebook][jax],
[pinned MPS documentation][mps]. The notebook imports a broad font/UFO stack and `torchdiffeq`, but the active scorer
does not call `odeint` or compile a UFO. A minimal recovery may remove inactive imports only after preserving the actual
tensorfont/FreeType/HarfBuzz path. Tensorfont itself requires NumPy, SciPy, scikit-image, freetype-py and uharfbuzz and
imports fontTools; its declared requirements are not a transitive environment lock.
[Dependency declaration][tensorfont-old-setup]

**Host inventory, independently checked:** this machine has an Apple M2 Max, 12 logical CPUs and 64 GiB unified memory.
The default interpreter is Python 3.14.7; it has NumPy but no Torch, JAX, tensorfont or gputools. This describes that
interpreter, not every existing environment. A compatible isolated environment is still required. CPU and MPS execution,
peak memory and throughput have not been tested; installed hardware alone does not establish a viable training run. The
inventory and arithmetic checks are retained in `training-audit/host-verification.json` under the evidence directory.

**Unknown:** a currently installable, tested compatibility matrix for the host. No install was attempted. No evidence
justifies requiring CUDA, claiming CPU is fast enough, claiming OpenCL is sufficient on Apple hardware, or claiming MPS
is universally incompatible. Native memory is separate from browser memory feasibility.

## Memory and runtime requirements

**Inference from the historical shapes and dtypes, not measured peaks:** `static_probe.py` computes tensor payloads. Let
`B=1`, `D=5`, `S=10`, `O=8`, `P=4`, `H=80`, `W=161`; FFT dimensions are `2H × 2W`. Float32 is four bytes and complex64
eight. MiB below is bytes divided by `2²⁰`.

| Allocation                                         | Shape                           | Payload MiB |
| -------------------------------------------------- | ------------------------------- | ----------: |
| Fixed V1 filter bank                               | `[S,O,2H,2W]`, complex64        |       31.45 |
| Cached 26 individual V1 responses                  | `[26,S,O,H,W]`, complex64       |      204.39 |
| One left or right candidate input                  | `[B,D,S,O,H,W]`, complex64      |       39.31 |
| One B activation                                   | `[B,D,S,2O,P,H,W]`, float32     |      157.23 |
| One G activation                                   | `[B,D,S,P,H,W]`, float32        |        9.83 |
| One padded B-to-G transform/result                 | `[B,D,S,2O,2H,2W]`, complex64   |      314.45 |
| One G-to-B broadcast product or inverse FFT output | `[B,D,S,2O,P,2H,2W]`, complex64 |    1,257.81 |
| One fixed G FFT filter                             | `[S,2O,2H,2W]`, complex64       |       62.89 |

The 1,416 parameter entries nominally occupy just 5,664 float32 bytes; weights and Adam states are not the dominant
cost. The G-to-B broadcast alone materializes about **1.23 GiB** before accounting for its inverse FFT output, workspace
or backward. B tensors recur through feedback/normalization and all three glyph branches; autograd retains
intermediates. The dataset also unnecessarily constructs its own B/G module with duplicate fixed filters. Views,
allocator reuse, graph lifetime and FFT workspace prevent summing these rows into an honest peak. **Several-GiB working
memory is a plausible inference, not a measured minimum or hardware recommendation.** [Cells 5–12][torch]

Spatial memory grows with `B*D*S*O*P*H*W`, and padded FFT work also depends on FFT geometry. Changing factor/box size,
precision, phase count, caching or branch evaluation can change the result or its gradients; do not present a smaller
benchmark as the full historical run. For a later authorized smoke, record peak RSS/accelerator allocation, input
shapes, warm-up and synchronized forward/backward/step timings. Only then estimate total time from measured step cost
and actual stopping policy. The full loop count is known; seconds per step and convergence are **unknown**. No GPU-hour
estimate is supported by retained logs or this static audit.

The host independently checked the G-to-B broadcast expression against its notebook source and recomputed its
1,318,912,000-byte payload, the 3,718,000-step loop ceiling and the static 760-parameter score-reachability count. These
arithmetic checks reproduce the audit's numbers; they do not verify actual allocation, gradients or convergence.

## Useful Glypherie training is a separate evidence gate

**Proposed requirements, not upstream capabilities or approval to implement:**

- **Define the claim and labels first.** Source-design imitation can retain per-font designed spacing targets. Claiming
  better optical spacing on delivered bitmaps requires independent judged placements/preferences at those delivered
  sizes/profiles, with uncertainty and annotator policy. The original labels and loss do not supply those judgments. Do
  not silently invent a new optical objective. Confirm a sourced adaptation or stop at imitation/generalization.
- **Split before tuning.** Group related fonts, styles and variable instances by family to prevent family leakage;
  freeze whole held-out families plus a separate pair-identity holdout. For the strict pair-generalization claim,
  exclude those pairs across training families, including the reported diagnostic/problem pairs; decide explicitly
  whether reversed pairs and shared glyphs belong in the same group. Keep validation for model/seed/threshold choices
  separate from a final untouched test. Original-domain all-676-pair reproduction has no held-out claim.
- **Capture actual delivered inputs.** Enumerate font hash, glyph IDs/shaping, size definition, rasterizer/model,
  baseline/origin, advances, source label coordinate units, integer candidate translations, quantization/bit depth and
  variable axes for every item. Include both isolated pair measurements and word/context evaluation; training on
  isolated pairs does not prove contextual rhythm. Preserve the agreed preview scope and approved baseline.
- **Treat bit depth and size as separate domains.** Original normalized grayscale at 34-pixel x-height does not validate
  1-bit or 4-bit small output, a 16-pixel target, gamma/threshold choices or fitted glyphs. Render the actual delivered
  profiles, with source labels mapped through the same coordinate/rounding rules, and expose target quantization error.
  The continuous label may have no equivalent feasible integer position. No per-glyph tuning to force a gain.
- **Revisit scales and candidate support explicitly.** Absolute `[-3,-1,0,1,5]` pixels and fixed scale progression do
  not automatically transfer to tiny glyphs. Confirm distinct candidates, sufficient padding, valid contact/no-overlap
  placements and an interior supported optimum; record out-of-range optima and failures rather than accepting the
  boundary minimum. Any rescaling/new search support is a declared model adaptation needing evidence.
- **Support axes only when sampled and tested.** The historical notebook loads one static font, no axis matrix. Current
  tensorfont adds variation handling, but using it changes the dependency and requires instance parity. Keep axes, size,
  profile and related instances grouped during splits; unseen axes, scripts, marks, ligatures, italics, uppercase and
  punctuation remain unsupported until tested. Model globals and fixed box/filter tensors need explicit geometry
  configuration for multiple font heights rather than mixing inconsistent cached responses. [Historical][torch],
  [current tensorfont][tensorfont-new]
- **Evaluate both accuracy and failure behavior.** Report placement error/target rank only as imitation evidence, with
  per-family/pair/profile coverage, score nonconstancy, seed variance, finite gradients, search-boundary hits, clipping,
  determinism and feasibility. Optical classification stays confirmed regression, pending assessment or acceptable
  deviation according to the repository rules, using independent visual evidence. Mechanical success is not optical
  closure. [Evaluation rules](../evaluation.md#review-and-decision)

Unknowns that block a useful-model claim are independent target availability, representative family coverage, delivered
size/axis/profile support, acceptable evaluation-noise policy, and the host's measured resource envelope. None is
resolved by running the full 5,500-epoch notebook.

## Staged falsifiable next step

**Recommendation: authorize only stage 1 next, as a separate task.** Recovery success would justify discussing a bounded
training run; it would not authorize one automatically.

1. **Recover and falsify without optimization.** Deliver a pinned source/input/dependency manifest; isolated historical
   scorer with explicitly listed compatibility changes; retained 26-glyph/676-pair label and translation manifest;
   numerical fixtures for both loss branches, including the degenerate cubic; a deterministic-evaluation proposal;
   forward score traces and resource measurements for a few predetermined pairs at all five candidates; checkpoint
   schema and save/load score parity. No optimizer steps. Stop if inputs cannot be traced, pixels/metrics unexpectedly
   differ, any scores are nonfinite/constant, candidates collapse/clip, the loss guard needs an unapproved fallback, the
   noise policy is unresolved, or the measured resource envelope is unsuitable. Missing state means fresh calibration,
   not checkpoint recovery.
2. **Only after separate authorization, bounded gradient smoke and original-domain calibration.** Start with a finite
   gradient census and one optimizer step, then a predeclared short cap, not 5,500 epochs by default. Deliver seeds,
   ordered batches, timings/peak memory, loss traces, checkpoint/resume parity and repeatability under the declared
   evaluation policy. Stop on missing expected gradients, NaNs/infinities, unstable roots, order-dependent deterministic
   scores or unsuitable cost. Full-dataset fit can establish original-domain imitation only. Hold-out experiments must
   use a separate split/run identity; do not claim an all-pairs checkpoint has unseen-pair evidence.
3. **Only with an agreed target, test transfer.** Deliver the frozen family/pair splits, delivered-bitmap corpus,
   supported size/axis/bit-depth matrix, baselines and independent visual assessments. Stop before preview integration
   if held-out behavior or deterministic feasible placement fails, or if only training-font imitation has been shown.
4. **Only after scorer acceptance, specify deployment.** Deliver a versioned artifact and browser/native parity and
   memory/latency results for the actual intended interface. A trained `.pth` alone is not that interface.

No stage changes the existing preview, baseline or accepted optical status. Apache-2.0 applies to copied YinYangFit
code; tensorfont, dependencies and font inputs have their own license/provenance requirements.
[Upstream license][license], [tensorfont declaration][tensorfont-old-setup]

[head]: https://github.com/skosch/YinYangFit/tree/609d17e8a6446ec4413a1b02a0768b8214d73333
[torch]: https://github.com/skosch/YinYangFit/blob/d9c7e2580f2ad4884c45e5081e8e4613b86632cf/YinYangFit.ipynb
[jax]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/YinYangFit.ipynb
[frontmatter]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/frontmatter.markdown
[algorithms]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown
[tensorfont-old]: https://github.com/simoncozens/tensorfont/blob/ca40a251693022a86eff63301dbae45ec27b608e/tensorfont/__init__.py
[tensorfont-old-setup]: https://github.com/simoncozens/tensorfont/blob/ca40a251693022a86eff63301dbae45ec27b608e/setup.py
[tensorfont-new]: https://github.com/simoncozens/tensorfont/blob/ecb2a3817d7f2c41167cf79aa1fd2ec154d86ada/tensorfont/__init__.py
[crimson]: https://github.com/skosch/Crimson/tree/685b5a2478a7213a806e9bbf1e36f6a9e7f5c7ef
[cufft]: https://github.com/pytorch/pytorch/blob/56b43f4fec1f76953f15a627694d4bba34588969/torch/backends/cuda/__init__.py
[serialization]: https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/docs/source/notes/serialization.rst
[randomness]: https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/docs/source/notes/randomness.rst
[mps]: https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/docs/source/notes/mps.rst
[skimage]: https://github.com/scikit-image/scikit-image/blob/e128e0743bb2cded104654352a13ed5b4e53efb8/skimage/util/__init__.py
[numpy]: https://github.com/numpy/numpy/blob/8cec82012694571156e8d7696307c848a7603b4e/numpy/__init__.py
[engine]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/__init__.py#L143-L311
[filters]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/filter_bank.py
[license]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/LICENSE
