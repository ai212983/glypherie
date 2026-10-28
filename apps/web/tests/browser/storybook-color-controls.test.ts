import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import assert from "node:assert/strict";
import test, { after, type TestContext } from "node:test";
import { browserAvailable, launch, webRoot } from "../helpers/spa-helpers.ts";
import type { Browser, Frame, Page } from "playwright-core";

// Real-rendering playground tests: they drive the FontCanvas stories (actual
// preview worker + bundled fonts) in the Storybook manager and assert
// repainted glyph pixels, font/text/profile cooperation, and recovery.
const DEV_PORT = 6164;

let server: ChildProcess | null = null;

after(() => {
  server?.kill("SIGKILL");
  server = null;
});

async function devBase(_t: TestContext): Promise<string> {
  if (!server) {
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
      { cwd: webRoot, stdio: "pipe" },
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

async function openPreview(browser: Browser, base: string, path: string): Promise<Page> {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text().slice(0, 300)}`);
  });
  await page.goto(`${base}?path=/${path}`, { waitUntil: "networkidle" });
  await page.waitForSelector("#storybook-preview-iframe", { timeout: 120000 });
  (page as Page & { managerErrors?: string[] }).managerErrors = errors;
  return page;
}

async function openManager(browser: Browser, base: string, story: string, extra = ""): Promise<Page> {
  return openPreview(browser, base, `story/${story}${extra}`);
}

async function storyFrame(page: Page): Promise<Frame> {
  const deadline = Date.now() + 120000;
  for (;;) {
    const frame = page.frame({ url: /iframe\.html/ });
    if (frame) return frame;
    if (Date.now() > deadline) throw new Error("Story iframe never attached.");
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

// Fails immediately when the preview itself is broken (hook misuse,
// story crash) instead of timing out on a status line that never appears.
async function requirePreview(frame: Frame, page: Page): Promise<void> {
  await frame.waitForFunction(
    () => document.querySelector("[data-story-status]") !== null
      || document.querySelector("#error-message") !== null,
    null,
    { timeout: 120000 },
  );
  const fatal = await frame.evaluate(
    () => document.querySelector("#error-message")?.textContent?.trim() ?? "",
  );
  assert.equal(fatal, "", `Storybook preview failed: ${fatal || "(empty)"} | errors: ${managerErrors(page)}`);
}

function managerErrors(page: Page): string[] {
  return (page as Page & { managerErrors?: string[] }).managerErrors ?? [];
}

// Known Storybook-internal manager/preview store-sync timeouts observed
// under headless timing. They carry no story code: logged once per page for
// diagnosis while only the rest can fail an assertion.
function storyErrors(page: Page): string[] {
  const peer = page as Page & { loggedNoise?: string[] };
  const kept: string[] = [];
  for (const message of managerErrors(page)) {
    if (/Timed out waiting for leader state for UniversalStore follower with id: 'storybook\/(status|test-provider|checklist)'/.test(message)) {
      if (!(peer.loggedNoise ?? []).includes(message)) {
        peer.loggedNoise = [...(peer.loggedNoise ?? []), message];
        console.log(`[storybook-noise] ${message}`);
      }
      continue;
    }
    kept.push(message);
  }
  return kept;
}

async function storyStatus(frame: Frame): Promise<string> {
  // The machine probe is truly hidden (never announced), so read textContent
  // with a non-null check instead of innerText.
  const text = await frame.evaluate(
    () => document.querySelector("[data-story-status]")?.textContent ?? null,
  );
  assert.ok(text !== null, "the machine status probe exists");
  return text;
}

// Opens a disclosure by hook when closed; no-op when already open.
async function openDisclosure(frame: Frame, hook: string): Promise<void> {
  const details = frame.locator(`[${hook}]`);
  await details.locator("summary").first().waitFor({ timeout: 30000 });
  const open = await details.evaluate((el) => (el as HTMLDetailsElement).open);
  if (!open) {
    await details.locator("summary").first().click();
  }
}

async function storyPaints(frame: Frame): Promise<number> {
  return Number(await frame.locator("[data-story-paints]").textContent());
}

async function waitPainted(frame: Frame): Promise<void> {
  await frame.locator("[data-story-status]").waitFor({ state: "attached", timeout: 120000 });
  await frame.waitForFunction(
    () => /painted/.test(document.querySelector("[data-story-status]")?.textContent ?? ""),
    null,
    { timeout: 120000 },
  );
}

// Waits for the successful paint counter to advance past its previous
// value: every painted line reads the same, so only the counter proves the
// new paint landed.
async function waitMorePaints(frame: Frame, before: number): Promise<void> {
  await frame.waitForFunction(
    (expected) => {
      const status = document.querySelector("[data-story-status]")?.textContent ?? "";
      return Number(document.querySelector("[data-story-paints]")?.textContent ?? "0") >= expected
        || status.startsWith("error:");
    },
    before + 1,
    { timeout: 60000 },
  );
  const status = await storyStatus(frame);
  assert.ok(status.startsWith("painted"), `edit repainted successfully, got: ${status}`);
}

interface CanvasStats {
  digest: number;
  distinct: number;
  ink: number;
  rowDistinct: number;
  width: number;
  height: number;
}

// FNV-1a digest plus shape facts of the story canvas backing store. Gray
// output quantizes coverage to 2^bits levels, so real text shows a small
// ramp (not hundreds of values); what proves glyphs over band patterns is
// ink volume plus variation WITHIN one row (synthetic bands are row-constant).
async function canvasStats(frame: Frame): Promise<CanvasStats> {
  return frame.evaluate(() => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement | null;
    if (!canvas) throw new Error("Story canvas is missing.");
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    let digest = 0x811c9dc5;
    const seen = new Set<number>();
    let ink = 0;
    const mid = Math.floor(canvas.height / 2);
    const rowSeen = new Set<number>();
    for (let y = 0; y < canvas.height; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const i = (y * canvas.width + x) * 4;
        const quad = ((data[i] as number) << 24) | ((data[i + 1] as number) << 16)
          | ((data[i + 2] as number) << 8) | (data[i + 3] as number);
        digest ^= quad;
        digest = Math.imul(digest, 0x01000193);
        seen.add(quad);
        if (quad !== -1) ink += 1;
        if (y === mid) rowSeen.add(quad);
      }
    }
    return {
      digest: digest >>> 0,
      distinct: seen.size,
      ink,
      rowDistinct: rowSeen.size,
      width: canvas.width,
      height: canvas.height,
    };
  });
}

async function canvasPixel(frame: Frame, x: number, y: number): Promise<number[]> {
  return frame.evaluate(([px, py]) => {
    const canvas = document.querySelector("canvas") as HTMLCanvasElement | null;
    if (!canvas) throw new Error("Story canvas is missing.");
    const data = (canvas.getContext("2d") as CanvasRenderingContext2D)
      .getImageData(0, 0, canvas.width, canvas.height).data;
    const i = (py * canvas.width + px) * 4;
    return [data[i] as number, data[i + 1] as number, data[i + 2] as number, data[i + 3] as number];
  }, [x, y] as [number, number]);
}

// Commits one combined #rrggbbaa value through an entry's real popup hex
// field — the only opacity path. Background and level rows commit
// immediately; the font row only stages a draft (see applyInk).
async function setRgbaField(frame: Frame, name: string, hex8: string): Promise<void> {
  // A previous popup can cover the next trigger, so dismiss it first with
  // the same Escape a human would use; with nothing open this is a no-op.
  await frame.page().keyboard.press("Escape");
  await frame.locator(`[data-picker-trigger="${name}"]`).click();
  const field = frame.locator(`[data-rgba-field="${name}"]`);
  await field.waitFor({ timeout: 30000 });
  await field.fill(hex8);
}

async function setRgba(frame: Frame, name: string, hex8: string): Promise<void> {
  const before = await storyPaints(frame);
  await setRgbaField(frame, name, hex8);
  await waitMorePaints(frame, before);
}

// Applies the staged font-color draft, rebuilding every ink level. The
// staging popup stays open over the rebuild button, so dismiss it first:
// covered controls need a normal dismissal before use.
async function applyInk(frame: Frame): Promise<void> {
  const before = await storyPaints(frame);
  await frame.page().keyboard.press("Escape");
  await frame.locator("[data-apply-ink]").click();
  await waitMorePaints(frame, before);
}

async function waitStoryError(frame: Frame): Promise<string> {
  await frame.waitForFunction(
    () => (document.querySelector("[data-story-status]")?.textContent ?? "").startsWith("error:"),
    null,
    { timeout: 120000 },
  );
  return storyStatus(frame);
}

test("real glyphs paint non-uniform coverage", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await frame.locator("[data-color-playground]").waitFor({ timeout: 30000 });

  // Fresh defaults are mono: the profile control, one ink level over the
  // paper, and real glyphs on the canvas.
  const profileRow = page.locator("#storybook-panel-root tr", { hasText: /profile/i });
  assert.equal(await profileRow.locator("select").inputValue(), "mono_1bit");
  await openDisclosure(frame, "data-levels-disclosure");
  assert.equal(await frame.locator('[data-picker-row^="level-"]').count(), 1, "mono shows one ink level");
  const mono = await canvasStats(frame);
  assert.ok(mono.ink > 500, `mono paints real glyphs, got ${mono.ink} ink pixels`);

  // The coverage ramp below needs gray: switch explicitly, then assert.
  const paints = await storyPaints(frame);
  await profileRow.locator("select").selectOption("gray_3bit");
  await waitMorePaints(frame, paints);
  assert.equal(await frame.locator('[data-picker-row^="level-"]').count(), 7, "gray shows seven ink levels");
  const stats = await canvasStats(frame);
  assert.ok(stats.distinct >= 4, `coverage ramp varies, got ${stats.distinct} distinct pixels`);
  assert.ok(stats.ink > 500, `glyphs cover volume, got ${stats.ink} ink pixels`);
  assert.ok(stats.rowDistinct >= 4, `one text row varies, got ${stats.rowDistinct} (bands are row-constant)`);
  assert.match(await storyStatus(frame), /missing=0/, "default text is fully covered");
  assert.equal(
    await frame.locator("[data-story-human]").count(),
    0,
    "a clean paint renders no human status line",
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("shared form and studio dropdowns select by keyboard and retain disabled and invalid states", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  for (const state of ["default", "disabled", "invalid"]) {
    const page = await openManager(browser, base, `ui-form-controls--${state}`);
    const frame = await storyFrame(page);
    const profile = frame.getByRole("combobox", { name: "Output profile", exact: true });
    await profile.waitFor();
    assert.equal(await profile.isDisabled(), state === "disabled");
    assert.equal(await profile.getAttribute("aria-invalid"), String(state === "invalid"));
    if (state !== "disabled") {
      await profile.focus();
      await profile.press("Space");
      await frame.waitForFunction(() => document.activeElement?.getAttribute("role") === "option");
      await page.keyboard.press("End");
      await frame.waitForFunction(() => document.activeElement?.textContent === "Grayscale");
      await page.keyboard.press("Enter");
      await frame.waitForFunction(
        () => document.activeElement?.getAttribute("role") === "combobox"
          && (document.activeElement?.textContent ?? "").includes("Grayscale"),
      );
      assert.equal(await profile.textContent(), "Grayscale");
      assert.equal(await profile.evaluate((element) => element === document.activeElement), true);
    }
    assert.equal(await frame.locator("select:visible").count(), 0);
    assert.deepEqual(storyErrors(page), []);
    await page.close();
  }
  const page = await openManager(browser, base, "ui-studio-card--default");
  const frame = await storyFrame(page);
  const preset = frame.getByRole("combobox", { name: "Quick presets", exact: true });
  await preset.click();
  await frame.getByRole("option", { name: "Digits + Symbols", exact: true }).click();
  assert.equal(await frame.getByRole("textbox", { name: "Test buffer text", exact: true }).inputValue(), "0123456789 !@#$%^&*()");
  assert.equal(await frame.locator("select:visible").count(), 0);
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("default card slots own their styling and nested variants stay isolated", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "ui-card--nested-variants");
  const frame = await storyFrame(page);
  await frame.locator('[data-card-fixture="nested-default"]').waitFor();
  const snapshot = (id: string) => frame.locator(`[data-card-fixture="${id}"]`).evaluate((card) => {
    const style = (slot: string, fields: string[]): string[] => {
      const element = card.querySelector(`:scope > [data-slot="${slot}"]`)!;
      const computed = getComputedStyle(element);
      return fields.map((field) => computed.getPropertyValue(field));
    };
    const header = card.querySelector(':scope > [data-slot="card-header"]')!;
    const title = header.querySelector('[data-slot="card-title"]')!;
    const heading = getComputedStyle(title);
    return {
      heading: [heading.fontFamily, heading.fontSize, heading.fontWeight, heading.lineHeight, heading.letterSpacing, heading.color, heading.textTransform],
      titleTag: title.tagName,
      header: style("card-header", ["padding-left", "padding-bottom", "border-bottom-width", "row-gap"]),
      content: style("card-content", ["padding-left", "padding-right"]),
      footer: style("card-footer", ["padding-top", "padding-left", "border-top-width"]),
      action: getComputedStyle(header.querySelector('[data-slot="card-action"]')!).gridRowEnd,
    };
  });
  for (const theme of ["light", "dark"]) {
    await frame.locator("html").evaluate((html, dark) => html.classList.toggle("dark", dark), theme === "dark");
    const outer = await snapshot("outer-default");
    assert.equal(outer.titleTag, "H2", "shared title styles apply directly to semantic headings");
    assert.deepEqual(outer.heading.slice(1, 5), ["10px", "700", "16px", "0.5px"]);
    assert.equal(outer.heading[6], "uppercase");
    assert.deepEqual(outer.header, ["0px", "6px", "1px", "0px"]);
    assert.deepEqual(outer.content, ["0px", "0px"]);
    assert.deepEqual(outer.footer, ["8px", "0px", "1px"]);
    assert.deepEqual(await snapshot("nested-default"), outer, `${theme}: defaults survive a plain parent`);
    const nestedPlain = await snapshot("nested-plain");
    const standalonePlain = await snapshot("standalone-plain");
    // Fonts and palette inherit from the surrounding theme; slot variants do not.
    const ownStyles = (value: typeof nestedPlain) => ({
      ...value, heading: [...value.heading.slice(1, 5), value.heading[6]],
    });
    assert.deepEqual(ownStyles(nestedPlain), ownStyles(standalonePlain), `${theme}: outer slot styles do not leak into plain cards`);
  }
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("shared tooltips work through the Storybook provider", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "ui-tooltip--default");
  const frame = await storyFrame(page);
  const trigger = frame.getByRole("button", { name: "Hover or focus", exact: true });
  await trigger.hover();
  await frame.getByRole("tooltip", { name: "Helpful information.", exact: true }).waitFor();
  await page.mouse.move(0, 0, { steps: 5 });
  await frame.getByRole("tooltip").waitFor({ state: "hidden" });
  await trigger.focus();
  await frame.getByRole("tooltip").waitFor();
  await page.keyboard.press("Escape");
  await frame.getByRole("tooltip").waitFor({ state: "hidden" });
  assert.equal(await trigger.evaluate((element) => element === document.activeElement), true);
  assert.equal(await trigger.getAttribute("title"), null);
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("editing text repaints actual glyphs", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const before = await canvasStats(frame);

  const textField = page.locator("#control-text");
  const paints = await storyPaints(frame);
  await textField.fill("Ag");
  await textField.press("Enter");
  await textField.press("Tab");
  await waitMorePaints(frame, paints);
  const after = await canvasStats(frame);
  assert.notEqual(after.digest, before.digest, "new text paints different glyphs");
  assert.ok(after.ink > 0, `short text paints nonempty glyphs, got ${after.ink} ink pixels`);
  assert.ok(after.distinct >= 2, `short text paints non-uniform coverage, got ${after.distinct} pixel values`);
  assert.match(await storyStatus(frame), /missing=0/, "short text stays fully covered");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("font selection repaints from bundled bytes", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const before = await canvasStats(frame);

  const paints = await storyPaints(frame);
  await frame.getByRole("combobox", { name: "Font", exact: true }).click();
  await frame.getByRole("option", { name: "Literata", exact: true }).click();
  await waitMorePaints(frame, paints);
  const after = await canvasStats(frame);
  assert.notEqual(after.digest, before.digest, "the new font paints different glyphs");
  assert.match(await storyStatus(frame), /missing=0/);
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("playground colors repaint real glyphs", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await frame.locator("[data-color-playground]").waitFor({ timeout: 30000 });

  // Opaque paper corner proves the background path exactly.
  await setRgba(frame, "background", "#0a141eff");
  const stats = await canvasStats(frame);
  assert.deepEqual(
    await canvasPixel(frame, stats.width - 1, stats.height - 1),
    [10, 20, 30, 255],
    "uncovered corner holds the paper color",
  );

  const before = await canvasStats(frame);
  // The swatch only stages a draft: nothing repaints until the explicit
  // rebuild, so an uneven palette is never clobbered by accident.
  const draftPaints = await storyPaints(frame);
  await setRgbaField(frame, "font", "#1e5ac8ff");
  assert.equal(await storyPaints(frame), draftPaints, "the font draft paints nothing");
  assert.equal((await canvasStats(frame)).digest, before.digest, "the font draft changes no pixels");
  await applyInk(frame);
  const after = await canvasStats(frame);
  assert.notEqual(after.digest, before.digest, "ink rebuild repaints the glyphs");

  await setRgba(frame, "background", "#0a141e00");
  const transparent = await canvasStats(frame);
  assert.notEqual(transparent.digest, after.digest, "transparent paper repaints");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("palette mode follows profile switches on real glyphs", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--palette-and-transparency");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await frame.locator("[data-color-playground]").waitFor({ timeout: 30000 });
  await openDisclosure(frame, "data-levels-disclosure");
  assert.equal(await frame.locator('[data-picker-row^="level-"]:not([data-picker-row="level-0"])').count(), 7);

  const before = await canvasStats(frame);
  await setRgba(frame, "level-3", "#c81e1eff");
  const edited = await canvasStats(frame);
  assert.notEqual(edited.digest, before.digest, "edited level repaints");
  const editedLevel3 = await frame.locator('[data-picker-bytes="level-3"]').innerText();
  assert.equal(editedLevel3, "#c81e1eff", "the level readout shows the edited bytes");

  // Profile switches gate the canvas until the actual palette args
  // converge, so no Invalid palette status may flash in between: record
  // every status change across both switches.
  await frame.evaluate(() => {
    const seen: string[] = [];
    ((window as unknown) as { __statusLog?: string[] }).__statusLog = seen;
    const target = document.querySelector("[data-story-status]");
    if (target) {
      new MutationObserver(() => {
        seen.push(target.textContent ?? "");
      }).observe(target, { childList: true, characterData: true, subtree: true });
    }
  });
  const profileRow = page.locator("#storybook-panel-root tr", { hasText: /profile/i });
  let paints = await storyPaints(frame);
  await profileRow.locator("select").selectOption("mono_1bit");
  await waitFreshPaint(frame, paints);
  assert.equal(await frame.locator('[data-picker-row^="level-"]:not([data-picker-row="level-0"])').count(), 1);

  paints = await storyPaints(frame);
  await profileRow.locator("select").selectOption("gray_3bit");
  await waitFreshPaint(frame, paints);
  const statusLog = await frame.evaluate(
    () => ((window as unknown) as { __statusLog?: string[] }).__statusLog ?? [],
  );
  assert.ok(
    statusLog.every((text) => !text.startsWith("error:")),
    `profile switches never flash an error, got: ${JSON.stringify(statusLog)}`,
  );
  assert.equal((await canvasStats(frame)).digest, edited.digest, "level colors survive the round trip");
  assert.equal(
    await frame.locator('[data-picker-bytes="level-3"]').innerText(),
    editedLevel3,
    "the edited level readout survives the round trip",
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("mono paper edits preserve gray levels across return and recovery", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await frame.locator("[data-color-playground]").waitFor({ timeout: 30000 });

  // Build a custom gray palette through the RGBA popups: paper plus one
  // edited ink level.
  await selectGrayProfile(page, frame);
  await openDisclosure(frame, "data-levels-disclosure");
  await setRgba(frame, "background", "#f0e6d280");
  await setRgba(frame, "level-3", "#c81e1eff");
  assert.equal(await frame.locator('[data-picker-bytes="background"]').innerText(), "#f0e6d280");
  assert.equal(await frame.locator('[data-picker-bytes="level-3"]').innerText(), "#c81e1eff");

  await frame.evaluate(() => {
    const seen: string[] = [];
    ((window as unknown) as { __statusLog?: string[] }).__statusLog = seen;
    const target = document.querySelector("[data-story-status]");
    if (target) {
      new MutationObserver(() => {
        seen.push(target.textContent ?? "");
      }).observe(target, { childList: true, characterData: true, subtree: true });
    }
  });
  const profileRow = page.locator("#storybook-panel-root tr", { hasText: /profile/i });
  let paints = await storyPaints(frame);
  await profileRow.locator("select").selectOption("mono_1bit");
  await waitFreshPaint(frame, paints);
  assert.equal(await frame.locator('[data-picker-row^="level-"]:not([data-picker-row="level-0"])').count(), 1);
  assert.equal(
    await frame.locator('[data-picker-bytes="background"]').innerText(),
    "#f0e6d280",
    "the collapse keeps the paper",
  );
  assert.equal(
    await frame.locator('[data-picker-bytes="level-1"]').innerText(),
    "#24282bff",
    "the collapse keeps full-coverage ink",
  );

  // Combined RGBA paper edit while narrow; the ink entry is untouched.
  await setRgba(frame, "background", "#0a141e5a");
  assert.equal(await frame.locator('[data-picker-bytes="background"]').innerText(), "#0a141e5a");
  assert.equal(
    await frame.locator('[data-picker-bytes="level-1"]').innerText(),
    "#24282bff",
    "paper edits preserve the ink entry",
  );

  // Return carries the current paper forward while restoring the parked
  // nonzero entries — never the parked paper.
  paints = await storyPaints(frame);
  await profileRow.locator("select").selectOption("gray_3bit");
  await waitFreshPaint(frame, paints);
  const statusLog = await frame.evaluate(
    () => ((window as unknown) as { __statusLog?: string[] }).__statusLog ?? [],
  );
  assert.ok(
    statusLog.every((text) => !text.startsWith("error:")),
    `profile switches never flash an error, got: ${JSON.stringify(statusLog)}`,
  );
  assert.equal(
    await frame.locator('[data-picker-bytes="background"]').innerText(),
    "#0a141e5a",
    "the return carries the edited paper forward",
  );
  assert.equal(
    await frame.locator('[data-picker-bytes="level-3"]').innerText(),
    "#c81e1eff",
    "the return restores parked ink levels",
  );
  assert.equal(await frame.locator('[data-picker-bytes="level-1"]').innerText(), "#24282b24");
  const returned = await canvasStats(frame);

  // The customized palette survives an error and a ready recovery verbatim.
  await selectDiagnostic(frame, "invalid-palette");
  assert.match(await waitStoryError(frame), /Invalid palette/, "invalid palette reports");
  paints = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, paints);
  assert.equal((await canvasStats(frame)).digest, returned.digest, "recovery preserves the customized palette");
  assert.equal(
    await frame.locator('[data-picker-bytes="background"]').innerText(),
    "#0a141e5a",
    "recovery preserves the edited paper",
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

const REAL_PROPS = [
  "text", "sizePx", "zoom", "mode", "profile", "palette", "ready",
];
const HELPER_NAMES = [
  "fontName", "paletteEditor", "diagnostic", "scenario", "viewportWidth", "checkerboard",
  "rawPalette", "rawBackground", "spareLevels", "colorMode", "hideWhenEmpty", "hideEmpty",
  "background",
];

// First-cell names of the manager Controls table: input ids alone would
// miss a control:false row, so the audit reads the rendered row labels.
async function managerRowNames(page: Page): Promise<string[]> {
  await page.locator("#control-text").waitFor({ timeout: 60000 });
  return page.evaluate(() => Array.from(document.querySelectorAll("#storybook-panel-root tr"))
    .map((row) => row.querySelector("td, th")?.textContent?.trim().split("\n")[0]?.trim() ?? "")
    .filter((name) => name.length > 0));
}

function expectOnlyRealProps(names: string[], where: string): void {
  for (const name of REAL_PROPS) {
    assert.ok(names.includes(name), `${where}: props table lists the real prop ${name}`);
  }
  for (const name of HELPER_NAMES) {
    assert.ok(!names.includes(name), `${where}: props table has no helper row ${name}`);
  }
}

test("manager controls list only real props, setup lives inline", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  // Radio groups render without a #control-* id, so mode is covered by the
  // row-name audit above rather than by id here.
  const editableControls = ["text", "sizePx", "zoom", "profile", "ready"];
  for (const story of ["renderer-fontcanvas--playground", "renderer-fontcanvasdiagnostics--states"]) {
    const page = await openManager(browser, base, story);
    const frame = await storyFrame(page);
    await requirePreview(frame, page);
    await waitPainted(frame);
    expectOnlyRealProps(await managerRowNames(page), `${story} manager`);
    for (const name of editableControls) {
      assert.ok(
        await page.locator(`#control-${name}`).count() > 0,
        `${story}: Controls keeps the real prop ${name}`,
      );
    }
    for (const name of HELPER_NAMES) {
      assert.equal(
        await page.locator(`#control-${name}`).count(),
        0,
        `${story}: Controls has no helper row ${name}`,
      );
    }
    assert.equal(await frame.locator("[data-setup-panel]").count(), 1, `${story}: one Playground setup panel`);
    await frame.getByRole("combobox", { name: "Font", exact: true }).click();
    assert.ok(await frame.getByRole("option").count() > 1, `${story}: the font select lists bundled fonts`);
    await frame.locator("[data-setup-font]").press("Escape");
    assert.deepEqual(storyErrors(page), []);
    await page.close();
  }
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  assert.equal(await frame.locator("[data-diagnostic-tools]").count(), 1, "diagnostics story shows Diagnostic tools");
  await frame.getByRole("combobox", { name: "Failure state", exact: true }).click();
  assert.ok(
    await frame.getByRole("option", { name: "Invalid palette", exact: true }).count() > 0,
    "the inline state select offers the invalid-palette state",
  );
  await frame.locator("[data-diagnostic-state]").press("Escape");
  assert.deepEqual(storyErrors(page), []);
  await page.close();

  const normal = await openManager(browser, base, "renderer-fontcanvas--playground");
  const normalFrame = await storyFrame(normal);
  await requirePreview(normalFrame, normal);
  await waitPainted(normalFrame);
  assert.equal(
    await normalFrame.locator("[data-diagnostic-tools]").count(),
    0,
    "normal stories never show Diagnostic tools",
  );
  assert.deepEqual(storyErrors(normal), []);
  await normal.close();
});

