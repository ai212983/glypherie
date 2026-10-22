//! Exact planar-arrangement topology for straight directed loops.
//!
//! Portable port of the CGAL arrangement reference
//! (`experiments/hobby_fitting/exact_topology/checker.cpp`, itself an
//! application of the [CGAL 6.1 arrangement/DCEL
//! model](https://doc.cgal.org/6.1/Arrangement_on_surface_2/index.html)):
//! split directed segments at exact intersections, subdivide faces as a
//! DCEL, propagate per-contour nonzero windings from the unbounded face,
//! and classify filled components, counters, labeled attachments and
//! contact singularities. Invariants: exact finite `f64` transport via
//! the shared exact scalar (never resnapped), neutral/coincident edges
//! retained for cover jumps, invalid or over-budget input fails closed
//! (`None`). Binary fractions use the shared checked/big integer tiers;
//! non-dyadic intersections and face probes retain rational quotients,
//! following CGAL's exact MP_Float/Quotient division boundary:
//! https://doc.cgal.org/latest/Number_types/classCGAL_1_1MP__Float.html
//! Output holds exactly the comparison keys of Python
//! `exact_topology._signature` minus area/seam evidence.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

use super::exact::Exact;
use super::filtered;
use serde_json::{json, Value};

/// Hard computational budget, not a geometric threshold: the 72-cell
/// ASCII corpus stays far below it. Oversize input fails closed.
const MAX_INPUT_EDGES: usize = 512;
/// Atomic-edge budget after exact splitting; oversize fails closed.
const MAX_ATOMIC_EDGES: usize = 8192;

/// Exact point with lexicographic order for canonical vertex keys.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct Pt(Exact, Exact);

impl Pt {
    fn mid(&self, other: &Pt) -> Pt {
        let two = Exact::integer(2);
        Pt((&self.0 + &other.0) / &two, (&self.1 + &other.1) / &two)
    }
}

fn cross(a: &(Exact, Exact), b: &(Exact, Exact)) -> Exact {
    &a.0 * &b.1 - &a.1 * &b.0
}

fn sub(a: &Pt, b: &Pt) -> (Exact, Exact) {
    (&a.0 - &b.0, &a.1 - &b.1)
}

/// Exact orientation sign of triangle (a, b, c); the certified
/// filter's fallback. Exact segment splitting still uses this path
/// whenever the filter is indecisive.
fn orient_exact(a: &Pt, b: &Pt, c: &Pt) -> i8 {
    let v = cross(&sub(b, a), &sub(c, a));
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}

/// Filter-first orientation for the exact splitting loop: decisive
/// interval sign, else exact. Intersection construction stays exact.
fn orient(a: &Pt, b: &Pt, c: &Pt) -> i8 {
    if let Some(s) = filtered::orient_sign((&a.0, &a.1), (&b.0, &b.1), (&c.0, &c.1)) {
        return s;
    }
    orient_exact(a, b, c)
}

fn is_upper(d: &(Exact, Exact)) -> bool {
    d.1.is_positive() || (d.1.is_zero() && d.0.is_positive())
}

/// Strict point-in-cycle test; the probe never lies on any edge.
fn strictly_inside(p: &Pt, verts: &[Pt]) -> bool {
    let mut inside = false;
    for i in 0..verts.len() {
        let a = &verts[i];
        let b = &verts[(i + 1) % verts.len()];
        if (a.1 > p.1) != (b.1 > p.1) {
            let x = &a.0 + (&p.1 - &a.1) * (&b.0 - &a.0) / (&b.1 - &a.1);
            if x > p.0 {
                inside = !inside;
            }
        }
    }
    inside
}

fn in_box(q: &Pt, a: &Pt, b: &Pt) -> bool {
    let (lox, hix) = if a.0 <= b.0 {
        (&a.0, &b.0)
    } else {
        (&b.0, &a.0)
    };
    let (loy, hiy) = if a.1 <= b.1 {
        (&a.1, &b.1)
    } else {
        (&b.1, &a.1)
    };
    &q.0 >= lox && &q.0 <= hix && &q.1 >= loy && &q.1 <= hiy
}

/// CGAL's closed-box broad phase:
/// https://doc.cgal.org/latest/Box_intersection_d/index.html
/// Bounds select existing finite input coordinates; no arithmetic, rounding
/// or rational-to-float conversion can shrink them. Strict separation alone
/// rejects a pair, retaining zero-width boxes, shared endpoints and overlaps.
#[derive(Clone, Copy)]
struct Bounds {
    min: [f64; 2],
    max: [f64; 2],
}

impl Bounds {
    fn new(a: [f64; 2], b: [f64; 2]) -> Self {
        Self {
            min: [a[0].min(b[0]), a[1].min(b[1])],
            max: [a[0].max(b[0]), a[1].max(b[1])],
        }
    }

    fn disjoint(self, other: Self) -> bool {
        self.max[0] < other.min[0]
            || other.max[0] < self.min[0]
            || self.max[1] < other.min[1]
            || other.max[1] < self.min[1]
    }
}

struct Seg {
    bounds: Bounds,
    a: Pt,
    b: Pt,
    contour: usize,
}

struct Atomic {
    a: Pt,
    b: Pt,
    va: usize,
    vb: usize,
    /// Net per-contour cover (+1 aligned / -1 opposed); zero nets erased.
    cover: BTreeMap<usize, i64>,
    /// Incident faces left of a->b and b->a.
    f1: usize,
    f2: usize,
}

/// Exact proper-crossing point of segments p+tr and q+us (nonparallel).
fn crossing(p: &Pt, r: &(Exact, Exact), q: &Pt, s: &(Exact, Exact)) -> Pt {
    let d = cross(r, s);
    let t = cross(&sub(q, p), s) / &d;
    Pt(&p.0 + &t * &r.0, &p.1 + &t * &r.1)
}

/// Exact arrangement with assigned vertex and face incidence.
struct Arrangement {
    atomics: Vec<Atomic>,
    incident: Vec<Vec<usize>>,
    members: Vec<Vec<usize>>,
    contours: Vec<usize>,
}

