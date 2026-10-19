import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import assert from "node:assert/strict";
import test, { after, type TestContext } from "node:test";
import {
  browserAvailable,
  launch,
  webRoot,
} from "../helpers/spa-helpers.ts";
import type { Browser, Page } from "playwright-core";

// Mounted renderer lifecycle tests. They drive the LifecycleHarness stories
// in a Storybook dev server (development React, so StrictMode replays its
// effects) and assert the real effect wiring: one active worker across
// setup-cleanup-setup, deliberate session replacement, readiness/font/
// geometry transitions, debounce staleness and unmount.
const DEV_PORT = 6163;

let server: ChildProcess | null = null;

after(() => {
  server?.kill("SIGKILL");
  server = null;
});

async function devBase(_t: TestContext): Promise<string> {
  if (!server) {
    // Spawn the Storybook binary directly (no npm wrapper) so the test owns
    // the server process it must kill afterwards.
    server = spawn(
      process.execPath,
      [
        path.join(webRoot, "node_modules", "storybook", "dist", "bin", "dispatcher.js"),
        "dev",
        "--host", "127.0.0.1",
        "--port", String(DEV_PORT),
        "--no-open",
        "--disable-telemetry",
      ],
      // The lifecycle fixtures load only with the opt-in flag, so this dev
      // server (and only it) serves them.
      { cwd: webRoot, stdio: "pipe", env: { ...process.env, STORYBOOK_TEST_HARNESSES: "1" } },
    );
    const deadline = Date.now() + 120000;
    for (;;) {
      try {
        const response = await fetch(`http://127.0.0.1:${DEV_PORT}/iframe.html`);
        if (response.ok) break;
      } catch {
        // Server is still starting.
      }
      if (Date.now() > deadline) throw new Error("Storybook dev server did not start.");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  return `http://127.0.0.1:${DEV_PORT}/`;
}

interface HarnessCalls {
  constructed: number;
  terminated: number;
  renders: Array<{
    fontId: string;
    token: number;
    text: string;
    width: number;
    height: number;
    foreground?: readonly [number, number, number, number];
    background?: readonly [number, number, number, number];
    palette?: ReadonlyArray<readonly [number, number, number, number]> | null;
  }>;
}

// Machine probes are hidden elements: read textContent, never innerText. A
// missing probe is a harness failure, never a default value.
async function probeText(page: Page, selector: string): Promise<string> {
  const text = await page.locator(selector).textContent();
  assert.notEqual(text, null, `machine probe ${selector} must be present`);
  return text as string;
}

async function paints(page: Page): Promise<number> {
  return Number(await probeText(page, "[data-harness-paints]"));
}

async function fillPalette(page: Page, palette: string): Promise<void> {
  await page.locator("[data-harness-palette]").fill(palette);
}

interface PixelSummary {
  width: number;
  height: number;
  row0: number[];
  row1: number[];
  row3: number[];
  distinctAlphas: number[];
  distinctPixels: number;
}

// Backing-store pixels of the painted display canvas. Geometry follows the
// fixture contract: first band starts at row 0, ink spans columns 4..190,
// rows cycle coverage levels with level 0 left as background.
async function probePixels(page: Page): Promise<PixelSummary> {
  return page.evaluate(() => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement;
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    const at = (x: number, y: number): number[] => {
      const i = (y * canvas.width + x) * 4;
      return [data[i] as number, data[i + 1] as number, data[i + 2] as number, data[i + 3] as number];
    };
    const alphas = new Set<number>();
    const quads = new Set<string>();
    for (let i = 0; i < data.length; i += 4) {
      alphas.add(data[i + 3] as number);
      quads.add(`${data[i]},${data[i + 1]},${data[i + 2]},${data[i + 3]}`);
    }
    return {
      width: canvas.width,
      height: canvas.height,
      row0: at(10, 0),
      row1: at(10, 1),
      row3: at(10, 3),
      distinctAlphas: [...alphas].sort((a, b) => a - b),
      distinctPixels: quads.size,
    };
  });
}

async function pixelAt(page: Page, x: number, y: number): Promise<number[]> {
  return page.evaluate(([px, py]) => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement;
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    const i = (py * canvas.width + px) * 4;
    return [data[i] as number, data[i + 1] as number, data[i + 2] as number, data[i + 3] as number];
  }, [x, y] as [number, number]);
}

