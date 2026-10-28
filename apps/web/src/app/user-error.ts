import { VARIANT_NAME_MAX_LENGTH } from "./variants/model.ts";

export class UserFacingError extends Error {}

// UI boundaries keep implementation details in the console while preserving
// the recovery instructions users need to act on storage failures.
export function userError(error: unknown, fallback: string): string {
  console.warn(fallback, error);
  if (error instanceof UserFacingError) return error.message;
  const code = error && typeof error === "object" && "code" in error ? error.code : undefined;
  const message = error instanceof Error ? error.message : "";
  switch (code) {
    case "blocked": return "Storage is blocked. Close other Glypherie tabs and reload.";
    case "quota-exceeded": return message.includes("variant")
      ? "Browser storage is full. Remove a variant to free space."
      : "Browser storage is full. Remove an imported font to free space.";
    case "unavailable": return "Browser storage is unavailable.";
    case "conflict": return "Another tab changed this variant.";
    case "not-found": return "Variant not found.";
    case "font-not-found": return "Font not found in this library.";
    case "invalid-input":
      if (message.includes("names must be non-empty")) return "Enter a variant name.";
      if (message.includes("names must stay within")) return `Use a name of ${VARIANT_NAME_MAX_LENGTH} characters or fewer.`;
      return fallback;
    default: return fallback;
  }
}
