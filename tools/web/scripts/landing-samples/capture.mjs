// Sources: https://pdfontconv.frozenfractal.com/main.js
//          https://kaasiand.cool/tophat/tophat.js
import { chromium } from "../../node_modules/playwright-core/index.mjs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createHash } from "node:crypto";

const [directory, font, settingsFile] = process.argv.slice(2);
const settings = JSON.parse(await readFile(settingsFile, "utf8"));
const ascii = Array.from({ length: 95 }, (_, i) => String.fromCharCode(i + 32)).join("");
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const browser = await chromium.launch({ headless: true, ...(process.env.WEB_TEST_BROWSER ? { executablePath: process.env.WEB_TEST_BROWSER } : {}) });
const result = { captured_at: new Date().toISOString(), browser: browser.version(), platform: `${os.platform()} ${os.release()} ${os.arch()}`, font_sha256: hash(await readFile(font)), samples: {}, sources: [] };
async function download(page, selector, destination) {
  const next = page.waitForEvent("download");
  await page.locator(selector).click();
  const item = await next;
  if (await item.failure()) throw new Error(await item.failure());
  await item.saveAs(destination);
}
try {
  for (const tool of ["pdfontconv", "tophat"]) {
    console.log(`Capturing ${tool}…`);
    const dir = path.join(directory, tool);
    await mkdir(path.join(dir, "sources"), { recursive: true });
    const context = await browser.newContext({ deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.setDefaultTimeout(60000);
    const errors = [];
    const pending = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("response", response => {
      if (!["document", "script", "stylesheet"].includes(response.request().resourceType()) || !response.ok()) return;
      pending.push((async () => {
        const bytes = await response.body();
        const file = `${hash(bytes)}.source`;
        await writeFile(path.join(dir, "sources", file), bytes);
        result.sources.push({ url: response.url(), file: `${tool}/sources/${file}`, sha256: hash(bytes) });
      })().catch(error => { errors.push(`Source capture: ${error.message}`); }));
    });
    let metadata;
    if (tool === "pdfontconv") {
      await page.goto("https://pdfontconv.frozenfractal.com/");
      await page.locator("#fontFileInput").setInputFiles(font);
      await page.waitForFunction(() => input.fontDataBytes?.length > 0);
      for (const [selector, value] of [["#fontSizeInput", settings.size_px], ["#opacityThresholdInput", settings.threshold], ["#charSetTextarea", ascii]]) {
        await page.locator(selector).fill(String(value));
        await page.locator(selector).dispatchEvent("change");
      }
      // The stock upload handler reads bytes asynchronously. A setting change
      // persists those bytes; reload then awaits creation of the actual FontFace.
      await page.reload();
      await page.waitForFunction(size => +input.fontSize === size && fontData.charSet.length === 95 && [...document.fonts].some(face => face.family === "pdfontconv" && face.status === "loaded"), settings.size_px);
      metadata = await page.evaluate(() => {
        const c = fontCanvas.getContext("2d");
        c.font = getCssFont();
        return { baseline: Math.max(...fontData.charSet.map(ch => Math.ceil(c.measureText(ch).actualBoundingBoxAscent))), threshold: +input.opacityThreshold, cell_width: fontData.cellSizeX, cell_height: fontData.cellSizeY, offset_x: fontData.offsetX };
      });
      for (const prefix of ["font", "repeat"]) {
        await page.locator("#fontSizeInput").dispatchEvent("change");
        await download(page, "#downloadFntButton", path.join(dir, `${prefix}.fnt`));
        await download(page, "#downloadPngButton", path.join(dir, `${prefix}.png`));
      }
    } else {
      await page.goto("https://kaasiand.cool/tophat/");
      await page.waitForFunction(() => typeof opentype !== "undefined");
      for (const prefix of ["font", "repeat"]) {
        if (prefix === "repeat") {
          await page.evaluate(() => openNewFontModal());
          await page.locator("#ttfpick").setInputFiles([]);
        }
        await page.locator("#ttfpick").setInputFiles(font);
        await page.locator("#importfontmodal").waitFor({ state: "visible" });
        await page.locator("#importfontmodal_size_px").check();
        for (const [selector, value] of [["#fontimportkeepglyph", ascii], ["#alphathresh", 255 - settings.threshold], ["#importfontmodal_size", settings.size_px]]) {
          if (selector === "#alphathresh") {
            await page.locator(selector).evaluate((element, value) => { element.value = String(value); }, value);
          } else {
            await page.locator(selector).fill(String(value));
          }
          await page.locator(selector).dispatchEvent("input");
          await page.locator(selector).dispatchEvent("change");
        }
        metadata = await page.evaluate(() => ({ baseline: uploadedFontB, threshold: 255 - +alphathresh.value, cell_width: uploadedFontW, cell_height: uploadedFontH, version: document.querySelector("[data-ver]")?.dataset.ver }));
        await page.locator("#importfontmodal button").filter({ hasText: /^Import font$/ }).click();
        await download(page, "#exportbtn", path.join(dir, `${prefix}.fnt`));
      }
    }
    metadata.loaded_font_faces = await page.evaluate(() => [...document.fonts].map(face => ({ family: face.family, status: face.status })));
    const glyphs = await page.evaluate(tool => {
      const result = {};
      for (let code = 32; code <= 126; code++) {
        const ch = String.fromCharCode(code);
        if (tool === "pdfontconv") {
          const i = fontData.charSet.indexOf(ch), w = fontData.cellSizeX, h = fontData.cellSizeY;
          const cols = fontCanvas.width / w;
          const data = fontCanvas.getContext("2d").getImageData(i % cols * w, Math.floor(i / cols) * h, w, h).data;
          result[ch] = { alpha: Array.from(data).filter((_, i) => i % 4 === 3), advance: fontData.widths[i] + fontData.tracking };
        } else {
          result[ch] = { alpha: Array.from(glyphBitmaps[ch].data).filter((_, i) => i % 4 === 3), advance: advanceWidth[ch] + settings.tracking };
        }
      }
      return result;
    }, tool);
    await writeFile(path.join(dir, "memory.json"), JSON.stringify(glyphs));
    await Promise.all(pending);
    metadata.errors = errors;
    if (errors.length) throw new Error(`${tool}: ${errors.join("; ")}`);
    if (!metadata.loaded_font_faces.length || metadata.loaded_font_faces.some(face => face.status !== "loaded")) throw new Error(`${tool}: font did not load`);
    if (metadata.threshold !== settings.threshold) throw new Error(`${tool}: threshold differs from request`);
    result.samples[tool] = metadata;
    await context.close();
  }
  await writeFile(path.join(directory, "browser.json"), JSON.stringify(result, null, 2) + "\n");
} finally {
  await browser.close();
}