async function fullBuffer(page: Page): Promise<number[]> {
  return page.evaluate(() => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement;
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    return [...data];
  });
}

async function openStory(browser: Browser, base: string, id: string, extra = ""): Promise<Page> {
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${base}iframe.html?id=${id}&viewMode=story${extra}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-harness-status]") !== null, null, {
    timeout: 120000,
  });
  (page as Page & { harnessErrors?: string[] }).harnessErrors = errors;
  return page;
}

async function painted(page: Page): Promise<void> {
  await page.waitForFunction(
    () => document.querySelector("[data-harness-status]")?.textContent?.startsWith("painted"),
    null,
    { timeout: 120000 },
  );
}

async function calls(page: Page): Promise<HarnessCalls> {
  return JSON.parse(await probeText(page, "[data-harness-calls]")) as HarnessCalls;
}

async function session(page: Page): Promise<number> {
  return Number(await probeText(page, "[data-harness-session]"));
}

function harnessErrors(page: Page): string[] {
  return (page as Page & { harnessErrors?: string[] }).harnessErrors ?? [];
}

async function strictCalls(page: Page, name: "canvas" | "lib"): Promise<HarnessCalls & { loads: Array<{ fontId: string }> }> {
  const text = await probeText(page, `[data-strict-${name}-calls]`);
  return JSON.parse(text) as HarnessCalls & { loads: Array<{ fontId: string }> };
}

async function strictText(page: Page, name: string): Promise<string> {
  return probeText(page, `[data-strict-${name}]`);
}