impl Arrangement {
    fn build(loops: &[Vec<[f64; 2]>]) -> Option<Self> {
        let inputs = lift_inputs(loops)?;
        let mut splits = split_inputs(&inputs);
        let mut atomics = assemble_atomics(&inputs, &mut splits)?;
        // Contour order matches the reference (sorted input labels).
        let mut contour_set = BTreeSet::new();
        for s in inputs.iter() {
            contour_set.insert(s.contour);
        }
        let contours: Vec<usize> = contour_set.into_iter().collect();
        let incident = index_vertices(&mut atomics);
        let (cycles, he_cycle) = trace_cycles(&atomics, incident.len())?;
        let members = group_faces(&mut atomics, &cycles, &he_cycle);
        Some(Self {
            atomics,
            incident,
            members,
            contours,
        })
    }

    fn atomics(&self) -> &[Atomic] {
        &self.atomics
    }

    fn incident(&self) -> &[Vec<usize>] {
        &self.incident
    }

    fn members(&self) -> &[Vec<usize>] {
        &self.members
    }

    fn contours(&self) -> &[usize] {
        &self.contours
    }

    fn nverts(&self) -> usize {
        self.incident.len()
    }

    fn nhe(&self) -> usize {
        2 * self.atomics.len()
    }

    fn nfaces(&self) -> usize {
        self.members.len()
    }
}

fn lift_inputs(loops: &[Vec<[f64; 2]>]) -> Option<Vec<Seg>> {
    let mut inputs: Vec<Seg> = Vec::new();
    for (label, contour) in loops.iter().enumerate() {
        let mut pts: Vec<Pt> = Vec::with_capacity(contour.len());
        for p in contour {
            pts.push(Pt(Exact::from_f64(p[0])?, Exact::from_f64(p[1])?));
        }
        if pts.is_empty() {
            continue;
        }
        for i in 0..pts.len() {
            let a = pts[i].clone();
            let b = pts[(i + 1) % pts.len()].clone();
            if a == b {
                continue; // Exact zero-length edges carry no winding.
            }
            inputs.push(Seg {
                bounds: Bounds::new(contour[i], contour[(i + 1) % pts.len()]),
                a,
                b,
                contour: label,
            });
        }
    }
    if inputs.is_empty() || inputs.len() > MAX_INPUT_EDGES {
        return None;
    }
    Some(inputs)
}

/// Split proper crossings, endpoint contacts and collinear overlaps.
fn split_inputs(inputs: &[Seg]) -> Vec<Vec<Pt>> {
    let mut splits: Vec<Vec<Pt>> = inputs
        .iter()
        .map(|s| vec![s.a.clone(), s.b.clone()])
        .collect();
    for i in 0..inputs.len() {
        for j in (i + 1)..inputs.len() {
            if inputs[i].bounds.disjoint(inputs[j].bounds) {
                continue;
            }
            let (a, b) = (&inputs[i].a, &inputs[i].b);
            let (c, d) = (&inputs[j].a, &inputs[j].b);
            let o1 = orient(a, b, c);
            let o2 = orient(a, b, d);
            let o3 = orient(c, d, a);
            let o4 = orient(c, d, b);
            if ((o1 == 1 && o2 == -1) || (o1 == -1 && o2 == 1))
                && ((o3 == 1 && o4 == -1) || (o3 == -1 && o4 == 1))
            {
                let x = crossing(a, &sub(b, a), c, &sub(d, c));
                splits[i].push(x.clone());
                splits[j].push(x);
                continue;
            }
            for (q, slot) in [(c, i), (d, i), (a, j), (b, j)] {
                let (p, r) = if slot == i { (a, b) } else { (c, d) };
                if orient(p, r, q) == 0 && in_box(q, p, r) {
                    splits[slot].push(q.clone());
                }
            }
        }
    }
    splits
}

/// Retain neutral edges when opposing contour contributions cancel.
fn assemble_atomics(inputs: &[Seg], splits: &mut [Vec<Pt>]) -> Option<Vec<Atomic>> {
    let mut atomics: Vec<Atomic> = Vec::new();
    let mut edge_index: BTreeMap<(Pt, Pt), usize> = BTreeMap::new();
    for (i, seg) in inputs.iter().enumerate() {
        let dx = &seg.b.0 - &seg.a.0;
        let dy = &seg.b.1 - &seg.a.1;
        let use_x = dx.abs() >= dy.abs();
        splits[i].sort_by(|p, q| {
            let o = if use_x { p.0.cmp(&q.0) } else { p.1.cmp(&q.1) };
            o.then_with(|| p.1.cmp(&q.1).then_with(|| p.0.cmp(&q.0)))
        });
        splits[i].dedup();
        for w in splits[i].windows(2) {
            let (lo, hi) = if w[0] <= w[1] {
                (&w[0], &w[1])
            } else {
                (&w[1], &w[0])
            };
            let key = (lo.clone(), hi.clone());
            // Each split edge is collinear with a nonzero input segment,
            // so this dot product cannot be zero.
            let dot =
                (&seg.b.0 - &seg.a.0) * (&hi.0 - &lo.0) + (&seg.b.1 - &seg.a.1) * (&hi.1 - &lo.1);
            let aligned = dot.is_positive();
            let id = match edge_index.get(&key) {
                Some(&id) => id,
                None => {
                    if atomics.len() >= MAX_ATOMIC_EDGES {
                        return None;
                    }
                    let id = atomics.len();
                    atomics.push(Atomic {
                        a: key.0.clone(),
                        b: key.1.clone(),
                        va: 0,
                        vb: 0,
                        cover: BTreeMap::new(),
                        f1: 0,
                        f2: 0,
                    });
                    edge_index.insert(key, id);
                    id
                }
            };
            let net = atomics[id].cover.entry(seg.contour).or_insert(0);
            *net += if aligned { 1 } else { -1 };
            if *net == 0 {
                atomics[id].cover.remove(&seg.contour);
            }
        }
    }
    if atomics.is_empty() {
        return None;
    }
    Some(atomics)
}

/// Merge endpoints by exact coordinate equality.
fn index_vertices(atomics: &mut [Atomic]) -> Vec<Vec<usize>> {
    let mut vertex_index: BTreeMap<Pt, usize> = BTreeMap::new();
    let mut incident: Vec<Vec<usize>> = Vec::new();
    for e in atomics.iter_mut() {
        for end in [e.a.clone(), e.b.clone()] {
            if !vertex_index.contains_key(&end) {
                let id = incident.len();
                vertex_index.insert(end, id);
                incident.push(Vec::new());
            }
        }
        e.va = vertex_index[&e.a];
        e.vb = vertex_index[&e.b];
    }
    for (id, e) in atomics.iter().enumerate() {
        incident[e.va].push(id);
        incident[e.vb].push(id);
    }
    incident
}

