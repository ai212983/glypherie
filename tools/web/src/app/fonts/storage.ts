import { errorName, fontDatabase, isDatabaseBlocked, runWithReopen } from "../database.ts";
import type { FontRow } from "../database.ts";

export { fontDatabase };

export interface AxisMetadata {
  tag: string;
  name: string | null;
  min: number;
  default: number;
  max: number;
  hidden: boolean;
}

export interface KerningMetadata {
  horizontal: boolean;
  vertical: boolean;
  sources: string[];
}

export interface StyleMetadata {
  slope: string | null;
  weight_class: number | null;
  width_class: number | null;
  italic_angle: number | null;
}

export interface ClassificationMetadata {
  family_class: number | null;
  panose: number[] | null;
  monospaced: boolean | null;
}

export interface UnicodeCoverage {
  character_count: number;
  ranges: [number, number][];
}

export interface FontMetadata {
  names: Record<string, string | null>;
  axes: AxisMetadata[];
  kerning?: KerningMetadata;
  style?: StyleMetadata;
  classification?: ClassificationMetadata;
  coverage?: UnicodeCoverage | null;
  declared_unicode_ranges?: [number, number, number, number] | null;
}

export type FontSource = "bundled" | "uploaded";

export interface StoredFont {
  id: string;
  name: string;
  fileName: string;
  bytes: ArrayBuffer;
  metadata: FontMetadata;
  source: FontSource;
  addedAt: number;
}

export interface SaveFontInput {
  bytes: ArrayBuffer;
  fileName: string;
  name: string;
  metadata: FontMetadata;
  source: FontSource;
}

export interface BundledFontDescriptor {
  url: string;
  name: string;
  fileName: string;
}

export type FontStorageErrorCode =
  | "empty-bytes"
  | "invalid-metadata"
  | "invalid-input"
  | "invalid-descriptor"
  | "seed-failed"
  | "quota-exceeded"
  | "blocked"
  | "unavailable";

export class FontStorageError extends Error {
  readonly code: FontStorageErrorCode;
  constructor(code: FontStorageErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "FontStorageError";
    this.code = code;
  }
}

const SEED_MARKER_KEY = "bundled-fonts";

export function isFontDatabaseBlocked(): boolean {
  return isDatabaseBlocked();
}

function throwIfBlocked(): void {
  if (isDatabaseBlocked()) {
    throw new FontStorageError(
      "blocked",
      "Font storage is blocked by another open tab holding an older database version. Close other tabs and reload.",
    );
  }
}

async function runWithFonts<T>(operation: () => Promise<T>): Promise<T> {
  throwIfBlocked();
  try {
    return await runWithReopen(operation);
  } catch (error) {
    throw mapStorageError(error);
  }
}

function mapStorageError(error: unknown): FontStorageError {
  if (error instanceof FontStorageError) return error;
  if (errorName(error) === "QuotaExceededError") {
    return new FontStorageError(
      "quota-exceeded",
      "Browser font storage is full. Remove an uploaded font to free space; nothing was uploaded anywhere.",
      { cause: error },
    );
  }
  return new FontStorageError("unavailable", "Browser font storage is unavailable in this context.", {
    cause: error,
  });
}

function validateFontMetadata(metadata: FontMetadata): void {
  const fail = (why: string): never => {
    throw new FontStorageError("invalid-metadata", `Refusing to store malformed font metadata: ${why}.`);
  };
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) fail("metadata must be an object");
  if (!metadata.names || typeof metadata.names !== "object" || Array.isArray(metadata.names)) {
    fail("metadata.names must be an object");
  }
  if (!Array.isArray(metadata.axes)) fail("metadata.axes must be an array");
  for (const axis of metadata.axes) {
    if (!axis || typeof axis !== "object") fail("every axis must be an object");
    if (typeof axis.tag !== "string" || axis.tag.length !== 4) fail("every axis tag must be a 4-character string");
    if (axis.name !== null && (typeof axis.name !== "string" || axis.name.trim() === "")) {
      fail("axis names must be null or non-empty text");
    }
    if (![axis.min, axis.default, axis.max].every(Number.isFinite)) fail("axis bounds must be finite numbers");
    if (!(axis.min <= axis.default && axis.default <= axis.max)) fail("axis default must sit within its bounds");
    if (typeof axis.hidden !== "boolean") fail("axis hidden must be a boolean");
  }
}

function toStoredFont(row: FontRow): StoredFont {
  return {
    id: row.id,
    name: row.name,
    fileName: row.fileName,
    bytes: row.bytes,
    metadata: row.metadata,
    source: row.source,
    addedAt: row.addedAt,
  };
}

async function contentId(bytes: ArrayBuffer): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new FontStorageError("unavailable", "Font storage needs WebCrypto SHA-256, missing in this context.");
  }
  const digest = await subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function listFonts(): Promise<StoredFont[]> {
  return runWithFonts(async () => {
    const rows = await fontDatabase.fonts.orderBy("addedAt").toArray();
    return rows.map(toStoredFont);
  });
}

export async function getFont(id: string): Promise<StoredFont | undefined> {
  return runWithFonts(async () => {
    const row = await fontDatabase.fonts.get(id);
    return row ? toStoredFont(row) : undefined;
  });
}

