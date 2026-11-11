// Centered-viewport geometry for the Screen drawing panel: the logical device
// canvas aperture stays centered in the scrollport, fixed pixel rulers derive
// their origin from the same numbers, and scroll positions convert between
// viewport scrolled pixels and native device pixels. Pure; no DOM access.
export const RULER_SIZE = 22;
export const VIEWPORT_MARGIN = 240;

export interface ApertureBox {
  // Body box size in CSS px (shell artwork, or the bare canvas when hidden).
  bodyWidth: number;
  bodyHeight: number;
  // Canvas aperture placement and size in CSS px within the body box.
  apertureX: number;
  apertureY: number;
  apertureWidth: number;
  apertureHeight: number;
}

export interface CenteredContent {
  contentWidth: number;
  contentHeight: number;
  // Body top-left within the scrollable content; shifted so the aperture,
  // not the shell, lands centered when bezels are asymmetric.
  bodyX: number;
  bodyY: number;
  // Aperture top-left within the scrollable content (the ruler origin).
  canvasX: number;
  canvasY: number;
}

export function centeredContent(box: ApertureBox): CenteredContent {
  // Body-center minus aperture-center within the body: positive when the
  // aperture sits left of (above) center, so the body shifts by the same
  // amount to land the aperture on the content center.
  const shiftX = (box.bodyWidth - box.apertureWidth) / 2 - box.apertureX;
  const shiftY = (box.bodyHeight - box.apertureHeight) / 2 - box.apertureY;
  const bodyX = VIEWPORT_MARGIN + shiftX;
  const bodyY = VIEWPORT_MARGIN + shiftY;
  return {
    contentWidth: box.bodyWidth + VIEWPORT_MARGIN * 2,
    contentHeight: box.bodyHeight + VIEWPORT_MARGIN * 2,
    bodyX,
    bodyY,
    canvasX: bodyX + box.apertureX,
    canvasY: bodyY + box.apertureY,
  };
}

// Free space the flex centering splits around the content; zero while the
// content overflows (margin:auto absorbs nothing once scrolling).
export function centeringOffset(viewport: number, content: number): number {
  return Math.max(0, (viewport - content) / 2);
}

// Ruler scroll position in native px: the scrolled viewport position minus
// the aperture origin, in the ruler zoom space (screen px per native px).
export function rulerScrollPos(
  scroll: number,
  viewport: number,
  content: number,
  canvas: number,
  zoom: number,
): number {
  return (scroll - centeringOffset(viewport, content) - canvas) / zoom;
}

// Native point under the viewport center; preserved across zoom, body and
// panel-size changes so the view does not jump.
export function centerNative(scroll: number, viewport: number, content: number, canvas: number, zoom: number): number {
  return rulerScrollPos(scroll + viewport / 2, viewport, content, canvas, zoom);
}

// Scroll position keeping a native point centered; clamps at the edges.
export function scrollToCenterNative(
  native: number,
  viewport: number,
  content: number,
  canvas: number,
  zoom: number,
  maxScroll: number,
): number {
  const next = centeringOffset(viewport, content) + canvas + native * zoom - viewport / 2;
  return Math.min(Math.max(0, next), Math.max(0, maxScroll));
}

// Major tick spacing in native px from the 1/2/5 series, holding majors
// roughly 48-120 screen px apart across the 25-400% zoom band.
export function rulerUnitForScale(zoom: number): number {
  if (!Number.isFinite(zoom) || zoom <= 0) return 50;
  const target = 48 / zoom;
  let unit = 1;
  while (unit < target) {
    const step = unit.toString()[0];
    unit = step === "1" ? unit * 2 : step === "2" ? (unit * 5) / 2 : unit * 2;
  }
  return unit;
}