fn trace_cycles(atomics: &[Atomic], nverts: usize) -> Option<(Vec<Vec<usize>>, Vec<usize>)> {
    // Directed half-edges: 2e is a->b, 2e+1 is b->a.
    let mut outgoing: Vec<Vec<usize>> = vec![Vec::new(); nverts];
    for e in 0..atomics.len() {
        outgoing[atomics[e].va].push(2 * e);
        outgoing[atomics[e].vb].push(2 * e + 1);
    }
    // Outgoing half-edges in exact CCW order (half-plane + cross
    // product, never atan2).
    let mut he_dir: Vec<(Exact, Exact)> = Vec::with_capacity(2 * atomics.len());
    for e in 0..atomics.len() {
        he_dir.push(sub(&atomics[e].b, &atomics[e].a));
        he_dir.push(sub(&atomics[e].a, &atomics[e].b));
    }
    for list in outgoing.iter_mut() {
        list.sort_by(|&h, &k| {
            let (dh, dk) = (&he_dir[h], &he_dir[k]);
            let (uh, uk) = (is_upper(dh), is_upper(dk));
            if uh != uk {
                return uk.cmp(&uh); // Upper half-plane first (CCW from +x).
            }
            let c = cross(dh, dk);
            if !c.is_zero() {
                return if c.is_positive() {
                    std::cmp::Ordering::Less
                } else {
                    std::cmp::Ordering::Greater
                };
            }
            h.cmp(&k)
        });
    }
    let mut rank: Vec<Vec<usize>> = vec![Vec::new(); nverts];
    for v in 0..nverts {
        rank[v].resize(2 * atomics.len(), usize::MAX);
        for (pos, &he) in outgoing[v].iter().enumerate() {
            rank[v][he] = pos;
        }
    }
    // Trace left-face boundary cycles: next(h) is the clockwise
    // predecessor of twin(h) around its target.
    let nhe = 2 * atomics.len();
    let mut he_cycle = vec![usize::MAX; nhe];
    let mut cycles: Vec<Vec<usize>> = Vec::new();
    for start in 0..nhe {
        if he_cycle[start] != usize::MAX {
            continue;
        }
        let id = cycles.len();
        let mut cyc = Vec::new();
        let mut he = start;
        loop {
            he_cycle[he] = id;
            cyc.push(he);
            let twin = he ^ 1;
            let e = he / 2;
            let v = if he % 2 == 0 {
                atomics[e].vb
            } else {
                atomics[e].va
            };
            let deg = outgoing[v].len();
            he = outgoing[v][(rank[v][twin] + deg - 1) % deg];
            if he == start {
                break;
            }
            if cyc.len() > nhe + 1 {
                return None; // Inconsistent topology fails closed.
            }
        }
        cycles.push(cyc);
    }
    Some((cycles, he_cycle))
}

fn group_faces(
    atomics: &mut [Atomic],
    cycles: &[Vec<usize>],
    he_cycle: &[usize],
) -> Vec<Vec<usize>> {
    // Doubled signed areas classify outers (+) / holes (-) / bridges (0).
    let mut cycle_area: Vec<Exact> = Vec::with_capacity(cycles.len());
    for cyc in cycles.iter() {
        let mut s = Exact::zero();
        for &he in cyc {
            let e = &atomics[he / 2];
            let (p, q) = if he % 2 == 0 {
                (&e.a, &e.b)
            } else {
                (&e.b, &e.a)
            };
            s += &p.0 * &q.1 - &q.0 * &p.1;
        }
        cycle_area.push(s);
    }
    // Each positive cycle is the outer boundary of a new face;
    // negative/zero cycles attach to the innermost strictly containing
    // positive cycle (or the unbounded face). Probes sit left of a cycle
    // edge at half the nearest positive ray distance, so no epsilon.
    let cycle_verts = |cyc: &[usize]| -> Vec<Pt> {
        cyc.iter()
            .map(|&he| {
                let e = &atomics[he / 2];
                if he % 2 == 0 {
                    e.a.clone()
                } else {
                    e.b.clone()
                }
            })
            .collect()
    };
    let left_probe = |cyc: &[usize]| -> Pt {
        let he = cyc[0];
        let e = &atomics[he / 2];
        let (s, t) = if he % 2 == 0 {
            (&e.a, &e.b)
        } else {
            (&e.b, &e.a)
        };
        let m = s.mid(t);
        let d = sub(t, s);
        let n = (-d.1.clone(), d.0.clone());
        let nn = &n.0 * &n.0 + &n.1 * &n.1;
        let mut best: Option<Exact> = None;
        for f in atomics.iter() {
            let q = sub(&f.b, &f.a);
            let den = cross(&n, &q);
            if den.is_zero() {
                // Collinear with the ray: nearest endpoint ahead counts.
                let w = sub(&f.a, &m);
                if cross(&w, &q).is_zero() && cross(&w, &n).is_zero() {
                    for end in [&f.a, &f.b] {
                        let w = sub(end, &m);
                        let tt = (&w.0 * &n.0 + &w.1 * &n.1) / &nn;
                        if tt.is_positive() && best.as_ref().is_none_or(|b| tt < *b) {
                            best = Some(tt);
                        }
                    }
                }
                continue;
            }
            let w = sub(&f.a, &m);
            let tt = cross(&w, &q) / &den;
            let u = cross(&w, &n) / &den;
            if tt.is_positive() && !u.is_negative() && u <= Exact::integer(1) {
                if best.as_ref().is_none_or(|b| tt < *b) {
                    best = Some(tt);
                }
            }
        }
        let half = best
            .map(|t| t / Exact::integer(2))
            .unwrap_or_else(|| Exact::integer(1));
        Pt(&m.0 + &half * &n.0, &m.1 + &half * &n.1)
    };
    let positives: Vec<usize> = (0..cycles.len())
        .filter(|&c| cycle_area[c].is_positive())
        .collect();
    let pos_verts: Vec<Vec<Pt>> = positives.iter().map(|&c| cycle_verts(&cycles[c])).collect();
    let mut face_of_cycle = vec![0usize; cycles.len()];
    for (fi, &c) in positives.iter().enumerate() {
        face_of_cycle[c] = fi + 1;
    }
    for c in 0..cycles.len() {
        if cycle_area[c].is_positive() {
            continue;
        }
        let p = left_probe(&cycles[c]);
        let mut owner = 0usize;
        let mut owner_area: Option<Exact> = None;
        for (k, &pc) in positives.iter().enumerate() {
            if strictly_inside(&p, &pos_verts[k])
                && owner_area.as_ref().is_none_or(|b| cycle_area[pc] < *b)
            {
                owner = k + 1;
                owner_area = Some(cycle_area[pc].clone());
            }
        }
        face_of_cycle[c] = owner;
    }
    let nfaces = positives.len() + 1;
    let nhe = 2 * atomics.len();
    let mut members: Vec<Vec<usize>> = vec![Vec::new(); nfaces];
    for he in 0..nhe {
        members[face_of_cycle[he_cycle[he]]].push(he);
    }
    for e in 0..atomics.len() {
        atomics[e].f1 = face_of_cycle[he_cycle[2 * e]];
        atomics[e].f2 = face_of_cycle[he_cycle[2 * e + 1]];
    }
    members
}

