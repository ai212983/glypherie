import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  blockDomainStorage,
  bootDetail,
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  cardVariantIds,
  cardVariantNames,
  createPalettePreset,
  fontDir,
  hashPath,
  launch,
  openNewVariant,
  selectPalettePreset,
  servePrefix,
  setRange,
  sha256,
} from "../helpers/spa-helpers.ts";
import type { Page } from "playwright-core";

async function flexId(page: Page): Promise<{ index: number; id: string }> {
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((name) => /^Roboto Flex/.test(name));
  assert.ok(index >= 0, "catalog has Roboto Flex");
  return { index, id: ids[index]! };
}

async function waitSaved(page: Page): Promise<void> {
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
}

async function waitEditor(page: Page): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await page.waitForFunction(canvasRendered, null, { timeout: 20000 });
}

async function sliderValue(page: Page, attribute: string): Promise<string | null> {
  return page.locator(`[${attribute}]`).getByRole("slider").getAttribute("aria-valuenow");
}

async function setKerningSlider(page: Page, attribute: string, value: number): Promise<void> {
  const slider = page.locator(`[${attribute}]`).getByRole("slider");
  const minimum = Number(await slider.getAttribute("aria-valuemin"));
  const step = attribute === "data-hu-hersch-cavity" || attribute === "data-hu-hersch-visual" ? 0.01 : 0.005;
  await slider.focus();
  await slider.press("Home");
  for (let i = 0; i < Math.round((value - minimum) / step); i++) await slider.press("ArrowRight");
  assert.equal(Number(await slider.getAttribute("aria-valuenow")), value);
}

/** Last bundled font id: SHA-256 of its canonical bytes, the library identity. */
async function lastFontId(): Promise<string> {
  return sha256(await fs.readFile(path.join(fontDir, "SourceSans3.ttf")));
}

test(
  "kerning method controls retain settings across switches and saved editor reloads",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    await openNewVariant(page, id);
    await waitEditor(page);

    const choose = async (method: "Source" | "TypeFacet"): Promise<void> => {
      await page.locator("[data-kerning-method]").click();
      await page.getByRole("option", { name: method, exact: true }).click();
    };
    assert.equal(await page.locator("[data-typefacet-controls]").count(), 0);
    await page.locator("[data-kerning]").uncheck();
    await choose("TypeFacet");
    assert.equal(await page.locator("[data-kerning]").count(), 0, "the inactive source switch is removed");
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.1");
    await setKerningSlider(page, "data-typefacet-normal", 0.15);
    await setKerningSlider(page, "data-typefacet-intrusion", 0.025);
    await setKerningSlider(page, "data-typefacet-minimum", 0.025);
    await setKerningSlider(page, "data-typefacet-overlap", 0.075);
    assert.equal(await page.locator("[data-typefacet-controls] input[type=number]").count(), 0);
    assert.equal(await page.locator("[data-typefacet-controls]").getByRole("slider").count(), 4);
    assert.equal(
      await page.getByRole("slider", { name: "Minimum clearance", exact: true }).getAttribute("aria-valuemax"),
      "0.15",
    );
    await waitSaved(page);
    await choose("Source");
    assert.equal(await page.locator("[data-typefacet-controls]").count(), 0, "inactive TypeFacet controls are removed");
    assert.equal(await page.locator("[data-kerning]").isChecked(), false, "the source setting is retained");
    await choose("TypeFacet");
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.15");
    assert.equal(await sliderValue(page, "data-typefacet-intrusion"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-minimum"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-overlap"), "0.075");
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.match((await page.locator("[data-kerning-method]").textContent()) ?? "", /TypeFacet/);
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.15");
    assert.equal(await sliderValue(page, "data-typefacet-intrusion"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-minimum"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-overlap"), "0.075");
    assert.equal(await page.locator("[data-status]").textContent(), "", "the selected method renders successfully");

    await page.locator("[data-text]").fill("nn oo aa");
    await waitSaved(page);
    await page.getByRole("button", { name: "Reset specimen", exact: true }).click();
    await waitSaved(page);
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.15", "specimen Reset preserves method settings");

    const editorUrl = page.url();
    await createPalettePreset(page, url, { name: "Kerning gray", bits: 3 });
    await page.goto(editorUrl, { waitUntil: "domcontentloaded" });
    await waitEditor(page);
    await selectPalettePreset(page, "Kerning gray");
    await waitSaved(page);
    assert.match((await page.locator("[data-kerning-method]").textContent()) ?? "", /TypeFacet/);
    assert.equal(await page.locator("[data-typefacet-normal]").getByRole("slider").isDisabled(), false);
    assert.equal(await page.locator("[data-typefacet-intrusion]").getByRole("slider").isDisabled(), false);
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.15", "Gray retains the method settings");
    await setKerningSlider(page, "data-typefacet-normal", 0.175);
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-output-palette] [data-palette-name]").textContent(), "Kerning gray");
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.175");
    assert.equal(await sliderValue(page, "data-typefacet-intrusion"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-minimum"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-overlap"), "0.075");
    assert.equal(await page.locator("[data-status]").textContent(), "", "TypeFacet renders Gray after reload");
    assert.equal(await page.locator("[data-typefacet-controls] [role=alert]").count(), 0);
    await choose("Source");
    assert.equal(await page.locator("[data-kerning]").isChecked(), false);
    await choose("TypeFacet");
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.175", "switching methods in Gray retains edits");
    await selectPalettePreset(page, "Monochrome");
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.match((await page.locator("[data-kerning-method]").textContent()) ?? "", /TypeFacet/);
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.175", "returning to Mono retains Gray edits");
    assert.equal(await sliderValue(page, "data-typefacet-intrusion"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-minimum"), "0.025");
    assert.equal(await sliderValue(page, "data-typefacet-overlap"), "0.075");
    assert.equal(await page.locator("[data-status]").textContent(), "", "the same method renders Mono again");
    await page.getByRole("button", { name: "Reset TypeFacet settings", exact: true }).click();
    await waitSaved(page);
    for (const [attribute, value] of [
      ["data-typefacet-normal", "0.1"],
      ["data-typefacet-intrusion", "0.1"],
      ["data-typefacet-minimum", "0"],
      ["data-typefacet-overlap", "0.1"],
    ]) {
      assert.equal(await sliderValue(page, attribute!), value);
    }
    assert.equal(await page.getByRole("button", { name: "Reset TypeFacet settings", exact: true }).isDisabled(), true);
    await page.locator("[data-text]").fill("ac ck");
    await waitSaved(page);
    await page.locator("[data-typefacet-normal]").getByRole("slider").press("End");
    await page.locator("[data-typefacet-minimum]").getByRole("slider").press("End");
    await waitSaved(page);
    const fixedNormal = page.locator("[data-typefacet-normal]").getByRole("slider");
    assert.equal(await fixedNormal.getAttribute("aria-valuenow"), "0.5");
    assert.equal(await fixedNormal.getAttribute("aria-valuemin"), "0.5");
    assert.equal(await fixedNormal.getAttribute("aria-valuemax"), "0.5");
    assert.equal(await fixedNormal.getAttribute("aria-disabled"), "true");
    assert.equal(
      await page.locator("[data-typefacet-controls]").evaluate((element) => element.outerHTML.includes("NaN")),
      false,
    );
    await page.getByRole("button", { name: "Reset TypeFacet settings", exact: true }).click();
    await waitSaved(page);
    assert.equal(await sliderValue(page, "data-typefacet-normal"), "0.1");
    assert.equal(await page.locator("[data-typefacet-normal]").getByRole("slider").isDisabled(), false);
    assert.deepEqual(errors, []);
  },
);

