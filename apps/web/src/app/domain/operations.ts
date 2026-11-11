// Single transport-safe operation specification. One runtime metadata value
// owns method exposure and read/write classification; mapped types derive the
// public method names, wire argument/result typing and write predicates from
// it, with type-only references to the existing handler signatures. The
// browser transport (runtime.ts), the worker dispatch (worker.ts) and the
// Node direct path (runtime.ts callDomain) all consume this module. Handler
// references are type-only, so importing this module never pulls backend
// implementations (PGlite, TypeGraph) into the browser main thread.

import type * as commands from "./commands.ts";
import type { importLegacySnapshot } from "./importer.ts";
import type { DomainBackend } from "./backend.ts";

/**
 * Runtime metadata: the single owner of method exposure and write
 * classification. Reads never bump the version, announce or force a flush;
 * a skipped legacy import additionally reports no write at dispatch time.
 */
const OPERATION_METADATA = {
  saveFont: { mutating: true },
  getFont: { mutating: false },
  listFonts: { mutating: false },
  updateFontMetadata: { mutating: true },
  removeFont: { mutating: true },
  getSeedMarker: { mutating: false },
  setSeedMarker: { mutating: true },
  createVariant: { mutating: true },
  getVariant: { mutating: false },
  listVariants: { mutating: false },
  updateVariant: { mutating: true },
  deleteVariant: { mutating: true },
  listPalettes: { mutating: false },
  createPalette: { mutating: true },
  updatePalette: { mutating: true },
  deletePalette: { mutating: true },
  listTextStyles: { mutating: false },
  listOutputProfiles: { mutating: false },
  listScenes: { mutating: false },
  getScene: { mutating: false },
  createScene: { mutating: true },
  ensureDefaultScene: { mutating: true },
  updateScene: { mutating: true },
  deleteScene: { mutating: true },
  addSceneLabel: { mutating: true },
  updateSceneLabel: { mutating: true },
  removeSceneLabel: { mutating: true },
  reorderSceneLabels: { mutating: true },
  restoreSceneSnapshot: { mutating: true },
  resolveTextStyle: { mutating: false },
  resolveTextStyles: { mutating: false },
  importLegacySnapshot: { mutating: true },
} as const;

export type DomainMethod = keyof typeof OPERATION_METADATA;

// Type-only handler references supply wire typing. The checks below keep
// them in lockstep with the metadata: no silent gaps, extras or misshapes.
interface OperationHandlers {
  saveFont: typeof commands.saveFont;
  getFont: typeof commands.getFont;
  listFonts: typeof commands.listFonts;
  updateFontMetadata: typeof commands.updateFontMetadata;
  removeFont: typeof commands.removeFont;
  getSeedMarker: typeof commands.getSeedMarker;
  setSeedMarker: typeof commands.setSeedMarker;
  createVariant: typeof commands.createVariant;
  getVariant: typeof commands.getVariant;
  listVariants: typeof commands.listVariants;
  updateVariant: typeof commands.updateVariant;
  deleteVariant: typeof commands.deleteVariant;
  listPalettes: typeof commands.listPalettes;
  createPalette: typeof commands.createPalette;
  updatePalette: typeof commands.updatePalette;
  deletePalette: typeof commands.deletePalette;
  listTextStyles: typeof commands.listTextStyles;
  listOutputProfiles: typeof commands.listOutputProfiles;
  listScenes: typeof commands.listScenes;
  getScene: typeof commands.getScene;
  createScene: typeof commands.createScene;
  ensureDefaultScene: typeof commands.ensureDefaultScene;
  updateScene: typeof commands.updateScene;
  deleteScene: typeof commands.deleteScene;
  addSceneLabel: typeof commands.addSceneLabel;
  updateSceneLabel: typeof commands.updateSceneLabel;
  removeSceneLabel: typeof commands.removeSceneLabel;
  reorderSceneLabels: typeof commands.reorderSceneLabels;
  restoreSceneSnapshot: typeof commands.restoreSceneSnapshot;
  resolveTextStyle: typeof commands.resolveTextStyle;
  resolveTextStyles: typeof commands.resolveTextStyles;
  importLegacySnapshot: typeof importLegacySnapshot;
}

type Equals<X, Y> = (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? true : false;
type Expect<T extends true> = T;
// Every exposed method has a handler reference and vice versa.
type _HandlerCoverage = Expect<Equals<keyof OperationHandlers, DomainMethod>>;
// Every handler reference is an async domain command over a backend.
type _HandlerShapes = Expect<
  OperationHandlers extends Record<DomainMethod, (...args: never[]) => Promise<unknown>> ? true : false
>;

// Sound tuple mapping: compiler-intrinsic Parameters with the leading
// backend slot dropped. Unlike inferring against an unknown first parameter
// (which strict variance rejects, collapsing to never), this preserves the
// real handler parameter lists exactly, including optionality.
type Tail<Args> = Args extends readonly [unknown, ...infer Rest] ? Rest : never;

export type DomainArgs<M extends DomainMethod> = Tail<Parameters<OperationHandlers[M]>>;
export type DomainResult<M extends DomainMethod> = Awaited<ReturnType<OperationHandlers[M]>>;

// Dispatch table shape every command path agrees with: per-method arguments
// and results must match the specification entry.
export type DomainDispatch = {
  [M in DomainMethod]: (backend: DomainBackend, ...args: DomainArgs<M>) => Promise<DomainResult<M>>;
};

/** Writes bump the domain version; reads never do (or subscribers loop). */
export const MUTATING_METHODS: ReadonlySet<DomainMethod> = new Set(
  (Object.keys(OPERATION_METADATA) as DomainMethod[]).filter((method) => OPERATION_METADATA[method].mutating),
);

/**
 * Own-property exposure guard every dispatch seam applies. Method names pass
 * only when the metadata owns them: non-RPC command exports (callable but
 * never exposed) and object-prototype names both fail closed here.
 */
export function isDomainMethod(method: unknown): method is DomainMethod {
  return typeof method === "string" && Object.hasOwn(OPERATION_METADATA, method);
}
