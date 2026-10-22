//! Shared constrained least-squares numeric core for diagonal fitting.
//!
//! Source: primal feasible active-set method for convex quadratic programs
//! with equality, inequality and box constraints (Forsgren, Gill and Wong,
//! 2015). Each search direction is the equality-nullspace least-squares
//! minimizer; the first blocking bound limits the step, and a negative
//! bound multiplier releases that constraint. Delivery is gated on primal
//! feasibility and the convex KKT normal-cone condition, never on matching
//! an alternate numerical implementation.
//!
//! Project adaptations: dense `Vec<f64>` rows matching the fitting systems;
//! fixed model thresholds below (no per-glyph tuning); `None` on unresolved
//! initialization or iteration limits so callers abstain. Runtime never uses
//! Python, SciPy, subprocesses or corpus corrections.

use nalgebra::{DMatrix, DVector};

/// Fixed model thresholds mirroring the prototype constants.
struct Tolerances {
    /// Primal step/zero norm (`tol`).
    primal: f64,
    /// Delivered equality residual gate (prototype `1e-8` for the convex
    /// path, `tol` for the bounded path).
    equality: f64,
    /// Relative KKT stationarity gate (prototype `1e-7` convex, `tol`
    /// bounded).
    stationarity: f64,
    /// Dual feasibility scale (`tol * (1 + |gradient|)`).
    dual: f64,
}

const BOUNDED_TOL: Tolerances = Tolerances {
    primal: 1e-9,
    equality: 1e-9,
    stationarity: 1e-9,
    dual: 1e-9,
};

const CONVEX_TOL: Tolerances = Tolerances {
    primal: 1e-9,
    equality: 1e-8,
    stationarity: 1e-7,
    dual: 1e-9,
};

/// Delivered-point inequality slack gate (prototype `min(slack) < -1e-8`
/// rejects the candidate). General inequalities keep this prototype band;
/// box sides keep the tighter internal primal gate.
const DELIVER_SLACK: f64 = 1e-8;

/// Solver evidence returned alongside the displacement.
#[derive(Clone, Debug)]
pub(super) struct QpInfo {
    pub iterations: usize,
    pub equality_error: f64,
    pub stationarity_error: f64,
    pub inequality_slack: f64,
    pub active: usize,
}

/// Minimum-norm least squares, NumPy `lstsq(rcond=None)` semantics.
///
/// Rank rule matches the prototype exactly: singular values above
/// `eps * max(m, n) * sigma_max` are kept; the solution is the minimum-norm
/// one in the free modes. Local copy keeps the numeric core reviewable in
/// one file; it duplicates no fitting state.
fn lstsq(a: &DMatrix<f64>, b: &DVector<f64>) -> DVector<f64> {
    LeastSquares::new(a).solve(b)
}

/// Factor once, solve new right-hand sides with the same arithmetic and rank
/// rule. This follows nalgebra's separation of SVD construction and solving:
/// https://docs.rs/nalgebra/0.35.0/nalgebra/linalg/struct.SVD.html
/// The explicit solve retains the original accumulation order.
struct LeastSquares {
    n: usize,
    factors: Option<(DMatrix<f64>, DMatrix<f64>, DVector<f64>, f64)>,
}

impl LeastSquares {
    fn new(a: &DMatrix<f64>) -> Self {
        let (m, n) = (a.nrows(), a.ncols());
        let zero = Self { n, factors: None };
        if m == 0 || n == 0 {
            return zero;
        }
        let svd = a.clone().svd(true, true);
        let sigmax = svd.singular_values.iter().cloned().fold(0.0_f64, f64::max);
        if !(sigmax > 0.0) {
            return zero;
        }
        let tol = f64::EPSILON * (m.max(n) as f64) * sigmax;
        let (Some(u), Some(vt)) = (svd.u, svd.v_t) else {
            return zero;
        };
        Self {
            n,
            factors: Some((u, vt, svd.singular_values, tol)),
        }
    }

    fn solve(&self, b: &DVector<f64>) -> DVector<f64> {
        let Some((u, vt, values, tol)) = &self.factors else {
            return DVector::zeros(self.n);
        };
        let utb: DVector<f64> = u.transpose() * b;
        let mut x = DVector::zeros(self.n);
        for (i, &s) in values.iter().enumerate() {
            if s > *tol {
                let c = utb[i] / s;
                for j in 0..self.n {
                    x[j] += vt[(i, j)] * c;
                }
            }
        }
        x
    }
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

fn norm(v: &[f64]) -> f64 {
    v.iter().map(|x| x * x).sum::<f64>().sqrt()
}

/// One working-set row: equality, general inequality, or box side.
#[derive(Clone)]
enum WorkRow {
    /// Equality row, always active.
    Eq(Vec<f64>),
    /// Inequality `row . x >= lower`.
    Ineq(Vec<f64>, f64),
    /// Upper box side `x[i] <= bounds[i]`.
    Upper(usize),
    /// Lower box side `x[i] >= -bounds[i]`.
    Lower(usize),
}

impl WorkRow {
    fn coeffs(&self, n: usize) -> Vec<f64> {
        match self {
            WorkRow::Eq(row) | WorkRow::Ineq(row, _) => row.clone(),
            WorkRow::Upper(i) => {
                let mut row = vec![0.0; n];
                row[*i] = 1.0;
                row
            }
            WorkRow::Lower(i) => {
                let mut row = vec![0.0; n];
                row[*i] = -1.0;
                row
            }
        }
    }

