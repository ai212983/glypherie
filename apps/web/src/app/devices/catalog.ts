// cspell:words TEMPERA RLCD Soldered Waveshare Xteink precached
// Versioned external device catalog: native framebuffer geometry, physical
// density, and vector shell artwork per supported device. Adding a device is
// data/assets work (devices.json plus one SVG); no code switch tables.
// Shell SVGs resolve through Vite-hashed asset URLs, so the hosting prefix
// and the offline service worker apply without extra configuration.
import rawCatalog from "./devices.json" with { type: "json" };

export const DEVICE_CATALOG_VERSION = 1;

export type PpiBasis = "advertised" | "derived";

export interface DeviceShellRef {
  readonly src: string;
  readonly viewBox: readonly [x: number, y: number, w: number, h: number];
  readonly screenRect: readonly [x: number, y: number, w: number, h: number];
}

export interface DeviceDefinition {
  readonly id: string;
  readonly label: string;
  readonly widthPx: number;
  readonly heightPx: number;
  // Physical screen density in device pixels per inch. "advertised" is the
  // vendor's nominal figure; "derived" divides native pixels by a documented
  // active/diagonal size (see docs/devices.md).
  readonly ppi: number;
  readonly ppiBasis: PpiBasis;
  readonly shell: DeviceShellRef;
}

export interface DeviceCatalog {
  readonly version: number;
  readonly devices: readonly DeviceDefinition[];
}

// Shell artwork ships as static SVGs under public/devices/shells/ (copied to
// the build output beneath the hosting prefix and precached offline by the
// service worker's svg glob). No per-device import list to keep in sync.
function assetBase(): string {
  const env = (import.meta as unknown as { env?: { BASE_URL?: unknown } }).env;
  const base = typeof env?.BASE_URL === "string" ? env.BASE_URL : "/";
  return base.endsWith("/") ? base : `${base}/`;
}

