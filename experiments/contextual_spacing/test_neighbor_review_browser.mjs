// Mechanical verification of optional configured neighboring placements.
// No server, optical solver, fitting or full-table Playwright transport.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
if (!process.argv[2]) throw new Error("usage: node test_neighbor_review_browser.mjs PAGE.html [PAGE-DATA.json]");
const file = resolve(process.argv[2]);
const evidence = JSON.parse(
  await readFile(resolve(process.argv[3] || resolve(dirname(file), "page-data.json")), "utf8"),
);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 }, offline: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(file).href);
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  await page.locator("#neighbor-review[data-state=ready]").waitFor();
  await page.evaluate(() => {
    globalThis.__neighborData =
      globalThis.__inlineSpacingData || JSON.parse(document.getElementById("spacing-data").textContent);
  });
  const ids = await page.evaluate(() => globalThis.__neighborData.cases.map((font) => font.id));
  const fixtures = (evidence.neighborReviewVerification || []).filter((fixture) => ids.includes(fixture.caseId));
  assert.ok(fixtures.length, "authoritative Python fixtures are required");
  let parity = 0;
  for (let start = 0; start < fixtures.length; start += 50) {
    parity += await page.evaluate(
      (batch) => {
        const canonical = (value) =>
          JSON.stringify(value, (_key, entry) =>
            entry && !Array.isArray(entry) && typeof entry === "object"
              ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b)))
              : entry,
          );
        const data = globalThis.__neighborData,
          config = data.neighborReview;
        for (const fixture of batch) {
          const font = data.cases.find((font) => font.id === fixture.caseId);
          const width = fixture.width ?? null,
            letter = fixture.letterSpacing || 0,
            word = fixture.wordSpacing || 0;
          const current = ContextualSpacing.layout(
            font,
            fixture.text,
            fixture.kIndex,
            fixture.oIndex,
            letter,
            word,
            width,
            fixture.preserveTabularSpacing,
            config.spacingModel,
          );
          const snapshot = canonical(current),
            neighbor =
              width === null
                ? ContextualSpacing.neighborLayout(current, config.pairs, config.deltaPx)
                : ContextualSpacing.neighborTextLayout(
                    font,
                    fixture.text,
                    fixture.kIndex,
                    fixture.oIndex,
                    width,
                    fixture.preserveTabularSpacing,
                    config.spacingModel,
                    config.pairs,
                    config.deltaPx,
                    letter,
                    word,
                  );
          if (
            canonical(current) !== canonical(fixture.expectedCurrent) ||
            canonical(neighbor) !== canonical(fixture.expectedNeighbor)
          )
            throw new Error(`Python neighbor parity failed: ${font.label}, ${fixture.text}`);
          if (canonical(current) !== snapshot) throw new Error("Neighbor helper mutated completed positions");
          const indices = new Map(font.codepoints.map((cp, index) => [cp, index])),
            glyphs = new Map(font.glyphs.map((g) => [g.codepoint, g]));
          const table = (
            fixture.preserveTabularSpacing
              ? font.models[config.spacingModel].preservedPairTables
              : font.models[config.spacingModel].pairTables
          )[fixture.kIndex * 5 + fixture.oIndex];
          for (const line of neighbor.lines) {
            if (line.placements.length && line.placements[0].x_px !== 0)
              throw new Error("Neighbor shift crossed a line break");
            for (let index = 1; index < line.placements.length; index++) {
              const a = line.placements[index - 1],
                b = line.placements[index],
                selected = config.pairs.includes(String.fromCodePoint(a.codepoint, b.codepoint));
              const expected =
                a.advance_px +
                table[indices.get(a.codepoint) * font.codepoints.length + indices.get(b.codepoint)] +
                (a.codepoint !== 32 && b.codepoint !== 32 ? ContextualSpacing.pixelRound(letter) : 0) +
                (selected ? config.deltaPx : 0);
              if (b.x_px - a.x_px !== expected)
                throw new Error("Unselected pair step changed during independent wrapping");
            }
          }
        }
        return batch.length;
      },
      fixtures.slice(start, start + 50),
    );
  }
  const verifyRows = async () => {
    await page.locator("#neighbor-review[data-state=ready]").waitFor();
    return page.evaluate(() => {
      const data = globalThis.__neighborData,
        config = data.neighborReview,
        byId = (id) => document.getElementById(id),
        font = data.cases[Number(byId("family").value)];
      const k = Number(byId("kerning").value),
        o = Number(byId("optical").value),
        zoom = Number(byId("zoom").value),
        preserve = byId("preserve-tabular").checked,
        overlay = byId("neighbor-review-contacts").checked;
      const textMode = config.mode === "text",
        width = textMode ? Number(byId("wrap").value) : null,
        letter = textMode ? Number(byId("letter").value) : 0,
        word = textMode ? Number(byId("word").value) : 0;
      const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph])),
        model = font.models[config.spacingModel],
        policy = model.calibration.clearance_policy;
      const cells = (bitmap, origin) =>
        bitmap.pixels.flatMap((ink, index) =>
          ink ? [[origin + bitmap.left + (index % bitmap.width), bitmap.top + Math.floor(index / bitmap.width)]] : [],
        );
      const oracleCache = new Map();
      const oracle = (positions) => {
        const counts = { overlaps: 0, faces: 0, corners: 0 },
          rank = { corners: 1, faces: 2, overlaps: 3 };
        const contactsByLine = positions.lines.map((line) => {
          const marked = new Map();
          for (let index = 1; index < line.placements.length; index++) {
            const a = line.placements[index - 1],
              b = line.placements[index],
              step = b.x_px - a.x_px,
              key = `${a.codepoint},${b.codepoint},${step}`;
            if (!oracleCache.has(key)) {
              const points = new Set(cells(glyphs.get(b.codepoint).bitmap, step).map(([x, y]) => `${x},${y}`)),
                local = { overlaps: 0, faces: 0, corners: 0, pixels: [] },
                pixels = new Map();
              for (const [x, y] of cells(glyphs.get(a.codepoint).bitmap, 0))
                for (let dy = -1; dy <= 1; dy++)
                  for (let dx = -1; dx <= 1; dx++) {
                    if (!points.has(`${x + dx},${y + dy}`)) continue;
                    const kind = !dx && !dy ? "overlaps" : !dx || !dy ? "faces" : "corners";
                    local[kind]++;
                    for (const [px, py] of [
                      [x, y],
                      [x + dx, y + dy],
                    ]) {
                      const pk = `${px},${py}`;
                      if (!pixels.has(pk) || rank[kind] > rank[pixels.get(pk).kind])
                        pixels.set(pk, { x: px, y: py, kind });
                    }
                  }
              local.pixels = [...pixels.values()];
              oracleCache.set(key, local);
            }
            const contact = oracleCache.get(key);
            for (const key of ["overlaps", "faces", "corners"]) counts[key] += contact[key];
            for (const p of contact.pixels) {
              const value = { ...p, x: p.x + a.x_px },
                pk = `${value.x},${value.y}`;
              if (!marked.has(pk) || rank[p.kind] > rank[marked.get(pk).kind]) marked.set(pk, value);
            }
          }
          return { pixels: [...marked.values()] };
        });
        return { ...counts, contactsByLine };
      };
      const rows = [...document.querySelectorAll(".neighbor-review-row")],
        expectedTexts = textMode ? [byId("sample").value] : [...config.pairs, ...config.words];
      if (rows.length !== expectedTexts.length) throw new Error("Missing review rows");
      const results = [];
      rows.forEach((row, index) => {
        const text = row.dataset.text;
        if (text !== expectedTexts[index]) throw new Error("Review text/order changed");
        const current = ContextualSpacing.layout(font, text, k, o, letter, word, width, preserve, config.spacingModel);
        const neighbor = textMode
          ? ContextualSpacing.neighborTextLayout(
              font,
              text,
              k,
              o,
              width,
              preserve,
              config.spacingModel,
              config.pairs,
              config.deltaPx,
              letter,
              word,
            )
          : ContextualSpacing.neighborLayout(current, config.pairs, config.deltaPx);
        for (const [variant, positions] of [
          ["current", current],
          ["neighbor", neighbor],
        ]) {
          const cell = row.querySelector(`[data-variant=${variant}]`),
            contacts = oracle(positions);
          for (const key of ["overlaps", "faces", "corners"])
            if (Number(cell.dataset[key]) !== contacts[key])
              throw new Error("Contact counts disagree with brute-force bitmap oracle");
          const disposition = contacts.overlaps
            ? "forbidden_overlap"
            : contacts.faces || contacts.corners
              ? policy === "no_overlap"
                ? "allowed_contact"
                : "forbidden_contact"
              : "separated";
          if (cell.dataset.disposition !== disposition || cell.dataset.policy !== policy)
            throw new Error("Wrong diagnostic contact policy");
          for (const [scale, factor] of [
            ["native", 1],
            ["zoom", zoom],
          ]) {
            const expected = document.createElement("canvas");
            ContextualSpacing.paint(expected, font, positions, factor, scale === "zoom" && overlay ? contacts : null);
            const actual = cell.querySelector(`canvas[data-scale=${scale}]`);
            if (
              expected.toDataURL() !== actual.toDataURL() ||
              expected.style.width !== actual.style.width ||
              expected.style.height !== actual.style.height
            )
              throw new Error(`Wrong review bitmap/zoom: ${font.label}, ${text}, ${variant}, ${scale}`);
            if (scale === "zoom" && overlay) {
              let minX = 0,
                top = -Math.ceil(font.metricsAscent || font.sizePx),
                bottom = Math.ceil(-(font.metricsDescent || 0));
              for (const line of positions.lines) {
                minX = Math.min(minX, line.width_px);
                for (const item of line.placements) {
                  const b = glyphs.get(item.codepoint).bitmap;
                  minX = Math.min(minX, item.x_px + b.left);
                  top = Math.min(top, b.top);
                  bottom = Math.max(bottom, b.top + b.height);
                }
              }
              minX = Math.floor(minX);
              const lineStep = Math.max(1, bottom - top + Math.max(2, Math.ceil(font.metricsLineGap || 0))),
                wanted = new Set();
              contacts.contactsByLine.forEach((line, row) =>
                line.pixels.forEach((p) => wanted.add(`${p.x - minX},${row * lineStep + p.y - top}`)),
              );
              const rgba = actual.getContext("2d").getImageData(0, 0, actual.width, actual.height).data,
                found = new Set();
              for (let i = 0; i < rgba.length; i += 4)
                if (rgba[i] !== rgba[i + 1] || rgba[i + 1] !== rgba[i + 2])
                  found.add(`${(i / 4) % actual.width},${Math.floor(i / 4 / actual.width)}`);
              if (found.size !== wanted.size || [...wanted].some((p) => !found.has(p)))
                throw new Error("Multiline contact markers use the wrong baseline or cross a line break");
            }
          }
          if (row.dataset.kind === "pair") {
            const cps = Array.from(text).map((character) => character.codePointAt(0)),
              pairIndex = font.codepoints.indexOf(cps[0]) * font.codepoints.length + font.codepoints.indexOf(cps[1]);
            const minimum = (preserve ? model.preservedPairTargetMetadata : model.pairTargetMetadata)[pairIndex]
              .clearance_min_step_px;
            const step = positions.lines[0].placements[1].x_px - positions.lines[0].placements[0].x_px;
            if (
              Number(cell.dataset.step) !== step ||
              cell.dataset.feasible !== (minimum == null ? "" : String(step >= minimum))
            )
              throw new Error("Neighbor was clamped or bound came from another model");
            if (
              variant === "neighbor" &&
              step !== current.lines[0].placements[1].x_px - current.lines[0].placements[0].x_px + config.deltaPx
            )
              throw new Error("Neighbor pair was not shifted exactly");
          }
          results.push({
            font: font.label,
            text,
            variant,
            ...Object.fromEntries(["overlaps", "faces", "corners"].map((key) => [key, contacts[key]])),
            disposition,
          });
        }
        const browser = row.querySelector("[data-variant=browser]"),
          native = browser.querySelector("[data-scale=native]"),
          enlarged = browser.querySelector("[data-scale=zoom]");
        const style = getComputedStyle(native);
        if (browser.dataset.state !== "ready" || !document.fonts.check(`${font.sizePx}px ${style.fontFamily}`))
          throw new Error("Browser reference font is not loaded");
        if (
          native.textContent !== text ||
          enlarged.textContent !== text ||
          style.fontSize !== `${font.sizePx}px` ||
          getComputedStyle(enlarged).fontSize !== style.fontSize
        )
          throw new Error("Browser text resized before layout");
        if (
          native.style.fontVariationSettings !== document.getElementById("browser-native").style.fontVariationSettings
        )
          throw new Error("Browser reference axes differ");
        if (
          style.fontKerning !== "auto" ||
          style.fontOpticalSizing !== "none" ||
          style.fontFeatureSettings !== "normal" ||
          style.whiteSpace !== (textMode ? "pre-wrap" : "pre") ||
          native.style.letterSpacing !== "normal" ||
          native.style.wordSpacing !== "normal"
        )
          throw new Error("Browser reference uses custom layout controls");
        if (
          textMode &&
          (native.style.width !== `${width}px` ||
            enlarged.style.width !== `${width}px` ||
            style.overflowWrap !== "break-word")
        )
          throw new Error("Browser full text is not independently wrapped at selected width");
        const transform = getComputedStyle(enlarged).transform;
        if (transform !== `matrix(${zoom}, 0, 0, ${zoom}, 0, 0)`)
          throw new Error("Browser enlargement is not post-layout scaling");
      });
      return results;
    });
  };
  const mainSnapshot = () =>
    page.evaluate(() => ({
      canvases: Object.fromEntries(
        [...document.querySelectorAll(".comparisons canvas, .reference-comparisons canvas")].map((canvas) => [
          canvas.id,
          canvas.toDataURL(),
        ]),
      ),
      browserText: document.getElementById("browser-native").textContent,
      browserStyle: document.getElementById("browser-native").getAttribute("style"),
    }));
  const fonts = await page.getByLabel("Captured font").locator("option").count();
  const textMode = await page.evaluate(() => globalThis.__neighborData.neighborReview.mode === "text");
  let rowChecks = 0;
  const diagnostics = [],
    presetChecks = [],
    scrollChecks = [];
  const checkScroll = async () => {
    const report = await page.evaluate(async () => {
      const groups = Object.fromEntries(
        ["native", "zoom"].map((scale) => [
          scale,
          [...document.querySelectorAll(`#neighbor-review [data-neighbor-scroll=${scale}]`)],
        ]),
      );
      const results = [];
      for (const scale of ["native", "zoom"]) {
        const frames = groups[scale],
          other = groups[scale === "native" ? "zoom" : "native"];
        const before = other.map((frame) => ({ top: frame.scrollTop, left: frame.scrollLeft }));
        if (frames.length !== 3) throw new Error("Missing three-way scroll group");
        const source = frames[0],
          extent = source.scrollHeight - source.clientHeight;
        if (extent <= 0) throw new Error("Scroll test text does not fill the viewport");
        source.scrollTop = extent * 0.43;
        source.scrollLeft = scale === "zoom" ? 20 : 0;
        source.dispatchEvent(new Event("scroll"));
        await new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const ratio = source.scrollTop / extent;
        for (const frame of frames)
          if (Math.abs(frame.scrollTop - ratio * (frame.scrollHeight - frame.clientHeight)) > 2)
            throw new Error("Vertical scroll ratios diverged");
        for (const frame of frames)
          if (Math.abs(frame.scrollLeft - Math.min(source.scrollLeft, frame.scrollWidth - frame.clientWidth)) > 1)
            throw new Error("Horizontal scroll positions diverged");
        if (
          other.some((frame, index) => frame.scrollTop !== before[index].top || frame.scrollLeft !== before[index].left)
        )
          throw new Error("Native scroll leaked into zoom group");
        results.push({ scale, ratio, frames: frames.length });
      }
      return results;
    });
    scrollChecks.push(...report);
  };
  if (textMode) {
    assert.equal(
      await page.locator("#neighbor-review-contacts").isChecked(),
      false,
      "Whole-text contact markers default off",
    );
    assert.match(await page.locator("#neighbor-review header h2").textContent(), /complete texts/i);
    for (let index = 0; index < fonts; index++) {
      await page.getByLabel("Captured font").selectOption(String(index));
      await page.getByRole("button", { name: "Reset controls" }).click();
      await page.locator("#neighbor-review-contacts").uncheck();
      const presets = await page.evaluate(() =>
        globalThis.__neighborData.presets.map(({ id, text }) => ({ id, text })),
      );
      for (const preset of presets) {
        await page.getByLabel("Text preset").selectOption(preset.id);
        assert.equal(await page.getByLabel("Sample text").inputValue(), preset.text);
        assert.equal(
          await page.getByLabel("Text preset").inputValue(),
          preset.id,
          "Named preset is retained even when it is the default text",
        );
        const result = await verifyRows();
        rowChecks += result.length;
        diagnostics.push(...result);
        assert.equal(await page.getByRole("alert").isVisible(), false);
        presetChecks.push({ font: index, preset: preset.id });
      }
      await page.getByLabel("Sample text").fill("lynx nx hx mx\nauxiliary kx xn\nlynx lynx");
      await page.locator("#wrap").fill("160");
      for (const [k, o, preserve] of [
        [4, 4, false],
        [0, 4, false],
        [2, 3, false],
        [4, 0, false],
        [4, 4, true],
      ]) {
        await page.locator("#kerning").fill(String(k));
        await page.locator("#optical").fill(String(o));
        await page.locator("#preserve-tabular").setChecked(preserve);
        await page.locator("#neighbor-review-contacts").uncheck();
        rowChecks += (await verifyRows()).length;
        const before = await mainSnapshot();
        await page.locator("#neighbor-review-contacts").check();
        rowChecks += (await verifyRows()).length;
        assert.deepEqual(await mainSnapshot(), before, "Contact overlay does not change any main view");
      }
      for (const zoom of ["2", "8", "4"]) {
        await page.getByLabel("Enlargement").selectOption(zoom);
        rowChecks += (await verifyRows()).length;
      }
      const before = await page.locator("#neighbor-review-rows").evaluate((rows) => ({
        ink: [...rows.querySelectorAll("canvas[data-scale=native]")].map((c) => c.toDataURL()),
        browser: [...rows.querySelectorAll("[data-variant=browser] [data-scale]")].map((n) => ({
          text: n.textContent,
          style: n.getAttribute("style"),
        })),
      }));
      await page.getByLabel("Letter spacing (px)").fill("1");
      await page.getByLabel("Word spacing (px)").fill("2");
      await verifyRows();
      const after = await page.locator("#neighbor-review-rows").evaluate((rows) => ({
        ink: [...rows.querySelectorAll("canvas[data-scale=native]")].map((c) => c.toDataURL()),
        browser: [...rows.querySelectorAll("[data-variant=browser] [data-scale]")].map((n) => ({
          text: n.textContent,
          style: n.getAttribute("style"),
        })),
      }));
      assert.notDeepEqual(after.ink, before.ink, "Whole-text bitmap placements follow letter/word controls");
      assert.deepEqual(after.browser, before.browser, "Normal browser reference ignores custom tracking");
      await page.getByRole("button", { name: "Reset controls" }).click();
      await page.getByLabel("Text preset").selectOption(presets[0].id);
      await verifyRows();
      await checkScroll();
    }
  } else {
    for (let index = 0; index < fonts; index++) {
      await page.getByLabel("Captured font").selectOption(String(index));
      for (const [k, o, preserve] of [
        [4, 4, false],
        [0, 4, false],
        [2, 3, false],
        [4, 0, false],
        [4, 4, true],
      ]) {
        await page.locator("#kerning").fill(String(k));
        await page.locator("#optical").fill(String(o));
        await page.locator("#preserve-tabular").setChecked(preserve);
        await page.locator("#neighbor-review-contacts").uncheck();
        const result = await verifyRows();
        rowChecks += result.length;
        diagnostics.push(...result);
        const before = await mainSnapshot();
        await page.locator("#neighbor-review-contacts").check();
        rowChecks += (await verifyRows()).length;
        assert.deepEqual(
          await mainSnapshot(),
          before,
          "Contact overlay does not change main native/zoom/browser reference views",
        );
      }
      for (const zoom of ["2", "8", "4"]) {
        await page.getByLabel("Enlargement").selectOption(zoom);
        rowChecks += (await verifyRows()).length;
      }
      // Main tracking controls deliberately do not change the zero-tracking panel.
      const before = await page
        .locator("#neighbor-review-rows")
        .evaluate((rows) =>
          [...rows.querySelectorAll("canvas[data-scale=native]")].map((canvas) => canvas.toDataURL()),
        );
      await page.getByLabel("Letter spacing (px)").fill("1");
      await page.getByLabel("Word spacing (px)").fill("2");
      await verifyRows();
      assert.deepEqual(
        await page
          .locator("#neighbor-review-rows")
          .evaluate((rows) =>
            [...rows.querySelectorAll("canvas[data-scale=native]")].map((canvas) => canvas.toDataURL()),
          ),
        before,
      );
      await page.getByRole("button", { name: "Reset controls" }).click();
    }
  }
  if (textMode) {
    const selected = await page.getByLabel("Sample text").inputValue();
    await page.getByLabel("Sample text").fill("\u{1F642}");
    assert.equal(await page.getByRole("alert").isVisible(), true);
    assert.equal(
      await page.locator("#neighbor-review").isVisible(),
      false,
      "Invalid editing hides stale full-text comparisons",
    );
    assert.equal(await page.locator("#neighbor-review-rows").locator("article").count(), 0);
    await page.getByLabel("Sample text").fill(selected);
    await verifyRows();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await verifyRows();
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    false,
    "Neighbor panel does not overflow the mobile page",
  );
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    fonts,
    pythonNeighborFixtures: parity,
    rowChecks,
    diagnostics,
    contactsUseActualBitmapCells: true,
    mainViewsUnaffectedByOverlay: true,
    mode: textMode ? "text" : "pairs",
    presetChecks,
    scrollChecks,
    trackingFollowsControls: textMode,
    mobileOverflow: false,
    browserErrors: errors,
  };
  await writeFile(resolve(dirname(file), "neighbor-review-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(
    JSON.stringify({ status: report.status, fonts, pythonNeighborFixtures: parity, rowChecks, browserErrors: errors }),
  );
} finally {
  await browser.close();
}