    /// Constraint gradient with its sign restriction under the
    /// `L = f - λc, λ >= 0` convention: equalities stay free, while box
    /// sides enter through their `bound - x` form, negating the working
    /// coefficients.
    fn grad_row(&self, n: usize) -> (Vec<f64>, bool) {
        match self {
            WorkRow::Eq(row) => (row.clone(), false),
            WorkRow::Ineq(row, _) => (row.clone(), true),
            WorkRow::Upper(i) => {
                let mut row = vec![0.0; n];
                row[*i] = -1.0;
                (row, true)
            }
            WorkRow::Lower(i) => {
                // Lower side is x[i] >= -bound, i.e. c = x[i] + bound with
                // gradient +e[i]; the working coefficient carries the
                // opposite sign and must not leak into the multiplier.
                let mut row = vec![0.0; n];
                row[*i] = 1.0;
                (row, true)
            }
        }
    }
}

/// Immutable direction system for one ordered working set. A full step only
/// changes the residual; adding or releasing a constraint invalidates both
/// factors. Nothing is retained across separate active-set solves.
struct DirectionSystem {
    zmat: DMatrix<f64>,
    reduced: LeastSquares,
}

impl DirectionSystem {
    fn new(
        _a: &[Vec<f64>],
        active: &[WorkRow],
        n: usize,
        objective: &SparseObjective,
    ) -> Option<Self> {
        let k = active.len();
        // Padding recovers the full V factor, including the nullspace modes.
        let wrows = {
            let m = k.max(n);
            let mut flat = vec![0.0; m * n];
            for (r, work) in active.iter().enumerate() {
                let w = work.coeffs(n);
                for (j, v) in w.iter().enumerate() {
                    flat[r * n + j] = *v;
                }
            }
            DMatrix::from_row_slice(m, n, &flat)
        };
        let svd = wrows.svd(false, true);
        let sigmax = svd.singular_values.iter().cloned().fold(0.0_f64, f64::max);
        let cutoff = (k.max(n) as f64) * sigmax * 1e-12;
        let rank = if !(sigmax > 0.0) {
            0
        } else {
            svd.singular_values.iter().filter(|s| **s > cutoff).count()
        };
        let vt = svd.v_t?;
        let zn = n - rank;
        let mut zmat = DMatrix::zeros(n, zn);
        for (c, r) in (rank..n).enumerate() {
            for i in 0..n {
                zmat[(i, c)] = vt[(r, i)];
            }
        }
        let az = objective.project(&zmat);
        Some(Self {
            zmat,
            reduced: LeastSquares::new(&az),
        })
    }
}

/// Primal feasible active-set solve.
///
/// Minimizes `1/2 |A x - b|^2` subject to `G x = h`, `C x >= lower` and
/// `|x[i]| <= bounds[i]`. Equality pairs carry `(row, rhs)` with `rhs`
/// already on the constant side. Returns `None` when initialization is
/// infeasible, a row is degenerate, or the iteration budget
/// (20 * max(1, n), per the prototype) is exhausted.
fn active_set(
    tol: &Tolerances,
    a: &[Vec<f64>],
    b: &[f64],
    equalities: &[(Vec<f64>, f64)],
    inequalities: &[(Vec<f64>, f64)],
    bounds: &[f64],
    strict_init: bool,
) -> Option<(Vec<f64>, QpInfo)> {
    let n = a
        .iter()
        .map(Vec::len)
        .chain(equalities.iter().map(|(r, _)| r.len()))
        .chain(inequalities.iter().map(|(r, _)| r.len()))
        .chain(std::iter::once(bounds.len()))
        .max()?;
    if n == 0 || bounds.len() != n {
        return None;
    }
    if bounds.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return None;
    }
    for row in a
        .iter()
        .chain(equalities.iter().map(|(r, _)| r))
        .chain(inequalities.iter().map(|(r, _)| r))
    {
        if row.len() != n || !row.iter().all(|v| v.is_finite()) {
            return None;
        }
    }
    if b.len() != a.len() || !b.iter().all(|v| v.is_finite()) {
        return None;
    }

    // Normalize equality rows; exact-zero rows must carry zero constants.
    let mut eq: Vec<(Vec<f64>, f64)> = Vec::with_capacity(equalities.len());
    for (row, rhs) in equalities {
        let scale = norm(row);
        if scale <= 0.0 {
            if rhs.abs() > tol.primal {
                return None;
            }
            continue;
        }
        eq.push((row.iter().map(|v| v / scale).collect(), rhs / scale));
    }
    // Normalize inequality rows the same way.
    let mut ie: Vec<(Vec<f64>, f64)> = Vec::with_capacity(inequalities.len());
    for (row, lower) in inequalities {
        let scale = norm(row);
        if scale <= 0.0 {
            if *lower > tol.primal {
                return None;
            }
            continue;
        }
        ie.push((row.iter().map(|v| v / scale).collect(), lower / scale));
    }