/// Public entry: canonical topology signature, or `None` fail-closed.
pub fn signature(loops: &[Vec<[f64; 2]>]) -> Option<Value> {
    let arrangement = Arrangement::build(loops)?;
    let atomics = arrangement.atomics();
    let incident = arrangement.incident();
    let members = arrangement.members();
    let contours = arrangement.contours();
    let nverts = arrangement.nverts();
    let nhe = arrangement.nhe();
    let nfaces = arrangement.nfaces();
    let ncont = contours.len();
    let cindex: BTreeMap<usize, usize> =
        contours.iter().enumerate().map(|(i, &c)| (c, i)).collect();

    // Directed jump of each half-edge: cover net, negated for twins.
    let mut jump: Vec<Vec<(usize, i64)>> = vec![Vec::new(); nhe];
    for e in 0..atomics.len() {
        for (label, net) in atomics[e].cover.iter() {
            jump[2 * e].push((cindex[label], *net));
            jump[2 * e + 1].push((cindex[label], -*net));
        }
    }
    // Per-contour windings from the unbounded face: W[left] equals
    // W[right] plus the half-edge jump; spikes cancel in the sum.
    let mut wind = vec![vec![0i64; ncont]; nfaces];
    let mut known = vec![false; nfaces];
    let mut queue = VecDeque::new();
    known[0] = true;
    queue.push_back(0usize);
    while let Some(cur) = queue.pop_front() {
        for &he in members[cur].iter() {
            let e = he / 2;
            let (left, right) = if he % 2 == 0 {
                (atomics[e].f1, atomics[e].f2)
            } else {
                (atomics[e].f2, atomics[e].f1)
            };
            let (nxt, sign) = if left == cur && !known[right] {
                (right, -1i64)
            } else if right == cur && !known[left] {
                (left, 1i64)
            } else {
                continue;
            };
            wind[nxt] = wind[cur].clone();
            for &(c, net) in jump[he].iter() {
                wind[nxt][c] += sign * net;
            }
            known[nxt] = true;
            queue.push_back(nxt);
        }
    }
    if known.iter().any(|&k| !k) {
        return None; // Disconnected face graph fails closed.
    }
    for he in 0..nhe {
        let e = he / 2;
        let (left, right) = if he % 2 == 0 {
            (atomics[e].f1, atomics[e].f2)
        } else {
            (atomics[e].f2, atomics[e].f1)
        };
        let mut delta = vec![0i64; ncont];
        for &(c, net) in jump[he].iter() {
            delta[c] += net;
        }
        for c in 0..ncont {
            if wind[left][c] - wind[right][c] != delta[c] {
                return None; // Inconsistent winding fails closed.
            }
        }
    }
    let mut global = vec![0i64; nfaces];
    for f in 0..nfaces {
        global[f] = wind[f].iter().sum();
    }

    // Filled components merge over any shared edge, seams included.
    let mut comp = vec![-1i32; nfaces];
    let mut ncomp = 0i32;
    for f in 0..nfaces {
        if global[f] == 0 || comp[f] >= 0 {
            continue;
        }
        let mut q = VecDeque::new();
        q.push_back(f);
        comp[f] = ncomp;
        while let Some(cur) = q.pop_front() {
            for e in 0..atomics.len() {
                if atomics[e].f1 != cur && atomics[e].f2 != cur {
                    continue;
                }
                let ni = if atomics[e].f1 == cur {
                    atomics[e].f2
                } else {
                    atomics[e].f1
                };
                if global[ni] != 0 && comp[ni] < 0 {
                    comp[ni] = ncomp;
                    q.push_back(ni);
                }
            }
        }
        ncomp += 1;
    }
    // White components merge across zero edges; the unbounded holder
    // is the exterior, never a counter.
    let mut white = vec![-1i32; nfaces];
    let mut nwhite = 0i32;
    let mut exterior = 0i32;
    for f in 0..nfaces {
        if global[f] != 0 || white[f] >= 0 {
            continue;
        }
        let mut q = VecDeque::new();
        q.push_back(f);
        white[f] = nwhite;
        if f == 0 {
            exterior = nwhite;
        }
        while let Some(cur) = q.pop_front() {
            for e in 0..atomics.len() {
                if atomics[e].f1 != cur && atomics[e].f2 != cur {
                    continue;
                }
                let ni = if atomics[e].f1 == cur {
                    atomics[e].f2
                } else {
                    atomics[e].f1
                };
                if global[ni] == 0 && white[ni] < 0 {
                    white[ni] = nwhite;
                    if ni == 0 {
                        exterior = nwhite;
                    }
                    q.push_back(ni);
                }
            }
        }
        nwhite += 1;
    }
    // Component contour labels from boundary half-edges.
    let ncomp = ncomp as usize;
    let mut comp_labels: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); ncomp];
    for e in atomics.iter() {
        let (b1, b2) = (global[e.f1] != 0, global[e.f2] != 0);
        if b1 != b2 {
            let c = if b1 {
                comp[e.f1] as usize
            } else {
                comp[e.f2] as usize
            };
            for label in e.cover.keys() {
                comp_labels[c].insert(*label);
            }
        }
    }
    // Boundary degree and filled-component contacts per vertex.
    let mut degree = vec![0u64; nverts];
    let mut vcomps: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); nverts];
    for e in atomics.iter() {
        let (b1, b2) = (global[e.f1] != 0, global[e.f2] != 0);
        for &v in &[e.va, e.vb] {
            if b1 != b2 {
                degree[v] += 1;
            }
            if b1 {
                vcomps[v].insert(comp[e.f1] as usize);
            }
            if b2 {
                vcomps[v].insert(comp[e.f2] as usize);
            }
        }
    }
    // Pinch roster: degree >= 4 with labeled sides, canonical order.
    let mut pinches: Vec<(u64, Vec<Vec<usize>>)> = Vec::new();
    let mut contacts: Vec<Vec<Vec<usize>>> = Vec::new();
    for v in 0..nverts {
        if degree[v] >= 4 {
            let sides: Vec<Vec<usize>> = vcomps[v]
                .iter()
                .map(|&c| comp_labels[c].iter().cloned().collect())
                .collect();
            let mut ordered = sides.clone();
            for s in ordered.iter_mut() {
                s.sort();
            }
            ordered.sort();
            pinches.push((degree[v], ordered.clone()));
            if vcomps[v].len() >= 2 {
                contacts.push(ordered);
            }
        }
    }
    pinches.sort();
    contacts.sort();
    // Holes are bounded white components; adjacency comes from the
    // hole's own boundary edges, not whole-component labels.
    let mut comp_holes = vec![0u64; ncomp];
    let mut hole_adj: Vec<Vec<usize>> = Vec::new();
    let white_faces_of =
        |w: i32| -> Vec<usize> { (0..nfaces).filter(|&f| white[f] == w).collect() };
    for w in 0..nwhite as i32 {
        if w == exterior {
            continue;
        }
        let mut adjacent = BTreeSet::new();
        let mut adj_comps = BTreeSet::new();
        for f in white_faces_of(w) {
            for e in atomics.iter() {
                if e.f1 != f && e.f2 != f {
                    continue;
                }
                let ni = if e.f1 == f { e.f2 } else { e.f1 };
                if global[ni] == 0 {
                    continue;
                }
                adj_comps.insert(comp[ni] as usize);
                for label in e.cover.keys() {
                    adjacent.insert(*label);
                }
            }
        }
        for &c in adj_comps.iter() {
            comp_holes[c] += 1;
        }
        hole_adj.push(adjacent.into_iter().collect());
    }
    hole_adj.sort();
    // Per-pair attachment classes; masks use individual contour
    // windings so coincident cancellations still expose sharing.
    let mut pairs: Vec<(Vec<usize>, u64, u64, u64, u64, Vec<u64>)> = Vec::new();
    // Face adjacency once for the flood fills below.
    let mut face_edges: Vec<Vec<usize>> = vec![Vec::new(); nfaces];
    for (e, a) in atomics.iter().enumerate() {
        face_edges[a.f1].push(e);
        if a.f2 != a.f1 {
            face_edges[a.f2].push(e);
        }
    }
    let neighbor = |f: usize, e: usize| -> usize {
        if atomics[e].f1 == f {
            atomics[e].f2
        } else {
            atomics[e].f1
        }
    };
    for ai in 0..ncont {
        for bi in (ai + 1)..ncont {
            let in_mask = |f: usize| wind[f][ai] != 0 && wind[f][bi] != 0;
            let mut seen = vec![false; nfaces];
            let mut area_components = 0u64;
            for f in 0..nfaces {
                if !in_mask(f) || seen[f] {
                    continue;
                }
                area_components += 1;
                let mut q = VecDeque::new();
                q.push_back(f);
                seen[f] = true;
                while let Some(cur) = q.pop_front() {
                    for &e in face_edges[cur].iter() {
                        let ni = neighbor(cur, e);
                        if in_mask(ni) && !seen[ni] {
                            seen[ni] = true;
                            q.push_back(ni);
                        }
                    }
                }
            }
            let mut wmask = vec![-1i32; nfaces];
            let mut area_holes = 0u64;
            let mut nw = 0i32;
            for f in 0..nfaces {
                if in_mask(f) || wmask[f] >= 0 {
                    continue;
                }
                let mut q = VecDeque::new();
                q.push_back(f);
                wmask[f] = nw;
                let mut touches = f == 0;
                while let Some(cur) = q.pop_front() {
                    for &e in face_edges[cur].iter() {
                        let ni = neighbor(cur, e);
                        if !in_mask(ni) && wmask[ni] < 0 {
                            wmask[ni] = nw;
                            if ni == 0 {
                                touches = true;
                            }
                            q.push_back(ni);
                        }
                    }
                }
                if !touches {
                    area_holes += 1;
                }
                nw += 1;
            }
            // Pure edge contacts: both contours cover the edge but no
            // incident face carries the intersection mask.
            let mut edge_contact = vec![false; atomics.len()];
            for (e, a) in atomics.iter().enumerate() {
                let (mut ca, mut cb) = (false, false);
                for label in a.cover.keys() {
                    if *label == contours[ai] {
                        ca = true;
                    }
                    if *label == contours[bi] {
                        cb = true;
                    }
                }
                if ca && cb && !in_mask(a.f1) && !in_mask(a.f2) {
                    edge_contact[e] = true;
                }
            }
            let edge_components = {
                let mut parent: Vec<usize> = (0..nverts).collect();
                fn find(p: &mut [usize], mut x: usize) -> usize {
                    let mut root = x;
                    while p[root] != root {
                        root = p[root];
                    }
                    while p[x] != root {
                        let nxt = p[x];
                        p[x] = root;
                        x = nxt;
                    }
                    root
                }
                for (e, a) in atomics.iter().enumerate() {
                    if edge_contact[e] {
                        let (u, v) = (find(&mut parent, a.va), find(&mut parent, a.vb));
                        if u != v {
                            parent[u] = v;
                        }
                    }
                }
                let mut roots = BTreeSet::new();
                for (e, a) in atomics.iter().enumerate() {
                    if edge_contact[e] {
                        roots.insert(find(&mut parent, a.va));
                    }
                }
                roots.len() as u64
            };
            let mut point_contacts = 0u64;
            for v in 0..nverts {
                let (mut ca, mut cb, mut mask_near, mut edge_near) = (false, false, false, false);
                for &e in incident[v].iter() {
                    for label in atomics[e].cover.keys() {
                        if *label == contours[ai] {
                            ca = true;
                        }
                        if *label == contours[bi] {
                            cb = true;
                        }
                    }
                    if edge_contact[e] {
                        edge_near = true;
                    }
                    if in_mask(atomics[e].f1) || in_mask(atomics[e].f2) {
                        mask_near = true;
                    }
                }
                if ca && cb && !mask_near && !edge_near {
                    point_contacts += 1;
                }
            }
            // Intersection-mask boundary singularities: incident edges
            // separating mask interior from exterior; manifold boundary
            // vertices have degree 2, anything else is a pinch/branch.
            let mut boundary_degrees: Vec<u64> = Vec::new();
            for v in 0..nverts {
                let mut deg = 0u64;
                for &e in incident[v].iter() {
                    if in_mask(atomics[e].f1) != in_mask(atomics[e].f2) {
                        deg += 1;
                    }
                }
                if deg > 0 && deg != 2 {
                    boundary_degrees.push(deg);
                }
            }
            boundary_degrees.sort();
            if area_components > 0
                || area_holes > 0
                || edge_components > 0
                || point_contacts > 0
                || !boundary_degrees.is_empty()
            {
                pairs.push((
                    vec![contours[ai], contours[bi]],
                    area_components,
                    area_holes,
                    edge_components,
                    point_contacts,
                    boundary_degrees,
                ));
            }
        }
    }
    pairs.sort();
    let mut comp_rows: Vec<(Vec<usize>, u64)> = Vec::with_capacity(ncomp);
    for c in 0..ncomp {
        comp_rows.push((comp_labels[c].iter().cloned().collect(), comp_holes[c]));
    }
    comp_rows.sort();
    Some(ok_json(
        ncomp, hole_adj, pinches, contacts, pairs, comp_rows,
    ))
}