test(
  "additional kerning methods select their own controls and render after Mono and Gray reloads",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    await openNewVariant(page, id);
    await waitEditor(page);
    const choose = async (label: string): Promise<void> => {
      await page.locator("[data-kerning-method]").click();
      await page.getByRole("option", { name: label, exact: true }).click();
      await waitSaved(page);
    };
    await choose("TypeFacet");
    await setKerningSlider(page, "data-typefacet-normal", 0.15);
    await waitSaved(page);
    await choose("Hu/Hersch");
    assert.equal(
      await sliderValue(page, "data-hu-hersch-cavity"),
      "0.21",
      "default Hu/Hersch keeps the published cavity depth",
    );
    assert.equal(
      await sliderValue(page, "data-hu-hersch-visual"),
      "0.25",
      "default Hu/Hersch keeps the published visual depth",
    );
    assert.equal(
      await page.getByRole("slider", { name: "Cavity depth", exact: true }).getAttribute("aria-valuemax"),
      "1",
    );
    await setKerningSlider(page, "data-hu-hersch-cavity", 0.35);
    await setKerningSlider(page, "data-hu-hersch-visual", 0.4);
    await waitSaved(page);
    await choose("FontForge source-relative");
    assert.equal(
      await page.locator("[data-fontforge-controls]").getByRole("slider").count(),
      0,
      "FontForge has no blend control",
    );
    await waitSaved(page);

    const editorUrl = page.url();
    await createPalettePreset(page, url, { name: "Other kerning gray", bits: 3 });
    await page.goto(editorUrl, { waitUntil: "domcontentloaded" });
    await waitEditor(page);

    for (const palette of ["Monochrome", "Other kerning gray"]) {
      await selectPalettePreset(page, palette);
      await waitSaved(page);
      for (const label of ["Hu/Hersch", "FontForge source-relative"]) {
        await choose(label);
        assert.equal(await page.locator("[data-typefacet-controls]").count(), 0);
        assert.equal(await page.locator("[data-kerning]").count(), 0);
        assert.equal(await page.locator("[data-hu-hersch-controls]").count(), label.startsWith("Hu/") ? 1 : 0);
        assert.equal(await page.locator("[data-fontforge-controls]").count(), label.startsWith("FontForge") ? 1 : 0);
        await page.reload({ waitUntil: "domcontentloaded" });
        await waitEditor(page);
        assert.equal(await page.locator("[data-kerning-method]").textContent(), label);
        assert.equal(await page.locator("[data-status]").textContent(), "", `${label} renders ${palette}`);
        if (!label.startsWith("FontForge")) {
          assert.equal(
            await sliderValue(page, "data-hu-hersch-cavity"),
            "0.35",
            "Hu/Hersch cavity depth survives profile, method and reload changes",
          );
          assert.equal(
            await sliderValue(page, "data-hu-hersch-visual"),
            "0.4",
            "Hu/Hersch visual depth survives profile, method and reload changes",
          );
        }
      }
    }
    await choose("TypeFacet");
    assert.equal(
      await sliderValue(page, "data-typefacet-normal"),
      "0.15",
      "other method switches preserve TypeFacet parameters",
    );
    await choose("Hu/Hersch");
    await setKerningSlider(page, "data-hu-hersch-cavity", 0);
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(
      await sliderValue(page, "data-hu-hersch-cavity"),
      "0",
      "edited depths remain selected and saved as Hu/Hersch",
    );
    assert.equal(await page.locator("[data-status]").textContent(), "");
    await page.getByRole("button", { name: "Reset Hu/Hersch depths", exact: true }).click();
    await waitSaved(page);
    assert.equal(await sliderValue(page, "data-hu-hersch-cavity"), "0.21");
    assert.equal(await sliderValue(page, "data-hu-hersch-visual"), "0.25");
    assert.equal(await page.getByRole("button", { name: "Reset Hu/Hersch depths", exact: true }).isDisabled(), true);
    assert.deepEqual(errors, []);
  },
);