test("StrictMode replay settles canvas and library on exactly one live worker each", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${base}iframe.html?id=renderer-lifecycleharness--strict-root&viewMode=story`, {
    waitUntil: "networkidle",
  });
  // Canvas: the replayed setup's pending render is dropped; the live worker
  // issues the second render and paints.
  await page.waitForFunction(
    () => document.querySelector("[data-strict-canvas-status]")?.textContent === "painted",
    null,
    { timeout: 120000 },
  );
  // Library: delayed inspect/load boot completes on the live setup only, with
  // exactly one load of the stored font and readiness exposed for it.
  await page.waitForFunction(
    () => document.querySelector("[data-strict-lib-load]")?.textContent === "ready"
      && document.querySelector("[data-strict-lib-loaded]")?.textContent === "yes",
    null,
    { timeout: 120000 },
  );
  const canvas = await strictCalls(page, "canvas");
  assert.equal(canvas.constructed, 2, "two canvas workers constructed across the replay");
  assert.equal(canvas.terminated, 1, "the first canvas worker is terminated, none leak");
  assert.equal(canvas.renders.length, 1, "only the live setup renders; replay issues no duplicate");
  const canvasSession = Number(await strictText(page, "canvas-session"));
  assert.ok(canvasSession > 1, `the live canvas session postdates the replay, got ${canvasSession}`);

  const library = await strictCalls(page, "lib");
  assert.equal(library.constructed, 2, "two library workers constructed across the replay");
  assert.equal(library.terminated, 1, "the first library worker is terminated, none leak");
  assert.equal(library.loads.length, 1, "no duplicate load from the retired setup");
  const librarySession = Number(await strictText(page, "lib-session"));
  assert.ok(librarySession > 1, `the live library session postdates the replay, got ${librarySession}`);
  assert.ok(Number(await strictText(page, "lib-fonts")) >= 1, "stored fonts are listed");
  assert.ok((await strictText(page, "lib-font-id")).length > 0, "the harness font seeded an id");
  assert.equal(await strictText(page, "lib-available"), "true");
  assert.deepEqual(errors, []);

  // Session replacement reloads the font on the new worker only.
  await page.locator("[data-strict-lib-replace]").click();
  await page.waitForFunction(
    (previous) => document.querySelector("[data-strict-lib-session]")?.textContent !== previous
      && document.querySelector("[data-strict-lib-load]")?.textContent === "ready",
    String(librarySession),
    { timeout: 120000 },
  );
  const replaced = await strictCalls(page, "lib");
  assert.equal(replaced.constructed, 3, "replacement constructs a new worker");
  assert.equal(replaced.terminated, 2, "the replaced worker is terminated while the new one stays active");
  assert.equal(replaced.loads.length, 2, "the new session loads the font once");
  assert.equal(Number(await strictText(page, "lib-session")), librarySession + 1, "replacement bumps the session by one");

  // A replacement load pending at unmount is dropped; remount loads again.
  await page.locator("[data-strict-lib-replace]").click();
  await page.waitForFunction(
    () => document.querySelector("[data-strict-lib-load]")?.textContent === "loading",
    null,
    { timeout: 120000 },
  );
  await page.locator("[data-strict-lib-mounted]").uncheck();
  await page.waitForTimeout(500);
  assert.equal(await page.locator("[data-strict-lib-load]").count(), 0, "unmounted library leaves no readout");
  await page.locator("[data-strict-lib-mounted]").check();
  await page.waitForFunction(
    () => document.querySelector("[data-strict-lib-load]")?.textContent === "ready",
    null,
    { timeout: 120000 },
  );
  assert.equal((await strictCalls(page, "lib")).loads.length, 4, "dropped plus remount loads, no more");
  assert.deepEqual(errors, []);
  await page.close();
});

test("replacing the renderer starts a new session without remounting", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const firstSession = await session(page);
  const firstCalls = (await calls(page)).renders.length;
  assert.ok(firstCalls >= 1);

  await page.locator("[data-harness-replace]").click();
  await page.waitForFunction(
    (previous) => document.querySelector("[data-harness-session]")?.textContent !== previous,
    String(firstSession),
    { timeout: 120000 },
  );
  await painted(page);
  const observed = await calls(page);
  assert.equal(await session(page), firstSession + 1, "replacement bumps the session");
  assert.equal(observed.constructed, 2, "a second worker is constructed");
  assert.equal(observed.terminated, 1, "the replaced worker is terminated while the new one stays active");
  assert.ok(observed.renders.length > firstCalls, "the new session renders with unchanged specimen");
  assert.deepEqual(harnessErrors(page), []);
  await page.close();
});

test("readiness transitions repaint with an unchanged specimen", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const firstCalls = (await calls(page)).renders.length;

  await page.locator("[data-harness-ready]").uncheck();
  await page.waitForFunction(
    () => document.querySelector("[data-harness-status]")?.textContent === "Waiting for paint…",
    null,
    { timeout: 60000 },
  );
  await page.locator("[data-harness-ready]").check();
  await painted(page);
  assert.ok((await calls(page)).renders.length > firstCalls, "re-enabling renders without input changes");
  await page.close();
});

test("changing the font id renders the new font", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);

  await page.locator("[data-harness-font]").fill("other-font");
  await painted(page);
  const observed = await calls(page);
  assert.equal(observed.renders[observed.renders.length - 1]?.fontId, "other-font");
  await page.close();
});

test("a zero-width viewport cancels pending work and widening renders", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const firstCalls = (await calls(page)).renders.length;

  await page.locator("[data-harness-narrow]").check();
  await page.waitForTimeout(400);
  assert.equal((await calls(page)).renders.length, firstCalls, "no render issues while the viewport is hidden");

  await page.locator("[data-harness-narrow]").uncheck();
  await painted(page);
  assert.ok((await calls(page)).renders.length > firstCalls, "restoring geometry renders again");
  await page.close();
});

test("empty text paints a blank canvas and restores on input", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);

  const startPaints = await paints(page);
  await page.locator("[data-harness-text]").fill("");
  await waitPaints(page, startPaints + 1);
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("canvas").length),
    1,
    "empty text keeps its mounted canvas",
  );
  assert.match(
    await probeText(page, "[data-harness-readiness]"),
    /renderer ready/,
    "empty input stays ready",
  );
  const observed = await calls(page);
  assert.equal(
    observed.renders[observed.renders.length - 1]?.text,
    "",
    "empty text reaches the renderer instead of hiding",
  );

  const restoredPaints = await paints(page);
  await page.locator("[data-harness-text]").fill("Agave grids glint.");
  await waitPaints(page, restoredPaints + 1);
  assert.equal(await page.evaluate(() => document.querySelectorAll("canvas").length), 1, "restored text paints again");
  await page.close();
});

test("stale text during debounce never paints", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const firstCalls = (await calls(page)).renders.length;

  await page.locator("[data-harness-text]").fill("A");
  await page.locator("[data-harness-text]").fill("A longer specimen");
  await painted(page);
  const observed = await calls(page);
  const fresh = observed.renders.slice(firstCalls);
  assert.equal(fresh.length, 1, "one render for the settled text");
  assert.equal(fresh[0]?.text, "A longer specimen", "the superseded text never renders");
  await page.close();
});

test("unmount drops a pending paint and remount renders", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=latencyMs:250;debounceMs:0");
  await painted(page);
  const firstCalls = (await calls(page)).renders.length;

  await page.locator("[data-harness-text]").fill("text while mounted");
  await page.locator("[data-harness-mounted]").uncheck();
  await page.waitForTimeout(600);
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("canvas").length),
    0,
    "unmounted canvas leaves no element behind",
  );

  await page.locator("[data-harness-mounted]").check();
  await painted(page);
  assert.ok((await calls(page)).renders.length > firstCalls, "remount renders again");
  assert.deepEqual(harnessErrors(page), []);
  await page.close();
});

test("resize commits canvas dimensions only with the new paint", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=latencyMs:250;debounceMs:0");
  await painted(page);
  const before = await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).width);

  await page.locator("[data-harness-width]").fill("640");
  // The new request is still pending behind fixture latency: the committed
  // canvas must keep its old backing size until the new paint lands.
  await page.waitForTimeout(100);
  assert.equal(
    await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).width),
    before,
    "pending work cannot resize the committed canvas",
  );
  await page.waitForFunction(
    (expected) => (document.querySelector("canvas") as HTMLCanvasElement)?.width === expected,
    640,
    { timeout: 120000 },
  );
  await painted(page);
  await page.close();
});

test("a throwing factory shows unavailable UI without crashing", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=factoryBehavior:throw");
  await page.waitForFunction(
    () => document.querySelector("[data-harness-readiness]")?.textContent?.includes("renderer unavailable"),
    null,
    { timeout: 120000 },
  );
  assert.match(
    (await page.locator("[data-harness-readiness]").textContent()) ?? "",
    /Harness factory failure/,
    "the construction error reaches the UI",
  );
  assert.equal(await page.locator("[data-harness-available]").textContent(), "false");
  assert.deepEqual(harnessErrors(page), []);
  await page.close();
});

async function waitPaints(page: Page, count: number): Promise<void> {
  await page.waitForFunction((expected) => Number(
    document.querySelector("[data-harness-paints]")?.textContent,
  ) === expected, count, { timeout: 120000 });
}

test("color-only changes rerender without remounting", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const startPaints = await paints(page);

  await page.locator("[data-harness-palette]").fill("[[10,20,30,255],[200,30,30,255]]");
  await waitPaints(page, startPaints + 1);
  await page.evaluate(() => {
    (document.querySelector("canvas") as HTMLCanvasElement).dataset.probe = "kept";
  });
  await page.locator("[data-harness-palette]").fill("[[10,20,30,255],[30,90,200,255]]");
  await waitPaints(page, startPaints + 2);
  assert.equal(
    await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).dataset.probe),
    "kept",
    "the canvas element survives color changes",
  );
  const observed = await calls(page);
  assert.deepEqual(observed.renders[observed.renders.length - 1]?.background, [10, 20, 30, 255]);
  assert.deepEqual(
    observed.renders[observed.renders.length - 1]?.palette,
    [[10, 20, 30, 255], [30, 90, 200, 255]],
    "full palettes travel verbatim with entry 0 as paper",
  );
  assert.deepEqual(harnessErrors(page), []);
  await page.close();
});

test("entry 0 paper and explicit ink paint expected mono RGBA", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  const expectedPaints = await paints(page);

  await page.locator("[data-harness-palette]").fill("[[10,20,30,40],[200,30,30,255]]");
  await waitPaints(page, expectedPaints + 1);
  const pixels = await probePixels(page);
  assert.deepEqual(pixels.row1, [200, 30, 30, 255], "explicit mono level 1 applies verbatim");
  // A translucent paper cannot round-trip exactly through 8-bit
  // premultiplied canvas storage (single fill reads back ~[13,19,32,40]),
  // but it must be applied exactly once: alpha stays 40 (a second composite
  // behind the already-composited image would move it to 74) and RGB stays
  // within one premultiply round-trip (worst case +/-0.5*255/40 ~= +/-3.2).
  assert.equal(pixels.row0[3], 40, "entry 0 paper applies once, not twice");
  for (let i = 0; i < 3; i += 1) {
    assert.ok(Math.abs((pixels.row0[i] ?? Number.NaN) - ((([10, 20, 30] as const)[i]) ?? Number.NaN)) <= 4, `paper RGB holds, got ${pixels.row0}`);
  }
  await page.close();
});

test("uneven opaque gray entries apply verbatim per level", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=profile:gray_3bit");
  await painted(page);
  const startPaints = await paints(page);

  // Distinct opaque RGB per level: no coverage alpha may reshape them, so
  // every row reads back its own entry exactly.
  const entries = [
    [255, 255, 255, 255], [200, 30, 30, 255], [30, 90, 200, 255], [30, 180, 90, 255],
    [150, 60, 200, 255], [200, 150, 30, 255], [90, 200, 180, 255], [40, 50, 60, 255],
  ];
  await page.locator("[data-harness-palette]").fill(JSON.stringify(entries));
  await waitPaints(page, startPaints + 1);
  const rows = await page.evaluate(() => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement;
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    return [0, 1, 2, 3, 4, 5, 6, 7].map((row) => {
      const i = (row * canvas.width + 10) * 4;
      return [data[i], data[i + 1], data[i + 2], data[i + 3]];
    });
  });
  for (let level = 0; level < 8; level += 1) {
    assert.deepEqual(rows[level], entries[level], `row ${level} paints entry ${level} exactly`);
  }
  await page.close();
});

test("full gray palette applies levels verbatim", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=profile:gray_3bit");
  await painted(page);
  const startPaints = await paints(page);

  await page.locator("[data-harness-palette]").fill(
    "[[0,0,0,0],[30,60,200,36],[30,90,200,72],[30,120,200,108],[30,150,200,144],[30,180,200,180],[30,210,200,216],[30,240,200,252]]",
  );
  await waitPaints(page, startPaints + 1);
  const pixels = await probePixels(page);
  // Entry 0 is transparent, so the translucent level 1 entry composites to
  // itself; the 8-bit premultiplied canvas storage rounds RGB through
  // round(round(c*a/255)*255/a) on readback while alpha stays exact, i.e.
  // [28,57,198,36] here.
  assert.deepEqual(pixels.row1, [28, 57, 198, 36], "explicit level 1 applies verbatim");
  assert.ok(pixels.distinctPixels >= 5, `levels vary across rows, got ${pixels.distinctPixels} distinct pixels`);
  await page.close();
});

test("opaque to transparent leaves no ghosting; partial repaints do not accumulate", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  let expectedPaints = await paints(page);

  await page.locator("[data-harness-palette]").fill("[[255,255,255,255],[200,30,30,255]]");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  await page.locator("[data-harness-palette]").fill("[[0,0,0,0],[200,30,30,255]]");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  let pixels = await probePixels(page);
  assert.deepEqual(pixels.row0, [0, 0, 0, 0], "cleared paper holds no ghost of opaque white");
  assert.deepEqual(pixels.row1, [200, 30, 30, 255], "opaque ink over transparency is exact");

  await page.locator("[data-harness-palette]").fill("[[0,0,0,0],[30,90,200,160]]");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  const first = await fullBuffer(page);
  await page.locator("[data-harness-ready]").uncheck();
  await page.locator("[data-harness-ready]").check();
  await waitPaints(page, expectedPaints + 1);
  assert.deepEqual(await fullBuffer(page), first, "repeated same-size partial paints are byte-identical");
  pixels = await probePixels(page);
  assert.equal(pixels.row1[3], 160, "partial alpha does not accumulate across repaints");
  await page.close();
});

test("uncovered padding paints background once without accumulation", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 4300, height: 700 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${base}iframe.html?id=renderer-lifecycleharness--default&viewMode=story`, {
    waitUntil: "networkidle",
  });
  await page.waitForFunction(() => document.querySelector("[data-harness-status]") !== null, null, {
    timeout: 120000,
  });
  await painted(page);
  let expectedPaints = await paints(page);

  // The native width cap leaves padding past 4096 at zoom 1.
  await page.locator("[data-harness-width]").fill("4200");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  const backing = await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).width);
  assert.ok(backing > 4096, `viewport exceeds the native width cap, got ${backing}`);
  assert.deepEqual(await pixelAt(page, 4100, 1), [255, 255, 255, 255], "padding holds opaque paper");
  assert.deepEqual(await pixelAt(page, 10, 1), [36, 40, 43, 255], "image region paints default ink");

  await page.locator("[data-harness-palette]").fill("[[0,0,0,0],[36,40,43,255]]");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  assert.deepEqual(await pixelAt(page, 4100, 1), [0, 0, 0, 0], "padding clears to transparency");
  assert.deepEqual(await pixelAt(page, 10, 1), [36, 40, 43, 255], "image region keeps exact ink");
  await page.locator("[data-harness-ready]").uncheck();
  await page.locator("[data-harness-ready]").check();
  await waitPaints(page, expectedPaints + 1);
  assert.deepEqual(await pixelAt(page, 4100, 1), [0, 0, 0, 0], "repaint keeps padding transparent");
  assert.deepEqual(await pixelAt(page, 10, 1), [36, 40, 43, 255], "repaint keeps image pixels exact");
  assert.deepEqual(errors, []);
  await page.close();
});

