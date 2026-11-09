"""Versioned staged settings policy for the Class-L repair staging page.

Staged-only policy for the YinYang normalization-repair integration
(``page-staging/`` under ``yinyang-normalization-repair/``). The live
reviewed page keeps ``yinyangfit_interactive_v3_ranges.py`` untouched.

Controls (parent-commissioned units for this staging):

- Interaction target: the chosen step minimizes ``|gl - target|`` under
  the unchanged TIE-v2 rule (global minimum, then lowest step index).
  Slider ``0..20`` step ``0.02`` (1001 stops); exact numeric entry
  accepts any finite value ``>= 0`` with NO clamp and NO snap (kept
  exactly as entered, including off-slider and off-grid values); zero
  stays usable exact. Non-finite, negative, and overflowing input is
  rejected and keeps the last valid setting. Initial/reset ``8.0`` is a
  transparent exploration start, not an optical recommendation. The
  ``0.02`` step is NAVIGATION precision only: the adjacent-slider-step
  predictability gate FAILED structurally, and no optical calibration
  is claimed.
- Reach (R): the square kernel half-width in px. Slider ``4..24`` step
  ``1``; exact numeric entry is an integer in ``[1, 32]``. Default
  ``12`` (frozen field geometry). The old G2 Standard/Extended numeric
  bounds do not transfer to Class L.
- Falloff (q): the radial exponent. Slider ``0.5..10`` step ``0.5``;
  exact numeric entry ``[0.25, 16]``. Default ``2.0`` (frozen).

Frozen, no knobs: ``tau = 0.5``, ``kappa = 4``, 16 directed channels,
five half-octave scales around sigma 1.5 with neutral uniform weights,
``eps = 1e-12``. The normalizer window ``normalization_radius = 12``
is FIXED and never user-controlled: no slider, no numeric entry, no
coupling to Reach. Guardrails are evaluated/resource bounds with
validating messages, never silent clamping; reset returns to the
model seed, not to Source. R/q change geometry and force full
recompute.
"""

import math

RANGES_VERSION = "v3-settings-2026-11-05-classl"

# Slider bands (UX working ranges, not validity limits).
TARGETS = [round(i * 0.02, 2) for i in range(1001)]
REACHES = [float(r) for r in range(4, 25)]
FALLOFFS = [0.5 + i * 0.5 for i in range(20)]

# Numeric-entry guardrails (evaluated/resource bounds, not model limits).
# The target has no finite upper clamp by design: any finite value >= 0
# is accepted exactly. Reach/falloff keep the evaluated bounds.
TARGET_MIN = 0.0
REACH_BOUNDS = (1, 32)
FALLOFF_BOUNDS = (0.25, 16.0)

# Defaults: frozen geometry plus the staged exploration start (not an
# optical default). Band rounds the measured p99 (~17.59) outward.
DEFAULT_TARGET = 8.0
DEFAULT_REACH = 12
DEFAULT_FALLOFF = 2.0

# Fast path: exactly one shipped geometry column (the frozen defaults).
# Only (R, q) == (12, 2.0) answers from tables; every other setting is
# scored exactly on demand in the page worker through the same engine,
# never interpolated.
FAST_GEOMETRY = (float(DEFAULT_REACH), float(DEFAULT_FALLOFF))

# Spot grid for shipped-table choice checks (7 declared targets across
# the slider band, endpoints included). Browser rechecks by value.
TARGET_SPOT_GRID = [0.0, 1.0, 4.0, 8.0, 12.0, 16.0, 20.0]

# Score model this policy stages. Tables, caches, and maps reject any
# other score identity.
SCORE_MODEL = "yinyangfit-local-energy-v2"


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_numeric(target, reach, falloff):
    """Guardrail check for direct numeric entry.

    Returns ``(True, "")`` for admissible settings, else ``(False,
    message)``. Bounds are validating guardrails, never silent
    clamping: out-of-range input keeps the last valid setting and shows
    the message. The target accepts any finite value >= 0 (overflow to
    infinity is rejected as non-finite); R must be an integer;
    fractional R input errors (never rounds).
    """
    for key, value in (("target", target), ("reach", reach),
                       ("falloff", falloff)):
        if not _is_number(value):
            return False, f"{key} must be a number"
        if not math.isfinite(float(value)):
            return False, f"{key} must be finite"
    if not float(target) >= TARGET_MIN:
        return False, "target must be finite and >= 0"
    if not float(reach).is_integer() or not (
            REACH_BOUNDS[0] <= int(reach) <= REACH_BOUNDS[1]):
        return False, "reach must be an integer in [1, 32]"
    if not FALLOFF_BOUNDS[0] <= float(falloff) <= FALLOFF_BOUNDS[1]:
        return False, "falloff must be in [0.25, 16]"
    return True, ""


def make_controls(target, reach, falloff):
    """Validated settings triple for the engine params + choice target."""
    ok, message = validate_numeric(target, reach, falloff)
    if not ok:
        raise ValueError(message)
    return {"target": float(target), "reach": int(reach),
            "falloff": float(falloff)}


def default_controls():
    """Seed settings: frozen geometry plus the staged start."""
    return {"target": float(DEFAULT_TARGET), "reach": int(DEFAULT_REACH),
            "falloff": float(DEFAULT_FALLOFF)}


def is_fast_geometry(reach, falloff):
    """True only at the shipped default geometry column."""
    return (int(reach) == int(FAST_GEOMETRY[0])
            and float(falloff) == float(FAST_GEOMETRY[1]))


def default_indexes():
    """Grid positions of the seed (by value)."""
    return (TARGETS.index(DEFAULT_TARGET),
            REACHES.index(float(DEFAULT_REACH)),
            FALLOFFS.index(float(DEFAULT_FALLOFF)))


def tie_pick(deviations, steps, metric, tol_factor=1e-9):
    """TIE-v2 choice mirror: global minimum, then lowest step index.

    Matches the engine (``score.rs`` tie_set plus lowest-step
    single-pick): the minimizing set is every valid candidate within
    ``m* + 1e-9*max(1, m*)``; the pick is the lowest step index in the
    set (never metric-nearest). Empty validity falls back to metric.
    """
    valid = [(i, dev) for i, dev in enumerate(deviations)
             if dev is not None and math.isfinite(dev)]
    if not valid:
        return metric, [], True
    mstar = min(dev for _, dev in valid)
    tol = tol_factor * max(1.0, mstar)
    members = [i for i, dev in enumerate(deviations) if dev is not None
               and math.isfinite(dev) and dev <= mstar + tol]
    chosen = min(steps[i] for i in members)
    return chosen, [steps[i] for i in members], False
