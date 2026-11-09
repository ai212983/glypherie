// Node/test backend ownership. Imported directly by tests and lazily by
// runtime.callDomain outside the browser, so the browser main-thread chunk
// never pays for the PGlite engine (the domain worker owns it there).

import { createDomainBackend, type DomainBackend } from "./backend.ts";
import { closeDomainChannelForTests, resetDomainVersionForTests } from "./events.ts";
import { resetDomainTransportForTests } from "./runtime.ts";

let backend: DomainBackend | null = null;

export function getBackend(): DomainBackend {
  if (!backend)
    throw new Error("Domain backend is not configured; call configureDomain() or initBrowserDomain() first.");
  return backend;
}

export async function configureDomain(next: DomainBackend): Promise<void> {
  if (backend && backend !== next) {
    await backend.close().catch(() => undefined);
  }
  backend = next;
}

/** Node/test path: direct backend, no worker involved. */
export async function ensureNodeBackend(): Promise<DomainBackend> {
  if (!backend) backend = await createDomainBackend();
  return backend;
}

/** Test seam: drop the ambient backend so the next call starts isolated. */
export async function resetDomainForTests(): Promise<DomainBackend> {
  resetDomainTransportForTests();
  if (backend) {
    await backend.close().catch(() => undefined);
    backend = null;
  }
  resetDomainVersionForTests();
  backend = await createDomainBackend();
  return backend;
}

/** Test seam: release the ambient backend so the test process can exit. */
export async function closeDomainForTests(): Promise<void> {
  resetDomainTransportForTests();
  closeDomainChannelForTests();
  if (backend) {
    await backend.close().catch(() => undefined);
    backend = null;
  }
}