test("rapid typing saves the final value and reload shows it", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-variant-name]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-variant-name]").pressSequentially("QA variant heavy");
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("heavy");
  await waitSaved(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "QA variant heavy");
  assert.equal(await page.locator("[data-text]").inputValue(), "heavy");

  await page.reload({ waitUntil: "domcontentloaded" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "QA variant heavy");
  assert.equal(await page.locator("[data-text]").inputValue(), "heavy");
  await waitSaved(page);
  assert.deepEqual(errors, []);
});

test("latest edits survive immediate Back and Forward navigation", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("back-forward-probe-value");
  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.goForward();
  await waitEditor(page);
  await page.waitForFunction(
    () => (document.querySelector("[data-text]") as HTMLTextAreaElement | null)?.value === "back-forward-probe-value",
  );
  assert.equal(await page.locator("[data-text]").inputValue(), "back-forward-probe-value");
  await waitSaved(page);
  assert.equal(await page.locator("[data-text]").inputValue(), "back-forward-probe-value");
});

test("a cross-tab write surfaces a conflict notice with explicit reload", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const first = await context.newPage();
  await bootLibrary(first, url);
  const { id } = await flexId(first);
  const variantId = await openNewVariant(first, id);
  await waitEditor(first);
  await waitSaved(first);

  const second = await context.newPage();
  await second.goto(`${url}#/font/${id}/variant/${variantId}/`, { waitUntil: "domcontentloaded" });
  await waitEditor(second);
  await waitSaved(second);

  // Keep the first tab typing so its debounced save cannot fire yet; the
  // second tab commits a rename mid-typing and the first tab's save then
  // conflicts on its stale revision.
  const text = first.locator("[data-text]");
  await text.click();
  await first.keyboard.press("ControlOrMeta+a");
  const typing = text.pressSequentially("local edit text that keeps arriving", { delay: 40 });
  const secondName = second.locator("[data-variant-name]");
  await secondName.click();
  await second.keyboard.press("ControlOrMeta+a");
  await secondName.pressSequentially("Second tab name");
  await waitSaved(second);
  await typing;
  await first.waitForFunction(() => document.querySelector("[data-variant-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await first.locator("[data-variant-error] h2").innerText(), "Another tab changed this variant.");
  assert.equal(await first.locator("[data-error-reload]").count(), 1, "reload is the only recovery");
  assert.equal(
    await first.locator("[data-text]").inputValue(),
    "local edit text that keeps arriving",
    "local edits are kept",
  );

  await first.locator("[data-error-reload]").click();
  await first.waitForFunction(
    () => (document.querySelector("[data-variant-name]") as HTMLInputElement)?.value === "Second tab name",
    null,
    { timeout: 20000 },
  );
  assert.equal(await first.locator("[data-variant-name]").inputValue(), "Second tab name");
  await waitSaved(first);
  await context.close();
});

test("a blank variant name fails visibly and saves again once fixed", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-variant-name]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("renamed sample");
  await page.waitForFunction(() => document.querySelector("[data-variant-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-variant-error] h2").innerText(), "Couldn’t save changes.");
  assert.equal(await page.locator("[data-error-retry]").count(), 1, "ordinary errors offer retry");

  await page.locator("[data-variant-name]").click();
  await page.locator("[data-variant-name]").pressSequentially("Recovered name");
  await waitSaved(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Recovered name");
  assert.equal(await page.locator("[data-text]").inputValue(), "renamed sample");

  await page.reload({ waitUntil: "domcontentloaded" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Recovered name");
});

test("a cold missing variant route recovers with a working library link", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const probe = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(probe, url);
  const ids = await cardIds(probe);
  await probe.close();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/font/${ids[0]}/variant/00000000-0000-4000-8000-000000000000/`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() => document.querySelector("[data-variant-deleted]") !== null, null, {
    timeout: 20000,
  });
  await page.locator("[data-variant-deleted] [data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await hashPath(page), "/fonts/");
});

test("denied storage shows a query error with Retry instead of hanging", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  // The domain owner lives in a SharedWorker (PGlite); stubbing the main
  // thread's indexedDB cannot fail it. Block the domain worker instead so
  // its calls reject unavailable while the renderer worker stays alive.
  await blockDomainStorage(context);
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("[data-library-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-library-retry]").count(), 1, "a retry is offered");
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(text.includes("Browser storage is unavailable."), `the supported user message is shown, got: ${text}`);
  assert.ok(!text.includes("Domain storage"), "the underlying cause is not exposed");
  await page.locator("[data-library-retry]").click();
  await page.waitForFunction(() => document.querySelector("[data-library-error]") !== null, null, {
    timeout: 20000,
  });
  assert.deepEqual(errors, [], "query failures never throw during render");
  await context.close();
});

test("delayed seeding still resolves deep links instead of falling back", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const fontId = await lastFontId();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route("**/*.ttf", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });
  await page.goto(`${url}#/font/${fontId}/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("[data-unsaved-preview]") !== null, null, {
    timeout: 30000,
  });
  assert.equal(
    await page.locator('.family h2[id^="heading-"]').innerText(),
    "Source Sans 3",
    "the delayed font renders its preview instead of falling back",
  );
  await page.goto(`${url}#/font/${fontId}/variant/00000000-0000-4000-8000-000000000000/`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() => document.querySelector("[data-variant-deleted]") !== null, null, {
    timeout: 30000,
  });
  assert.equal(await page.locator("[data-font-card]").count(), 0, "no premature library fallback");
});

