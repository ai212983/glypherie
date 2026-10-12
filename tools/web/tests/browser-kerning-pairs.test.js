import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { build, serve, webRoot } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const repoRoot = path.resolve(webRoot, "../..");
const wasmDir = process.env.FONT_WASM_PREVIEW_DIR ?? path.join(repoRoot, "tools/wasm/pkg-web-preview");
const ready = await Promise.all([browserPath, path.join(wasmDir, "font_wasm.js"), path.join(wasmDir, "font_wasm_bg.wasm"), path.join(repoRoot, "out/specimens/published.json")].map(p => fs.access(p).then(() => true, () => false))).then(values => values.every(Boolean));

async function setup(t) {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-kern-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const output = path.join(temp, "web");
  await build(path.join(repoRoot, "out/specimens"), output);
  await fs.mkdir(path.join(output, "assets/wasm"), { recursive: true });
  for (const file of ["font_wasm.js", "font_wasm_bg.wasm"]) await fs.copyFile(path.join(wasmDir, file), path.join(output, "assets/wasm", file));
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  return { browser, url };
}

test("kerning details show real font data, selected coordinates and independent cached family state", { skip: !ready }, async t => {
  const { browser, url } = await setup(t);
  const page = await browser.newPage({viewport:{width:1100,height:900}});
  const errors=[];
  page.on('pageerror', e=>errors.push(e.message));
  await page.route('**/assets/wasm/font_wasm.js*', async route=>{
    const response=await route.fetch();
    const source=await response.text();
    await route.fulfill({response,body:source+`
const nativeKern = Font.prototype.kerning_pairs;
Font.prototype.kerning_pairs = function(size,axes) {
  const data=nativeKern.call(this,size,axes);
  (globalThis.__kernCalls??=[]).push({size,axes:structuredClone(axes),data});
  return data;
};`});
  });
  await page.goto(url,{waitUntil:'networkidle'});
  await page.waitForFunction(()=>!document.querySelector('#interactive-roboto [data-size]').disabled);
  assert.equal(await page.locator('details[data-kerning-details][open]').count(),0);
  assert.equal(await page.evaluate(()=>globalThis.__kernCalls?.length??0),0);
  const report=[];
  for(const id of ['roboto','literata','source-sans-3']) {
    await page.locator('#font-select').selectOption(id);
    await page.waitForFunction(id=>!document.querySelector(`#interactive-${id} [data-size]`).disabled,id);
    const details=page.locator(`[data-kerning-details="${id}"]`);
    await details.locator('summary').focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(id=>document.querySelector(`[data-kerning-details="${id}"] [data-kerning-list] li`),id);
    const call=await page.evaluate(()=>globalThis.__kernCalls.at(-1));
    const wanted=await page.locator(`#interactive-${id}`).evaluate(section=>{
      const axes=JSON.parse(section.dataset.defaultAxes);
      for(const i of section.querySelectorAll('[data-axis]'))axes[i.dataset.axis]=Number(i.value);
      return {size:Number(section.querySelector('[data-size]').value),axes};
    });
    assert.equal(call.size,wanted.size);
    assert.deepEqual(call.axes,wanted.axes);
    const av=call.data.pairs.find(p=>p.left===65&&p.right===86);
    assert.ok(av?.adjustment_26_6<0);
    await details.locator('[data-kerning-filter]').fill('AV');
    const row=details.locator('[data-kerning-list] li').filter({has:page.locator('.pair', {hasText:/^AV$/})});
    assert.equal(await row.count(),1);
    await details.locator('[data-kerning-filter]').fill('zzzz');
    await assert.equal(await details.locator('[data-kerning-list] li').count(),0);
    assert.match(await details.locator('[data-kerning-status]').textContent(),/No pairs match/);
    await details.locator('[data-kerning-filter]').fill('');
    assert.equal(await details.locator('[data-kerning-list] li').count(),call.data.pairs.length);
    report.push({id,size:call.size,axes:call.axes,pairs:call.data.pairs.length,skipped:call.data.skipped_pairs,av:av.adjustment_26_6});
  }
  await page.locator('#font-select').selectOption('roboto');
  const before=await page.evaluate(()=>globalThis.__kernCalls.length);
  await page.locator('#interactive-roboto [data-size]').fill('28');
  await page.waitForFunction(before=>globalThis.__kernCalls.length>before&&globalThis.__kernCalls.at(-1).size===28,before);
  const large=await page.evaluate(()=>globalThis.__kernCalls.at(-1).data.pairs.find(p=>p.left===65&&p.right===86).adjustment_26_6);
  assert.ok(Math.abs(large-2*report[0].av)<=1);
  const calls=await page.evaluate(()=>globalThis.__kernCalls.length);
  await page.locator('#interactive-roboto [data-spacing]').fill('-1');
  await page.locator('#interactive-roboto [data-kerning]').uncheck();
  await page.locator('#zoom').fill('1');
  await page.locator('.profile-options input[value="gray_3bit"]').check();
  await page.waitForTimeout(350);
  assert.equal(await page.evaluate(()=>globalThis.__kernCalls.length),calls);
  await page.locator('#interactive-roboto [data-size]').fill('14');
  await page.waitForTimeout(350);
  assert.equal(await page.evaluate(()=>globalThis.__kernCalls.length),calls,'returning to a cached coordinate avoids extraction');
  await page.locator('#interactive-roboto-wght').fill('535');
  await page.waitForFunction(()=>globalThis.__kernCalls.at(-1).axes.wght===535);
  await page.locator('#interactive-roboto [data-reset]').click();
  await page.waitForFunction(()=>document.querySelector('#interactive-roboto-wght').value==='400');
  await page.waitForTimeout(350);
  await page.locator('[data-kerning-details="roboto"] [data-kerning-filter]').fill('AV');
  const resetAV=page.locator('[data-kerning-details="roboto"] li').filter({has:page.locator('.pair', {hasText:/^AV$/})});
  assert.ok((await resetAV.textContent()).includes(`${report[0].av/64} px`));
  assert.deepEqual(errors,[]);

});

