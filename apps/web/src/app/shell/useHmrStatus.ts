import * as React from "react";

export type HmrStatus = "connecting" | "connected" | "disconnected";

const PING = "glypherie:hmr-ping";
const PONG = "glypherie:hmr-pong";

export function useHmrStatus(): HmrStatus {
  const hot = import.meta.hot;
  const [status, setStatus] = React.useState<HmrStatus>(() =>
    hot ? (hot.data.hmrStatus as HmrStatus | undefined) ?? "connecting" : "connecting",
  );
  React.useEffect(() => {
    if (!hot) return;
    const retain = (next: HmrStatus): void => {
      hot.data.hmrStatus = next;
      setStatus(next);
    };
    const connected = (): void => retain("connected");
    const disconnected = (): void => retain("disconnected");
    hot.on("vite:ws:connect", connected);
    hot.on("vite:ws:disconnect", disconnected);
    hot.on(PONG, connected);
    // https://vite.dev/guide/api-hmr.html — ws:connect may fire before this
    // effect subscribes, so ask the server for a pong to learn the live state.
    try {
      hot.send(PING);
    } catch {
      // Socket not open yet; the ws:connect listener covers this path.
    }
    return () => {
      hot.off("vite:ws:connect", connected);
      hot.off("vite:ws:disconnect", disconnected);
      hot.off(PONG, connected);
    };
  }, [hot]);
  return status;
}