    // Minimum-norm particular solution of the equalities.
    let x = if eq.is_empty() {
        vec![0.0; n]
    } else {
        let flat: Vec<f64> = eq.iter().flat_map(|(r, _)| r.iter().copied()).collect();
        let mat = DMatrix::from_row_slice(eq.len(), n, &flat);
        lstsq(
            &mat,
            &DVector::from_vec(eq.iter().map(|(_, h)| *h).collect()),
        )
        .iter()
        .copied()
        .collect()
    };
    if eq_error_max(&eq, &x) > tol.equality || x.iter().any(|v| !v.is_finite()) {
        return None;
    }
    if strict_init {
        // Original bounded path: the min-norm start must already respect
        // the box; no SLSQP-style repair applies here.
        if x.iter()
            .zip(bounds.iter())
            .any(|(v, limit)| v.abs() > limit + tol.primal)
        {
            return None;
        }
        solve_core(tol, a, b, &eq, &ie, bounds, x)
    } else {
        // Convex path: the original clips the start and lets the optimizer
        // repair, so a box- or inequality-violating min-norm start goes to
        // the elastic Phase I instead of being rejected outright.
        let Some(start) = elastic_start(tol, &eq, &ie, bounds, x) else {
            return None;
        };
        solve_core(tol, a, b, &eq, &ie, bounds, start)
    }
}

/// Primal feasible active-set core: nullspace steps with release from a
/// feasible start. Delivery stays gated on primal feasibility and the KKT
/// normal-cone check, so the core never certifies an infeasible point.
#[allow(clippy::too_many_arguments)]
fn solve_core(
    tol: &Tolerances,
    a: &[Vec<f64>],
    b: &[f64],
    eq: &[(Vec<f64>, f64)],
    ie: &[(Vec<f64>, f64)],
    bounds: &[f64],
    mut x: Vec<f64>,
) -> Option<(Vec<f64>, QpInfo)> {
    let n = bounds.len();
    // Objective gradient pieces: Q = A'A, q = -A'b, kept factored.
    let at_rows: Vec<Vec<f64>> = (0..n)
        .map(|j| a.iter().map(|row| row[j]).collect())
        .collect();
    let objective = SparseObjective::new(a, n);
    let at_b: Vec<f64> = at_rows.iter().map(|row| dot(row, b)).collect();
    let gradient = |x: &[f64]| {
        let ax = objective.product(x);
        let at_ax = objective.transpose_product(&at_rows, &ax);
        let d: Vec<f64> = at_ax.iter().zip(&at_b).map(|(v, w)| v - w).collect();
        (d, ax)
    };

    // Working set: all equalities plus active bounds/inequalities.
    let mut active: Vec<WorkRow> = eq.iter().map(|(r, _)| WorkRow::Eq(r.clone())).collect();
    let mut direction = None;
    let cap = 20 * n.max(1);
    for iteration in 0..cap {
        let (d, ax) = gradient(&x);
        let dnorm = norm(&d);
        // Equality-nullspace least squares supplies each direction, in the
        // prototype's explicit form: with P the orthoprojector onto ker W
        // (V rows past the 1e-12 working-set rank), p = P lstsq(A P, b - Ax).
        // No Gram matrix A'A is ever formed, so the step keeps the
        // conditioning of the prototype's nullspace solve.
        let k = active.len();
        // Nullspace basis from the zero-padded working set: padding to
        // max(k, n) rows recovers the full n x n V factor from the thin
        // native SVD, and the modes at or below the 1e-12 rank cutoff form
        // Z. The projector form P = I - Vr'Vr is never used: at full rank
        // its all-epsilon entries read as full rank in the reduced solve.
        if direction.is_none() {
            direction = Some(DirectionSystem::new(a, &active, n, &objective)?);
        }
        let system = direction.as_ref()?;
        let zmat = &system.zmat;
        let zn = zmat.ncols();
        let p: Vec<f64> = if zn == 0 {
            vec![0.0; n]
        } else {
            let res: Vec<f64> = b.iter().zip(ax.iter()).map(|(bi, ai)| bi - ai).collect();
            let y = system.reduced.solve(&DVector::from_vec(res));
            (0..n)
                .map(|i| (0..zn).map(|j| zmat[(i, j)] * y[j]).sum())
                .collect()
        };
        if !p.iter().all(|v| v.is_finite()) {
            return None;
        }
        if norm(&p) <= tol.primal {
            // Stationary on the working set: multiplier signs decide, under
            // L = f - λc with λ >= 0 on inequalities and box sides.
            let grads: Vec<(Vec<f64>, bool)> = active.iter().map(|w| w.grad_row(n)).collect();
            let wmat = if k == 0 {
                DMatrix::zeros(0, n)
            } else {
                let flat: Vec<f64> = grads.iter().flat_map(|(w, _)| w.iter().copied()).collect();
                DMatrix::from_row_slice(k, n, &flat)
            };
            let lambda = lstsq(&wmat.transpose(), &DVector::from_vec(d.clone()));
            let gl: Vec<f64> = (0..n)
                .map(|j| (0..k).map(|r| wmat[(r, j)] * lambda[r]).sum())
                .collect();
            let residual = norm(
                &d.iter()
                    .zip(gl.iter())
                    .map(|(a, b)| a - b)
                    .collect::<Vec<f64>>(),
            );
            let mut worst: Option<usize> = None;
            let mut worst_val = 0.0f64;
            for (r, (_, nonneg)) in grads.iter().enumerate() {
                if !nonneg {
                    continue;
                }
                if lambda[r] < worst_val {
                    worst_val = lambda[r];
                    worst = Some(r);
                }
            }
            let scale = 1.0 + dnorm;
            let dual_ok = worst_val >= -tol.dual * scale;
            if dual_ok && residual <= tol.stationarity * scale {
                let slack = ie
                    .iter()
                    .map(|(row, lower)| dot(row, &x) - lower)
                    .fold(f64::INFINITY, f64::min);
                let box_slack = x
                    .iter()
                    .zip(bounds.iter())
                    .map(|(v, limit)| limit - v.abs())
                    .fold(f64::INFINITY, f64::min);
                // Prototype delivery gate: a stationary point that still
                // violates a general inequality is infeasible, never a
                // result, even with a zero gradient.
                if slack < -DELIVER_SLACK {
                    return None;
                }
                if eq_error_max(&eq, &x) > tol.equality
                    || x.iter()
                        .zip(bounds.iter())
                        .any(|(v, limit)| v.abs() > limit + tol.primal)
                {
                    return None;
                }
                return Some((
                    x.clone(),
                    QpInfo {
                        iterations: iteration + 1,
                        equality_error: eq_error_max(&eq, &x),
                        stationarity_error: residual,
                        inequality_slack: slack.min(box_slack).min(0.0),
                        active: active.len(),
                    },
                ));
            }
            if let Some(r) = worst {
                if worst_val < -tol.dual * scale {
                    // Release the most negative bound multiplier and continue.
                    active.remove(r);
                    direction = None;
                    continue;
                }
            }
            return None;
        }
        // Step to the first blocking bound or inequality.
        let mut step = 1.0f64;
        let mut blocking: Option<WorkRow> = None;
        for (i, &pi) in p.iter().enumerate() {
            if active
                .iter()
                .any(|w| matches!(w, WorkRow::Upper(j) | WorkRow::Lower(j) if *j == i))
            {
                continue;
            }
            if pi > tol.primal {
                let dist = (bounds[i] - x[i]) / pi;
                if dist < step {
                    step = dist.max(0.0);
                    blocking = Some(WorkRow::Upper(i));
                }
            } else if pi < -tol.primal {
                let dist = (-bounds[i] - x[i]) / pi;
                if dist < step {
                    step = dist.max(0.0);
                    blocking = Some(WorkRow::Lower(i));
                }
            }
        }
        for (row, lower) in ie {
            if active
                .iter()
                .any(|w| matches!(w, WorkRow::Ineq(r, l) if r == row && l == lower))
            {
                continue;
            }
            let denom = dot(row, &p);
            if denom < -tol.primal {
                let dist = (lower - dot(row, &x)) / denom;
                if dist < step {
                    step = dist.max(0.0);
                    blocking = Some(WorkRow::Ineq(row.clone(), *lower));
                }
            }
        }
        for (v, pi) in x.iter_mut().zip(p.iter()) {
            *v += step * pi;
        }
        // A recorded blocker was the strict minimum, so the step stops on
        // it; a full step leaves the working set unchanged.
        if let Some(work) = blocking {
            active.push(work);
            direction = None;
        }
    }
    None
}

