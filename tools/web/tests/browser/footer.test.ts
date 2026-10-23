import assert from "node:assert/strict";
import test from "node:test";
import { bootLibrary, browserAvailable, buildApp, cardIds, launch, openNewVariant, servePrefix, tooltipText } from "../helpers/spa-helpers.ts";

test("footer stays visible across pages, exposes build details and fits small screens", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, permissions: ["clipboard-read", "clipboard-write"] });
  t.after(() => context.close());
  const page = await context.newPage();
  await bootLibrary(page, url);
  const footer = page.getByRole("contentinfo");
  assert.equal(await footer.getByRole("img", { name: "Online", exact: true }).count(), 0);
  assert.equal(await footer.locator("[data-connection]").count(), 0, "production hides the online indicator");
  assert.equal(await footer.locator(".site-footer__development").count(), 0, "production renders no dev HMR UI");
  assert.equal(await footer.locator("[data-hmr-status]").count(), 0);
  assert.match(await footer.locator("[data-app-version]").innerText(), /^0\.1\.0(?:-dev)?$/);
  await context.setOffline(true);
  const offline = footer.getByRole("img", { name: "Offline", exact: true });
  await offline.waitFor();
  assert.equal(await offline.getAttribute("title"), null);
  assert.match(await tooltipText(page, offline), /still work on this device/);
  await context.setOffline(false);
  await offline.waitFor({ state: "detached" });
  assert.match((await footer.locator("time").textContent()) ?? "", /^\d{6}-\d{4}$/);
  assert.match(await footer.locator("summary").innerText(), /^Build \d{6}-\d{4}$/);
  const geometry = await footer.evaluate((element) => ({
    bottom: element.getBoundingClientRect().bottom,
    viewport: window.innerHeight,
    height: element.getBoundingClientRect().height,
  }));
  assert.equal(geometry.bottom, geometry.viewport);
  assert.equal(geometry.height, 36);
  assert.equal(await footer.getByText("Glypherie", { exact: true }).count(), 0);
  await footer.getByRole("button", { name: /^Version .*: check for updates$/ }).click();
  await footer.locator('[data-update-state="current"]').waitFor();
  assert.equal(await footer.locator('.site-footer__updates > [role="status"]').innerText(), "Up to date");
  const success = footer.locator("[data-update-success]");
  await success.waitFor({ state: "visible" });
  assert.equal(await success.innerText(), "Up to date");
  assert.equal(await success.evaluate((element) => element.previousElementSibling?.matches(".site-footer__details")), true);
  const successBox = await success.boundingBox();
  const buildBox = await footer.locator("summary").boundingBox();
  assert.ok(successBox && buildBox && successBox.x >= buildBox.x + buildBox.width && successBox.y === buildBox.y, "success appears inline after the build");
  await success.waitFor({ state: "hidden", timeout: 6000 });
  await footer.getByRole("button", { name: /^Version .*: check for updates$/ }).click();
  await success.waitFor({ state: "visible" });
  await success.waitFor({ state: "hidden", timeout: 6000 });
  await footer.locator("summary").click();
  await footer.getByRole("button", { name: "Copy build info" }).click();
  await footer.getByRole("status").filter({ hasText: "Copied." }).waitFor();
  assert.match(await page.evaluate(() => navigator.clipboard.readText()), /Glypherie 0\.1\.0.*\nBuild \d{6}-\d{4} UTC/);
  const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  const shown = await footer.locator(".site-footer__info").evaluate((info) => {
    const labels = [...info.querySelectorAll("dt")];
    const at = (label: string): string | null => {
      const dt = labels.find((candidate) => candidate.textContent === label);
      return dt?.nextElementSibling?.textContent ?? null;
    };
    return { commit: at("Commit"), renderer: at("Renderer") };
  });
  const commitFull = /Commit: (.+)/.exec(clipboardText)?.[1] ?? "";
  if (commitFull === "unavailable") {
    assert.equal(shown.commit, "Unavailable");
  } else {
    assert.equal(shown.commit?.length, 12);
    assert.ok(commitFull.startsWith(shown.commit ?? ""));
  }
  const rendererFull = /Renderer SHA-256: (.+)/.exec(clipboardText)?.[1] ?? "";
  if (rendererFull === "unavailable") {
    assert.equal(shown.renderer, "Unavailable");
  } else {
    assert.equal(rendererFull.length, 64);
    assert.equal(shown.renderer?.length, 12);
    assert.ok(rendererFull.startsWith(shown.renderer ?? ""));
  }
  assert.equal(await footer.locator(".site-footer__info").isVisible(), true, "inside interactions keep build info open");
  await page.locator("#main").click({ position: { x: 5, y: 5 } });
  await footer.locator(".site-footer__info").waitFor({ state: "hidden" });
  await footer.locator("summary").click();
  await footer.locator(".site-footer__info").waitFor({ state: "visible" });
  await page.evaluate(() => {
    const stopper = (event: Event): void => event.stopPropagation();
    (window as unknown as { __captureProbe?: (event: Event) => void }).__captureProbe = stopper;
    document.querySelector("#main")?.addEventListener("pointerdown", stopper);
  });
  try {
    await page.locator("#main").click({ position: { x: 5, y: 5 } });
    await footer.locator(".site-footer__info").waitFor({ state: "hidden" });
  } finally {
    await page.evaluate(() => {
      const holder = window as unknown as { __captureProbe?: (event: Event) => void };
      const probe = holder.__captureProbe;
      if (probe) document.querySelector("#main")?.removeEventListener("pointerdown", probe);
      delete holder.__captureProbe;
    });
  }
  await footer.locator("summary").click();
  await page.keyboard.press("Escape");
  await footer.locator(".site-footer__info").waitFor({ state: "hidden" });
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  assert.equal((await footer.boundingBox())?.y, 864);
  await page.goto(`${url}#/palettes/`);
  await page.locator("#main").waitFor();
  assert.equal((await footer.boundingBox())?.y, 864);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(url);
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await footer.scrollIntoViewIfNeeded();
  assert.equal(await footer.isVisible(), true);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await footer.locator("summary").click();
  const info = await footer.locator(".site-footer__info").boundingBox();
  assert.ok(info && info.x >= 0 && info.x + info.width <= 375, "build details fit mobile width");
});