test(
  "legacy preview Save as variant copies settings without implicit writes",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    assert.deepEqual(await cardVariantIds(page, id), [], "no variants before the preview loads");

    await bootDetail(page, `${url}#/font/${id}/`);
    await page.locator("[data-size-px]").fill("28");
    await setRange(page, '[data-axis="wght"]', "600");
    await page.locator("[data-text]").click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.locator("[data-text]").pressSequentially("preview copy probe");
    await page.locator("[data-save-variant]").click();
    await waitEditor(page);
    const variantPath = await hashPath(page);
    assert.match(variantPath, new RegExp(`^/font/${id}/variant/[^/]+/$`), "save lands on the new variant route");
    assert.equal(await page.locator("[data-size-px]").inputValue(), "28", "size copies to the saved row");
    assert.equal(await page.locator('[data-axis="wght"]').inputValue(), "600", "axes copy to the saved row");
    assert.equal(await page.locator("[data-text]").inputValue(), "preview copy probe", "text copies to the saved row");
    await waitSaved(page);

    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-size-px]").inputValue(), "28", "copied settings persist");
    assert.equal(await page.locator("[data-text]").inputValue(), "preview copy probe");

    await page.goto(`${url}#/`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    // The saved-variant list arrives through its own reactive query, so wait
    // for it explicitly instead of assuming it settles with the cards.
    await page.waitForFunction(
      (fontId) => document.querySelectorAll(`[data-variant-link][data-variant-font="${fontId}"]`).length === 1,
      id,
      { timeout: 20000 },
    );
    assert.deepEqual((await cardVariantIds(page, id)).length, 1, "loading the preview created no extra variant");
  },
);