fn eq_error_max(eq: &[(Vec<f64>, f64)], x: &[f64]) -> f64 {
    eq.iter()
        .map(|(row, h)| (dot(row, x) - h).abs())
        .fold(0.0_f64, f64::max)
}

/// Elastic Phase I: minimize t subject to Gx = h, Cx + t >= lower,
/// |x| <= bounds + t and t >= 0.
///
/// The auxiliary program has the known feasible start (x_eq, t0) with t0
/// the worst violation at the equality min-norm point, and its optimum is
/// t* = 0 exactly for feasible originals. It runs through the real
/// active-set core with release, so no row is ever frozen in: constraints
/// leave the working set by the same multiplier rule as the main solve.
/// Returns the repaired x when t* certifies feasibility; otherwise None,
/// which is the infeasible certificate the main solve would otherwise lack.
fn elastic_start(
    tol: &Tolerances,
    eq: &[(Vec<f64>, f64)],
    ie: &[(Vec<f64>, f64)],
    bounds: &[f64],
    x0: Vec<f64>,
) -> Option<Vec<f64>> {
    let n = x0.len();
    let mut t0 = 0.0f64;
    for (row, lower) in ie {
        t0 = t0.max(lower - dot(row, &x0));
    }
    for (v, limit) in x0.iter().zip(bounds.iter()) {
        t0 = t0.max(v.abs() - limit);
    }
    if !t0.is_finite() {
        return None;
    }
    let mut t_row = vec![0.0; n + 1];
    t_row[n] = 1.0;
    let eq_el: Vec<(Vec<f64>, f64)> = eq
        .iter()
        .map(|(w, h)| ([w.clone(), vec![0.0]].concat(), *h))
        .collect();
    let mut ie_el: Vec<(Vec<f64>, f64)> = Vec::with_capacity(ie.len() + 2 * n + 1);
    for (w, l) in ie {
        ie_el.push(([w.clone(), vec![1.0]].concat(), *l));
    }
    for (i, limit) in bounds.iter().enumerate() {
        let mut up = vec![0.0; n + 1];
        up[i] = -1.0;
        up[n] = 1.0;
        ie_el.push((up, -limit));
        let mut dn = vec![0.0; n + 1];
        dn[i] = 1.0;
        dn[n] = 1.0;
        ie_el.push((dn, -limit));
    }
    ie_el.push((t_row.clone(), 0.0));
    let eb: Vec<f64> = bounds
        .iter()
        .map(|l| l + t0 + 1e-6)
        .chain(std::iter::once(t0 + 1e-6))
        .collect();
    let mut start = x0;
    start.push(t0);
    let (xt, _) = solve_core(tol, &[t_row], &[0.0], &eq_el, &ie_el, &eb, start)?;
    // The handoff band admits near-zero slack only; delivery itself stays
    // gated on the prototype bands inside the main solve.
    if !(xt[n] <= 1e-7) {
        return None;
    }
    Some(xt[..n].to_vec())
}

