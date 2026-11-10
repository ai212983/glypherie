// Thin React adapter from the scene document session to the workspace.
//
// The adapter binds the scenes service (load bundle, id-free restore,
// conflict classification, domain subscription) and mirrors the session
// snapshot into React. It owns no queue, revision, history or adoption rules:
// those live in the session core, and document edits arrive as meaningful
// intents through the scene-intents controller.
import * as React from "react";
import {
  getScene,
  listOutputProfiles,
  listTextStyles,
  restoreSceneSnapshot,
  subscribeDomain,
} from "../scenes/service.ts";
import { isConflict } from "../scenes/conflict.ts";
import { SceneDocumentSession, type SceneSessionSnapshot } from "./scene-session.ts";

export function useSceneSession(sceneId: string): SceneDocumentSession {
  const [session] = React.useState(
    () =>
      new SceneDocumentSession({
        loadBundle: async (id) => {
          const [scene, styles, profiles] = await Promise.all([getScene(id), listTextStyles(), listOutputProfiles()]);
          return { scene: scene ?? null, styles, profiles };
        },
        restore: (id, revision, snapshot) => restoreSceneSnapshot(id, revision, snapshot),
        isConflict,
      }),
  );
  React.useEffect(() => {
    void session.openScene(sceneId);
    return subscribeDomain(() => {
      void session.reload();
    });
  }, [session, sceneId]);
  return session;
}

// Mirrors the session snapshot into React without leaking refs, queue depth
// or history stacks: consumers re-render on the monotonic version and read
// the stable document/status/conflict snapshot plus meaningful intents.
export function useSceneSnapshot(session: SceneDocumentSession): SceneSessionSnapshot {
  const version = React.useSyncExternalStore(
    React.useCallback((notify) => session.subscribe(notify), [session]),
    React.useCallback(() => session.version, [session]),
  );
  void version;
  return session.snapshot;
}
