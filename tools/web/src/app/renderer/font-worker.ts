// Dedicated module worker owning every WASM call: renderer init, font
// parsing/metadata, renders, and kerning inspection. Fonts stay cached here
// by id; render results cross back as transferred ArrayBuffers. A per-font
// generation token tags stale results so the main thread paints only the
// latest request. All owned allocations are freed in finally blocks.
import initWasm, { Font } from "./wasm/font_wasm.js";
import wasmBinaryUrl from "./wasm/font_wasm_bg.wasm?url";
import staged from "./wasm/staged.json";

interface LoadMessage { seq: number; kind: "load"; fontId: string; bytes: ArrayBuffer }
interface InspectMessage { seq: number; kind: "inspect"; bytes: ArrayBuffer }
interface RenderMessage { seq: number; kind: "render"; fontId: string; token: number; spec: Record<string, unknown> }
interface KerningMessage { seq: number; kind: "kerning"; fontId: string; sizePx: number; axes: Record<string, number> }
interface UnloadMessage { seq: number; kind: "unload"; fontId: string }
interface PingMessage { seq: number; kind: "ping" }
type InMessage = LoadMessage | InspectMessage | RenderMessage | KerningMessage | UnloadMessage | PingMessage;

interface OkResponse { seq: number; ok: true; value?: unknown; token?: number; dropped?: boolean }
interface ErrResponse { seq: number; ok: false; error: string }
type OutMessage = OkResponse | ErrResponse;

const fonts = new Map<string, Font>();
const generations = new Map<string, number>();
let ready: Promise<void> | null = null;

function ensureReady(): Promise<void> {
  ready ??= (async () => {
    if (!staged.available) {
      throw new Error("Preview renderer unavailable: rebuild with the preview WASM staged (`just wasm-build-preview`).");
    }
    await initWasm({ module_or_path: wasmBinaryUrl });
  })();
  return ready;
}

function message(error: unknown): string {
  const value = error !== null && (typeof error === "object" || typeof error === "function") && "message" in error
    ? error.message : undefined;
  return String(value ?? error ?? "");
}

async function handle(msg: InMessage): Promise<{ response: OutMessage; transfer?: Transferable[] }> {
  await ensureReady();
  switch (msg.kind) {
    case "ping":
      return { response: { seq: msg.seq, ok: true, value: { available: true } } };
    case "load": {
      const bytes = new Uint8Array(msg.bytes);
      const font = new Font(bytes);
      fonts.get(msg.fontId)?.free();
      fonts.set(msg.fontId, font);
      return { response: { seq: msg.seq, ok: true } };
    }
    case "inspect": {
      const bytes = new Uint8Array(msg.bytes.slice(0));
      const font = new Font(bytes);
      try {
        return { response: { seq: msg.seq, ok: true, value: font.metadata() } };
      } finally {
        font.free();
      }
    }
    case "render": {
      const font = fonts.get(msg.fontId);
      if (!font) throw new Error("Font is not loaded in the render worker.");
      generations.set(msg.fontId, msg.token);
      const result = font.render(msg.spec);
      try {
        const width = result.width();
        const height = result.height();
        const pixels = new Uint8ClampedArray(result.pixels());
        let layout: unknown = null;
        try {
          layout = result.layout();
        } catch {
          layout = null;
        }
        const dropped = generations.get(msg.fontId) !== msg.token;
        const buffer = pixels.buffer.slice(0);
        return {
          response: { seq: msg.seq, ok: true, token: msg.token, dropped, value: { width, height, pixels: buffer, layout } },
          transfer: [buffer],
        };
      } finally {
        result.free();
      }
    }
    case "kerning": {
      const font = fonts.get(msg.fontId);
      if (!font) throw new Error("Font is not loaded in the render worker.");
      const data = font.kerning_pairs(msg.sizePx, msg.axes);
      const table = Array.isArray(data) ? { pairs: data, skipped_pairs: 0 } : data;
      return { response: { seq: msg.seq, ok: true, value: table } };
    }
    case "unload": {
      fonts.get(msg.fontId)?.free();
      fonts.delete(msg.fontId);
      generations.delete(msg.fontId);
      return { response: { seq: msg.seq, ok: true } };
    }
  }
}

self.onmessage = (event: MessageEvent<InMessage>): void => {
  const msg = event.data;
  handle(msg).then(
    ({ response, transfer }) => self.postMessage(response, { transfer: transfer ?? [] }),
    (error: unknown) => self.postMessage({ seq: msg.seq, ok: false, error: message(error) } satisfies ErrResponse),
  );
};