/// Feasible primal active-set least squares with equality and box limits.
///
/// Native port of the joint-model `_bounded_equalities`: `a x = b` in the
/// least-squares sense subject to `g x = h` and `|x[i]| <= bounds[i]`.
/// Returns the displacement and solver evidence, or `None` when
/// initialization is infeasible or the iteration budget is exhausted.
pub(super) fn bounded_equalities(
    a: &[Vec<f64>],
    b: &[f64],
    g: &[Vec<f64>],
    h: &[f64],
    bounds: &[f64],
) -> Option<(Vec<f64>, QpInfo)> {
    active_set(
        &BOUNDED_TOL,
        a,
        b,
        &g.iter()
            .zip(h.iter())
            .map(|(r, v)| (r.clone(), *v))
            .collect::<Vec<_>>(),
        &[],
        bounds,
        true,
    )
}

/// Fixed convex least squares with linear constraints and box bounds.
///
/// Native port of the attached-model `_convex_qp`: minimizes
/// `1/2 |a x - b|^2` subject to `g x = h`, `c x >= lower` and
/// `|x| <= bound`. SciPy SLSQP supplies the prototype's numerical
/// candidate; this independent active-set implementation targets the same
/// constrained minimizer, gated by primal feasibility and the KKT
/// normal-cone check. Any rounding-level difference against an alternate
/// algorithm is diagnosed from these errors, never patched with offsets.
pub(super) fn convex_qp(
    a: &[Vec<f64>],
    b: &[f64],
    g: &[Vec<f64>],
    h: &[f64],
    c: &[Vec<f64>],
    lower: &[f64],
    bound: f64,
) -> Option<(Vec<f64>, QpInfo)> {
    let Some(n) = a
        .iter()
        .map(Vec::len)
        .chain(g.iter().map(Vec::len))
        .chain(c.iter().map(Vec::len))
        .max()
    else {
        return None;
    };
    // Prototype spectral normalization: the objective runs at
    // max(1, ||A||_2) so the SLSQP numerics and the KKT gates share one
    // scale. The minimizer is unchanged; the reported errors live in the
    // scaled system exactly as in the prototype.
    let scale = if a.is_empty() {
        1.0
    } else {
        let flat: Vec<f64> = a.iter().flat_map(|r| r.iter().copied()).collect();
        let normed = DMatrix::from_row_slice(a.len(), n, &flat);
        normed
            .svd(false, false)
            .singular_values
            .iter()
            .cloned()
            .fold(0.0_f64, f64::max)
            .max(1.0)
    };
    let a_scaled: Vec<Vec<f64>> = a
        .iter()
        .map(|r| r.iter().map(|v| v / scale).collect())
        .collect();
    let b_scaled: Vec<f64> = b.iter().map(|v| v / scale).collect();
    active_set(
        &CONVEX_TOL,
        &a_scaled,
        &b_scaled,
        &g.iter()
            .zip(h.iter())
            .map(|(r, v)| (r.clone(), *v))
            .collect::<Vec<_>>(),
        &c.iter()
            .zip(lower.iter())
            .map(|(r, v)| (r.clone(), *v))
            .collect::<Vec<_>>(),
        &vec![bound; n],
        false,
    )
}

