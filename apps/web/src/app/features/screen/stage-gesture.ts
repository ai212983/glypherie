// Cohesive stage gesture core: native-pixel drag/resize math, anchored
// resize correction and pending-preview reconciliation for the scene stage.
// Framework-free and DOM-free: the SceneStage adapter owns Moveable binding,
// refs, rendering and the timed exactly-once handoff, and calls into this
// core for every calculation and outcome decision. Rendering never duplicates
// release state: previews clear only against the matching saved render.
export interface InkRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ResizeStart {
  fontSize: number;
  width: number;
  // Frame size in screen px when the gesture started.
  boxWidth: number;
  boxHeight: number;
}

export interface ResizeEstimate {
  fontSize: number;
  width: number;
}

// Display translation (screen px) to native device grid steps. Pointer
// motion converts through the presentation cssScale only; the store keeps
// integer native pixels.
export function dragNativeDelta(translate: readonly [number, number], cssScale: number): { dx: number; dy: number } {
  const scale = Number.isFinite(cssScale) && cssScale > 0 ? cssScale : 1;
  return { dx: Math.round(translate[0] / scale), dy: Math.round(translate[1] / scale) };
}

// Fallback release position from the cumulative drag translation when no
// measured repaint is available: the gesture-start position plus the rounded
// native drag.
export function releasedPosition(
  start: { x: number; y: number },
  drag: readonly [number, number],
  cssScale: number,
): { x: number; y: number } {
  const delta = dragNativeDelta(drag, cssScale);
  return { x: start.x + delta.dx, y: start.y + delta.dy };
}

// Live resize estimate from the gesture-start size: proportional scaling
// (keepRatio) carries both axes, so the width ratio converts pointer motion
// along either axis. Ratios cancel cssScale; only the width delta converts
// back through it. Returns null when the frame carries no finite span.
export function resizeEstimates(start: ResizeStart, eventWidthCssPx: number, cssScale: number): ResizeEstimate | null {
  const scale = Number.isFinite(cssScale) && cssScale > 0 ? cssScale : 1;
  const span = Math.max(eventWidthCssPx, 1) / start.boxWidth;
  if (!Number.isFinite(span) || span <= 0 || !Number.isFinite(start.boxWidth) || start.boxWidth <= 0) return null;
  return {
    // Moveable clamps extreme inward drags at zero or negative sizes; pin to
    // the domain minimum instead of swallowing the gesture.
    fontSize: Math.min(512, Math.max(1, Math.round(start.fontSize * span))),
    width: Math.min(4096, Math.max(1, Math.round(start.width + (eventWidthCssPx - start.boxWidth) / scale))),
  };
}

// Opposite-corner anchor in native device px: the fixed corner is opposite
// the dragged handle (a westward drag fixes the east side), so the released
// position places the repaint's measured far corner onto the gesture-start
// far corner. Integer rounding is the only error this introduces.
export function correctedResizePosition(
  anchorBaseX: number,
  anchorBaseY: number,
  anchorInk: InkRect,
  direction: readonly [number, number],
  ink: InkRect,
): { x: number; y: number } {
  const farX = direction[0]! < 0 ? ink.x + ink.width : ink.x;
  const farY = direction[1]! < 0 ? ink.y + ink.height : ink.y;
  const anchorFarX = direction[0]! < 0 ? anchorInk.x + anchorInk.width : anchorInk.x;
  const anchorFarY = direction[1]! < 0 ? anchorInk.y + anchorInk.height : anchorInk.y;
  return {
    x: Math.round(anchorBaseX + anchorFarX - farX),
    y: Math.round(anchorBaseY + anchorFarY - farY),
  };
}

export interface MovePreview {
  id: string;
  x: number;
  y: number;
}

export interface ResizePreview extends MovePreview {
  fontSize: number;
  width: number;
}

