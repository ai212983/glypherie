import { MAX_TEXT_LENGTH, TEXT_DEFAULT } from "../../renderer/render-spec.ts";

import { isFontSize } from "../../../components/font-size.ts";

export type LibraryBaseSize = number;

export const DEFAULT_LIBRARY_BASE_SIZE: LibraryBaseSize = 16;

export function isLibraryBaseSize(value: unknown): value is LibraryBaseSize {
  return isFontSize(value);
}

export interface LibraryPreferences {
  text: string;
  baseSize: LibraryBaseSize;
}

export const LIBRARY_PREFERENCES_KEY = "font-preview.library";

export function readStoredLibraryPreferences(): LibraryPreferences {
  const defaults: LibraryPreferences = {
    text: TEXT_DEFAULT,
    baseSize: DEFAULT_LIBRARY_BASE_SIZE,
  };
  try {
    const raw = globalThis.localStorage?.getItem(LIBRARY_PREFERENCES_KEY);
    if (raw != null) {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return defaults;
      const value = parsed as Record<string, unknown>;
      return {
        text: typeof value.text === "string" ? value.text.slice(0, MAX_TEXT_LENGTH) : defaults.text,
        baseSize: isLibraryBaseSize(value.baseSize) ? value.baseSize : defaults.baseSize,
      };
    }
    return defaults;
  } catch {
    return defaults;
  }
}

export function writeStoredLibraryPreferences(preferences: LibraryPreferences): void {
  try {
    globalThis.localStorage?.setItem(LIBRARY_PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // Controls still work in memory when browser storage is unavailable.
  }
}
