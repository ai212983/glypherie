import { FontWorkerClient } from "./client.js";
import type { RendererService } from "./renderer-types.js";

// Concrete renderer runtime for the app composition root and the real
// rendering stories. Importing this module pulls the worker bundle (and its
// staged WASM) into the graph; keep it out of unit tests and the fixture
// lifecycle harness.
export function createWorkerRendererService(): RendererService {
  return new FontWorkerClient();
}
