import assert from "node:assert/strict";
import test from "node:test";
import { createNavigationOwner } from "../../src/app/navigation/navigation-owner.ts";
import type { StoredFont } from "../../src/app/fonts/storage.ts";

interface HistoryCall {
  kind: "push" | "replace";
  url: string;
}

function storedFont(id: string, family: string): StoredFont {
  return {
    id,
    name: family,
    fileName: `${family}.ttf`,
    bytes: new ArrayBuffer(8),
    metadata: { names: { family }, axes: [] },
    source: "bundled",
    addedAt: 0,
  };
}

function installWindow(
  pathname: string,
  search = "",
  hash = "",
): {
  calls: HistoryCall[];
  setLocation: (next: string) => void;
  restore: () => void;
} {
  const calls: HistoryCall[] = [];
  const store = new Map<string, string>();
  const location = {
    pathname,
    search,
    hash,
    get href(): string {
      return `http://test${location.pathname}${location.search}${location.hash}`;
    },
  };
  const applyUrl = (url: string): void => {
    const parsed = new URL(url, "http://test/");
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
  };
  const listeners = new Map<string, Set<() => void>>();
  const fakeWindow = {
    location,
    history: {
      state: null as unknown,
      pushState: (_state: unknown, _title: string, url: string): void => {
        calls.push({ kind: "push", url });
        applyUrl(url);
      },
      replaceState: (_state: unknown, _title: string, url: string): void => {
        calls.push({ kind: "replace", url });
        applyUrl(url);
      },
    },
    localStorage: {
      getItem: (key: string): string | null => store.get(key) ?? null,
      setItem: (key: string, value: string): void => void store.set(key, String(value)),
    },
    addEventListener: (type: string, listener: () => void): void => {
      const set = listeners.get(type) ?? new Set<() => void>();
      set.add(listener);
      listeners.set(type, set);
    },
    removeEventListener: (type: string, listener: () => void): void => {
      listeners.get(type)?.delete(listener);
    },
  };
  const previous = (globalThis as Record<string, unknown>).window;
  (globalThis as Record<string, unknown>).window = fakeWindow;
  return {
    calls,
    setLocation: applyUrl,
    restore: () => {
      (globalThis as Record<string, unknown>).window = previous;
    },
  };
}

const tick = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

test("a patch followed by a real transition cannot resurrect the old route", async (t) => {
  const env = installWindow("/font/alpha/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  owner.setCatalog([storedFont("alpha", "Alpha"), storedFont("beta", "Beta")]);
  assert.equal(owner.getSnapshot().page?.name, "preview");
  const writes = env.calls.length;
  owner.onPatch({ profile: "gray_2bit" });
  assert.equal(owner.getSnapshot().snapshot?.profile, "gray_2bit");
  owner.openIndex();
  assert.equal(owner.getSnapshot().page?.name, "index");
  const afterTransition = env.calls.length;
  assert.ok(afterTransition > writes);
  await tick(350);
  assert.equal(env.calls.length, afterTransition);
  t.after(() => owner.dispose());
});

test("successive patch intents resolve to the latest snapshot and URL", async (t) => {
  const env = installWindow("/font/alpha/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  owner.setCatalog([storedFont("alpha", "Alpha")]);
  owner.onPatch({ profile: "gray_2bit" });
  owner.onPatch({ profile: "gray_3bit" }, true);
  assert.equal(owner.getSnapshot().snapshot?.profile, "gray_3bit");
  const last = env.calls[env.calls.length - 1]!;
  assert.equal(last.kind, "replace");
  assert.match(last.url, /gray_3bit/);
  const settled = env.calls.length;
  await tick(350);
  assert.equal(env.calls.length, settled);
  t.after(() => owner.dispose());
});

test("a font requested while the catalog is pending resolves on arrival", (t) => {
  const env = installWindow("/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog(null);
  assert.equal(owner.getSnapshot().page?.name, "home");
  owner.openScreen();
  assert.equal(owner.getSnapshot().page?.name, "screen");
  env.setLocation("/font/alpha/");
  owner.handleHistoryChange();
  assert.equal(owner.getSnapshot().page?.name, "screen");
  const seen: Array<string | null> = [];
  const stop = owner.subscribe(() => {
    const page = owner.getSnapshot().page;
    seen.push(page === null ? null : page.name);
  });
  owner.setCatalog([storedFont("alpha", "Alpha"), storedFont("beta", "Beta")]);
  assert.deepEqual(owner.getSnapshot().page, { name: "preview", font: "alpha" });
  assert.equal(owner.getSnapshot().snapshot?.font, "alpha");
  assert.ok(seen.includes("preview"));
  stop();
});

test("an explicit transition supersedes a deferred request before the catalog arrives", (t) => {
  const env = installWindow("/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog(null);
  env.setLocation("/font/alpha/");
  owner.handleHistoryChange();
  assert.equal(owner.getSnapshot().page?.name, "home");
  owner.openScreen();
  assert.equal(owner.getSnapshot().page?.name, "screen");
  owner.setCatalog([storedFont("alpha", "Alpha")]);
  assert.equal(owner.getSnapshot().page?.name, "screen");
});

test("boot consumes a deferred font route before catalog refresh can replay it", (t) => {
  const env = installWindow("/font/alpha/", "?v=1&profile=mono_1bit");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog(null);
  env.setLocation("/font/beta/?v=1&profile=mono_1bit");
  owner.handleHistoryChange();
  owner.setCatalog(null);
  assert.equal(owner.getSnapshot().page, null);
  const catalog = [storedFont("alpha", "Alpha"), storedFont("beta", "Beta")];
  owner.setCatalog(catalog);
  assert.deepEqual(owner.getSnapshot().page, { name: "preview", font: "beta" });
  owner.onPatch({ profile: "gray_2bit" });
  const writes = env.calls.length;
  owner.setCatalog([...catalog]);
  assert.equal(owner.getSnapshot().snapshot?.profile, "gray_2bit");
  assert.equal(env.calls.length, writes, "a catalog refresh never replays the boot location");
});

test("repeated pending catalog updates keep the deferred request waiting", (t) => {
  const env = installWindow("/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog(null);
  env.setLocation("/font/alpha/");
  owner.handleHistoryChange();
  assert.equal(owner.getSnapshot().page?.name, "home");
  owner.setCatalog(null);
  assert.equal(owner.getSnapshot().page?.name, "home");
  owner.setCatalog([storedFont("alpha", "Alpha")]);
  assert.deepEqual(owner.getSnapshot().page, { name: "preview", font: "alpha" });
});

test("removing the active preview font retargets through the owner", (t) => {
  const env = installWindow("/font/alpha/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog([storedFont("alpha", "Alpha"), storedFont("beta", "Beta")]);
  const next = owner.removePreviewFont("alpha");
  assert.equal(next?.font, "beta");
  assert.equal(owner.getSnapshot().snapshot?.font, "beta");
  assert.ok(!("alpha" in (owner.getSnapshot().snapshot?.families ?? {})));
});

test("removing the last preview font leaves an empty selection", (t) => {
  const env = installWindow("/font/alpha/");
  t.after(env.restore);
  const owner = createNavigationOwner();
  t.after(() => owner.dispose());
  owner.setCatalog([storedFont("alpha", "Alpha")]);
  const next = owner.removePreviewFont("alpha");
  assert.equal(next?.font, "");
  assert.deepEqual(owner.getSnapshot().snapshot?.families, {});
});
