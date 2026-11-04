// Bounded undo/redo over successful local scene changes. The parent records
// each pre-image after its mutation succeeds and restores snapshots through
// one revision-guarded transaction. Adopting remote changes clears history.
import * as React from "react";
import type { DomainSceneView } from "../scenes/service.js";

const HISTORY_LIMIT = 50;

export function useSceneHistory(): {
  canUndo: boolean;
  canRedo: boolean;
  checkpoint: (scene: DomainSceneView) => void;
  peekUndo: (currentId: string) => DomainSceneView | null;
  peekRedo: (currentId: string) => DomainSceneView | null;
  takeUndo: (currentId: string) => DomainSceneView | null;
  takeRedo: (currentId: string) => DomainSceneView | null;
  stashForRedo: (scene: DomainSceneView) => void;
  stashForUndo: (scene: DomainSceneView) => void;
  reset: () => void;
} {
  const [past, setPast] = React.useState<DomainSceneView[]>([]);
  const [future, setFuture] = React.useState<DomainSceneView[]>([]);
  // Refs mirror the stacks so take reads stay pure under StrictMode's
  // double-invoked updaters.
  const pastRef = React.useRef<DomainSceneView[]>([]);
  const futureRef = React.useRef<DomainSceneView[]>([]);
  pastRef.current = past;
  futureRef.current = future;

  const checkpoint = React.useCallback((scene: DomainSceneView) => {
    setPast((previous) => [...previous.slice(-(HISTORY_LIMIT - 1)), scene]);
    setFuture([]);
  }, []);

  // Peeks read without popping, so a failed restore leaves both stacks
  // intact: the caller commits with take/stash only after a success.
  const peekUndo = React.useCallback((currentId: string): DomainSceneView | null => {
    const stack = pastRef.current;
    if (stack.length === 0) return null;
    const candidate = stack[stack.length - 1]!;
    return candidate.id === currentId ? candidate : null;
  }, []);

  const peekRedo = React.useCallback((currentId: string): DomainSceneView | null => {
    const stack = futureRef.current;
    if (stack.length === 0) return null;
    const candidate = stack[stack.length - 1]!;
    return candidate.id === currentId ? candidate : null;
  }, []);

  // Undo/redo only span one composition; switching scenes clears the stacks
  // so a stale snapshot can never replay into the wrong scene.
  const takeUndo = React.useCallback((currentId: string): DomainSceneView | null => {
    const stack = pastRef.current;
    if (stack.length === 0) return null;
    const candidate = stack[stack.length - 1]!;
    if (candidate.id !== currentId) {
      setPast([]);
      return null;
    }
    setPast(stack.slice(0, -1));
    return candidate;
  }, []);

  const takeRedo = React.useCallback((currentId: string): DomainSceneView | null => {
    const stack = futureRef.current;
    if (stack.length === 0) return null;
    const candidate = stack[stack.length - 1]!;
    if (candidate.id !== currentId) {
      setFuture([]);
      return null;
    }
    setFuture(stack.slice(0, -1));
    return candidate;
  }, []);

  const stashForRedo = React.useCallback((scene: DomainSceneView) => {
    setFuture((previous) => [...previous.slice(-(HISTORY_LIMIT - 1)), scene]);
  }, []);

  const stashForUndo = React.useCallback((scene: DomainSceneView) => {
    setPast((previous) => [...previous.slice(-(HISTORY_LIMIT - 1)), scene]);
  }, []);

  const reset = React.useCallback(() => {
    setPast([]);
    setFuture([]);
  }, []);

  return { canUndo: past.length > 0, canRedo: future.length > 0, checkpoint, peekUndo, peekRedo, takeUndo, takeRedo, stashForRedo, stashForUndo, reset };
}