test("invalid colors report and valid correction recovers", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default");
  await painted(page);
  let expectedPaints = await paints(page);

  await page.locator("[data-harness-palette]").fill("[[1,2,3],[4,5,6],[7,8,9]]");
  await page.waitForFunction(
    () => document.querySelector("[data-harness-status]")?.textContent?.startsWith("error:"),
    null,
    { timeout: 120000 },
  );
  assert.match(
    (await page.locator("[data-harness-status]").textContent()) ?? "",
    /Invalid palette: expected exactly 2 entries/,
    "length mismatch reports through onError",
  );
  await page.locator("[data-harness-palette]").fill("[[10,20,30,40],[200,30,30,255]]");
  await waitPaints(page, expectedPaints + 1);
  expectedPaints += 1;
  assert.deepEqual((await probePixels(page)).row1, [200, 30, 30, 255], "valid correction repaints");

  await page.locator("[data-harness-palette]").fill("[[1,2,3],[200,30,30,255]]");
  await page.waitForFunction(
    () => document.querySelector("[data-harness-status]")?.textContent?.startsWith("error:"),
    null,
    { timeout: 120000 },
  );
  assert.match((await page.locator("[data-harness-status]").textContent()) ?? "", /Invalid palette color/);
  await page.locator("[data-harness-palette]").fill("");
  await waitPaints(page, expectedPaints + 1);
  assert.deepEqual((await probePixels(page)).row0, [255, 255, 255, 255], "omitted palette restores paper");
  assert.deepEqual((await probePixels(page)).row1, [36, 40, 43, 255], "omitted palette restores default ink");
  await page.close();
});

