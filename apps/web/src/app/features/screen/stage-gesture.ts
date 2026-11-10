// Native-pixel gesture calculations and pending-release state. SceneStage owns DOM updates, timers
// and persistence.
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

// Fallback native-pixel position from the gesture-start origin and CSS-pixel drag, before measured
// renderer geometry can anchor the release.
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

// Clear when saved size, width and position match, or when the label is absent or replaced.
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

// Holds one pending release. fulfill and flush consume it at most once; the adapter matches paint
// inputs and owns timeout and persistence.
export class AwaitedResizeCommit {
  private armed: AwaitedRelease | null = null;

  get pendingId(): string | null {
    return this.armed?.id ?? null;
  }

  // Before replacing a pending release, flush or cancel it and clear its adapter timer; arm does
  // neither.
  arm(release: AwaitedRelease): void {
    this.armed = release;
  }

  cancel(): void {
    this.armed = null;
  }

  peek(): AwaitedRelease | null {
    return this.armed;
  }

  // Consume the pending release using matching measured ink, or its drag fallback when ink is null.
  // The caller must ensure the measurement belongs to the released paint inputs.
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

  // Consume the pending release using recorded ink only when text, size and width match; otherwise
  // return its drag-translation fallback.
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