// NIST Sparse BLAS matrix/vector and matrix/matrix operations:
// https://math.nist.gov/spblas/ . Exact-zero supports retain ascending
// accumulation order. Finite operands and nonzero finite results permit
// omitted zero products; otherwise the original dense dot retains signed
// zero, overflow and exceptional arithmetic. No approximate sparsity.
struct SparseObjective<'a> {
    dense: &'a [Vec<f64>],
    rows: Vec<Vec<(usize, f64)>>,
    cols: Vec<Vec<(usize, f64)>>,
}
impl<'a> SparseObjective<'a> {
    fn new(a: &'a [Vec<f64>], n: usize) -> Self {
        let mut cols = vec![Vec::new(); n];
        let rows = a
            .iter()
            .enumerate()
            .map(|(i, row)| {
                row.iter()
                    .enumerate()
                    .filter_map(|(j, &v)| {
                        if v != 0.0 {
                            cols[j].push((i, v));
                            Some((j, v))
                        } else {
                            None
                        }
                    })
                    .collect()
            })
            .collect();
        Self {
            dense: a,
            rows,
            cols,
        }
    }
    fn product(&self, x: &[f64]) -> Vec<f64> {
        let finite = x.iter().all(|v| v.is_finite());
        self.rows
            .iter()
            .zip(self.dense)
            .map(|(nz, row)| {
                if !finite {
                    return dot(row, x);
                }
                let value = nz.iter().map(|&(j, v)| v * x[j]).sum::<f64>();
                if value == 0.0 || !value.is_finite() {
                    dot(row, x)
                } else {
                    value
                }
            })
            .collect()
    }
    fn transpose_product(&self, at: &[Vec<f64>], x: &[f64]) -> Vec<f64> {
        let finite = x.iter().all(|v| v.is_finite());
        self.cols
            .iter()
            .zip(at)
            .map(|(nz, col)| {
                if !finite {
                    return dot(col, x);
                }
                let value = nz.iter().map(|&(i, v)| v * x[i]).sum::<f64>();
                if value == 0.0 || !value.is_finite() {
                    dot(col, x)
                } else {
                    value
                }
            })
            .collect()
    }
    fn project(&self, z: &DMatrix<f64>) -> DMatrix<f64> {
        let mut az = DMatrix::zeros(self.dense.len(), z.ncols());
        for j in 0..z.ncols() {
            let finite = z.column(j).iter().all(|v| v.is_finite());
            for (i, row) in self.dense.iter().enumerate() {
                let value = if finite {
                    self.rows[i]
                        .iter()
                        .map(|&(l, v)| v * z[(l, j)])
                        .sum::<f64>()
                } else {
                    f64::NAN
                };
                az[(i, j)] = if value == 0.0 || !value.is_finite() {
                    (0..row.len()).map(|l| row[l] * z[(l, j)]).sum()
                } else {
                    value
                };
            }
        }
        az
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordered_sparse_products_match_dense_rounding_and_exceptional_values() {
        // Dense BLAS-style arithmetic is the independent oracle for the
        // ordered Sparse BLAS adaptation, including cancellation and signed
        // zero. NaN classification is compared; payloads are not portable.
        let a = vec![
            vec![0.0, -0.0, 1.0, -1.0],
            vec![-0.0, 0.0, -0.0, 0.0],
            vec![1e308, 0.0, -1e308, 0.0],
            vec![0.0, 1e-300, 0.0, -1e-300],
            vec![1.0, 0.0, f64::from_bits(1), -0.0],
        ];
        let objective = SparseObjective::new(&a, 4);
        let xs = [
            [1.0, 0.0, 1.0, -0.0],
            [f64::from_bits(1), -0.0, -f64::from_bits(1), 1.0],
            [1e300, 1e-300, -1e300, -1e-300],
            [f64::INFINITY, 1.0, 1.0, 0.0],
            [1.0, f64::NAN, 1.0, 0.0],
        ];
        let same = |got: f64, want: f64| {
            if want.is_nan() {
                assert!(got.is_nan());
            } else {
                assert_eq!(got.to_bits(), want.to_bits());
            }
        };
        for x in xs {
            for (got, row) in objective.product(&x).iter().zip(&a) {
                same(*got, dot(row, &x));
            }
        }
        let at: Vec<Vec<f64>> = (0..4)
            .map(|j| a.iter().map(|row| row[j]).collect())
            .collect();
        for x in [
            [1.0, 0.0, 1.0, -0.0, 0.0],
            [0.0, -0.0, 0.0, 0.0, -0.0],
            [1.0, f64::INFINITY, 1.0, 1.0, 1.0],
        ] {
            for (got, row) in objective.transpose_product(&at, &x).iter().zip(&at) {
                same(*got, dot(row, &x));
            }
        }
        let z = DMatrix::from_fn(4, xs.len(), |i, j| xs[j][i]);
        let projected = objective.project(&z);
        for i in 0..a.len() {
            for j in 0..z.ncols() {
                same(projected[(i, j)], (0..4).map(|l| a[i][l] * z[(l, j)]).sum());
            }
        }
    }

    #[test]
    fn sparse_solver_preserves_exact_bound_contact_without_extra_active_row() {
        // The analytic minimum lies exactly on the upper bound. Reordered
        // arithmetic must not introduce an earlier blocking step or a
        // displacement in the objective's null coordinate.
        let (x, info) = convex_qp(
            &[vec![0.0, -1.0], vec![0.0, 0.0]],
            &[-0.5, -2.25],
            &[],
            &[],
            &[],
            &[],
            0.5,
        )
        .expect("feasible exact-bound minimum");
        assert_eq!(
            x.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
            vec![0.0f64.to_bits(), 0.5f64.to_bits()]
        );
        assert_eq!(info.active, 0);
        assert_eq!(info.iterations, 2);
    }

    fn close(x: &[f64], want: &[f64], tol: f64) {
        assert_eq!(x.len(), want.len());
        for (v, w) in x.iter().zip(want.iter()) {
            assert!((v - w).abs() <= tol, "{x:?} far from {want:?}");
        }
    }

    #[test]
    fn equality_projects_onto_affine_space() {
        // min |x - b|^2 s.t. x0 + x1 = 1 with b = (1, 2): analytic (0, 1).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![1.0, 2.0];
        let (x, info) = bounded_equalities(&a, &b, &[vec![1.0, 1.0]], &[1.0], &[10.0, 10.0])
            .expect("feasible equality solves");
        close(&x, &[0.0, 1.0], 1e-9);
        assert!(
            info.equality_error <= 1e-9,
            "primal residual {}",
            info.equality_error
        );
        assert!(
            info.stationarity_error <= 1e-9 * (1.0 + info.stationarity_error),
            "KKT residual {}",
            info.stationarity_error
        );
    }

    #[test]
    fn active_box_side_holds() {
        // Unconstrained minimizer (3, -2) violates x0 <= 0.5: the bound
        // activates and the joint optimum is (0.5, 0.5).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![5.0, 0.0];
        let (x, info) = bounded_equalities(&a, &b, &[vec![1.0, 1.0]], &[1.0], &[0.5, 10.0])
            .expect("box-feasible equality solves");
        close(&x, &[0.5, 0.5], 1e-9);
        assert!(info.equality_error <= 1e-9);
        assert!(x[0] <= 0.5 + 1e-12);
    }

    #[test]
    fn infeasible_start_returns_none() {
        // Equality demands x0 = 5 outside the box: no feasible start.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        assert!(bounded_equalities(&a, &b, &[vec![1.0, 0.0]], &[5.0], &[1.0, 1.0]).is_none());
    }

    #[test]
    fn rank_deficient_equalities_keep_minimum_norm() {
        // Doubled equality rows carry one constraint: (0.5, 0.5).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let g = vec![vec![1.0, 1.0], vec![2.0, 2.0]];
        let (x, info) = bounded_equalities(&a, &b, &g, &[1.0, 2.0], &[10.0, 10.0])
            .expect("rank-deficient equalities solve");
        close(&x, &[0.5, 0.5], 1e-9);
        assert!(info.equality_error <= 1e-9);
    }

    #[test]
    fn repeated_right_hand_sides_keep_minimum_norm() {
        // Both rows observe x0 + x1; x2 is unobserved. The analytic
        // minimum-norm solution divides each requested sum equally.
        let a = DMatrix::from_row_slice(2, 3, &[1.0, 1.0, 0.0, 2.0, 2.0, 0.0]);
        let system = LeastSquares::new(&a);
        for sum in [2.0, -4.0, 0.0, 6.0] {
            let x = system.solve(&DVector::from_vec(vec![sum, 2.0 * sum]));
            close(x.as_slice(), &[sum / 2.0, sum / 2.0, 0.0], 1e-12);
        }
    }

    #[test]
    fn obsolete_upper_bound_is_released() {
        // Unconstrained optimum (2, 3) first hits x0 = 0.5, then x1 = 1.
        // At that corner the x0 multiplier has the wrong sign, so the
        // first bound must leave. The constrained optimum is (0.4, 1):
        // gradient (0, -0.72), with only the upper x1 side active.
        // This exercises factor invalidation on both additions and release.
        let a = vec![vec![1.0, -0.8], vec![0.0, 0.6]];
        let (x, info) = bounded_equalities(&a, &[-0.4, 1.8], &[], &[], &[0.5, 1.0])
            .expect("feasible box solve releases the obsolete side");
        close(&x, &[0.4, 1.0], 1e-9);
        assert_eq!(info.active, 1);
        assert!(info.stationarity_error <= 1e-9);
    }

    #[test]
    fn inequality_cuts_the_unconstrained_minimum() {
        // min x0^2 + x1^2 s.t. x0 + x1 = 1 and x0 >= 0.5: (0.5, 0.5).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let (x, info) = convex_qp(
            &a,
            &b,
            &[vec![1.0, 1.0]],
            &[1.0],
            &[vec![1.0, 0.0]],
            &[0.5],
            10.0,
        )
        .expect("inequality-constrained minimum solves");
        close(&x, &[0.5, 0.5], 1e-9);
        assert!(info.equality_error <= 1e-8);
        assert!(info.stationarity_error <= 1e-7 * (1.0 + 1.0));
        assert!(info.inequality_slack <= 1e-9);
    }

