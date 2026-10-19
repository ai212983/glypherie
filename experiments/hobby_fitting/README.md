# Hobby geometric prototype

<!-- cspell:words Hobby's NumPy -->

Isolated research prototype for the coupled geometric system described in the
[Hobby fitting model](../../docs/hobby-fitting.md). It operates on synthetic supplied features, without loading fonts or
changing the generator. The [equation audit](../../docs/references/papers/1993-hobby/audit.md) records checked notation,
report-version discrepancies and remaining source uncertainties. See [experiment guidance](../AGENTS.md) for placement
and verification routing.

## Run

Python 3.12 and the pinned NumPy dependency in [requirements.txt](requirements.txt) suffice; the existing
paper-extraction environment also supplies it. From the repository root, with `uv`:

```sh
uv run --with-requirements experiments/hobby_fitting/requirements.txt python experiments/hobby_fitting/prototype.py
uv run --with-requirements experiments/hobby_fitting/requirements.txt python -m unittest discover -s experiments/hobby_fitting/tests -p 'test_*.py'
```

The first command emits diagnostic JSON with source/projected widths, relative width errors, movement, rank and squared
residuals by group. Redirect it to an ignored location such as `out/diagnostics/hobby-prototype.json` to retain a run.
It does not produce specimen packages or publish a preview.