test("delayed stale color result is suppressed", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openStory(browser, base, "renderer-lifecycleharness--default", "&args=latencyMs:250;debounceMs:0");
  await painted(page);
  const startPaints = await paints(page);
  const startCalls = (await calls(page)).renders.length;

  await page.locator("[data-harness-palette]").fill("[[10,20,30,255],[200,30,30,255]]");
  await page.locator("[data-harness-palette]").fill("[[10,20,30,255],[30,90,200,255]]");
  await page.waitForFunction(
    (expected) => JSON.parse(document.querySelector("[data-harness-calls]")?.textContent ?? "{}").renders?.length === expected,
    startCalls + 2,
    { timeout: 120000 },
  );
  await page.waitForTimeout(600);
  assert.equal(await paints(page), startPaints + 1, "only the latest color paints");
  assert.deepEqual((await probePixels(page)).row1, [30, 90, 200, 255], "the superseded color never commits");
  const observed = await calls(page);
  assert.deepEqual(
    observed.renders[observed.renders.length - 1]?.palette,
    [[10, 20, 30, 255], [30, 90, 200, 255]],
    "the latest full palette travels verbatim",
  );
  assert.deepEqual(harnessErrors(page), []);
  await page.close();
});

test("alpha survives normal and exact paints", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const cases: Array<{ extra: string; check: (page: Page) => Promise<void> }> = [
    { extra: "&args=mode:normal", check: async (page: Page) => { assert.match(
      await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).style.width),
      /^\d+px$/,
      "normal canvas carries explicit pixel sizing",
    ); } },
    { extra: "&args=mode:exact", check: async (page: Page) => { assert.match(
      await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).style.transform),
      /scale\(/,
      "exact canvas keeps its pixel snap",
    ); } },
  ];
  for (const { extra: storyExtra, check: styleCheck } of cases) {
    const page = await openStory(browser, base, "renderer-lifecycleharness--default", storyExtra);
    await painted(page);
    const startPaints = await paints(page);
    await fillPalette(page, "[[0,0,0,0],[200,30,30,255]]");
    await waitPaints(page, startPaints + 1);
    const pixels = await probePixels(page);
    assert.deepEqual(pixels.row1, [200, 30, 30, 255], `opaque ink is exact in ${storyExtra}`);
    assert.deepEqual(pixels.row0, [0, 0, 0, 0], `transparent background is exact in ${storyExtra}`);
    await styleCheck(page);
    await page.close();
  }
});