function fail(message: string): never {
  throw new Error(`Invalid device catalog: ${message}.`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function checkId(id: unknown): string {
  if (typeof id !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) {
    fail(`device id ${JSON.stringify(id)} must be a stable kebab-case slug`);
  }
  return id;
}

function checkLabel(label: unknown): string {
  if (typeof label !== "string" || label.length === 0 || label.length > 80) {
    fail("device label must be non-empty text within 80 characters");
  }
  return label;
}

function checkPixels(value: unknown, name: string): number {
  if (!Number.isInteger(value) || (value as number) < 1 || (value as number) > 4096) {
    fail(`${name} must be an integer within 1..4096`);
  }
  return value as number;
}

function checkPpi(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value > 2000) {
    fail("ppi must be a finite positive density");
  }
  return value;
}

function checkBox(value: unknown, name: string): readonly [number, number, number, number] {
  if (
    !Array.isArray(value) ||
    value.length !== 4 ||
    value.some((entry) => typeof entry !== "number" || !Number.isFinite(entry))
  ) {
    fail(`${name} must be four finite numbers [x, y, w, h]`);
  }
  const [x, y, w, h] = value as [number, number, number, number];
  if (w <= 0 || h <= 0) fail(`${name} must have a positive area`);
  return [x, y, w, h];
}

function checkShell(value: unknown): DeviceShellRef {
  if (!isRecord(value)) fail("device shell must be an object");
  const src = value.src;
  if (
    typeof src !== "string" ||
    src.startsWith("/") ||
    src.includes("..") ||
    !src.startsWith("shells/") ||
    !src.endsWith(".svg")
  ) {
    fail(`shell src ${JSON.stringify(src)} must be a relative shells/*.svg asset path`);
  }
  const viewBox = checkBox(value.viewBox, "shell viewBox");
  const screenRect = checkBox(value.screenRect, "shell screenRect");
  const [, , vw, vh] = viewBox;
  const [sx, sy, sw, sh] = screenRect;
  if (sx < viewBox[0] || sy < viewBox[1] || sx + sw > viewBox[0] + vw || sy + sh > viewBox[1] + vh) {
    fail("shell screenRect must sit inside the viewBox");
  }
  return { src, viewBox, screenRect };
}

function checkDevice(value: unknown): DeviceDefinition {
  if (!isRecord(value)) fail("device entries must be objects");
  const id = checkId(value.id);
  const label = checkLabel(value.label);
  const widthPx = checkPixels(value.widthPx, "widthPx");
  const heightPx = checkPixels(value.heightPx, "heightPx");
  const ppi = checkPpi(value.ppi);
  if (value.ppiBasis !== "advertised" && value.ppiBasis !== "derived") {
    fail(`device ${id} ppiBasis must be "advertised" or "derived"`);
  }
  const shell = checkShell(value.shell);
  // The aperture must reproduce the native aspect exactly; the screen render
  // fills it without distortion.
  const expected = widthPx / heightPx;
  const actual = shell.screenRect[2] / shell.screenRect[3];
  if (Math.abs(actual - expected) / expected > 1e-6) {
    fail(`device ${id} screenRect aspect must match ${widthPx}x${heightPx}`);
  }
  return Object.freeze({ id, label, widthPx, heightPx, ppi, ppiBasis: value.ppiBasis, shell });
}

export function loadDeviceCatalog(data: unknown): DeviceCatalog {
  if (!isRecord(data)) fail("expected a catalog object");
  if (data.version !== DEVICE_CATALOG_VERSION) {
    fail(`expected version ${DEVICE_CATALOG_VERSION}`);
  }
  if (!Array.isArray(data.devices) || data.devices.length === 0) {
    fail("devices must be a non-empty array");
  }
  const devices = data.devices.map(checkDevice);
  const ids = new Set<string>();
  for (const device of devices) {
    if (ids.has(device.id)) fail(`duplicate device id ${device.id}`);
    ids.add(device.id);
  }
  return Object.freeze({ version: DEVICE_CATALOG_VERSION, devices: Object.freeze(devices) });
}

// Validated shipped catalog; malformed bundled data fails fast at startup.
export const DEVICE_CATALOG: DeviceCatalog = loadDeviceCatalog(rawCatalog);

export function deviceById(catalog: DeviceCatalog, id: unknown): DeviceDefinition | null {
  if (typeof id !== "string") return null;
  return catalog.devices.find((device) => device.id === id) ?? null;
}

// Public shell URL for a validated catalog entry, resolved beneath the
// hosting prefix. Missing shipped artwork surfaces in the build packaging
// test and the browser shell-load test, not behind a second registry.
export function shellUrl(device: DeviceDefinition): string {
  return `${assetBase()}devices/${device.shell.src}`;
}

export interface DeviceLayout {
  // SVG element size in CSS px.
  readonly svgWidth: number;
  readonly svgHeight: number;
  // Screen canvas placement and size in CSS px within the SVG element.
  readonly screenX: number;
  readonly screenY: number;
  readonly screenWidth: number;
  readonly screenHeight: number;
}

// CSS geometry for one device at cssScale CSS px per device pixel: the shell
// and the screen aperture scale together from the aperture.
export function deviceLayout(device: DeviceDefinition, cssScale: number): DeviceLayout {
  const scale = Number(cssScale);
  if (!Number.isFinite(scale) || scale <= 0) fail("cssScale must be a positive number");
  const [, , vw, vh] = device.shell.viewBox;
  const [sx, sy, sw] = device.shell.screenRect;
  const unit = (device.widthPx * scale) / sw;
  return {
    svgWidth: vw * unit,
    svgHeight: vh * unit,
    screenX: (sx - device.shell.viewBox[0]) * unit,
    screenY: (sy - device.shell.viewBox[1]) * unit,
    screenWidth: device.widthPx * scale,
    screenHeight: device.heightPx * scale,
  };
}