test(
  "variant specimens inherit root text and Reset preserves variant settings",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    await page.locator("[data-index-text]").fill("Root specimen Ag 123");
    await page.locator('[data-size-stop="48"]').click();
    const firstId = await openNewVariant(page, id);
    await waitEditor(page);
    await waitSaved(page);
    const preset = page.getByRole("combobox", { name: "Preset", exact: true });
    assert.equal(await preset.textContent(), "Default");
    assert.equal(await page.locator("[data-text]").inputValue(), "Root specimen Ag 123");
    const defaultSize = await page.locator("[data-size-px]").inputValue();
    assert.equal(defaultSize, "16", "root base size does not affect a variant");
    const defaultWght = await page.locator('[data-axis="wght"]').inputValue();

    await page.locator("[data-size-px]").fill("32");
    await setRange(page, '[data-axis="wght"]', "700");
    await page.getByRole("switch", { name: "Kerning", exact: true }).click();
    await page.locator("[data-text]").fill("Variant override");
    await waitSaved(page);
    assert.equal(await preset.textContent(), "Custom");
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-text]").inputValue(), "Variant override", "override survives reload");

    await page.locator('[data-primary-nav="fonts"]').click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    assert.equal(
      await page.locator("[data-index-text]").inputValue(),
      "Root specimen Ag 123",
      "override leaves root text alone",
    );
    await page.locator("[data-index-text]").fill("Updated root gj 456");
    const secondId = await openNewVariant(page, id);
    assert.notEqual(secondId, firstId);
    await waitEditor(page);
    assert.equal(
      await page.locator("[data-size-px]").inputValue(),
      defaultSize,
      "new variants start from font defaults",
    );
    assert.equal(await page.locator('[data-axis="wght"]').inputValue(), defaultWght);
    assert.equal(await page.locator("[data-text]").inputValue(), "Updated root gj 456");

    await page.goto(`${url}#/font/${id}/variant/${firstId}/`, { waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-text]").inputValue(), "Variant override", "root changes preserve overrides");
    await page.getByRole("button", { name: "Reset specimen", exact: true }).click();
    await waitSaved(page);
    assert.equal(await preset.textContent(), "Default");
    assert.equal(await page.locator("[data-size-px]").inputValue(), "32", "Reset preserves variant size");
    assert.equal(await page.locator('[data-axis="wght"]').inputValue(), "700", "Reset preserves axes");
    assert.equal(await page.getByRole("switch", { name: "Kerning", exact: true }).isChecked(), false);
    assert.equal(await page.locator("[data-text]").inputValue(), "Updated root gj 456");

    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await preset.textContent(), "Default", "inheritance survives reload");
    assert.equal(await page.locator("[data-text]").inputValue(), "Updated root gj 456");
    await preset.click();
    await page.getByRole("option", { name: "Pangram", exact: true }).click();
    await waitSaved(page);
    assert.equal(await preset.textContent(), "Pangram");
    await preset.click();
    await page.getByRole("option", { name: "Default", exact: true }).click();
    await waitSaved(page);
    assert.equal(await page.locator("[data-text]").inputValue(), "Updated root gj 456", "preset restores inheritance");

    await page.locator('[data-primary-nav="fonts"]').click();
    await page.locator("[data-index-text]").fill("");
    await page.locator(`[data-variant-link="${firstId}"]`).click();
    await waitEditor(page);
    assert.equal(await page.locator("[data-text]").inputValue(), "", "inheritance follows an empty root specimen too");
    assert.equal(await preset.textContent(), "Default");
  },
);

test("font cards are not clickable; variants are real child links", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  assert.deepEqual(await cardVariantIds(page, id), [], "fresh fonts start with zero variants");
  assert.equal(
    await page.locator(`[data-font-card="${id}"] a`).count(),
    0,
    "a font card without variants contains no links",
  );

  let reloaded = false;
  page.once("load", () => {
    reloaded = true;
  });
  await page.locator(`[data-font-card="${id}"]`).click({ position: { x: 4, y: 4 } });
  await page.waitForTimeout(500);
  assert.equal(reloaded, false, "clicking the card performs no navigation");
  assert.equal(await page.locator("[data-variant-editor]").count(), 0, "clicking the card opens no editor");

  const variantId = await openNewVariant(page, id);
  await waitEditor(page);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  // The saved-variant list arrives through its own reactive query, so wait
  // for the new link explicitly instead of assuming it settles with the cards.
  await page.waitForFunction(
    ([fontId, linkId]) =>
      document.querySelector(`[data-variant-link="${linkId}"][data-variant-font="${fontId}"]`) !== null,
    [id, variantId] as [string, string],
    { timeout: 20000 },
  );
  assert.deepEqual(await cardVariantIds(page, id), [variantId], "the saved variant lists under its font");
  assert.deepEqual(await cardVariantNames(page, id), ["Variant 1"]);

  const link = page.locator(`[data-variant-link="${variantId}"]`);
  assert.ok(((await link.getAttribute("href")) ?? "").includes(`/preview/font/${id}/variant/${variantId}/`));
  assert.equal(await link.getAttribute("aria-label"), "Variant 1");
  await link.focus();
  await page.keyboard.press("Enter");
  await waitEditor(page);
  assert.equal(await hashPath(page), `/font/${id}/variant/${variantId}/`);

  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const [tab] = await Promise.all([
    context.waitForEvent("page"),
    page
      .locator(`[data-variant-link="${variantId}"]`)
      .click({ modifiers: [process.platform === "darwin" ? "Meta" : "Control"] }),
  ]);
  await tab.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await hashPath(tab), `/font/${id}/variant/${variantId}/`);
  assert.equal(await page.locator("[data-font-card]").count(), 5, "original tab stays on the catalog");
  await context.close();
});

