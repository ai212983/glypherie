// Stage the candidate-enabled preview renderer for the Vite app.
//
// Copies crates/wasm/pkg-web-preview-simd128/font_wasm.js (+ .d.ts) and
// font_wasm_bg.wasm into src/app/renderer/wasm/ (git-ignored build input) so Vite bundles
// the glue and emits the binary as a content-hashed asset. Strict by default:
// a missing preview build fails with the fix. `--allow-missing` (dev only)
// writes throwing stubs so the app boots degraded instead.
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot: string = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const allowMissing: boolean = process.argv.includes("--allow-missing");
const previewDir: string = process.env.FONT_WASM_PREVIEW_DIR
  ?? path.resolve(webRoot, "..", "..", "crates", "wasm", "pkg-web-preview-simd128");
const outDir: string = path.join(webRoot, "src", "app", "renderer", "wasm");

const STUB_JS: string = `// Generated degraded stub (preview WASM not staged). Every use throws.
export class Font {
  constructor() {
    throw new Error("Preview renderer unavailable: stage the preview WASM build first.");
  }
}
export default async function init() {
  throw new Error("Preview renderer unavailable: stage the preview WASM build first.");
}
`;
const STUB_DTS: string = `export class Font {
  constructor(bytes: Uint8Array);
  free(): void;
  render(spec: unknown): unknown;
  export_playdate(request: unknown): Uint8Array;
  kerning_pairs(sizePx: number, axes?: Record<string, number>): unknown;
  metadata(): unknown;
}
declare const init: (input?: unknown) => Promise<unknown>;
export default init;
`;
const EMPTY_WASM: Buffer = Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]);

async function exists(file: string): Promise<boolean> {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

async function readDest(file: string): Promise<Buffer | null> {
  try {
    return await fs.readFile(file);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function stageBytes(dest: string, data: Buffer): Promise<void> {
  const current = await readDest(dest);
  if (current !== null && current.equals(data)) return;
  const temp = `${dest}.${process.pid}.${Date.now()}.tmp`;
  try {
    await fs.writeFile(temp, data);
    await fs.rename(temp, dest);
  } catch (error) {
    await fs.rm(temp, { force: true }).catch(() => {});
    throw error;
  }
}

const js: string = path.join(previewDir, "font_wasm.js");
const dts: string = path.join(previewDir, "font_wasm.d.ts");
const bin: string = path.join(previewDir, "font_wasm_bg.wasm");
await fs.mkdir(outDir, { recursive: true });
if (await exists(js) && await exists(bin)) {
  await stageBytes(path.join(outDir, "font_wasm.js"), await fs.readFile(js));
  await stageBytes(path.join(outDir, "font_wasm_bg.wasm"), await fs.readFile(bin));
  if (await exists(dts)) await stageBytes(path.join(outDir, "font_wasm.d.ts"), await fs.readFile(dts));
  else await stageBytes(path.join(outDir, "font_wasm.d.ts"), Buffer.from(STUB_DTS));
  await stageBytes(path.join(outDir, "staged.json"), Buffer.from(JSON.stringify({ available: true })));
} else if (allowMissing) {
  await stageBytes(path.join(outDir, "font_wasm.js"), Buffer.from(STUB_JS));
  await stageBytes(path.join(outDir, "font_wasm_bg.wasm"), EMPTY_WASM);
  await stageBytes(path.join(outDir, "font_wasm.d.ts"), Buffer.from(STUB_DTS));
  await stageBytes(path.join(outDir, "staged.json"), Buffer.from(JSON.stringify({ available: false })));
  console.warn(`stage-wasm: preview renderer missing in ${previewDir}; dev-degraded stubs written.`);
} else {
  throw new Error(
    `stage-wasm: preview renderer missing in ${previewDir}.\n`
    + `Build it with \`just wasm-build-preview\`, or set FONT_WASM_PREVIEW_DIR.`,
  );
}
