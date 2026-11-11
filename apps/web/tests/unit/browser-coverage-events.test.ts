// Coverage joins pages it did not create: pre-existing pages and the
// context "page" events behind popups and target=_blank links (the
// variants-suite popup path). Fakes mirror installed Playwright: the event
// fires for every page including newPage-created ones, and stopJSCoverage on
// a page without coverage returns [] instead of throwing.
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import type { BrowserContext } from "playwright-core";

interface FakePage {
  url: () => string;
  coverage: {
    startJSCoverage: () => Promise<void>;
    stopJSCoverage: () => Promise<Array<{ url: string; source: string; functions: unknown[] }>>;
  };
  close: () => Promise<void>;
  startCalls: number;
  stopCalls: number;
}

function scriptEntry(url: string) {
  const sourceMap = { version: 3, sources: ["src/app.ts"], names: [], mappings: "AAAA" };
  return {
    url,
    source: `const value = 1;\n//# sourceMappingURL=data:application/json;base64,${Buffer.from(
      JSON.stringify(sourceMap),
    ).toString("base64")}`,
    functions: [],
  };
}

function makePage(url: string, stop: FakePage["coverage"]["stopJSCoverage"]): FakePage {
  const page: FakePage = {
    url: () => url,
    coverage: {
      startJSCoverage: async () => {
        page.startCalls += 1;
      },
      stopJSCoverage: async () => {
        page.stopCalls += 1;
        return stop();
      },
    },
    close: async () => undefined,
    startCalls: 0,
    stopCalls: 0,
  };
  return page;
}

interface FakeContext {
  handlers: Map<string, Array<(page: FakePage) => void>>;
  livePages: FakePage[];
  newPage: () => Promise<FakePage>;
  close: () => Promise<void>;
  emitPage: (page: FakePage) => void;
}

function makeContext(pages: FakePage[] = []): FakeContext {
  const context: FakeContext = {
    handlers: new Map(),
    livePages: [...pages],
    newPage: async () => {
      throw new Error("not used");
    },
    close: async () => undefined,
    emitPage: (page) => {
      context.livePages.push(page);
      for (const handler of context.handlers.get("page") ?? []) handler(page);
    },
  };
  return context;
}

function asContext(fake: FakeContext): BrowserContext {
  return {
    pages: () => [...fake.livePages],
    on: (event: string, handler: (page: FakePage) => void) => {
      const list = fake.handlers.get(event) ?? [];
      list.push(handler);
      fake.handlers.set(event, list);
    },
    newPage: fake.newPage,
    close: fake.close,
  } as unknown as BrowserContext;
}

