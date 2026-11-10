// Grayscale response presentation. The pure GrayCurve value model lives in
// the shared output-profile owner (domain/output-profiles/curve.ts); this
// module keeps only the SVG rendering of that same response.
import type { GrayCurve } from "../../domain/output-profiles/curve.ts";

// Hermite-to-Bezier conversion draws exactly the same response we sample;
// only the final palette is rounded to bytes.
// https://www.w3.org/TR/SVG/paths.html#PathDataCubicBezierCommands
export function curvePath(curve: GrayCurve, x: (position: number) => number, y: (gray: number) => number): string {
  const knots = curve.map((level, i) => ({ x: i / (curve.length - 1), value: level.value, slope: level.slope }));
  let path = `M ${x(0)},${y(knots[0]!.value)}`;
  for (let i = 1; i < knots.length; i += 1) {
    const a = knots[i - 1]!;
    const b = knots[i]!;
    const third = (b.x - a.x) / 3;
    path += ` C ${x(a.x + third)},${y(a.value + third * a.slope)} ${x(b.x - third)},${y(b.value - third * b.slope)} ${x(b.x)},${y(b.value)}`;
  }
  return path;
}