test("kerning details handle empty, unavailable and failed data without breaking rendering", { skip: !ready }, async t => {
  const { browser, url } = await setup(t);
  for (const mode of ["empty", "error", "unavailable"]) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/assets/wasm/font_wasm.js*", async route => {
      const response = await route.fetch();
      const source = await response.text();
      const override = mode === "unavailable"
        ? "delete Font.prototype.kerning_pairs;"
        : mode === "empty"
          ? "Font.prototype.kerning_pairs = () => ({pairs:[], skipped_pairs:0});"
          : "Font.prototype.kerning_pairs = () => {throw new Error('Extraction failed');};";
      await route.fulfill({ response, body: source + "\n" + override });
    });
    await page.goto(url, { waitUntil: "networkidle" });
    const details = page.locator('[data-kerning-details="roboto"]');
    await details.locator("summary").click();
    await page.waitForFunction(() => {
      const text = document.querySelector('[data-kerning-details="roboto"] [data-kerning-status]').textContent;
      return /No nonzero|unavailable|Extraction failed|Reload the page/.test(text);
    });
    assert.equal(await details.locator("li").count(), 0);
    assert.match(await details.locator("[data-kerning-status]").textContent(), mode === "empty" ? /No nonzero/ : mode === "error" ? /Extraction failed/ : /Reload the page/);
    if (mode === "unavailable") {
      // A missing renderer API does not establish absent font kerning:
      // the message names the loaded renderer and the reload fix.
      assert.match(await details.locator("[data-kerning-status]").textContent(), /loaded renderer/i);
      assert.doesNotMatch(await details.locator("[data-kerning-status]").textContent(), /unavailable for this font/);
    }
    await page.waitForFunction(() => document.querySelector('#interactive-roboto canvas').dataset.rendered === "true");
    // Glyph rendering and its controls keep working in every kerning mode.
    assert.equal(await page.locator('#interactive-roboto [data-size]').isEnabled(), true);
    assert.deepEqual(errors, []);
    await page.close();
  }
});
