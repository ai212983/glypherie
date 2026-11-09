<!-- cspell:words YinYangFit yinyangfit Kosch Colab Colaboratory PyTorch CUDA OpenCL gputools tensorfont nptyping torchdiffeq cufft nn rd ipynb pth loggabor softplus Gabor ckpt randn pgrid Matplotlib tqdm Bokeh nonconstant -->

# YinYangFit feasibility audit

Research only, 2026-10-31. **Stop capture adaptation and preview work: no reproducible, calibrated scorer has been
established.** The host findings about the current engine and JAX notebook are correct, but a broader claim that
upstream has no scalar objective or fitting code would be wrong: historical PyTorch notebooks contain both. Recovering
that prototype is a possible separate task, not a completed reproduction or permission to invent the JAX objective.

The [feasibility gate](../designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
remains unmet. Control B stays `hu_fitted_full_density_conserved_touch`, with unchanged glyphs, full strength, zero
tracking, contact allowed and occupied-cell overlap forbidden. The four-family 16 px captures were not adapted or
evaluated.

## Scope and evidence

Audited immutable upstream [609d17e8a6446ec4413a1b02a0768b8214d73333][head], including the complete current notebook
source, directly from `.ipynb`, rather than trusting `notebook-code.txt`. Inventoried the 45 notebook-change commits;
closely read the last self-contained PyTorch notebook, its retained successor, and representative original engine code.
Read-only upstream ref discovery returned only `master` at that HEAD and no tags. This is a bounded recovery audit, not
certification of every historical notebook or a search of forks/unadvertised refs.

Local evidence is under
[`out/diagnostics/contextual-spacing/yinyangfit/audit/`](../../out/diagnostics/contextual-spacing/yinyangfit/audit/):
`independent-probe.json` records the repeated host probe and synthetic selector check; `history-inventory.json` records
notebook identities and the history inventory. No upstream file, dependency, solver, renderer or preview was changed.

## Verified current behavior

- **Engine penalty is a stub.** [`render_penalty_fields`, lines 143–150][engine] returns zeros with dimensions selected
  from scales, orientations, box size and number of distances; it never reads either glyph. The independent rerun of the
  unchanged AST-extracted bodies reproduces five zero totals for each label `HH`, `nn`, `rd`, `os`. These labels do not
  represent rendered examples: imports/initialization were bypassed, dimensions were synthetic, and the font stub's
  minimum ink distance was zero. This establishes method behavior, not full-engine reproduction.
- **Selection is independently broken.** [`get_best_distances_and_full_penalty_fields`, lines 248–305][engine] searches
  `-1, 1, …, 39`, but its unconditional `break` exits after index zero. It emits the selected distance minus the font's
  minimum ink distance; the host's `-1` therefore depends on its zero stub. Replacing only the field provider in an
  audit check with synthetic strictly decreasing costs still selects `-1`, although the minimum is at `39`. Fixing the
  zero field alone would not fix this selector. `prepare_params` also replaces `v1_k` and `v1_b` with zeros.
- **Current JAX code extracts features, not a spacing score.** In the [HEAD notebook][notebook], zero-based cells 5–23
  implement log-Gabor filtering, phase coherence, normalization, directional distance/confidence estimation and
  aggregation into per-pixel distance/orientation maps. Stored figures support prior execution of portions; none of this
  was rerun here. Cell 24 translates glyphs relative to `f.pair_distance` and minimum ink distance. Cell 25 requests
  delta zero, creates distance/orientation matching masks, and uses them as plot alpha. Plotting is outside the loop
  over `"test"`, so only its final pair, `st`, is displayed. There is no scalar reduction, candidate-distance
  minimization, training loss or learned-state export in this revision. Constants such as `.01` and the orientation
  power `6` are explicit source choices, not evidenced fitted parameters.

The [article][article] describes itself as provisional and offers computational building blocks. Its
[pinned algorithm text][algorithms] discusses aggregation choices and a neighboring-distance fitting proposal. It does
not specify the missing JAX reduction or provide a calibrated parameter set. Summing the plotted mask would create a
project hypothesis, not reproduce this reference.

## Historical recovery: real objective, incomplete provenance

The strongest lead is **[d9c7e2580f2ad4884c45e5081e8e4613b86632cf, 2021-04-01][torch]**, `YinYangFit.ipynb`:

- Cells 5–7 build V1 filters and a trainable B/G interaction model. Cell 8, `G_Targets.forward`, applies a saturating
  transform to separate-glyph and paired G responses. It forms positive gain and loss terms using learned factors and
  returns their sum. Cell 9, `YinYangFit.forward`, explicitly sums over scales, phases and spatial dimensions to produce
  one penalty per sampled distance. That aggregation belongs to this historical model; it is not the missing JAX rule.
- Cells 10–12 construct all `26²` lowercase pairs of Crimson Roman, rendered through `tensorfont` at `34 * factor`, at
  deltas `[-3, -1, 0, 1, 5]` around the font's designed pair distance. Cell 13 supplies an explicit fitting loss:
  estimate a minimum from a fitted cubic for selected valley patterns and square its displacement from zero; otherwise
  use cross-entropy on negative penalties with target index 2. Cell 14 trains with Adam, learning rate `0.0011`, up to
  5,500 epochs. This differs from the article's neighboring-cost maximum proposal.
- **No fitted state was recovered.** Cell 14 saves `./yinyangfit.pth` only after training; its retained output ends with
  `KeyboardInterrupt`. The available Git object/path inventory contains no `.pth`, `.pt`, `.pkl`, `.h5`, `.ckpt`, `.npz`
  or similar checkpoint paths. Printed losses and parameter figures are not a serialized model. This does not prove that
  an author-held checkpoint never existed.
- **Evaluation is stochastic as written.** Cell 7 calls `randn_like` on activations and several parameters during every
  forward pass, without a `self.training` guard; calling `eval()` alone does not disable it. Training shuffles pairs,
  records no PyTorch/NumPy seed, and has no held-out split. Its all-pairs calibration would include problem pairs that
  our experiment requires holding out. New training needs explicit provenance and a disclosed evaluation policy.

The [2022-10-26 revision, 4df967467247d606c23e524cebd5ef0efbc92af5][mixed], retains those scorer/training cells
unchanged under “old torch code,” after JAX experiments. Its Torch imports are commented and its support cell retains a
`NameError` for `unit_pgrid`. It is a worse clean-restart candidate than `d9c7e25`. Related [9e9a37a][torch-previous]
also contains training and save code; its retained scores do not supply a checkpoint or completed validation.

Original nonzero costs also exist in the [2019 engine, dcf6452][original-engine]: nonlinear pair-minus-single V1
responses, signed gain/loss weights, a scalar sum and root-based distance selection. A [later 2019 kernel][old-kernel]
implements weighted hyperbolic-ratio response differences. Those are genuine earlier components with a different
selection convention, not a calibrated version of the later JAX model. The [2020 restructuring][stub-change] introduced
the active zero stub and unconditional search break. Restoring commented OpenCL calls is not a complete recovery recipe.

## Dependencies and license

The [repository license][license] is Apache-2.0. Any copied code must retain the applicable license/notices and identify
modifications. Independently downloaded fonts and third-party dependencies need their own provenance; the repository's
license file does not establish those inputs' licenses.

[`setup.py`][setup] is only a commented requirements list, not an installable, version-pinned package definition. The
[packaged filters][filters] use `gputools` OpenCL arrays/FFT; the [font loader][font-loader] uses `tensorfont`.
Additional imports include NumPy, Matplotlib and tqdm. Commenting out the engine's own OpenCL setup does not remove the
filters' OpenCL requirement.

Both notebook families install unpinned packages and download Crimson fonts from mutable `master` URLs, without hashes.
The current notebook assumes Colab and uses JAX, `nptyping`, SciPy, NumPy, Matplotlib and Bokeh. The historical notebook
uses PyTorch, Colab, font tooling and `torchdiffeq`; its nominal CPU fallback is undermined by unconditional CUDA FFT
cache housekeeping in training. No Python environment lock was found in the inspected history. The audit interpreter has
NumPy but lacks JAX, PyTorch, `gputools` and `tensorfont`; no dependency installation or notebook execution was
attempted. These are reproducibility obstacles, not evidence of universal platform incompatibility.

## Decision and exact missing pieces

**Stop before 1-bit adaptation.** Missing prerequisites are (1) one declared historical model rather than a mixture of
versions, (2) its fitted checkpoint or a repeatable calibration run with font hashes, dependency versions, seeds and
recorded outcomes, (3) a justified policy for its always-on forward noise, and (4) demonstrated finite, nonconstant,
stable distance scores and held-out placement behavior. The JAX alternative additionally lacks the actual objective and
fitting procedure. No complete executable reproduction command can honestly be supplied yet.

Historical recovery would start from the self-contained Torch notebook, preserving source through read-only extraction
rather than switching the reference checkout:

```sh
git -C out/diagnostics/contextual-spacing/yinyangfit/source show \
  d9c7e2580f2ad4884c45e5081e8e4613b86632cf:YinYangFit.ipynb \
  > out/diagnostics/contextual-spacing/yinyangfit/audit/d9c7e25.ipynb
```

Recover the original environment/state, or establish a reproducible fresh training experiment, before adapting captures.
Do not repair the gap with a new sum, weight, target or loss. Neither historical training output, zero penalties nor
passing mechanical checks establishes optical acceptance or justifies another reading preview.

[head]: https://github.com/skosch/YinYangFit/tree/609d17e8a6446ec4413a1b02a0768b8214d73333
[engine]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/__init__.py#L143-L311
[notebook]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/YinYangFit.ipynb
[article]: https://skosch.github.io/YinYangFit/
[algorithms]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown
[torch]: https://github.com/skosch/YinYangFit/blob/d9c7e2580f2ad4884c45e5081e8e4613b86632cf/YinYangFit.ipynb
[mixed]: https://github.com/skosch/YinYangFit/blob/4df967467247d606c23e524cebd5ef0efbc92af5/YinYangFit.ipynb
[torch-previous]: https://github.com/skosch/YinYangFit/blob/9e9a37a3c1ad8b5e6bad2495c4363c3ea9c62fad/YinYangFit.ipynb
[original-engine]: https://github.com/skosch/YinYangFit/blob/dcf64524795cbcac77539f54d4d65e2217370381/engine/__init__.py#L112-L131
[old-kernel]: https://github.com/skosch/YinYangFit/blob/7f40adc273410bce88ae311e7b7fe33d3857490b/engine/kernels.cl
[stub-change]: https://github.com/skosch/YinYangFit/commit/1f4d3d42b2c49862dd20b4d6b150e01ee20b64a1
[license]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/LICENSE
[setup]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/setup.py
[filters]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/filter_bank.py
[font-loader]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/font_loader.py
