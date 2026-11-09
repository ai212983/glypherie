// Shared scene save-conflict policy: a revision mismatch surfaces as a
// reload prompt, never as a silent overwrite. Both the detail page and the
// export panel classify the same storage error shape.
export function isConflict(error: unknown): boolean {
  const code = (error as { code?: unknown }).code;
  if (code === "conflict") return true;
  return error instanceof Error && /conflict|another tab|expected revision/i.test(error.message);
}
