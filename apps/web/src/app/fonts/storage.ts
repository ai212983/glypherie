// Browser-local font library, backed by the domain graph store. Same exports
// and observable semantics as the legacy Dexie implementation: fonts stay
// content-addressed by SHA-256, uploaded sources upgrade bundled rows, and
// removal cascades the font's variants. Only the storage mechanics changed.

import { callDomain } from "../domain/runtime.ts";

export { fontDatabase } from "../database.ts";

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
  glyph_count?: number | null;
  font_hints?: boolean | null;
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
  | "stale-owner"
  | "referenced"
  | "unavailable";

export class FontStorageError extends Error {
  readonly code: FontStorageErrorCode;
  constructor(code: FontStorageErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "FontStorageError";
    this.code = code;
  }
}

// "stale-owner" passes through with its honest message: a version-skewed
// domain owner is never recast as generic unavailability.
const KNOWN_CODES: ReadonlySet<string> = new Set([
  "empty-bytes",
  "invalid-metadata",
  "invalid-input",
  "invalid-descriptor",
  "seed-failed",
  "quota-exceeded",
  "blocked",
  "stale-owner",
  "referenced",
  "unavailable",
]);

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function mapStorageError(error: unknown): FontStorageError {
  if (error instanceof FontStorageError) return error;
  const code = (error as { code?: unknown })?.code;
  if (typeof code === "string" && KNOWN_CODES.has(code)) {
    return new FontStorageError(code as FontStorageErrorCode, messageOf(error), { cause: error });
  }
  return new FontStorageError("unavailable", "Browser font storage is unavailable in this context.", {
    cause: error,
  });
}

export function isFontDatabaseBlocked(): boolean {
  return false;
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
  if (metadata.font_hints !== undefined && metadata.font_hints !== null && typeof metadata.font_hints !== "boolean") {
    fail("font_hints must be a boolean or null");
  }
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

export async function listFonts(): Promise<StoredFont[]> {
  try {
    return await callDomain("listFonts", []);
  } catch (error) {
    throw mapStorageError(error);
  }
}

export async function updateFontMetadata(id: string, metadata: FontMetadata): Promise<void> {
  validateFontMetadata(metadata);
  try {
    await callDomain("updateFontMetadata", [id, metadata]);
  } catch (error) {
    throw mapStorageError(error);
  }
}

export async function getFont(id: string): Promise<StoredFont | undefined> {
  try {
    return await callDomain("getFont", [id]);
  } catch (error) {
    throw mapStorageError(error);
  }
}

export async function saveFont(input: SaveFontInput): Promise<StoredFont> {
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
  try {
    return await callDomain("saveFont", [
      {
        bytes: input.bytes,
        fileName: input.fileName,
        name: input.name,
        metadata: input.metadata,
        source: input.source,
      },
    ]);
  } catch (error) {
    throw mapStorageError(error);
  }
}

export async function removeFont(id: string): Promise<void> {
  try {
    await callDomain("removeFont", [id]);
  } catch (error) {
    throw mapStorageError(error);
  }
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
  const marker = await callDomain("getSeedMarker", []).catch((error: unknown) => {
    throw mapStorageError(error);
  });
  if (marker === key) return;
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
  try {
    await callDomain("setSeedMarker", [key]);
  } catch (error) {
    throw mapStorageError(error);
  }
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
