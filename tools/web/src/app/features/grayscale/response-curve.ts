// PCHIP: Fritsch & Butland (1984), with the one-sided endpoint rule
// documented by SciPy. Unlike unrestricted cubic splines, each monotone
// interval stays within its endpoint values (including plateaus).
// https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html
export interface CurveLevel {
  value: number;
  slope: number; // Gray units per normalized horizontal position.
  pinned: boolean;
}

export type GrayCurve = readonly CurveLevel[];
interface Knot { x: number; value: number; slope: number }

function endpointSlope(h0: number, h1: number, d0: number, d1: number): number {
  const slope = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
  if (Math.sign(slope) !== Math.sign(d0)) return 0;
  return Math.sign(d0) !== Math.sign(d1) && Math.abs(slope) > 3 * Math.abs(d0) ? 3 * d0 : slope;
}

function pchip(points: readonly { x: number; value: number }[]): Knot[] {
  const h = points.slice(1).map((point, i) => point.x - points[i]!.x);
  const d = points.slice(1).map((point, i) => (point.value - points[i]!.value) / h[i]!);
  return points.map((point, i) => {
    let slope: number;
    if (points.length === 2) slope = d[0]!;
    else if (i === 0) slope = endpointSlope(h[0]!, h[1]!, d[0]!, d[1]!);
    else if (i === points.length - 1) slope = endpointSlope(h[i - 1]!, h[i - 2]!, d[i - 1]!, d[i - 2]!);
    else {
      const before = d[i - 1]!;
      const after = d[i]!;
      const w1 = 2 * h[i]! + h[i - 1]!;
      const w2 = h[i]! + 2 * h[i - 1]!;
      slope = before === 0 || Math.sign(before) !== Math.sign(after) ? 0 : (w1 + w2) / (w1 / before + w2 / after);
    }
    return { ...point, slope };
  });
}

// Cubic Hermite evaluation and its derivative. Retaining derivatives at
// output samples subdivides the same cubic exactly, so pinning a sampled
// level never changes either the curve or the palette.
function evaluate(knots: readonly Knot[], x: number): { value: number; slope: number } {
  const exact = knots.find((point) => point.x === x);
  if (exact) return { value: exact.value, slope: exact.slope };
  let right = 1;
  while (right < knots.length - 1 && knots[right]!.x < x) right += 1;
  const a = knots[right - 1]!;
  const b = knots[right]!;
  const h = b.x - a.x;
  const t = (x - a.x) / h;
  const t2 = t * t;
  const t3 = t2 * t;
  return {
    value: (2 * t3 - 3 * t2 + 1) * a.value + (t3 - 2 * t2 + t) * h * a.slope
      + (-2 * t3 + 3 * t2) * b.value + (t3 - t2) * h * b.slope,
    slope: ((6 * t2 - 6 * t) * a.value + (-6 * t2 + 6 * t) * b.value) / h
      + (3 * t2 - 4 * t + 1) * a.slope + (3 * t2 - 2 * t) * b.slope,
  };
}

function knotsOf(curve: GrayCurve): Knot[] {
  return curve.map((level, i) => ({ x: i / (curve.length - 1), value: level.value, slope: level.slope }));
}

function rebuild(curve: GrayCurve): GrayCurve {
  const knots = pchip(knotsOf(curve).filter((_, i) => curve[i]!.pinned));
  return curve.map((level, i) => ({ ...evaluate(knots, i / (curve.length - 1)), pinned: level.pinned }));
}

export function linearCurve(count: number): GrayCurve {
  // Preview gray codes only; this is not a measured panel response.
  return Array.from({ length: count }, (_, i) => ({
    value: 255 * (1 - i / (count - 1)), slope: -255, pinned: i === 0 || i === count - 1,
  }));
}

export function curveLevels(curve: GrayCurve): number[] {
  return curve.map((level) => Math.min(255, Math.max(0, Math.round(level.value))));
}

export function pinCurveLevel(curve: GrayCurve, index: number): GrayCurve {
  return curve.map((level, i) => i === index ? { ...level, pinned: true } : level);
}

export function pinAllCurveLevels(curve: GrayCurve): GrayCurve {
  return curve.map((level) => ({ ...level, pinned: true }));
}

export function editCurveLevel(curve: GrayCurve, index: number, gray: number): GrayCurve {
  const pinned = pinCurveLevel(curve, index);
  // A no-op numeric edit must not reshape a curve just to round a handle.
  if (curveLevels(curve)[index] === gray) return pinned;
  return rebuild(pinned.map((level, i) => i === index ? { ...level, value: Math.min(255, Math.max(0, Math.round(gray))) } : level));
}

export function unpinCurveLevel(curve: GrayCurve, index: number): GrayCurve {
  if (index <= 0 || index >= curve.length - 1 || !curve[index]?.pinned) return curve;
  return rebuild(curve.map((level, i) => i === index ? { ...level, pinned: false } : level));
}

export function resizeCurve(curve: GrayCurve, count: number): GrayCurve {
  if (count === curve.length) return curve;
  const knots = knotsOf(curve);
  const pinned = new Set(curve.flatMap((level, i) => level.pinned ? [Math.round(i * (count - 1) / (curve.length - 1))] : []));
  // Sample the current response, not a previously rounded palette. Handle
  // positions follow the nearest available output level at the new depth.
  const samples = Array.from({ length: count }, (_, i) => ({ x: i / (count - 1), value: evaluate(knots, i / (count - 1)).value }));
  // Old knots may fall between the new output positions. Recalculate the
  // derivatives to retain PCHIP's bounds rather than copying incompatible
  // tangents across those now-absent knots.
  return pchip(samples).map((point, i) => ({ value: point.value, slope: point.slope, pinned: pinned.has(i) }));
}

// Hermite-to-Bezier conversion draws exactly the same response we sample;
// only the final palette is rounded to bytes.
// https://www.w3.org/TR/SVG/paths.html#PathDataCubicBezierCommands
export function curvePath(curve: GrayCurve, x: (position: number) => number, y: (gray: number) => number): string {
  const knots = knotsOf(curve);
  let path = `M ${x(0)},${y(knots[0]!.value)}`;
  for (let i = 1; i < knots.length; i += 1) {
    const a = knots[i - 1]!;
    const b = knots[i]!;
    const third = (b.x - a.x) / 3;
    path += ` C ${x(a.x + third)},${y(a.value + third * a.slope)} ${x(b.x - third)},${y(b.value - third * b.slope)} ${x(b.x)},${y(b.value)}`;
  }
  return path;
}
