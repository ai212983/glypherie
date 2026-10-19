import type * as React from "react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { Button } from "../../components/ui/button";

export function PwaStatus(): React.JSX.Element | null {
  const {
    needRefresh: [needRefresh],
    offlineReady: [offlineReady],
    updateServiceWorker,
  } = useRegisterSW({
    immediate: false,
    onRegisterError(error: unknown) {
      console.warn("Service worker registration failed; the app still works online.", error);
    },
  });

  if (needRefresh) {
    return (
      <p className="mx-auto w-[min(100%-3rem,1440px)] px-6 pt-4 text-[.875rem]" role="status">
        A new version is available.{" "}
        <Button size="sm" variant="outline" onClick={() => { void updateServiceWorker(true); }}>
          Update now
        </Button>
      </p>
    );
  }

  if (offlineReady) {
    return (
      <p className="mx-auto w-[min(100%-3rem,1440px)] px-6 pt-4 text-[.875rem] text-soft" role="status">
        Ready for offline use.
      </p>
    );
  }

  return null;
}