test(
  "variant sidebar shares specimen rows and supports switching, adding and deleting",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    const first = await openNewVariant(page, id);
    await waitEditor(page);
    const sidebar = page.locator('aside[aria-label="Font"]');
    const list = sidebar.getByRole("group", { name: "Variants", exact: true });
    const comparisonStyle = (input: HTMLElement): Record<string, string> => {
      const style = getComputedStyle(input);
      return {
        border: style.borderWidth,
        radius: style.borderRadius,
        height: style.height,
        background: style.backgroundColor,
        shadow: style.boxShadow,
        padding: style.padding,
      };
    };
    const variantTextStyle = await sidebar.locator("[data-specimen-list-text]").evaluate(comparisonStyle);
    assert.equal(await sidebar.locator('[data-slot="card"]').first().getByRole("heading").textContent(), "Variants");
    assert.equal(await list.locator('[aria-current="page"]').getAttribute("data-variant-link"), first);
    const mainText = await page.locator("[data-text]").inputValue();
    await sidebar.getByRole("textbox", { name: "Sample text", exact: true }).fill("Zz 99");
    assert.equal(
      await page.locator("[data-text]").inputValue(),
      mainText,
      "comparison text does not edit the saved specimen",
    );
    await page.locator("[data-variant-name]").fill("First variant");
    await page.locator("[data-size-px]").fill("32");
    await sidebar.getByRole("button", { name: "Add variant", exact: true }).click();
    await page.waitForFunction(
      (previous) =>
        document.querySelector("[data-variant-editor]")?.getAttribute("data-variant-editor") !== previous &&
        document.querySelector("[data-variant-name]") !== null,
      first,
    );
    await waitEditor(page);
    const second = (await list.locator('[aria-current="page"]').getAttribute("data-variant-link"))!;
    assert.notEqual(second, first);
    assert.equal(await list.getByRole("link").count(), 2);
    await page.waitForFunction(() => {
      const canvases = [...document.querySelectorAll("aside [data-library-variant-canvas]")];
      return (
        canvases.length === 2 &&
        canvases.every(
          (canvas) =>
            canvas.getAttribute("data-rendered") === "true" &&
            JSON.parse(canvas.getAttribute("data-render-key") || "{}").text === "Zz 99",
        )
      );
    });
    assert.equal(
      await sidebar.getByRole("textbox", { name: "Sample text", exact: true }).inputValue(),
      "Zz 99",
      "comparison text survives switching",
    );
    assert.notEqual(await page.locator("[data-size-px]").inputValue(), "32", "Add starts from font defaults");
    await list.locator(`[data-variant-link="${first}"]`).focus();
    await page.keyboard.press("Enter");
    await waitEditor(page);
    assert.equal(await page.locator("[data-variant-name]").inputValue(), "First variant");
    assert.equal(await page.locator("[data-size-px]").inputValue(), "32", "latest edits survive immediate switching");
    assert.match(await list.locator(`[data-library-variant-caption="${first}"]`).innerText(), /^32 px/);
    await list.locator(`[data-delete-variant="${second}"]`).click();
    await list.locator(`[data-variant-link="${second}"]`).waitFor({ state: "detached" });
    assert.equal(
      await hashPath(page),
      `/font/${id}/variant/${first}/`,
      "deleting an inactive variant keeps the current editor",
    );
    await sidebar.getByRole("button", { name: "Add variant", exact: true }).click();
    await page.waitForFunction(
      (previous) =>
        document.querySelector("[data-variant-editor]")?.getAttribute("data-variant-editor") !== previous &&
        document.querySelector("[data-variant-name]") !== null,
      first,
    );
    await waitEditor(page);
    await list.locator('[aria-current="page"]').waitFor();
    const third = (await list.locator('[aria-current="page"]').getAttribute("data-variant-link"))!;
    await list.locator(`[data-delete-variant="${third}"]`).click();
    await page.waitForFunction(
      (expected) =>
        location.pathname.includes(`/variant/${expected}/`) && document.querySelector("[data-variant-name]") !== null,
      first,
    );
    await waitEditor(page);
    assert.equal(
      await page.locator("[data-variant-name]").inputValue(),
      "First variant",
      "deleting the active variant selects another saved variant",
    );
    await list.locator(`[data-delete-variant="${first}"]`).click();
    await page.locator("[data-font-card]").first().waitFor();
    assert.equal(await hashPath(page), "/fonts/", "deleting the last variant returns to Fonts");
    assert.deepEqual(await cardVariantIds(page, id), []);
    await page.getByRole("link", { name: "Palettes", exact: true }).click();
    assert.deepEqual(
      await page.locator("[data-specimen-list-text]").evaluate(comparisonStyle),
      variantTextStyle,
      "shared comparison fields keep identical styling on both pages",
    );
  },
);

