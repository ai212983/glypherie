// Device packaging guard: validator matrix over disposable fixtures (the
// production-build tests prove the pipeline wiring; these pin the reasons).
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  resolveDeviceAssetSources,
  validateDeviceAssets,
  vectorSvgViolation,
} from "../../scripts/devices-packaging.ts";
import { webRoot } from "../helpers/spa-helpers.ts";

async function stage(
  mutate: (fixtures: { catalogFile: string; shellsDir: string }) => Promise<void> | void,
): Promise<{ catalogFile: string; shellsDir: string; cleanup: () => Promise<void> }> {
  const staged = await fs.mkdtemp(path.join(os.tmpdir(), "font-devices-unit-"));
  const catalogFile = path.join(staged, "devices.json");
  const shellsDir = path.join(staged, "shells");
  await fs.mkdir(shellsDir, { recursive: true });
  await fs.copyFile(path.join(webRoot, "src", "app", "devices", "devices.json"), catalogFile);
  for (const name of await fs.readdir(path.join(webRoot, "public", "devices", "shells"))) {
    await fs.copyFile(path.join(webRoot, "public", "devices", "shells", name), path.join(shellsDir, name));
  }
  await mutate({ catalogFile, shellsDir });
  return { catalogFile, shellsDir, cleanup: () => fs.rm(staged, { recursive: true, force: true }) };
}

test("shipped device assets validate clean", async () => {
  const fixtures = await stage(() => {});
  try {
    assert.deepEqual(await validateDeviceAssets(webRoot, fixtures), { devices: 6 });
  } finally {
    await fixtures.cleanup();
  }
});

test("guard names the broken device asset", async () => {
  const cases: Array<{ name: string; mutate: (fixtures: { catalogFile: string; shellsDir: string }) => Promise<void>; match: RegExp }> = [
    {
      name: "missing catalog",
      mutate: async ({ catalogFile }) => {
        await fs.rm(catalogFile);
      },
      match: /missing catalog/,
    },
    {
      name: "unparseable catalog",
      mutate: async ({ catalogFile }) => {
        await fs.writeFile(catalogFile, "{broken");
      },
      match: /invalid catalog/,
    },
    {
      name: "invalid profile",
      mutate: async ({ catalogFile }) => {
        const catalog = JSON.parse(await fs.readFile(catalogFile, "utf8")) as {
          devices: Array<Record<string, unknown>>;
        };
        catalog.devices[0]!.widthPx = 0;
        await fs.writeFile(catalogFile, JSON.stringify(catalog));
      },
      match: /invalid catalog.*widthPx/,
    },
    {
      name: "missing shell",
      mutate: async ({ shellsDir }) => {
        await fs.rm(path.join(shellsDir, "xteink-x4.svg"));
      },
      match: /xteink-x4.*missing/,
    },
    {
      name: "raster shell",
      mutate: async ({ shellsDir }) => {
        const shell = path.join(shellsDir, "xteink-x3.svg");
        await fs.writeFile(shell, `${await fs.readFile(shell, "utf8")}<image href="scan.png"/>`);
      },
      match: /xteink-x3.*raster/,
    },
    {
      name: "remote-linked shell",
      mutate: async ({ shellsDir }) => {
        const shell = path.join(shellsDir, "playdate.svg");
        await fs.writeFile(shell, `${await fs.readFile(shell, "utf8")}<!-- https://example.com/shell -->`);
      },
      match: /playdate.*remote/,
    },
    {
      name: "non-svg shell",
      mutate: async ({ shellsDir }) => {
        await fs.writeFile(path.join(shellsDir, "playdate.svg"), "not artwork");
      },
      match: /playdate.*not SVG/,
    },
  ];
  for (const { name, mutate, match } of cases) {
    const fixtures = await stage(mutate);
    try {
      await assert.rejects(validateDeviceAssets(webRoot, fixtures), match, name);
    } finally {
      await fixtures.cleanup();
    }
  }
});

test("vector-only rule ignores the svg namespace but nothing else", () => {
  assert.equal(vectorSvgViolation('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'), null);
  assert.match(vectorSvgViolation("<svg><image href=\"x.png\"/></svg>") ?? "", /raster/);
  assert.match(vectorSvgViolation("<svg><use href=\"https://example.com/a.svg\"/></svg>") ?? "", /remote/);
  assert.match(vectorSvgViolation("plain text") ?? "", /not SVG/);
});

test("asset sources default to shipped paths with fixture overrides", () => {
  const defaults = resolveDeviceAssetSources(webRoot, {});
  assert.equal(defaults.catalogFile, path.join(webRoot, "src", "app", "devices", "devices.json"));
  assert.equal(defaults.shellsDir, path.join(webRoot, "public", "devices", "shells"));
  const overridden = resolveDeviceAssetSources(webRoot, {
    FONT_DEVICE_CATALOG: "/tmp/catalog.json",
    FONT_DEVICE_SHELLS: "/tmp/shells",
  });
  assert.equal(overridden.catalogFile, "/tmp/catalog.json");
  assert.equal(overridden.shellsDir, "/tmp/shells");
});
