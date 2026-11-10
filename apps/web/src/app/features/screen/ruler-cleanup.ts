// Host cleanup for a pinned @scena/ruler instance.
//
// The 0.20.0 core destroy() deterministically throws
// `TypeError: Cannot set properties of null (setting '__CROACT__')` and leaves
// its canvas behind: the constructor keeps the element in a local instead of
// `this.selfElement`, so destroy unmounts and removes nothing
// (packages/ruler/src/Ruler.tsx vs the published dist/ruler.esm.js; proven by
// the destroy probe under implementation-control/). Only that known defect is
// contained; any other destroy failure still propagates after the host is
// cleared, so stray canvases never survive a remount or unmount.
let warnedDestroyDefect = false;

export function isKnownDestroyDefect(error: unknown): boolean {
  return error instanceof TypeError && error.message.includes("__CROACT__");
}

export function cleanupRulerHost(host: Pick<HTMLElement, "replaceChildren">, destroy: () => void): void {
  try {
    destroy();
  } catch (error) {
    if (!isKnownDestroyDefect(error)) throw error;
    if (!warnedDestroyDefect) {
      warnedDestroyDefect = true;
      console.warn("@scena/ruler destroy() is a known no-op that throws; the host was cleared instead.");
    }
  } finally {
    host.replaceChildren();
  }
}