test(
  "saved variant page uses the studio layout with every control reachable",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 600 } });
    const page = await context.newPage();
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    await openNewVariant(page, id);
    await waitEditor(page);

    assert.match(
      await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).innerText(),
      /^Glypherie$/i,
    );
    assert.equal(
      await page.locator("[data-site-header] [data-all-fonts]").count(),
      0,
      "duplicate back link is removed",
    );
    assert.equal(await page.getByRole("link", { name: "Glypherie", exact: true }).count(), 1);
    const mainControls = page.getByRole("group", { name: "Variant controls", exact: true });
    assert.equal(await mainControls.getByRole("textbox", { name: "Name", exact: true }).count(), 1);
    for (const heading of ["Preview", "Rendering & spacing", "Rendering", "Spacing"]) {
      assert.ok(
        (await page
          .locator('.family [aria-label="Variant controls"]')
          .getByRole("heading", { name: heading })
          .count()) >= 1,
        `right pane shows ${heading}`,
      );
    }
    const previewGroup = mainControls.getByRole("group", { name: "Preview", exact: true });
    assert.equal(await previewGroup.locator("[data-text]").count(), 1, "sample controls belong to the preview");
    assert.equal(
      await previewGroup.locator("[data-variant-paper] .interactive-canvas").count(),
      1,
      "the rendered specimen shares the preview card with its controls",
    );
    assert.equal(
      await mainControls.locator(':scope > [data-slot="card"]').count(),
      5,
      "the main panel has Name, Preview, Rendering & spacing, Export (Playdate) and License cards",
    );
    assert.equal(await mainControls.getByRole("heading", { name: "License", exact: true }).count(), 1);
    for (const heading of ["Variants", "Font", "Axes"]) {
      assert.equal(
        await page.locator('aside[aria-label="Font"]').getByRole("heading", { name: heading }).count(),
        1,
        `left sidebar shows ${heading}`,
      );
    }
    for (const control of [
      "[data-variant-name]",
      "[data-text]",
      "[data-size-px]",
      "#output-mode",
      "[data-kerning]",
      "#zoom",
    ]) {
      assert.equal(await page.locator(control).count(), 1, `${control} stays reachable`);
    }
    await page.locator("#output-mode").scrollIntoViewIfNeeded();
    assert.ok(await page.locator("#output-mode").isVisible(), "output mode stays usable inside the scrolling pane");
    assert.equal(await page.locator("[data-spacing]").count(), 1, "the Layout section offers extra tracking");
    assert.equal(
      await page.locator('label[for^="spacing-"]').textContent(),
      "Tracking (px)",
      "tracking control carries its saved-layout label",
    );
    assert.ok((await page.locator("[data-axis]").count()) >= 1, "variable axes stay reachable");
    assert.equal(
      await page.getByRole("group", { name: "Palette", exact: true }).count(),
      1,
      "the fixed palette stays visible",
    );
    assert.equal(await page.locator("[data-variant-paper]").count(), 1, "paper frame wraps the specimen");
    assert.equal(
      await page.locator("[data-variant-paper] .interactive-canvas").count(),
      1,
      "native canvas paints inside the frame",
    );
    assert.match(
      (await page.locator("[data-variant-paper]").innerText()) ?? "",
      /\d+ px \/ \d-bit/,
      "paper caption shows size and bit depth",
    );

    await page.locator("[data-size-px]").fill("28");
    await waitSaved(page);
    await page.reload();
    await waitEditor(page);
    assert.equal(await page.locator("[data-size-px]").inputValue(), "28", "sidebar edits autosave across reload");
    assert.match(
      await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).innerText(),
      /^Glypherie$/i,
      "studio chrome survives reload",
    );

    const desktopLayout = await page.evaluate(() => ({
      height: window.innerHeight,
      document: document.documentElement.scrollHeight,
      boxes: [".variant-studio", "main", 'aside[aria-label="Font"]', ".family", "[data-site-header]"].map(
        (selector) => {
          const element = document.querySelector(selector) as HTMLElement;
          const rect = element.getBoundingClientRect();
          return {
            selector,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
            height: rect.height,
            scroll: element.scrollHeight,
            overflow: getComputedStyle(element).overflowY,
          };
        },
      ),
    }));
    assert.ok(
      desktopLayout.document <= desktopLayout.height,
      `a short desktop page never scrolls: ${JSON.stringify(desktopLayout)}`,
    );
    const [, , inputs, preview] = desktopLayout.boxes;
    assert.ok(inputs!.right <= preview!.left, "font inputs stay left of the preview pane");
    assert.equal(await page.locator("main aside").count(), 1, "only the left pane is a sidebar");
    assert.equal(await page.locator("main > div > *").count(), 2, "the editor has exactly two panes");
    const controlsPane = page.locator(".family");
    assert.ok(
      await controlsPane.evaluate((element) => element.scrollHeight > element.clientHeight),
      "the controls pane scrolls when short",
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await waitEditor(page);
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      "no overflow on mobile",
    );
    await page.locator("[data-variant-name]").scrollIntoViewIfNeeded();
    assert.ok(await page.locator("[data-variant-name]").isVisible(), "controls stay reachable on mobile");
    await context.close();
  },
);