test("coverage joins event-created and pre-existing pages", async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-coverage-events-"));
  const previous = process.env.GLYPHERIE_COVERAGE_DIR;
  process.env.GLYPHERIE_COVERAGE_DIR = dir;
  t.after(async () => {
    if (previous === undefined) delete process.env.GLYPHERIE_COVERAGE_DIR;
    else process.env.GLYPHERIE_COVERAGE_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  });
  // One import: the helper captures the directory at module initialization.
  const { registerCoverageBuild, trackBrowserCoverage, trackContextCoverage } =
    await import("../helpers/browser-coverage.ts");
  registerCoverageBuild("http://app.test", path.join(dir, "app"), "/preview/");

  await t.test("newPage and close both wait for event-started coverage", async () => {
    let releaseStart!: () => void;
    const started = new Promise<void>((resolve) => {
      releaseStart = resolve;
    });
    const context = makeContext();
    const page = makePage("http://app.test/preview/app.js", async () => [
      scriptEntry("http://app.test/preview/app.js"),
    ]);
    page.coverage.startJSCoverage = async () => {
      page.startCalls += 1;
      await started;
    };
    context.newPage = async () => {
      context.emitPage(page);
      return page;
    };
    const tracked = asContext(context);
    trackContextCoverage(tracked);
    let returned = false;
    const opening = tracked.newPage().then(() => {
      returned = true;
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    const closing = page.close();
    await new Promise<void>((resolve) => setImmediate(resolve));
    try {
      assert.equal(returned, false, "newPage waits for the start admitted by the page event");
      assert.equal(page.stopCalls, 0, "close cannot collect before startup completes");
    } finally {
      releaseStart();
      await Promise.all([opening, closing]);
    }
    assert.equal(page.startCalls, 1);
    assert.equal(page.stopCalls, 1);
  });

  await t.test("context close awaits a pending startup failure record", async () => {
    const before = new Set(await fs.readdir(dir));
    let rejectStart!: (error: Error) => void;
    const start = new Promise<void>((_resolve, reject) => {
      rejectStart = reject;
    });
    const page = makePage("http://app.test/preview/app.js", async () => []);
    page.coverage.startJSCoverage = () => start;
    const context = makeContext([page]);
    const tracked = asContext(context);
    trackContextCoverage(tracked);
    let closed = false;
    const closing = tracked.close().then(() => {
      closed = true;
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    try {
      assert.equal(closed, false);
    } finally {
      rejectStart(new Error("startup failed"));
      await closing;
    }
    assert.equal(page.stopCalls, 0);
    const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
    assert.equal(written.filter((name) => name.startsWith("failed-")).length, 1);
  });

  await t.test("overlapping page and context closes join the complete collection", async () => {
    const before = new Set(await fs.readdir(dir));
    let releaseStop!: () => void;
    const stopped = new Promise<void>((resolve) => {
      releaseStop = resolve;
    });
    const page = makePage("http://app.test/preview/app.js", async () => {
      await stopped;
      return [scriptEntry("http://app.test/preview/app.js")];
    });
    let pageClosed = false;
    page.close = async () => {
      pageClosed = true;
    };
    const context = makeContext([page]);
    const tracked = asContext(context);
    trackContextCoverage(tracked);
    const closing = Promise.all([page.close(), page.close(), tracked.close()]);
    await new Promise<void>((resolve) => setImmediate(resolve));
    try {
      assert.equal(page.stopCalls, 1);
      assert.equal(pageClosed, false);
    } finally {
      releaseStop();
      await closing;
    }
    const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
    assert.equal(written.filter((name) => name.startsWith("v8-")).length, 1);
  });

  await t.test("event-created pages start collection synchronously and flush on page close", async () => {
    const before = new Set(await fs.readdir(dir));
    const context = makeContext();
    trackContextCoverage(asContext(context));
    const page = makePage("http://app.test/preview/app.js", async () => [
      scriptEntry("http://app.test/preview/app.js"),
    ]);
    context.emitPage(page);
    assert.equal(page.startCalls, 1, "the page event starts collection before navigation settles");
    await page.close();
    assert.equal(page.stopCalls, 1);
    const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
    assert.equal(written.filter((name) => name.startsWith("v8-")).length, 1);
    assert.equal(written.filter((name) => name.startsWith("failed-")).length, 0);
  });

  await t.test("pre-existing pages join tracking and flush once on context close", async () => {
    const before = new Set(await fs.readdir(dir));
    const page = makePage("http://app.test/preview/app.js", async () => [
      scriptEntry("http://app.test/preview/app.js"),
    ]);
    const context = makeContext([page]);
    const tracked = asContext(context);
    trackContextCoverage(tracked);
    assert.equal(page.startCalls, 1, "pages that predate tracking still start collection");
    await tracked.close();
    await tracked.close();
    assert.equal(page.stopCalls, 1, "repeated closes flush exactly once");
    const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
    assert.equal(written.filter((name) => name.startsWith("v8-")).length, 1);
    assert.equal(written.filter((name) => name.startsWith("failed-")).length, 0);
  });

  await t.test("an empty stop writes nothing and records no failure", async () => {
    const before = new Set(await fs.readdir(dir));
    const context = makeContext();
    trackContextCoverage(asContext(context));
    // Installed Playwright returns [] for a page without coverage data.
    const page = makePage("http://app.test/preview/app.js", async () => []);
    context.emitPage(page);
    await page.close();
    assert.equal(page.stopCalls, 1);
    assert.deepEqual(
      (await fs.readdir(dir)).filter((name) => !before.has(name)),
      [],
    );
  });

  await t.test("a failed start is recorded without throwing into the page event", async () => {
    const before = new Set(await fs.readdir(dir));
    const context = makeContext();
    trackContextCoverage(asContext(context));
    const page = makePage("http://app.test/preview/app.js", async () => []);
    page.coverage.startJSCoverage = async () => {
      page.startCalls += 1;
      throw new Error("JSCoverage is already enabled");
    };
    context.emitPage(page);
    await new Promise((resolve) => setTimeout(resolve, 20));
    await page.close();
    const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
    assert.equal(written.filter((name) => name.startsWith("failed-")).length, 1);
    assert.equal(written.filter((name) => name.startsWith("v8-")).length, 0);
  });

  await t.test("browser tracking joins pre-existing contexts and their pages", async () => {
    const context = makeContext([
      makePage("http://app.test/preview/app.js", async () => [scriptEntry("http://app.test/preview/app.js")]),
    ]);
    const browser = {
      contexts: () => [asContext(context)] as unknown as BrowserContext[],
      newPage: async () => {
        throw new Error("not used");
      },
      newContext: async () => asContext(makeContext()),
      close: async () => undefined,
    };
    // A stub hook context: the real t.after flush would run after this
    // test's temp dir is removed.
    trackBrowserCoverage({ after: () => undefined } as never, browser as never);
    assert.equal(context.livePages[0]!.startCalls, 1);
  });
});
