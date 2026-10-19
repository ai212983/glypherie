import type { RenderPixels } from "./client.js";
import type { RenderSpec } from "./renderer-types.js";

export type FontCanvasMode = "normal" | "exact";

export interface PaintOutcome {
  data: RenderPixels;
  fullHeight: number;
  // Rows to commit to the canvas: the laid-out height bounded by the cap.
  shown: number;
  truncated: boolean;
}

export interface RenderJob {
  // Full request identity: renderer session, font, display mode, geometry and
  // the first-pass spec. Readiness is deliberately not part of the key; the
  // owner resets identity when disabling so re-enabling re-renders.
  key: string;
  fontId: string;
  estimate: number;
  cap: number;
  specForHeight: (height: number) => RenderSpec;
  // Laid-out content height of a first-pass result; the owner wires the real
  // layout helper so this module stays free of DOM and worker imports.
  contentHeight: (pixels: RenderPixels) => number;
  debounceMs: number;
  immediate: boolean;
  nextToken: () => number;
  render: (fontId: string, token: number, spec: RenderSpec) => Promise<{
    token: number;
    dropped: boolean;
    pixels: RenderPixels;
  }>;
  onPaint: (outcome: PaintOutcome) => void;
  onError: (error: unknown) => void;
}

// Complete identity for one paint, including the renderer session and font.
// Two requests share a key only when every input that changes pixels does.
export function buildRequestKey(input: {
  session: number;
  fontId: string;
  mode: FontCanvasMode;
  zoom: number;
  width: number;
  extra: unknown;
  spec: RenderSpec;
}): string {
  return JSON.stringify({
    session: input.session,
    font: input.fontId,
    mode: input.mode,
    zoom: input.zoom,
    width: input.width,
    extra: input.extra,
    spec: input.spec,
  });
}

// Per-consumer paint coordinator: debounced scheduling, two-pass layout
// resolution and stale-result protection. One instance per canvas keeps
// distinct consumers of the same font independent; the epoch drops any
// completion that is no longer the latest request (superseded, disabled,
// unmounted, or re-keyed), including between the two passes.
export class RenderScheduler {
  private epoch = 0;
  private current: string | null = null;
  private lastKey = "";
  private activeKey: string | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;

  request(job: RenderJob): void {
    if (job.key === this.current && this.timer !== undefined) {
      // Identical work is already debounced: preserve its timing instead of
      // firing early (a rerender racing the debounce must not bypass it).
      return;
    }
    if (this.timer !== undefined) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    const changed = job.key !== this.current;
    this.current = job.key;
    if (job.key === this.lastKey && (this.activeKey === null || this.activeKey === job.key)) {
      return;
    }
    if (!changed && this.activeKey === job.key) {
      return;
    }
    this.epoch += 1;
    this.activeKey = null;
    if (job.key === this.lastKey) {
      return;
    }
    if (job.immediate || job.debounceMs <= 0) {
      this.activeKey = job.key;
      void this.run(job, this.epoch);
      return;
    }
    const epoch = this.epoch;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.activeKey = job.key;
      void this.run(job, epoch);
    }, job.debounceMs);
  }

  // Disabling (or unmounting) invalidates in-flight and pending work and
  // clears the painted identity, so re-enabling re-renders even when the
  // specimen itself is unchanged.
  cancel(): void {
    if (this.timer !== undefined) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    this.epoch += 1;
    this.current = null;
    this.activeKey = null;
    this.lastKey = "";
  }

  private async run(job: RenderJob, epoch: number): Promise<void> {
    const alive = (): boolean => epoch === this.epoch && this.current === job.key;
    const token = job.nextToken();
    try {
      const first = await job.render(job.fontId, token, job.specForHeight(job.estimate));
      if (!alive() || first.dropped || first.token !== token) return;
      let data = first.pixels;
      const full = job.contentHeight(data);
      const need = Math.min(job.cap, Math.max(1, full));
      if (need > job.estimate) {
        const second = await job.render(job.fontId, token, job.specForHeight(need));
        if (!alive() || second.dropped || second.token !== token) return;
        data = second.pixels;
      }
      if (!alive()) return;
      // Paint commits before the identity does: a throwing paint lands in the
      // error path below with the key unmarked, so a later request can retry.
      job.onPaint({ data, fullHeight: full, shown: need, truncated: full > job.cap });
      this.activeKey = null;
      this.lastKey = job.key;
    } catch (error) {
      if (!alive()) return;
      this.activeKey = null;
      // The failed key painted nothing (consumers with clear-on-error blank
      // the canvas), so forget any previously painted identity: recovery with
      // identical inputs must render again instead of hitting the painted dedupe.
      this.lastKey = "";
      job.onError(error);
    }
  }
}
