# CounterSpace reference

<!-- cspell:words counterspace tensorfont skimage -->

`CounterSpace.py` and `LICENSE` are verbatim files from
[Simon Cozens / CounterSpace](https://github.com/simoncozens/CounterSpace), commit
`01b33477225eb5fc7bedf93a090b5cd7dd0c812b`. SHA-256 identities are recorded in `../../counterspace.lock.json`. No
upstream image assets are included.

The adapter executes this source with the command-line tensorfont backend. Tensorfont 0.0.6 remains an installed
dependency. Its private compatibility loader replaces `skimage.util.pad` with `numpy.pad`, replaces the removed
`numpy.float` alias with `float`, and redirects internal package imports. The CounterSpace source file itself is
untouched. A separate private intensity adapter scales normalized inputs into tensorfont's byte-scale contour domain for
its original concavity operation, then restores normalized output and rendering metadata. This semantic repair is
identified separately from API compatibility in the manifest and model metadata. The adapter supplies integer-expanded
captured bitmap cells at maintained full metric reference placements for calibration and scoring. Axis-instantiated
source calibration remains a separate control. Whole delivered-pixel origins use either the upstream first-crossing
criterion or the project's closest feasible score search. These adaptations are not upstream parity claims for final
spacing. The upstream masks, convolution, concavity reduction, Gaussian weighting and fitting routines execute directly.
