// Device packaging: shipped shells reach the static build as vector-only
// static assets beneath the hosting prefix, and the versioned catalog rides
// with the app chunk (precached offline with the hashed bundle).
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { buildApp, webRoot } from "../helpers/spa-helpers.ts";
import { vectorSvgViolation } from "../../scripts/devices-packaging.ts";

const SHELLS = [
  ["shells/xteink-x4.svg", "Xteink X4 enclosure outline"],
  ["shells/xteink-x3.svg", "Xteink X3 enclosure outline"],
  ["shells/inkplate-4-tempera.svg", "Inkplate 4 TEMPERA enclosure outline"],
  ["shells/waveshare-esp32-s3-rlcd-4-2.svg", "Waveshare ESP32-S3-RLCD-4.2 board outline"],
  ["shells/playdate.svg", "Playdate console outline"],
  ["shells/boox-picco.svg", "BOOX Picco enclosure outline"],
] as const;

test("device shells ship as vector-only static assets", async (t) => {
  const output = await buildApp(t);
  for (const [relative, title] of SHELLS) {
    const body = await fs.readFile(path.join(output, "devices", relative), "utf8");
    assert.ok(body.includes(title), `${relative} ships its artwork`);
    // Same rule the production build guard enforces; a single owner.
    assert.equal(vectorSvgViolation(body), null, `${relative} ships vector-only artwork`);
  }
  const shipped = await fs.readdir(path.join(output, "devices", "shells"));
  assert.deepEqual([...shipped].sort(), SHELLS.map(([name]) => path.basename(name)).sort());
  const worker = await fs.readFile(path.join(output, "sw.js"), "utf8");
  for (const [relative] of SHELLS) {
    assert.ok(worker.includes(`devices/${relative}`), `service worker precaches devices/${relative} for offline use`);
  }
});

// Fault injection through disposable fixture copies: the guard reads
// FONT_DEVICE_CATALOG / FONT_DEVICE_SHELLS, so the live files behind other
// workers stay untouched while the real production pipeline runs.
async function stageDeviceFixtures(
  t: { after: (hook: () => unknown) => void },
  mutate: (fixtures: { catalogFile: string; shellsDir: string }) => Promise<void> | void,
): Promise<void> {
  const staged = await fs.mkdtemp(path.join(os.tmpdir(), "font-devices-"));
  t.after(() => fs.rm(staged, { recursive: true, force: true }));
  const catalogFile = path.join(staged, "devices.json");
  const shellsDir = path.join(staged, "shells");
  await fs.mkdir(shellsDir, { recursive: true });
  await fs.copyFile(path.join(webRoot, "src", "app", "devices", "devices.json"), catalogFile);
  for (const name of await fs.readdir(path.join(webRoot, "public", "devices", "shells"))) {
    await fs.copyFile(path.join(webRoot, "public", "devices", "shells", name), path.join(shellsDir, name));
  }
  await mutate({ catalogFile, shellsDir });
  const previousCatalog = process.env.FONT_DEVICE_CATALOG;
  const previousShells = process.env.FONT_DEVICE_SHELLS;
  process.env.FONT_DEVICE_CATALOG = catalogFile;
  process.env.FONT_DEVICE_SHELLS = shellsDir;
  t.after(() => {
    if (previousCatalog === undefined) delete process.env.FONT_DEVICE_CATALOG;
    else process.env.FONT_DEVICE_CATALOG = previousCatalog;
    if (previousShells === undefined) delete process.env.FONT_DEVICE_SHELLS;
    else process.env.FONT_DEVICE_SHELLS = previousShells;
  });
}

// A broken device asset must reject the production build itself, not just a
// runtime probe: the guard's message reaches the build's stderr.
async function assertBuildRejects(t: Parameters<typeof buildApp>[0], expected: RegExp): Promise<void> {
  let stderr = "";
  try {
    await buildApp(t);
  } catch (error) {
    const output = error as { stderr?: unknown; stdout?: unknown; message?: unknown };
    stderr = `${output.stderr ?? ""}\n${output.stdout ?? ""}\n${output.message ?? ""}`;
    assert.match(stderr, /device catalog guard/, "the device guard rejects the build");
    assert.match(stderr, expected, "the rejection names the fault");
    return;
  }
  assert.fail(`production build accepted broken device assets:\n${stderr}`);
}

test("production build rejects a missing device shell", async (t) => {
  await stageDeviceFixtures(t, async ({ shellsDir }) => {
    await fs.rm(path.join(shellsDir, "playdate.svg"));
  });
  await assertBuildRejects(t, /playdate.*missing/);
});

test("production build rejects raster-contaminated shell artwork", async (t) => {
  await stageDeviceFixtures(t, async ({ shellsDir }) => {
    const shell = path.join(shellsDir, "waveshare-esp32-s3-rlcd-4-2.svg");
    await fs.writeFile(shell, `${await fs.readFile(shell, "utf8")}<image href="photo.png" width="10" height="10"/>`);
  });
  await assertBuildRejects(t, /waveshare-esp32-s3-rlcd-4-2.*raster/);
});

test("production build rejects a corrupt device profile", async (t) => {
  await stageDeviceFixtures(t, async ({ catalogFile }) => {
    const catalog = JSON.parse(await fs.readFile(catalogFile, "utf8")) as {
      devices: Array<Record<string, unknown>>;
    };
    catalog.devices[0]!.ppiBasis = "measured";
    await fs.writeFile(catalogFile, JSON.stringify(catalog));
  });
  await assertBuildRejects(t, /invalid catalog.*ppiBasis/);
});

test("device catalog reaches the built app chunk", async (t) => {
  const output = await buildApp(t);
  const assets = await fs.readdir(path.join(output, "assets"));
  let bundle = "";
  for (const name of assets.filter((name) => name.endsWith(".js"))) {
    bundle += await fs.readFile(path.join(output, "assets", name), "utf8");
  }
  for (const id of [
    "xteink-x4",
    "xteink-x3",
    "inkplate-4-tempera",
    "waveshare-esp32-s3-rlcd-4-2",
    "playdate",
    "boox-picco",
  ]) {
    assert.ok(bundle.includes(id), `built app references ${id}`);
  }
});