export async function saveFont(input: SaveFontInput): Promise<StoredFont> {
  throwIfBlocked();
  if (!(input.bytes instanceof ArrayBuffer) || input.bytes.byteLength === 0) {
    throw new FontStorageError("empty-bytes", "Refusing to store a font with no bytes.");
  }
  if (typeof input.name !== "string" || input.name.trim() === "") {
    throw new FontStorageError("invalid-input", "Stored fonts need a non-empty name.");
  }
  if (typeof input.fileName !== "string" || input.fileName.trim() === "") {
    throw new FontStorageError("invalid-input", "Stored fonts need a non-empty file name.");
  }
  if (input.source !== "bundled" && input.source !== "uploaded") {
    throw new FontStorageError("invalid-input", "Font source must be bundled or uploaded.");
  }
  validateFontMetadata(input.metadata);
  const id = await contentId(input.bytes);
  return runWithFonts(async () => {
    return fontDatabase.transaction("rw", fontDatabase.fonts, async () => {
      const existing = await fontDatabase.fonts.get(id);
      if (existing) {
        if (existing.source === "uploaded" || input.source === "bundled") return toStoredFont(existing);
        existing.source = "uploaded";
        await fontDatabase.fonts.put(existing);
        return toStoredFont(existing);
      }
      const row: FontRow = {
        id,
        name: input.name,
        fileName: input.fileName,
        bytes: input.bytes.slice(0),
        metadata: input.metadata,
        source: input.source,
        addedAt: Date.now(),
      };
      await fontDatabase.fonts.add(row);
      return toStoredFont(row);
    });
  });
}

export async function removeFont(id: string): Promise<void> {
  return runWithFonts(() =>
    // One transaction: the font and its variants disappear together, so a
    // concurrent reader never sees variants of a deleted font.
    fontDatabase.transaction("rw", [fontDatabase.fonts, fontDatabase.variants], async () => {
      await fontDatabase.variants.where("fontId").equals(id).delete();
      await fontDatabase.fonts.delete(id);
    }),
  );
}

function assertSameOriginUrl(url: string): void {
  if (typeof url !== "string" || url === "") {
    throw new FontStorageError("invalid-descriptor", "Bundled font descriptors need a non-empty URL.");
  }
  const base = typeof globalThis.location?.href === "string" ? globalThis.location.href : undefined;
  let parsed: URL;
  try {
    parsed = base ? new URL(url, base) : new URL(url, "http://localhost/");
  } catch {
    throw new FontStorageError("invalid-descriptor", "Bundled font descriptors need a parseable URL.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new FontStorageError(
      "invalid-descriptor",
      "Bundled fonts must use http(s) URLs; data, blob and other schemes are rejected.",
    );
  }
  if (base && parsed.origin !== new URL(base).origin) {
    throw new FontStorageError("invalid-descriptor", "Bundled fonts must be fetched from the same origin.");
  }
}

function seedKey(descriptors: BundledFontDescriptor[]): string {
  return JSON.stringify(descriptors.map((descriptor) => descriptor.url).sort());
}

function rethrowUnlessStorage(error: unknown, url: string): never {
  if (
    error instanceof FontStorageError &&
    (error.code === "quota-exceeded" || error.code === "blocked" || error.code === "unavailable")
  ) {
    throw error;
  }
  throw new FontStorageError("seed-failed", `Bundled font seeding failed for ${url}.`, { cause: error });
}

async function seedInner(
  descriptors: BundledFontDescriptor[],
  inspect: (bytes: ArrayBuffer) => Promise<FontMetadata>,
): Promise<void> {
  throwIfBlocked();
  for (const descriptor of descriptors) {
    assertSameOriginUrl(descriptor.url);
    if (typeof descriptor.name !== "string" || descriptor.name.trim() === "") {
      throw new FontStorageError("invalid-descriptor", "Bundled font descriptors need a non-empty name.");
    }
    if (typeof descriptor.fileName !== "string" || descriptor.fileName.trim() === "") {
      throw new FontStorageError("invalid-descriptor", "Bundled font descriptors need a non-empty file name.");
    }
  }
  const key = seedKey(descriptors);
  const marker = await runWithFonts(() => fontDatabase.meta.get(SEED_MARKER_KEY));
  if (marker?.value === key) return;
  for (const descriptor of descriptors) {
    let bytes: ArrayBuffer;
    try {
      const response = await fetch(descriptor.url, { credentials: "same-origin", redirect: "error" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (typeof response.url === "string" && response.url !== "") {
        const base = typeof globalThis.location?.href === "string" ? globalThis.location.href : undefined;
        if (base && new URL(response.url, base).origin !== new URL(base).origin) {
          throw new Error("Cross-origin redirect target");
        }
      }
      bytes = await response.arrayBuffer();
    } catch (error) {
      rethrowUnlessStorage(error, descriptor.url);
    }
    if (bytes.byteLength === 0) {
      throw new FontStorageError("seed-failed", `Bundled font seeding failed for ${descriptor.url}: empty bytes.`);
    }
    let metadata: FontMetadata;
    try {
      metadata = await inspect(bytes);
    } catch (error) {
      rethrowUnlessStorage(error, descriptor.url);
    }
    try {
      await saveFont({ bytes, fileName: descriptor.fileName, name: descriptor.name, metadata, source: "bundled" });
    } catch (error) {
      rethrowUnlessStorage(error, descriptor.url);
    }
  }
  await runWithFonts(() => fontDatabase.meta.put({ key: SEED_MARKER_KEY, value: key }));
}

let seedInFlight: Promise<void> | null = null;

export function seedBundledFonts(
  descriptors: BundledFontDescriptor[],
  inspect: (bytes: ArrayBuffer) => Promise<FontMetadata>,
): Promise<void> {
  if (!seedInFlight) {
    seedInFlight = seedInner(descriptors, inspect).finally(() => {
      seedInFlight = null;
    });
  }
  return seedInFlight;
}