    #[test]
    fn box_only_solve_keeps_interior_point() {
        // No equalities or inequalities: the objective minimum (0.3, 0.2)
        // already satisfies the box and must come back unchanged.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.3, 0.2];
        let empty: Vec<Vec<f64>> = Vec::new();
        let none: Vec<f64> = Vec::new();
        let (x, _) = convex_qp(&a, &b, &empty, &none, &empty, &none, 0.5)
            .expect("interior box solve returns the minimum");
        close(&x, &[0.3, 0.2], 1e-12);
    }

    #[test]
    fn feasible_lower_bound_repairs_infeasible_start() {
        // min x0^2 + x1^2 s.t. x0 >= 0.2: the zero start violates the bound
        // with a zero gradient, so delivery requires Phase-I repair, not an
        // infeasible-start abstain. The certified minimizer is (0.2, 0).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let empty: Vec<Vec<f64>> = Vec::new();
        let none: Vec<f64> = Vec::new();
        let (x, info) = convex_qp(&a, &b, &empty, &none, &[vec![1.0, 0.0]], &[0.2], 10.0)
            .expect("repaired feasible start solves");
        close(&x, &[0.2, 0.0], 1e-9);
        assert!(info.equality_error <= 1e-8);
        assert!(info.stationarity_error <= 1e-7 * (1.0 + 1.0));
    }

