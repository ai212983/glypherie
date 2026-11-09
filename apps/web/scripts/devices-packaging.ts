// Build-time guard for device catalog profiles and shell artwork.
//
// The app validates the catalog at startup, but a production build would
// otherwise succeed with missing or raster-contaminated shells and only fail
// at runtime. This guard runs on every production build (never during dev)
// using the owning catalog validator, so broken device assets reject the
// build. Fault-injection tests point the guard at disposable fixture copies
// through FONT_DEVICE_CATALOG / FONT_DEVICE_SHELLS; the live files stay
// untouched.
import { promises as fs } from "node:fs";
import path from "node:path";
import { loadDeviceCatalog } from "../src/app/devices/catalog.ts";

export interface DeviceAssetSources {
  catalogFile?: string;
  shellsDir?: string;
}

// Disposable-fixture overrides for fault-injection builds; production uses
// the shipped catalog and public shells.
export function resolveDeviceAssetSources(
  webRoot: string,
  env: Record<string, string | undefined> = process.env,
): { catalogFile: string; shellsDir: string } {
  return {
    catalogFile: env.FONT_DEVICE_CATALOG ?? path.join(webRoot, "src", "app", "devices", "devices.json"),
    shellsDir: env.FONT_DEVICE_SHELLS ?? path.join(webRoot, "public", "devices", "shells"),
  };
}

// Shared vector-only artwork rule (single owner; the packaging test reuses
// it): shell SVGs must be SVG markup with no raster, image, or linked
// content. Returns the violation reason, or null when the artwork is clean.
export function vectorSvgViolation(body: string): string | null {
  if (!body.includes("<svg")) return "is not SVG artwork";
  const links = body.replace('xmlns="http://www.w3.org/2000/svg"', "");
  if (/<image[\s>/]/i.test(links)) return "embeds raster <image> content";
  if (/\.png|\.jpe?g|data:image|https?:\/\//i.test(links)) return "links raster or remote content";
  return null;
}

export async function validateDeviceAssets(
  webRoot: string,
  options: DeviceAssetSources = {},
): Promise<{ devices: number }> {
  const sources = { ...resolveDeviceAssetSources(webRoot), ...options };
  let catalogText: string;
  try {
    catalogText = await fs.readFile(sources.catalogFile, "utf8");
  } catch {
    throw new Error(`device catalog guard: missing catalog at ${sources.catalogFile}.`);
  }
  let catalog: ReturnType<typeof loadDeviceCatalog>;
  try {
    catalog = loadDeviceCatalog(JSON.parse(catalogText) as unknown);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error ?? "");
    throw new Error(`device catalog guard: invalid catalog at ${sources.catalogFile}: ${reason}`);
  }
  for (const device of catalog.devices) {
    // Shell src is validator-checked relative `shells/*.svg`; basename keeps
    // the read inside the shells directory.
    const file = path.join(sources.shellsDir, path.basename(device.shell.src));
    let body: string;
    try {
      body = await fs.readFile(file, "utf8");
    } catch {
      throw new Error(
        `device catalog guard: ${device.id} shell ${device.shell.src} is missing from ${sources.shellsDir}.`,
      );
    }
    const violation = vectorSvgViolation(body);
    if (violation !== null) {
      throw new Error(`device catalog guard: ${device.id} shell ${device.shell.src} ${violation}.`);
    }
  }
  return { devices: catalog.devices.length };
}

/** Vite plugin: enforce the guard on every production build, never during dev. */
export function devicePackagingPlugin(webRoot: string): { name: string; buildStart(): Promise<void> } {
  return {
    name: "device-packaging-guard",
    async buildStart() {
      await validateDeviceAssets(webRoot);
    },
  };
}