// The pending move clears only once the saved coordinates render (or the
// label leaves the scene), never when the async command merely returns while
// props are still old.
export function movePreviewClears(
  canonical: { id: string; x: number; y: number } | null | undefined,
  pending: MovePreview,
): boolean {
  if (!canonical || canonical.id !== pending.id) return true;
  return canonical.x === pending.x && canonical.y === pending.y;
}

// The pending resize clears against the label's own size, wrap width and
// anchored position together.
export function resizePreviewClears(
  canonical: { id: string; x: number; y: number; fontSize: number | null; width: number | null } | null | undefined,
  pending: ResizePreview,
): boolean {
  if (!canonical || canonical.id !== pending.id) return true;
  return (
    canonical.fontSize === pending.fontSize &&
    canonical.width === pending.width &&
    canonical.x === pending.x &&
    canonical.y === pending.y
  );
}

// A variant reference switch supersedes a direct-font gesture (including its
// deferred save): variant geometry must come only from its saved style,
// never from a stale direct-font preview.
export function previewSuperseded(
  canonical: { id: string; textStyleId: string | null } | null | undefined,
  pendingId: string,
): boolean {
  if (!canonical || canonical.id !== pendingId) return true;
  return canonical.textStyleId !== null;
}

export interface AwaitedRelease {
  id: string;
  text: string;
  fontSize: number;
  width: number;
  fallbackX: number;
  fallbackY: number;
  anchorBaseX: number;
  anchorBaseY: number;
  anchorInk: InkRect;
  lastDirection: readonly [number, number];
}

export interface AwaitedCommit {
  release: AwaitedRelease;
  x: number;
  y: number;
}

// A release whose save waits for the repaint of the released size. The
// commit fires exactly once: the first fulfillment wins, so a late paint, a
// paint failure and the bounded wait cannot write twice. The adapter owns the
// timer and performs the commit; this core decides position and outcome.
export class AwaitedResizeCommit {
  private armed: AwaitedRelease | null = null;

  get pendingId(): string | null {
    return this.armed?.id ?? null;
  }

  arm(release: AwaitedRelease): void {
    this.armed = release;
  }

  cancel(): void {
    this.armed = null;
  }

  // The currently awaited release, if any, so the adapter can match paints
  // and timeouts against the exact inputs the release waits for.
  peek(): AwaitedRelease | null {
    return this.armed;
  }

  // The repaint of the released inputs landed: correct the position against
  // its measured bounds. An inkless paint for the awaited inputs commits the
  // drag translation, since no later repaint of the same inputs can measure
  // more. The caller only invokes this when the paint inputs match the
  // awaited release.
  fulfill(ink: InkRect | null): AwaitedCommit | null {
    const awaiting = this.armed;
    if (!awaiting) return null;
    this.armed = null;
    if (!ink) return { release: awaiting, x: awaiting.fallbackX, y: awaiting.fallbackY };
    const corrected = correctedResizePosition(
      awaiting.anchorBaseX,
      awaiting.anchorBaseY,
      awaiting.anchorInk,
      awaiting.lastDirection,
      ink,
    );
    return { release: awaiting, x: corrected.x, y: corrected.y };
  }

  // Best-effort flush when a new gesture starts on the same label, a paint
  // fails, the stage unmounts, or the bounded wait expires: commit corrected
  // against measured bounds when they already match, else the translation.
  flush(recorded: { text: string; sizePx: number; width: number; ink: InkRect | null } | null): AwaitedCommit | null {
    const awaiting = this.armed;
    if (!awaiting) return null;
    this.armed = null;
    if (
      recorded &&
      recorded.ink &&
      recorded.text === awaiting.text &&
      recorded.sizePx === awaiting.fontSize &&
      recorded.width === awaiting.width
    ) {
      const corrected = correctedResizePosition(
        awaiting.anchorBaseX,
        awaiting.anchorBaseY,
        awaiting.anchorInk,
        awaiting.lastDirection,
        recorded.ink,
      );
      return { release: awaiting, x: corrected.x, y: corrected.y };
    }
    return { release: awaiting, x: awaiting.fallbackX, y: awaiting.fallbackY };
  }
}
