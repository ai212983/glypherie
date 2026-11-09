// Shared domain failure codes. Import from here, not commands.ts, so scene
// and variant modules share the type without a commands import cycle.

export type DomainCode =
  | "conflict"
  | "not-found"
  | "font-not-found"
  | "invalid-settings"
  | "invalid-input"
  | "blocked"
  | "quota-exceeded"
  | "unavailable"
  | "referenced";

export class DomainError extends Error {
  readonly code: DomainCode;
  constructor(code: DomainCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "DomainError";
    this.code = code;
  }
}
