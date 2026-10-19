// Stage the candidate-enabled preview renderer for the Vite app.
//
// Copies tools/wasm/pkg-web-preview/font_wasm.js (+ .d.ts) and
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
  ?? path.resolve(webRoot, "..", "wasm", "pkg-web-preview");
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

const js: string = path.join(previewDir, "font_wasm.js");
const dts: string = path.join(previewDir, "font_wasm.d.ts");
const bin: string = path.join(previewDir, "font_wasm_bg.wasm");
await fs.mkdir(outDir, { recursive: true });
if (await exists(js) && await exists(bin)) {
  await fs.copyFile(js, path.join(outDir, "font_wasm.js"));
  await fs.copyFile(bin, path.join(outDir, "font_wasm_bg.wasm"));
  if (await exists(dts)) await fs.copyFile(dts, path.join(outDir, "font_wasm.d.ts"));
  else await fs.writeFile(path.join(outDir, "font_wasm.d.ts"), STUB_DTS);
  await fs.writeFile(path.join(outDir, "staged.json"), JSON.stringify({ available: true }));
} else if (allowMissing) {
  await fs.writeFile(path.join(outDir, "font_wasm.js"), STUB_JS);
  await fs.writeFile(path.join(outDir, "font_wasm_bg.wasm"), EMPTY_WASM);
  await fs.writeFile(path.join(outDir, "font_wasm.d.ts"), STUB_DTS);
  await fs.writeFile(path.join(outDir, "staged.json"), JSON.stringify({ available: false }));
  console.warn(`stage-wasm: preview renderer missing in ${previewDir}; dev-degraded stubs written.`);
} else {
  throw new Error(
    `stage-wasm: preview renderer missing in ${previewDir}.\n`
    + `Build it with \`just wasm-build-preview\`, or set FONT_WASM_PREVIEW_DIR.`,
  );
}
