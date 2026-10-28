# Compensated norm provenance

The diagonal fitter adapts the two-coordinate `vector_norm`, `dl_mul` and `dl_fast_sum` calculations from
[CPython v3.14.0](https://github.com/python/cpython/blob/v3.14.0/Modules/mathmodule.c#L2360) into Rust. The reference
experiment runs on Python 3.14.7; its norm calculation has the same operation sequence. The retained
[PSF license](LICENSE) covers the adaptation.

The adaptation preserves scaled products, compensated additions and square-root correction. It supplies the
reference arithmetic for interval events without a Python runtime dependency. The geometric model and verification
boundary belong to the [fitting design](../../../../docs/hobby-fitting.md#native-width-only-adoption).