test("docs table and snippets show only real FontCanvas usage", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openPreview(browser, base, "docs/renderer-fontcanvas--docs");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await frame.waitForFunction(
    () => document.querySelectorAll("canvas").length >= 3,
    null,
    { timeout: 120000 },
  );
  const docNames = await frame.evaluate(() => Array.from(document.querySelectorAll("table"))
    .flatMap((table) => Array.from(table.querySelectorAll("tr"))
      .map((row) => row.querySelector("td, th")?.textContent?.trim().split("\n")[0]?.trim() ?? ""))
    .filter((name) => name.length > 0));
  expectOnlyRealProps(docNames, "docs");
  // Story sources render behind one Show code toggle per example (role
  // switch, not button); the toggles arrive after the canvases, so wait for
  // the first one.
  const showCode = frame.getByRole("switch", { name: "Show code" });
  await showCode.first().waitFor({ timeout: 60000 });
  const toggles = await showCode.count();
  assert.ok(toggles >= 3, `docs offer one source toggle per example, got ${toggles}`);
  for (let i = 0; i < toggles; i += 1) {
    await frame.getByRole("switch", { name: "Show code" }).first().click();
  }
  // Highlighted sources split tokens across spans and expand
  // asynchronously, so wait for all three blocks by concatenated text
  // rather than matching inside one element.
  await frame.waitForFunction(
    () => Array.from(document.querySelectorAll("pre, code"))
      .filter((el) => (el.textContent ?? "").includes("<FontCanvas")).length >= 3,
    null,
    { timeout: 60000 },
  );
  const blocks = await frame.evaluate(
    () => Array.from(document.querySelectorAll("pre, code")).map((el) => el.textContent ?? ""),
  );
  const snippets = blocks.filter((text) => text.includes("<FontCanvas"));
  assert.ok(snippets.length >= 3, `docs show one snippet per example, got ${snippets.length}`);
  assert.ok(
    snippets.some((snippet) => snippet.includes("palette={[")),
    "a snippet shows a complete palette",
  );
  for (const snippet of snippets) {
    assert.ok(snippet.includes("default Roboto fontId"), "snippet labels the default font usage");
    for (const required of ["stemFitting", "font_hints_first", 'role="baseline"', "axes={{}}", "kerning"]) {
      assert.ok(snippet.includes(required), `snippet shows the fixed prop ${required}`);
    }
    for (const helper of [
      "fontName", "colorMode", "paletteEditor", "diagnostic", "rawPalette", "spareLevels",
      "viewportWidth", "checkerboard", "scenario", "background",
    ]) {
      assert.ok(!snippet.includes(helper), `snippet never invents ${helper}`);
    }
  }
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("font color generates a complete coverage-scaled palette", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await frame.locator("[data-color-playground]").waitFor({ timeout: 30000 });
  await selectGrayProfile(page, frame);
  await openDisclosure(frame, "data-levels-disclosure");
  assert.equal(await frame.locator('[data-picker-row^="level-"]:not([data-picker-row="level-0"])').count(), 7);

  // A custom paper survives the generation: only the ink levels rebuild.
  // Staging the draft alone repaints nothing and keeps every level.
  await setRgba(frame, "background", "#0a141eff");
  const before = await canvasStats(frame);
  const stagedPaints = await storyPaints(frame);
  await setRgbaField(frame, "font", "#1e5ac8ff");
  assert.equal(await storyPaints(frame), stagedPaints, "the font draft paints nothing");
  assert.equal((await canvasStats(frame)).digest, before.digest, "the font draft changes no pixels");
  await applyInk(frame);
  const after = await canvasStats(frame);
  assert.notEqual(after.digest, before.digest, "generated levels repaint the glyphs");
  assert.equal(
    await frame.locator('[data-picker-bytes="background"]').innerText(),
    "#0a141eff",
    "generation keeps the paper entry",
  );
  // Ink #1e5ac8ff: level 1 carries 1/7 coverage alpha, the full level stays
  // opaque, and the hue never changes.
  assert.equal(await frame.locator('[data-picker-bytes="level-1"]').innerText(), "#1e5ac824");
  assert.equal(await frame.locator('[data-picker-bytes="level-7"]').innerText(), "#1e5ac8ff");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("rgba popup opens by keyboard, normalizes hex, escape returns focus", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  // Level 3 below needs gray; fresh defaults are mono.
  await selectGrayProfile(page, frame);
  await openDisclosure(frame, "data-levels-disclosure");

  // One shared header, row numbers only: no repeated visible labels.
  const levelsText = await frame.locator("[data-levels-disclosure]").innerText();
  assert.doesNotMatch(levelsText, /Level \d+ alpha/, "no repeated per-row alpha labels");
  assert.equal(await frame.locator("[data-levels-disclosure] thead th").count(), 2, "Level / RGBA headers named once");

  const trigger = frame.locator('[data-picker-trigger="level-3"]');
  assert.match(await trigger.getAttribute("aria-label") ?? "", /Level 3 RGBA/, "the trigger names its entry");
  await trigger.focus();
  await trigger.press("Enter");
  const dialog = frame.getByRole("dialog", { name: "Level 3 RGBA picker" });
  await dialog.waitFor({ timeout: 30000 });

  // A short 6-digit commit normalizes to opaque instead of being ignored.
  const paints = await storyPaints(frame);
  await frame.locator('[data-rgba-field="level-3"]').fill("#c81e1e");
  await waitMorePaints(frame, paints);
  assert.equal(await frame.locator('[data-picker-bytes="level-3"]').innerText(), "#c81e1eff");

  await page.keyboard.press("Escape");
  await frame.waitForFunction(
    () => document.querySelectorAll('[data-rgba-pop="level-3"]').length === 0,
    null,
    { timeout: 30000 },
  );
  // Radix restores focus asynchronously after dismissal, so wait for the
  // landing instead of asserting it in the same frame.
  await frame.waitForFunction(
    () => (document.activeElement as HTMLElement | null)?.dataset?.pickerTrigger === "level-3",
    null,
    { timeout: 30000 },
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("rgba popup alpha slider edits opacity from the keyboard", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);

  await frame.locator('[data-picker-trigger="background"]').click();
  const dialog = frame.getByRole("dialog", { name: "Background color RGBA picker" });
  await dialog.waitFor({ timeout: 30000 });
  const before = await canvasStats(frame);
  const paints = await storyPaints(frame);
  const alpha = dialog.getByRole("slider", { name: "Alpha" });
  await alpha.focus();
  await alpha.press("ArrowLeft");
  await alpha.press("ArrowLeft");
  await waitMorePaints(frame, paints);
  const readout = await frame.locator('[data-picker-bytes="background"]').innerText();
  assert.match(readout, /^#[0-9a-f]{6}[0-9a-f]{2}$/, "one combined readout");
  assert.ok(
    Number.parseInt(readout.slice(-2), 16) < 255,
    `the slider lowered opacity, got ${readout}`,
  );
  assert.notEqual((await canvasStats(frame)).digest, before.digest, "lower opacity repaints");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

// Commits the raw palette JSON through its Apply button and returns the
// paint counter from before the commit. Opens the collapsed raw disclosure
// first; every caller goes through the visible human path.
async function applyRaw(frame: Frame, value: string): Promise<number> {
  await openDisclosure(frame, "data-raw-disclosure");
  const before = await storyPaints(frame);
  await frame.locator("[data-raw-palette]").fill(value);
  await frame.locator("[data-raw-palette-apply]").click();
  await waitRawCommitted(frame, value === "" ? "" : JSON.stringify(JSON.parse(value)));
  return before;
}

async function waitRawCommitted(frame: Frame, expected: string): Promise<void> {
  await frame.waitForFunction(
    (value) => document.querySelector("[data-raw-palette]")?.getAttribute("data-raw-committed") === value,
    expected,
    { timeout: 30000 },
  );
}

// Waits for a NEW error status differing from the previous one: error to
// error transitions never repaint, so paint counters cannot tell them apart.
async function waitNewError(frame: Frame, previous: string): Promise<string> {
  await frame.waitForFunction(
    (prev) => {
      const status = document.querySelector("[data-story-status]")?.textContent ?? "";
      return status.startsWith("error:") && status !== prev;
    },
    previous,
    { timeout: 60000 },
  );
  return storyStatus(frame);
}

test("diagnostics raw JSON edits actual props and recovers user colors", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  // The custom palettes below are 8-entry gray: opt in explicitly.
  await selectGrayProfile(page, frame);

  // A valid raw commit writes the actual palette prop, entry 0 first: the
  // draft resyncs to the committed bytes and the uncovered corner paints
  // the paper entry.
  const customEight = "[[10,20,30,255],[200,30,30,255],[200,30,30,255],[200,30,30,255],[200,30,30,255],[200,30,30,255],[200,30,30,255],[200,30,30,255]]";
  let paints = await applyRaw(frame, customEight);
  await waitMorePaints(frame, paints);
  assert.equal(await frame.locator("[data-raw-palette]").getAttribute("data-raw-committed"), customEight);
  const tinted = await canvasStats(frame);
  assert.deepEqual(
    await canvasPixel(frame, tinted.width - 1, tinted.height - 1),
    [10, 20, 30, 255],
    "the raw entry 0 commit paints",
  );

  // Unparseable JSON never reaches the args: a brief error shows while the
  // last painted values keep applying.
  await openDisclosure(frame, "data-raw-disclosure");
  await frame.locator("[data-raw-palette]").fill("nope[");
  await frame.locator("[data-raw-palette-apply]").click();
  await frame.locator("[data-raw-error]").waitFor({ timeout: 30000 });
  assert.match(await storyStatus(frame), /^painted/, "bad syntax keeps the last paint");

  // A wrong-length palette commits verbatim and errors in the renderer.
  await applyRaw(frame, "[[1,2,3,4],[5,6,7,8]]");
  assert.match(await waitStoryError(frame), /Invalid palette/, "raw length mismatch reports");

  // Scalars, null and malformed tuples never crash the panels: they apply
  // verbatim and error in the renderer, with the pickers hidden meanwhile.
  // The resync proves each commit landed; the status line may already show
  // the previous error, so it cannot prove that here.
  for (const [bad, compact] of [
    ["5", "5"],
    ["null", "null"],
    ["[[1,2],[3,4],[5,6],[7,8],[9,0],[1,2],[3,4],[5,6]]", "[[1,2],[3,4],[5,6],[7,8],[9,0],[1,2],[3,4],[5,6]]"],
  ] as [string, string][]) {
    await applyRaw(frame, bad);
    await waitRawCommitted(frame, compact);
    assert.match(await storyStatus(frame), /Invalid palette/, `raw ${bad} reports`);
  }
  assert.ok(
    await frame.locator('[data-picker-note="invalid"]').count() > 0,
    "the pickers hide while a malformed palette applies",
  );

  // Blank means omitted: the renderer default applies instead of an empty
  // list. The error short-circuit must not fire on the outgoing error.
  paints = await applyRaw(frame, "");
  await waitFreshPaint(frame, paints);
  assert.match(await storyStatus(frame), /^painted/, "blank palette paints the default");
  const customHealthy = await canvasStats(frame);

  // Recovery restores the user's healthy colors, not story defaults. The
  // state select already shows ready from the manual edits, so recovery goes
  // through the human path that re-applies the selected state.
  await applyRaw(frame, "[[1,2,3,4],[5,6,7,8]]");
  assert.match(await waitStoryError(frame), /Invalid palette/, "invalid request errors again after a valid paint");
  paints = await storyPaints(frame);
  await frame.locator("[data-diagnostic-apply]").click();
  await waitFreshPaint(frame, paints);
  assert.equal((await canvasStats(frame)).digest, customHealthy.digest, "ready restores the user colors");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

// Gray-dependent cases opt in explicitly now that fresh defaults are mono.
async function selectGrayProfile(page: Page, frame: Frame): Promise<void> {
  const before = await storyPaints(frame);
  await page.locator("#storybook-panel-root tr", { hasText: /profile/i }).locator("select").selectOption("gray_3bit");
  await waitMorePaints(frame, before);
}

// Applies one diagnostics bundle through the inline state select, which
// writes the full bundle at once while the provider session stays mounted
// for scenario ok. The state lives only in the Diagnostic tools panel:
// there is no Controls row for it. Re-applying the selected state goes
// through the Apply state button instead (same-value selects fire nothing).
async function selectDiagnostic(frame: Frame, state: string): Promise<void> {
  await frame.getByRole("combobox", { name: "Failure state", exact: true }).click();
  const labels: Record<string, string> = {
    ready: "Ready", error: "Render error", unavailable: "Service unavailable",
    "missing-glyphs": "Missing glyphs", "invalid-palette": "Invalid palette",
    "not-ready": "Not ready", "empty-text": "Empty text",
  };
  await frame.getByRole("option", { name: labels[state], exact: true }).click();
}

// Recovery through the state selector only: each selection writes its full
// bundle, and the error status inherited from the previous request must
// never satisfy a paint wait, so recovery waits watch the paint counter.
// The baseline is captured BEFORE selecting, since a fast render can finish
// before a later read.
async function waitFreshPaint(frame: Frame, before: number): Promise<void> {
  await frame.waitForFunction(
    (expected) => Number(document.querySelector("[data-story-paints]")?.textContent ?? "0") > expected,
    before,
    { timeout: 60000 },
  );
  assert.match(await storyStatus(frame), /^painted/, "recovery paints instead of holding the old error");
}

test("raw invalid palette recovers through font mode", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const healthy = await canvasStats(frame);
  assert.ok(healthy.ink > 100, "ready state paints glyphs");

  await selectDiagnostic(frame, "invalid-palette");
  assert.match(await waitStoryError(frame), /Invalid palette/, "raw length mismatch reports");

  const beforeFirstRecovery = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, beforeFirstRecovery);
  const stats = await canvasStats(frame);
  assert.equal(stats.digest, healthy.digest, "recovery repaints identically");

  await selectDiagnostic(frame, "invalid-palette");
  assert.match(await waitStoryError(frame), /Invalid palette/, "invalid request errors again after a valid paint");
  const beforeSecondRecovery = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, beforeSecondRecovery);
  const recovered = await canvasStats(frame);
  assert.equal(recovered.digest, healthy.digest, "second recovery repaints identically");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("invalid colors clear across fixture states and recover", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const healthy = await canvasStats(frame);
  assert.ok(healthy.ink > 100, "ready state paints glyphs");

  await selectDiagnostic(frame, "invalid-palette");
  let status = await waitStoryError(frame);
  assert.match(status, /Invalid palette/, "invalid palette reports");

  // Every other preset restores the healthy colors, so each state exercises
  // its own case instead of inheriting the palette error. Error to error
  // transitions never repaint, so each wait keys on the status text itself.
  await selectDiagnostic(frame, "missing-glyphs");
  status = await waitNewError(frame, status);
  assert.match(status, /error: missing glyph U\+1F600/, "missing glyphs report, not the palette");

  await selectDiagnostic(frame, "invalid-palette");
  status = await waitNewError(frame, status);
  assert.match(status, /Invalid palette/, "invalid palette reports again");
  await selectDiagnostic(frame, "error");
  status = await waitNewError(frame, status);
  assert.match(status, /^error:/, "simulated render failure reports");
  await selectDiagnostic(frame, "unavailable");
  await frame.waitForFunction(
    () => /Renderer unavailable/.test(document.querySelector("[data-story-human]")?.textContent ?? ""),
    null,
    { timeout: 60000 },
  );

  // Recovery survives the fixture remounts: a fresh paint of the healthy glyphs.
  const beforeRecovery = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, beforeRecovery);
  assert.equal((await canvasStats(frame)).digest, healthy.digest, "ready repaints healthy glyphs after fixtures");

  // A full explicitly committed palette survives fixture states verbatim:
  // the same array and the same glyph digest. Eight entries need gray.
  await selectGrayProfile(page, frame);
  const fullEight = "[[0,0,0,0],[10,20,30,36],[40,50,60,72],[70,80,90,108],[100,110,120,144],[130,140,150,180],[160,170,180,216],[190,200,210,255]]";
  let paints = await applyRaw(frame, fullEight);
  await waitFreshPaint(frame, paints);
  const fullDigest = (await canvasStats(frame)).digest;
  await selectDiagnostic(frame, "error");
  assert.match(await waitStoryError(frame), /^error:/, "fixture error after a raw palette");
  await selectDiagnostic(frame, "unavailable");
  await frame.waitForFunction(
    () => /Renderer unavailable/.test(document.querySelector("[data-story-human]")?.textContent ?? ""),
    null,
    { timeout: 60000 },
  );
  paints = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, paints);
  assert.equal((await canvasStats(frame)).digest, fullDigest, "ready preserves the committed palette");
  assert.equal(
    await frame.locator("[data-raw-palette]").getAttribute("data-raw-committed"),
    fullEight,
    "the committed array restores verbatim",
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("missing glyphs are reported, readiness gates painting", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);

  await selectDiagnostic(frame, "missing-glyphs");
  assert.match(await waitStoryError(frame), /error: missing glyph U\+1F600/, "uncovered codepoint errors by name");

  await selectDiagnostic(frame, "not-ready");
  await frame.waitForFunction(
    () => /Rendering paused/.test(document.querySelector("[data-story-human]")?.textContent ?? ""),
    null,
    { timeout: 60000 },
  );
  await selectDiagnostic(frame, "missing-glyphs");
  assert.match(await waitStoryError(frame), /error: missing glyph U\+1F600/, "ready resets when leaving not-ready");

  const beforeGatingRecovery = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, beforeGatingRecovery);
  assert.ok((await canvasStats(frame)).ink > 100, "ready paints glyphs after readiness gating");

  // Empty text paints a mounted blank canvas; hiding is the card's own
  // policy, not a canvas state.
  const beforeEmpty = await storyPaints(frame);
  await selectDiagnostic(frame, "empty-text");
  await waitFreshPaint(frame, beforeEmpty);
  assert.equal(
    await frame.evaluate(() => document.querySelectorAll("canvas").length),
    1,
    "empty text keeps its mounted canvas",
  );
  assert.equal(
    await frame.locator("[data-story-human]").count(),
    0,
    "empty input paints cleanly with no status line",
  );
  await selectDiagnostic(frame, "error");
  assert.match(await waitStoryError(frame), /^error:/, "simulated render failure reports");
  await selectDiagnostic(frame, "unavailable");
  await frame.waitForFunction(
    () => /Renderer unavailable/.test(document.querySelector("[data-story-human]")?.textContent ?? ""),
    null,
    { timeout: 60000 },
  );
  const beforeFixtureRecovery = await storyPaints(frame);
  await selectDiagnostic(frame, "ready");
  await waitFreshPaint(frame, beforeFixtureRecovery);
  assert.ok((await canvasStats(frame)).ink > 100, "ready repaints after fixture states");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

// WCAG 2.2 contrast minimum (4.5:1) helpers for UI copy.
function relativeLuminance(rgb: [number, number, number]): number {
  const linear = rgb.map((channel) => {
    const sRGB = channel / 255;
    return sRGB <= 0.03928 ? sRGB / 12.92 : Math.pow((sRGB + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * (linear[0] ?? 0) + 0.7152 * (linear[1] ?? 0) + 0.0722 * (linear[2] ?? 0);
}

function parseCssColor(css: string): [number, number, number] {
  const match = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(css);
  assert.ok(match, `parseable color, got ${css}`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function contrastRatio(fg: string, bg: string): number {
  const first = relativeLuminance(parseCssColor(fg));
  const second = relativeLuminance(parseCssColor(bg));
  const [hi, lo] = first >= second ? [first, second] : [second, first];
  return (hi + 0.05) / (lo + 0.05);
}

async function elementColors(frame: Frame, selector: string): Promise<{ fg: string; bg: string }> {
  return frame.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`missing ${sel}`);
    const style = getComputedStyle(el);
    let bg: string | null = style.backgroundColor;
    let node: Element | null = el;
    while (node && (bg === "rgba(0, 0, 0, 0)" || bg === "transparent")) {
      node = node.parentElement;
      bg = node ? getComputedStyle(node).backgroundColor : null;
    }
    return { fg: style.color, bg: bg ?? "rgb(255, 255, 255)" };
  }, selector);
}

async function expectContrast(frame: Frame, selector: string, where: string): Promise<void> {
  // Measure only rendered content: the docs iframe also holds a hidden
  // loading skeleton whose unstyled text must never count as UI copy.
  await frame.locator(selector).first().waitFor({ state: "visible", timeout: 30000 });
  const { fg, bg } = await elementColors(frame, selector);
  const ratio = contrastRatio(fg, bg);
  assert.ok(ratio >= 4.5, `${where} ${selector} contrasts ${ratio.toFixed(2)}:1 (fg ${fg} on ${bg})`);
}

test("story surfaces keep text contrast in light and dark themes", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);

  await expectContrast(frame, "[data-fc-surface]", "light story surface");
  await expectContrast(frame, "[data-paper-note]", "light helper note");
  await frame.evaluate(() => document.documentElement.classList.add("dark"));
  await expectContrast(frame, "[data-fc-surface]", "dark story surface");
  await expectContrast(frame, "[data-paper-note]", "dark helper note");
  assert.deepEqual(storyErrors(page), []);
  await page.close();

  const errors = await openManager(browser, base, "renderer-fontcanvasdiagnostics--states");
  const errorsFrame = await storyFrame(errors);
  await requirePreview(errorsFrame, errors);
  await waitPainted(errorsFrame);
  await selectDiagnostic(errorsFrame, "invalid-palette");
  assert.match(await waitStoryError(errorsFrame), /Invalid palette/);
  await expectContrast(errorsFrame, "[data-story-human]", "light error line");
  await errorsFrame.evaluate(() => document.documentElement.classList.add("dark"));
  await expectContrast(errorsFrame, "[data-story-human]", "dark error line");
  assert.deepEqual(storyErrors(errors), []);
  await errors.close();
});

test("docs chrome stays legible in light and dark themes", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openPreview(browser, base, "docs/renderer-fontcanvas--docs");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await frame.waitForFunction(
    () => document.querySelectorAll("canvas").length >= 3,
    null,
    { timeout: 120000 },
  );
  // Expand the collapsed reference sections so their copy is checkable too.
  await openDisclosure(frame, "data-api-reference");
  const showCode = frame.getByRole("switch", { name: "Show code" });
  await showCode.first().waitFor({ timeout: 60000 });
  const toggles = await showCode.count();
  // Expanding one block re-renders the toolbar switches, so re-query and
  // click whichever switch is still closed instead of indexing a stale set.
  for (let i = 0; i < toggles + 3; i += 1) {
    const switches = frame.getByRole("switch", { name: "Show code" });
    const closedIndex = await switches.evaluateAll(
      (els) => els.findIndex((el) => el.getAttribute("aria-checked") !== "true"),
    );
    if (closedIndex < 0) break;
    await switches.nth(closedIndex).click();
  }
  // Table cells scope to the Component API reference: the story embeds now
  // hold their own (collapsed) level tables, which must never count as docs
  // copy — same reason the skeleton needed the visibility guard above.
  const selectors = ["[data-fc-docs] h1", "[data-fc-docs] > p", '[aria-label="FontCanvas examples"] a', "[data-api-reference] summary", "[data-api-reference] table td", "[data-api-reference] table th", "[data-fc-docs] pre"];
  for (const selector of selectors) {
    await expectContrast(frame, selector, `light docs ${selector}`);
  }
  await frame.evaluate(() => document.documentElement.classList.add("dark"));
  for (const selector of selectors) {
    await expectContrast(frame, selector, `dark docs ${selector}`);
  }
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("docs nav links to every standalone example", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openPreview(browser, base, "docs/renderer-fontcanvas--docs");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  const nav = frame.locator('[aria-label="FontCanvas examples"]');
  const links: [string, string][] = [
    ["Playground", "renderer-fontcanvas--playground"],
    ["Pixel accurate", "renderer-fontcanvas--pixel-accurate"],
    ["Palette & transparency", "renderer-fontcanvas--palette-and-transparency"],
    ["Diagnostics", "renderer-fontcanvasdiagnostics--states"],
  ];
  for (const [label, path] of links) {
    const href = await nav.getByRole("link", { name: label }).getAttribute("href");
    assert.ok(href?.includes(path), `nav links ${label} to its standalone page, got ${href}`);
  }
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("keyboard toggles disclosures without losing the palette", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const before = await canvasStats(frame);

  // Setup starts open: Enter closes it, Space reopens the levels disclosure.
  await frame.locator("[data-setup-panel] summary").press("Enter");
  assert.equal(
    await frame.locator("[data-setup-panel]").evaluate((el) => (el as HTMLDetailsElement).open),
    false,
    "Enter toggles the setup disclosure",
  );
  await frame.locator("[data-levels-disclosure] summary").press(" ");
  assert.equal(
    await frame.locator("[data-levels-disclosure]").evaluate((el) => (el as HTMLDetailsElement).open),
    true,
    "Space toggles the levels disclosure",
  );
  assert.equal((await canvasStats(frame)).digest, before.digest, "toggling disclosures repaints nothing");
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("preview precedes controls in the story layout", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  const order: string[] = await frame.evaluate(() => Array.from(
    document.querySelectorAll("canvas, [data-setup-panel], [data-levels-disclosure], [data-color-playground]"),
  ).map((el) => (el instanceof HTMLCanvasElement ? "canvas" : el.getAttribute("data-setup-panel") !== null
    ? "setup" : el.getAttribute("data-levels-disclosure") !== null ? "levels" : "quick")));
  const canvasAt = order.indexOf("canvas");
  assert.ok(canvasAt >= 0, "the story renders a canvas");
  for (const panel of ["setup", "quick", "levels"]) {
    assert.ok(order.indexOf(panel) > canvasAt, `the canvas precedes ${panel}, got ${order.join(",")}`);
  }
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});

test("narrow pages never scroll sideways with editors open", { skip: !browserAvailable }, async (t) => {
  const base = await devBase(t);
  const browser = await launch(t);
  const page = await openManager(browser, base, "renderer-fontcanvas--playground");
  const frame = await storyFrame(page);
  await requirePreview(frame, page);
  await waitPainted(frame);
  await openDisclosure(frame, "data-levels-disclosure");
  await page.setViewportSize({ width: 360, height: 800 });
  assert.ok(
    await frame.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    "no horizontal overflow at 360px with editors open",
  );
  assert.deepEqual(storyErrors(page), []);
  await page.close();
});
