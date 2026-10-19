import type { RendererService } from "./renderer-types.js";

// Fetches font bytes and loads them into the renderer worker. The abort
// signal belongs to the caller's lifetime (effect cleanup aborts it): an
// aborted fetch rejects, and bytes that arrive after abort are never sent,
// so a disposed worker can never receive a late load with no one to answer.
export async function fetchFontIntoService(
  service: Pick<RendererService, "load">,
  fontId: string,
  url: string,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Font asset fetch failed: ${response.status}.`);
  const bytes = await response.arrayBuffer();
  if (signal.aborted) return;
  await service.load(fontId, bytes);
}
