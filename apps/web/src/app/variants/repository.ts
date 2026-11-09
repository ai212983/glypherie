// Saved font variants over the split domain graph. The legacy composite
// VariantSettings DTO is preserved exactly (same validation, auto-naming,
// CAS codes); only the storage mechanics moved to domain commands.

import { callDomain } from "../domain/runtime.ts";
import { VariantStorageError, type FontVariant, type VariantSettings } from "./model.ts";

export { VariantStorageError };
export type { VariantSettings };

export interface VariantInput {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

export interface VariantChanges {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

// "stale-owner" passes through with its honest message: a version-skewed
// domain owner is never recast as generic unavailability.
const KNOWN_CODES: ReadonlySet<string> = new Set([
  "conflict",
  "not-found",
  "font-not-found",
  "invalid-settings",
  "invalid-input",
  "blocked",
  "stale-owner",
  "quota-exceeded",
  "referenced",
  "unavailable",
]);

function mapVariantError(error: unknown): VariantStorageError {
  if (error instanceof VariantStorageError) return error;
  const code = (error as { code?: unknown })?.code;
  const message = error instanceof Error ? error.message : String(error);
  if (typeof code === "string" && KNOWN_CODES.has(code)) {
    return new VariantStorageError(code as VariantStorageError["code"], message, { cause: error });
  }
  return new VariantStorageError("unavailable", "Browser variant storage is unavailable in this context.", {
    cause: error,
  });
}

export async function createVariant(fontId: string, input: VariantInput = {}): Promise<FontVariant> {
  try {
    return (await callDomain("createVariant", [fontId, input])) as FontVariant;
  } catch (error) {
    throw mapVariantError(error);
  }
}

export async function getVariant(id: string): Promise<FontVariant | undefined> {
  try {
    return (await callDomain("getVariant", [id])) as FontVariant | undefined;
  } catch (error) {
    throw mapVariantError(error);
  }
}

export async function listVariants(fontId?: string): Promise<FontVariant[]> {
  try {
    return (await callDomain("listVariants", [fontId])) as FontVariant[];
  } catch (error) {
    throw mapVariantError(error);
  }
}

export async function updateVariant(
  id: string,
  changes: VariantChanges,
  expectedRevision: number,
): Promise<FontVariant> {
  try {
    return (await callDomain("updateVariant", [id, changes, expectedRevision])) as FontVariant;
  } catch (error) {
    throw mapVariantError(error);
  }
}

export async function deleteVariant(id: string, expectedRevision?: number): Promise<void> {
  try {
    await callDomain("deleteVariant", [id, expectedRevision]);
  } catch (error) {
    throw mapVariantError(error);
  }
}