    #[test]
    fn active_lower_side_holds() {
        // The equality min-norm start (-0.65, -0.65) satisfies the box, but
        // the objective pulls x0 below -0.7: the lower side activates and
        // the joint optimum is (-0.7, -0.6), with a nonnegative multiplier
        // holding it there.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![-2.0, 0.0];
        let (x, info) = bounded_equalities(&a, &b, &[vec![1.0, 1.0]], &[-1.3], &[0.7, 10.0])
            .expect("box-feasible equality solves");
        close(&x, &[-0.7, -0.6], 1e-9);
        assert!(info.equality_error <= 1e-9);
        assert!(x[0] >= -0.7 - 1e-12);
    }

    #[test]
    fn real_source_s_joint_qp_matches_oracle() {
        // Frozen SourceSans 's' joint solve: the prototype active-set finds
        // a feasible KKT point in two iterations with no active bounds. The
        // native port must deliver the same point, isolating solver health
        // from row assembly. The tolerance admits alternate-LAPACK rounding,
        // never model drift.
        let raw: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fixtures/source-s-qp.json")).unwrap();
        // Fixture stores `a`/`g` as sparse rows: each row carries its
        // uniform zero (`0.0` or `-0.0`) plus indexed [col, value] nonzero
        // entries. Dense input is rebuilt here at the test boundary, so
        // solver numerics are unchanged.
        let mat = |k: &str| -> Vec<Vec<f64>> {
            let node = &raw[k];
            let ncols = node["ncols"].as_u64().unwrap() as usize;
            let rows = node["rows"].as_array().unwrap();
            assert_eq!(rows.len(), node["nrows"].as_u64().unwrap() as usize);
            rows.iter()
                .map(|row| {
                    let mut dense = vec![row["zero"].as_f64().unwrap(); ncols];
                    for e in row["entries"].as_array().unwrap() {
                        dense[e[0].as_u64().unwrap() as usize] = e[1].as_f64().unwrap();
                    }
                    dense
                })
                .collect()
        };
        let vecf = |k: &str| -> Vec<f64> {
            raw[k]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap())
                .collect()
        };
        let (a, b, g, h, bounds) = (mat("a"), vecf("b"), mat("g"), vecf("h"), vecf("bounds"));
        // Sparse-boundary bit identity: dimensions, nonzero counts and the
        // signed-zero rows survive reconstruction exactly.
        assert_eq!((a.len(), a[0].len()), (1432, 60));
        assert_eq!((g.len(), g[0].len()), (27, 60));
        assert_eq!(a.iter().flatten().filter(|v| **v != 0.0).count(), 4384);
        assert_eq!(g.iter().flatten().filter(|v| **v != 0.0).count(), 81);
        assert_eq!(
            a.iter()
                .filter(|row| row.iter().any(|v| v.to_bits() == (-0.0f64).to_bits()))
                .count(),
            722
        );
        assert_eq!(a[1][2].to_bits(), (-0.0f64).to_bits());
        let want = vecf("expected_x");
        let (x, info) = bounded_equalities(&a, &b, &g, &h, &bounds)
            .expect("real joint QP solves instead of phase-bounds-incompatible");
        assert!(
            info.equality_error <= 1e-9,
            "primal {}",
            info.equality_error
        );
        assert!(
            info.stationarity_error <= 1e-9,
            "kkt {}",
            info.stationarity_error
        );
        assert!(
            x.iter()
                .zip(bounds.iter())
                .all(|(v, l)| v.abs() <= l + 1e-9),
            "box respected"
        );
        let worst = x
            .iter()
            .zip(want.iter())
            .map(|(v, w)| (v - w).abs())
            .fold(0.0_f64, f64::max);
        assert!(worst <= 1e-6, "oracle drift {worst}");
    }

    #[test]
    fn box_violating_start_repairs_through_nullspace() {
        // Min-norm (0.8, 0.4) violates |x| <= 0.7, but the nullspace holds
        // the feasible (0.7, 0.6): the elastic Phase I must repair the start
        // instead of rejecting it, and the main solve then certifies the
        // KKT point. Analytic optimum (0.7, 0.6).
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let empty: Vec<Vec<f64>> = Vec::new();
        let none: Vec<f64> = Vec::new();
        let (x, info) = convex_qp(&a, &b, &[vec![2.0, 1.0]], &[2.0], &empty, &none, 0.7)
            .expect("repaired start solves");
        close(&x, &[0.7, 0.6], 1e-9);
        assert!(info.equality_error <= 1e-8);
        assert!(info.stationarity_error <= 1e-7 * (1.0 + 1.0));
        assert!(x.iter().all(|v| v.abs() <= 0.7 + 1e-9));
    }

    #[test]
    fn infeasible_box_certifies_none() {
        // Same geometry with h = 2.2: the line clears the box entirely, so
        // the elastic optimum keeps t* > 0 and the solver abstains with an
        // infeasible certificate instead of delivering.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let empty: Vec<Vec<f64>> = Vec::new();
        let none: Vec<f64> = Vec::new();
        assert!(convex_qp(&a, &b, &[vec![2.0, 1.0]], &[2.2], &empty, &none, 0.7).is_none());
    }

    #[test]
    fn contradictory_bounds_return_none() {
        // x0 >= 0.6 and the box cap |x0| <= 0.5 cannot both hold.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let b = vec![0.0, 0.0];
        let empty: Vec<Vec<f64>> = Vec::new();
        let none: Vec<f64> = Vec::new();
        assert!(convex_qp(&a, &b, &empty, &none, &[vec![1.0, 0.0]], &[0.6], 0.5).is_none());
    }
}