/// Canonical comparison object: equality keys only, same names as the
/// Python signature; seam/area/pinch-count evidence never gates equality.
#[allow(clippy::too_many_arguments)]
fn ok_json(
    ncomp: usize,
    hole_adj: Vec<Vec<usize>>,
    pinches: Vec<(u64, Vec<Vec<usize>>)>,
    contacts: Vec<Vec<Vec<usize>>>,
    pairs: Vec<(Vec<usize>, u64, u64, u64, u64, Vec<u64>)>,
    comp_rows: Vec<(Vec<usize>, u64)>,
) -> Value {
    json!({
        "filled_components": ncomp,
        "holes": hole_adj.len(),
        "pinch_roster": pinches.iter().map(|(d, sides)| json!({
            "degree": d, "components": sides
        })).collect::<Vec<_>>(),
        "point_contacts": contacts.iter().map(|sides| json!({ "sides": sides })).collect::<Vec<_>>(),
        "hole_boundaries": hole_adj,
        "pairs": pairs.iter().map(|(pair, ac, ah, ec, pc, bd)| json!({
            "pair": pair, "area_components": ac, "area_holes": ah,
            "edge_components": ec, "point_contacts": pc, "boundary_degrees": bd
        })).collect::<Vec<_>>(),
        "components": comp_rows.iter().map(|(contours, holes)| json!({
            "contours": contours, "holes": holes
        })).collect::<Vec<_>>(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<[f64; 2]> {
        vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    }

    fn rect_cw(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<[f64; 2]> {
        vec![[x0, y0], [x0, y1], [x1, y1], [x1, y0]]
    }

    fn sig(loops: &[Vec<[f64; 2]>]) -> Value {
        signature(loops).expect("supported topology")
    }

    #[test]
    fn closed_bounds_retain_boundary_and_zero_width_contacts() {
        // CGAL CLOSED boxes include boundaries and zero-width intervals.
        // These segments share endpoints, overlap collinearly, cross, or
        // only have touching bounds; every case must reach exact predicates.
        let a = Bounds::new([0.0, 0.0], [0.0, 2.0]);
        for (p, q) in [
            ([0.0, 2.0], [0.0, 3.0]),
            ([0.0, 1.0], [0.0, 3.0]),
            ([-1.0, 1.0], [1.0, 1.0]),
            ([0.0, 2.0], [2.0, 0.0]),
            ([-0.0, -0.0], [-0.0, 1.0]),
        ] {
            assert!(!a.disjoint(Bounds::new(p, q)));
        }
        // A one-ULP gap, even the smallest subnormal, is real separation.
        let gap = f64::from_bits(1);
        assert!(a.disjoint(Bounds::new([gap, 0.0], [gap, 2.0])));
        let n = f64::from_bits(1.0f64.to_bits() + 1);
        assert!(Bounds::new([0.0, 0.0], [1.0, 1.0]).disjoint(Bounds::new([n, 0.0], [n, 1.0])));
    }

    #[test]
    fn disjoint_bounds_exclude_exact_segment_contacts() {
        // Independent rational predicates verify the broad phase's only
        // rejection claim, including all directions on a 3x3 grid and
        // fractional coordinates. This never treats box overlap as proof
        // of a segment contact.
        let points: Vec<[f64; 2]> = [-1.0, 0.0, 1.0]
            .into_iter()
            .flat_map(|x| [-1.0, 0.0, 1.0].map(|y| [x, y]))
            .chain([[0.25, 0.5], [-0.5, 0.25], [1.0, 1.0 + f64::EPSILON]])
            .collect();
        use num_rational::BigRational as Rational;
        use num_traits::{FromPrimitive, Signed, Zero};
        type RationalPoint = (Rational, Rational);
        let rational_orient = |a: &RationalPoint, b: &RationalPoint, c: &RationalPoint| {
            let det = (&b.0 - &a.0) * (&c.1 - &a.1) - (&b.1 - &a.1) * (&c.0 - &a.0);
            if det.is_zero() {
                0
            } else if det.is_positive() {
                1
            } else {
                -1
            }
        };
        let rational_in_box = |q: &RationalPoint, a: &RationalPoint, b: &RationalPoint| {
            q.0 >= a.0.clone().min(b.0.clone())
                && q.0 <= a.0.clone().max(b.0.clone())
                && q.1 >= a.1.clone().min(b.1.clone())
                && q.1 <= a.1.clone().max(b.1.clone())
        };
        let mut segments = Vec::new();
        for i in 0..points.len() {
            for j in i + 1..points.len() {
                let exact = |p: [f64; 2]| {
                    (
                        Rational::from_f64(p[0]).unwrap(),
                        Rational::from_f64(p[1]).unwrap(),
                    )
                };
                segments.push((
                    Bounds::new(points[i], points[j]),
                    exact(points[i]),
                    exact(points[j]),
                ));
            }
        }
        for (box_a, a, b) in &segments {
            for (box_b, c, d) in &segments {
                if !box_a.disjoint(*box_b) {
                    continue;
                }
                let (o1, o2, o3, o4) = (
                    rational_orient(a, b, c),
                    rational_orient(a, b, d),
                    rational_orient(c, d, a),
                    rational_orient(c, d, b),
                );
                assert!(!(o1 * o2 < 0 && o3 * o4 < 0));
                assert!(!(o1 == 0 && rational_in_box(c, a, b)));
                assert!(!(o2 == 0 && rational_in_box(d, a, b)));
                assert!(!(o3 == 0 && rational_in_box(a, c, d)));
                assert!(!(o4 == 0 && rational_in_box(b, c, d)));
            }
        }
    }

    #[test]
    fn rect_single_component() {
        assert_eq!(
            sig(&[rect(0.0, 0.0, 100.0, 50.0)]),
            json!({
                "filled_components": 1, "holes": 0,
                "pinch_roster": [], "point_contacts": [],
                "hole_boundaries": [], "pairs": [],
                "components": [{"contours": [0], "holes": 0}],
            })
        );
    }

    #[test]
    fn non_dyadic_crossing_remains_exact() {
        // Two integer-coordinate segments intersect at (1/3, 2/3).
        // The construction must retain those rational coordinates, as
        // required by CGAL's exact quotient construction model.
        let point = |x, y| Pt(Exact::integer(x), Exact::integer(y));
        let p = point(0, 0);
        let a = point(1, 2);
        let q = point(0, 1);
        let b = point(1, 0);
        let hit = crossing(&p, &sub(&a, &p), &q, &sub(&b, &q));
        assert_eq!(
            hit.0.to_rational(),
            num_rational::BigRational::new(1.into(), 3.into())
        );
        assert_eq!(
            hit.1.to_rational(),
            num_rational::BigRational::new(2.into(), 3.into())
        );
    }

    #[test]
    fn wide_binary_exponents_preserve_rectangle_topology() {
        // A displacement from the smallest subnormal to 1 needs more
        // than 128 mantissa bits. Promotion must retain the rectangle's
        // analytic topology, including exact face-probe construction.
        let tiny = f64::from_bits(1);
        assert_eq!(
            sig(&[rect(-tiny, -tiny, 1.0, 1.0)]),
            sig(&[rect(0.0, 0.0, 1.0, 1.0)]),
        );
    }

    #[test]
    fn rect_with_hole_labels() {
        // Ground truth from the CGAL checker: the hole contour labels
        // the filled component and the pair mask, via nonzero winding.
        assert_eq!(
            sig(&[rect(0.0, 0.0, 100.0, 50.0), rect_cw(20.0, 10.0, 80.0, 40.0)]),
            json!({
                "filled_components": 1, "holes": 1,
                "pinch_roster": [], "point_contacts": [],
                "hole_boundaries": [[1]],
                "pairs": [{"pair": [0, 1], "area_components": 1,
                           "area_holes": 0, "edge_components": 0,
                           "point_contacts": 0, "boundary_degrees": []}],
                "components": [{"contours": [0, 1], "holes": 1}],
            })
        );
    }

    #[test]
    fn point_touch_reports_labeled_contact() {
        assert_eq!(
            sig(&[rect(0.0, 0.0, 100.0, 50.0), rect(100.0, 50.0, 200.0, 100.0)]),
            json!({
                "filled_components": 2, "holes": 0,
                "pinch_roster": [{"degree": 4, "components": [[0], [1]]}],
                "point_contacts": [{"sides": [[0], [1]]}],
                "hole_boundaries": [],
                "pairs": [{"pair": [0, 1], "area_components": 0,
                           "area_holes": 0, "edge_components": 0,
                           "point_contacts": 1, "boundary_degrees": []}],
                "components": [{"contours": [0], "holes": 0},
                               {"contours": [1], "holes": 0}],
            })
        );
    }

    #[test]
    fn subpixel_gap_is_not_a_touch() {
        let v = sig(&[
            rect(0.0, 0.0, 100.0, 50.0),
            rect(100.015625, 50.0, 200.0, 100.0),
        ]);
        assert_eq!(v["filled_components"], json!(2));
        assert_eq!(v["point_contacts"], json!([]));
        assert_eq!(v["pinch_roster"], json!([]));
        assert_eq!(v["pairs"], json!([]));
    }

    #[test]
    fn coincident_opposite_cancels() {
        // CGAL ground truth: zero fill, but the pair intersection mask
        // (nonzero per-contour windings) still exposes the sharing.
        let v = sig(&[rect(0.0, 0.0, 100.0, 50.0), rect_cw(0.0, 0.0, 100.0, 50.0)]);
        assert_eq!(v["filled_components"], json!(0));
        assert_eq!(v["holes"], json!(0));
        assert_eq!(v["components"], json!([]));
        assert_eq!(
            v["pairs"],
            json!([{"pair": [0, 1], "area_components": 1, "area_holes": 0,
                   "edge_components": 0, "point_contacts": 0, "boundary_degrees": []}])
        );
    }

    #[test]
    fn segmentation_churn_invisible() {
        let plain = sig(&[rect(0.0, 0.0, 100.0, 50.0)]);
        let split = sig(&[vec![
            [0.0, 0.0],
            [50.0, 0.0],
            [100.0, 0.0],
            [100.0, 25.0],
            [100.0, 50.0],
            [50.0, 50.0],
            [0.0, 50.0],
            [0.0, 25.0],
        ]]);
        assert_eq!(plain, split);
    }

    #[test]
    fn neutral_strip_creates_no_counter() {
        let annulus = vec![rect(0.0, 0.0, 10.0, 10.0), rect_cw(2.0, 2.0, 8.0, 8.0)];
        let mut with_neutral = annulus.clone();
        with_neutral.push(rect(4.0, 1.0, 6.0, 9.0));
        with_neutral.push(rect_cw(4.0, 1.0, 6.0, 9.0));
        assert_eq!(sig(&annulus)["holes"], json!(1));
        assert_eq!(sig(&with_neutral)["holes"], json!(1));
    }

    #[test]
    fn edge_contact_pair_class() {
        let v = sig(&[rect(0.0, 0.0, 2.0, 2.0), rect(2.0, 0.0, 4.0, 2.0)]);
        assert_eq!(v["filled_components"], json!(1));
        assert_eq!(v["point_contacts"], json!([]));
        assert_eq!(
            v["pairs"],
            json!([{"pair": [0, 1], "area_components": 0, "area_holes": 0,
                   "edge_components": 1, "point_contacts": 0, "boundary_degrees": []}])
        );
    }

    #[test]
    fn covered_point_touch_keeps_boundary_singularity() {
        // Two lobes point-touching at (2,2) under a covering rect: only
        // the pair boundary degree distinguishes the shifted candidate.
        let source_a = vec![vec![
            [0.0, 0.0],
            [2.0, 0.0],
            [2.0, 2.0],
            [4.0, 2.0],
            [4.0, 4.0],
            [2.0, 4.0],
            [2.0, 2.0],
            [0.0, 2.0],
        ]];
        let candidate_a = vec![vec![
            [0.0, 0.0],
            [2.0, 0.0],
            [2.0, 2.0],
            [2.125, 2.125],
            [4.125, 2.125],
            [4.125, 4.125],
            [2.125, 4.125],
            [2.125, 2.125],
            [2.0, 2.0],
            [0.0, 2.0],
        ]];
        let cover = rect(-1.0, -1.0, 6.0, 6.0);
        let mut source = source_a.clone();
        source.push(cover.clone());
        let mut candidate = candidate_a.clone();
        candidate.push(cover);
        let up = sig(&source);
        let down = sig(&candidate);
        assert_eq!(up["filled_components"], json!(1));
        assert_eq!(down["filled_components"], json!(1));
        let pair = |v: &Value| {
            v["pairs"]
                .as_array()
                .unwrap()
                .iter()
                .find(|p| p["pair"] == json!([0, 1]))
                .unwrap()
                .clone()
        };
        let (a, b) = (pair(&up), pair(&down));
        for p in [&a, &b] {
            assert_eq!(p["area_components"], json!(2));
            assert_eq!(p["edge_components"], json!(0));
            assert_eq!(p["point_contacts"], json!(0));
        }
        assert_eq!(a["boundary_degrees"], json!([4]));
        assert_eq!(b["boundary_degrees"], json!([]));
        assert_ne!(up, down);
    }

    #[test]
    fn weld_loss_visible_only_in_pairs() {
        // (0,1) weld drops edge contact to a point hinge while a bridge
        // keeps every global count, including holes.
        let counter = vec![rect(10.0, 0.0, 14.0, 4.0), rect_cw(11.0, 1.0, 13.0, 3.0)];
        let mut before = vec![
            rect(0.0, 0.0, 4.0, 4.0),
            rect(4.0, 0.0, 8.0, 4.0),
            rect(0.0, 4.0, 8.0, 8.0),
        ];
        before.extend(counter.clone());
        let mut after = vec![
            rect(0.0, 0.0, 4.0, 4.0),
            rect(4.0, 4.0, 8.0, 8.0),
            rect(0.0, 4.0, 8.0, 8.0),
        ];
        after.extend(counter);
        let (up, cand) = (sig(&before), sig(&after));
        for key in ["filled_components", "holes"] {
            assert_eq!(up[key], cand[key], "{key}");
        }
        assert_eq!(
            up["point_contacts"].as_array().unwrap().len(),
            cand["point_contacts"].as_array().unwrap().len()
        );
        let edge = |v: &Value| {
            v["pairs"]
                .as_array()
                .unwrap()
                .iter()
                .find(|p| p["pair"] == json!([0, 1]))
                .unwrap()["edge_components"]
                .clone()
        };
        assert_eq!(edge(&up), json!(1));
        assert_eq!(edge(&cand), json!(0));
        assert_ne!(up, cand);
    }

    #[test]
    fn transforms_and_reorder_consistent() {
        let base = vec![rect(0.0, 0.0, 4.0, 4.0), rect(2.0, 0.0, 6.0, 4.0)];
        let merged = vec![rect(0.0, 0.0, 6.0, 4.0)];
        let shift = |loops: &[Vec<[f64; 2]>], dx: f64, dy: f64| {
            loops
                .iter()
                .map(|l| l.iter().map(|p| [p[0] + dx, p[1] + dy]).collect())
                .collect::<Vec<_>>()
        };
        assert_eq!(sig(&base), sig(&shift(&base, 3.0, -2.0)));
        let mirror = |loops: &[Vec<[f64; 2]>]| {
            loops
                .iter()
                .map(|l| l.iter().map(|p| [-p[0], p[1]]).collect())
                .collect::<Vec<_>>()
        };
        // CGAL ground truth: two overlapping contours carry a pair mask
        // a single merged contour cannot, so they differ — identically
        // before and after mirroring.
        assert_ne!(sig(&base), sig(&merged));
        assert_eq!(sig(&mirror(&base)), sig(&mirror(&shift(&base, 0.0, 0.0))));
        assert_ne!(sig(&mirror(&base)), sig(&mirror(&merged)));
        let mut reordered = base.clone();
        reordered.reverse();
        // Reordering contours relabels but preserves the shape classes.
        assert_eq!(
            sig(&reordered)["filled_components"],
            sig(&base)["filled_components"]
        );
        assert_eq!(sig(&reordered)["holes"], sig(&base)["holes"]);
    }

    #[test]
    fn invalid_inputs_fail_closed() {
        assert!(signature(&[]).is_none());
        assert!(signature(&[vec![]]).is_none());
        assert!(signature(&[vec![[1.0, 1.0]]]).is_none());
        assert!(signature(&[vec![[f64::NAN, 0.0], [1.0, 0.0], [1.0, 1.0]]]).is_none());
        assert!(signature(&[vec![[f64::INFINITY, 0.0], [1.0, 0.0], [1.0, 1.0]]]).is_none());
        // Last point may repeat first: still a valid closed loop.
        assert!(signature(&[vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]).is_some());
    }

    #[test]
    fn oversize_input_fails_closed() {
        let big: Vec<[f64; 2]> = (0..600)
            .map(|i| [i as f64, (i % 2) as f64 * 10.0])
            .collect();
        assert!(signature(&[big]).is_none());
    }
}