for (const deviceScaleFactor of [1.25, 1.5, 2]) {
  test(`exact mode aligns at fractional DPR ${deviceScaleFactor}`, { skip: !browserAvailable }, async (t) => {
    const base = await devBase(t);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 900, height: 700 }, deviceScaleFactor });
    await page.goto(`${base}iframe.html?id=renderer-lifecycleharness--default&viewMode=story&args=mode:exact;zoom:2`, {
      waitUntil: "networkidle",
    });
    await page.waitForFunction(
      () => document.querySelector("[data-harness-status]")?.textContent?.startsWith("painted"),
      null,
      { timeout: 120000 },
    );
    const ratio = await page.evaluate(() => window.devicePixelRatio);
    const geometry = await page.evaluate(() => {
      const canvas = document.querySelector("canvas") as HTMLCanvasElement;
      return { width: canvas.width, height: canvas.height, transform: canvas.style.transform };
    });
    assert.ok(geometry.width > 0 && geometry.height > 0, `canvas has backing size at DPR ${ratio}`);
    assert.match(geometry.transform, /scale\(/, `pixel snap applies at DPR ${ratio}`);
    const firstTransform = geometry.transform;
    await page.locator("[data-harness-text]").fill("Agave grids glint!");
    await page.waitForFunction(
      () => document.querySelector("[data-harness-status]")?.textContent?.startsWith("painted"),
      null,
      { timeout: 120000 },
    );
    assert.equal(
      await page.evaluate(() => (document.querySelector("canvas") as HTMLCanvasElement).style.transform),
      firstTransform,
      "repeated exact renders do not accumulate placement",
    );
    await page.close();
  });
}
