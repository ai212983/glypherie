import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "..", "..");
const stageSource = path.join(webRoot, "scripts", "stage-wasm.ts");
const NODE = process.execPath;
const STAGED = ["font_wasm.js", "font_wasm_bg.wasm", "font_wasm.d.ts", "staged.json"] as const;
const OLD_MTIME = new Date("2000-01-01T00:00:00Z");
const FAKE_WASM = Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]);

async function makeTree(): Promise<{ root: string; fakeWeb: string; preview: string; out: string; stage: string }> {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "stage-wasm-"));
  const fakeWeb = path.join(root, "web");
  const preview = path.join(root, "preview");
  const out = path.join(fakeWeb, "src", "app", "renderer", "wasm");
  await fs.mkdir(path.join(fakeWeb, "scripts"), { recursive: true });
  await fs.mkdir(preview, { recursive: true });
  const stage = path.join(fakeWeb, "scripts", "stage-wasm.ts");
  await fs.copyFile(stageSource, stage);
  return { root, fakeWeb, preview, out, stage };
}

function runStage(stage: string, preview: string, allowMissing = false): { ok: boolean; stderr: string } {
  const args = [stage];
  if (allowMissing) args.push("--allow-missing");
  try {
    execFileSync(NODE, args, {
      env: { ...process.env, FONT_WASM_PREVIEW_DIR: preview },
      stdio: ["ignore", "ignore", "pipe"],
    });
    return { ok: true, stderr: "" };
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    return { ok: false, stderr: String(err.stderr ?? err.message ?? error) };
  }
}

async function writePreview(preview: string, js: string): Promise<void> {
  await fs.writeFile(path.join(preview, "font_wasm.js"), js);
  await fs.writeFile(path.join(preview, "font_wasm.d.ts"), "export declare const x: number;\n");
  await fs.writeFile(path.join(preview, "font_wasm_bg.wasm"), FAKE_WASM);
}

async function snapshot(out: string): Promise<Map<string, { bytes: Buffer; mtimeMs: number }>> {
  const snap = new Map<string, { bytes: Buffer; mtimeMs: number }>();
  for (const name of STAGED) {
    const file = path.join(out, name);
    const [bytes, stat] = await Promise.all([fs.readFile(file), fs.stat(file)]);
    snap.set(name, { bytes, mtimeMs: stat.mtimeMs });
  }
  return snap;
}

async function pinOld(out: string): Promise<void> {
  for (const name of STAGED) await fs.utimes(path.join(out, name), OLD_MTIME, OLD_MTIME);
}

test("unchanged input keeps staged bytes and mtimes", async () => {
  const { root, preview, out, stage } = await makeTree();
  try {
    await writePreview(preview, "export const v = 1;\n");
    assert.equal(runStage(stage, preview).ok, true);
    await pinOld(out);
    const before = await snapshot(out);
    assert.equal(runStage(stage, preview).ok, true);
    const after = await snapshot(out);
    for (const name of STAGED) {
      assert.deepEqual(after.get(name)!.bytes, before.get(name)!.bytes, name);
      assert.equal(after.get(name)!.mtimeMs, before.get(name)!.mtimeMs, name);
    }
    assert.deepEqual((await fs.readdir(out)).filter((f) => f.endsWith(".tmp")), []);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("changed js input replaces staged bytes exactly", async () => {
  const { root, preview, out, stage } = await makeTree();
  try {
    await writePreview(preview, "export const v = 1;\n");
    assert.equal(runStage(stage, preview).ok, true);
    await writePreview(preview, "export const v = 2;\n");
    assert.equal(runStage(stage, preview).ok, true);
    assert.equal(await fs.readFile(path.join(out, "font_wasm.js"), "utf8"), "export const v = 2;\n");
    assert.deepEqual((await fs.readdir(out)).filter((f) => f.endsWith(".tmp")), []);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("strict missing input fails without destroying staged output", async () => {
  const { root, preview, out, stage } = await makeTree();
  try {
    await writePreview(preview, "export const v = 1;\n");
    assert.equal(runStage(stage, preview).ok, true);
    const before = await snapshot(out);
    await fs.rm(path.join(preview, "font_wasm.js"));
    await fs.rm(path.join(preview, "font_wasm_bg.wasm"));
    const result = runStage(stage, preview);
    assert.equal(result.ok, false);
    const after = await snapshot(out);
    for (const name of STAGED) assert.deepEqual(after.get(name)!.bytes, before.get(name)!.bytes, name);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("degraded stubs stage on allow-missing and real input restores", async () => {
  const { root, preview, out, stage } = await makeTree();
  try {
    assert.equal(runStage(stage, preview, true).ok, true);
    assert.deepEqual((await fs.readdir(out)).filter((f) => f.endsWith(".tmp")), []);
    const staged = JSON.parse(await fs.readFile(path.join(out, "staged.json"), "utf8"));
    assert.equal(staged.available, false);
    assert.equal((await fs.readFile(path.join(out, "font_wasm_bg.wasm"))).length, 8);
    await writePreview(preview, "export const v = 3;\n");
    assert.equal(runStage(stage, preview).ok, true);
    assert.equal(await fs.readFile(path.join(out, "font_wasm.js"), "utf8"), "export const v = 3;\n");
    assert.equal(JSON.parse(await fs.readFile(path.join(out, "staged.json"), "utf8")).available, true);
    assert.deepEqual((await fs.readdir(out)).filter((f) => f.endsWith(".tmp")), []);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});