async function specimenDigest(page: Page): Promise<{ hash: number; ink: number }> {
  return page.evaluate(() => {
    const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
    if (!canvas || canvas.width === 0) return { hash: 0, ink: 0 };
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable.");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let hash = 0x811c9dc5;
    let ink = 0;
    for (let i = 0; i < data.length; i += 1) {
      hash ^= data[i]!;
      hash = Math.imul(hash, 0x01000193);
      if (i % 4 !== 3 && data[i] !== 255) ink += 1;
    }
    return { hash: hash >>> 0, ink };
  });
}

async function waitForDigestChange(page: Page, before: number): Promise<void> {
  await page.waitForFunction(
    (previous) => {
      const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
      if (!canvas || canvas.width === 0) return false;
      const context = canvas.getContext("2d");
      if (!context) return false;
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let hash = 0x811c9dc5;
      for (let i = 0; i < data.length; i += 1) {
        hash ^= data[i]!;
        hash = Math.imul(hash, 0x01000193);
      }
      return hash >>> 0 !== previous;
    },
    before,
    { timeout: 20000 },
  );
}

async function waitForDigestValue(page: Page, expected: number): Promise<void> {
  await page.waitForFunction(
    (target) => {
      const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
      if (!canvas || canvas.width === 0) return false;
      const context = canvas.getContext("2d");
      if (!context) return false;
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let hash = 0x811c9dc5;
      for (let i = 0; i < data.length; i += 1) {
        hash ^= data[i]!;
        hash = Math.imul(hash, 0x01000193);
      }
      return hash >>> 0 === target;
    },
    expected,
    { timeout: 20000 },
  );
}

test(
  "extra tracking persists, survives profile changes, and stays layout-only",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootLibrary(page, url);
    const { id } = await flexId(page);
    const variantId = await openNewVariant(page, id);
    await waitEditor(page);
    await waitSaved(page);

    assert.equal(await page.locator("[data-spacing]").inputValue(), "0", "new variants start at neutral tracking");
    await page.locator("[data-text]").fill("Ag");
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    const neutral = await specimenDigest(page);
    assert.ok(neutral.ink > 0, "the short specimen paints before tracking changes");

    await setRange(page, "[data-spacing]", "2");
    await waitSaved(page);
    assert.equal(await page.locator("[data-spacing-number]").inputValue(), "2");
    await waitForDigestChange(page, neutral.hash);
    const tracked = await specimenDigest(page);
    assert.notDeepEqual(tracked.hash, neutral.hash, "positive tracking shifts laid-out pixels");
    assert.equal(tracked.ink, neutral.ink, "tracking moves advances without repainting glyph bitmaps");

    const editorUrl = page.url();
    await createPalettePreset(page, url, { name: "Tracking gray", bits: 3 });
    await page.goto(editorUrl, { waitUntil: "domcontentloaded" });
    await waitEditor(page);
    await selectPalettePreset(page, "Tracking gray");
    await waitSaved(page);
    assert.equal(await page.locator("[data-spacing-number]").inputValue(), "2", "profile edits keep tracking");
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-spacing-number]").inputValue(), "2", "tracking persists across reload");
    assert.equal(await page.locator("[data-output-palette] [data-palette-name]").textContent(), "Tracking gray");

    await selectPalettePreset(page, "Monochrome");
    await waitSaved(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    const wide = await specimenDigest(page);
    await setRange(page, "[data-spacing]", "-2");
    await waitSaved(page);
    assert.equal(await page.locator("[data-spacing-number]").inputValue(), "-2");
    await waitForDigestChange(page, wide.hash);
    const negative = await specimenDigest(page);
    assert.notDeepEqual(negative.hash, neutral.hash, "negative tracking shifts laid-out pixels");
    assert.equal(negative.ink, neutral.ink, "tightening keeps every ink texel on one unwrapped line");
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitEditor(page);
    assert.equal(await page.locator("[data-spacing-number]").inputValue(), "-2", "negative tracking persists");

    await page.locator('[data-primary-nav="fonts"]').click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    await page.waitForFunction(
      (target) =>
        document.querySelector(`[data-library-variant-canvas="${target}"]`)?.hasAttribute("data-render-key") ?? false,
      variantId,
      { timeout: 20000 },
    );
    const libraryKey = JSON.parse(
      (await page.locator(`[data-library-variant-canvas="${variantId}"]`).getAttribute("data-render-key"))!,
    );
    assert.equal(libraryKey.spacing, -2, "the saved library variant still forwards tracking");
    assert.equal(libraryKey.text, "Ag", "the library preview keeps the saved sample");

    await page.locator(`[data-variant-link="${variantId}"]`).click();
    await waitEditor(page);
    await setRange(page, "[data-spacing]", "0");
    await waitSaved(page);
    await waitForDigestValue(page, neutral.hash);
    assert.deepEqual(await specimenDigest(page), neutral, "zero tracking restores the exact neutral bitmap");
  },
);
