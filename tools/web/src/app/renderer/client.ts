// Main-thread client for the font render worker. Every request carries a
// sequence id; responses resolve exactly one pending promise. Callers compare
// render tokens and drop stale results (the worker tags them too).
import type { FontMetadata } from "../fonts/storage.js";
import type { RenderSpec } from "./renderer-types.js";

export interface RenderPixels {
  width: number;
  height: number;
  pixels: ArrayBuffer;
  layout: RenderLayout | null;
}

export interface RenderLayoutLine {
  height_px: number;
}

export interface RenderLayout {
  lines: RenderLayoutLine[];
  missing_codepoints: number[];
}

interface Envelope {
  seq: number;
  ok: boolean;
  value?: unknown;
  token?: number;
  dropped?: boolean;
  error?: string;
}

interface Pending {
  resolve: (value: Omit<Envelope, "seq" | "ok">) => void;
  reject: (error: Error) => void;
}

export class FontWorkerClient {
  private worker: Worker;
  private seq = 0;
  private pending = new Map<number, Pending>();
  private token = 0;

  constructor() {
    this.worker = new Worker(new URL("./font-worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (event: MessageEvent) => {
      const data = event.data as Envelope;
      const entry = this.pending.get(data.seq);
      if (!entry) return;
      this.pending.delete(data.seq);
      if (data.ok) {
        const { seq: _seq, ok: _ok, ...rest } = data;
        entry.resolve(rest);
      } else {
        entry.reject(new Error(data.error ?? "Worker request failed."));
      }
    };
    this.worker.onerror = (event) => {
      const error = new Error(event.message || "Worker error.");
      for (const [, entry] of this.pending) entry.reject(error);
      this.pending.clear();
    };
  }

  private send(kind: string, fields: Record<string, unknown>, transfer?: Transferable[]): Promise<Omit<Envelope, "seq" | "ok">> {
    this.seq += 1;
    const seq = this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(seq, { resolve, reject });
      this.worker.postMessage({ seq, kind, ...fields }, transfer ?? []);
    });
  }

  async ping(): Promise<{ available: boolean }> {
    const response = await this.send("ping", {});
    return response.value as { available: boolean };
  }

  async inspect(bytes: ArrayBuffer): Promise<FontMetadata> {
    const response = await this.send("inspect", { bytes });
    return response.value as FontMetadata;
  }

  async load(fontId: string, bytes: ArrayBuffer): Promise<void> {
    await this.send("load", { fontId, bytes });
  }

  async unload(fontId: string): Promise<void> {
    await this.send("unload", { fontId });
  }

  async kerning(fontId: string, sizePx: number, axes: Record<string, number>): Promise<unknown> {
    const response = await this.send("kerning", { fontId, sizePx, axes });
    return response.value;
  }

  nextToken(): number {
    this.token += 1;
    return this.token;
  }

  async render(fontId: string, token: number, spec: RenderSpec): Promise<{ token: number; dropped: boolean; pixels: RenderPixels }> {
    const response = await this.send("render", { fontId, token, spec });
    const value = response.value as { width: number; height: number; pixels: ArrayBuffer; layout: unknown };
    const layout = value.layout && typeof value.layout === "object" && Array.isArray((value.layout as RenderLayout).lines)
      ? (value.layout as RenderLayout)
      : null;
    return {
      token: typeof response.token === "number" ? response.token : -1,
      dropped: response.dropped === true,
      pixels: { width: value.width, height: value.height, pixels: value.pixels, layout },
    };
  }

  terminate(): void {
    this.worker.terminate();
    const error = new Error("Worker terminated.");
    for (const [, entry] of this.pending) entry.reject(error);
    this.pending.clear();
  }
}
