// Saved compositions picker: select, create and delete. Creation defaults
// to the catalog's first device; the workspace keeps device switching.
import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { TooltipHint } from "../../../components/TooltipHint";
import type { DomainSceneView } from "../scenes/service.js";

function ListLoadError({
  message,
  loading,
  onRetry,
}: {
  message: string;
  loading: boolean;
  onRetry: () => void;
}): React.JSX.Element {
  return (
    <div className="flex flex-col items-start gap-2">
      <p role="alert" className="m-0 text-xs" data-screen-compositions-load-error>
        {message}
      </p>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        data-screen-compositions-retry
        disabled={loading}
        onClick={onRetry}
      >
        {loading ? "Retrying…" : "Retry"}
      </Button>
    </div>
  );
}

export function CompositionList({
  scenes,
  activeId,
  profilesLoaded,
  creating,
  loading,
  loadError,
  onRetry,
  onSelect,
  onCreate,
  onDelete,
}: {
  scenes: DomainSceneView[] | null;
  activeId: string | null;
  profilesLoaded: boolean;
  creating: boolean;
  loading: boolean;
  loadError: string;
  onRetry: () => void;
  onSelect: (id: string) => void;
  onCreate: (input: { name: string }) => Promise<void>;
  onDelete: (scene: DomainSceneView) => Promise<void>;
}): React.JSX.Element {
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState("");

  const create = async (): Promise<void> => {
    if (creating) return;
    setError("");
    try {
      if (!name.trim()) throw new Error("Composition names must be non-empty text.");
      await onCreate({ name: name.trim() });
      setName("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn’t create the composition.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle asChild>
          <h2>Compositions</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {scenes === null ? (
          loadError ? (
            <ListLoadError message={loadError} loading={loading} onRetry={onRetry} />
          ) : (
            <p role="status" className="m-0 text-xs" data-screen-compositions-loading>
              Loading compositions…
            </p>
          )
        ) : scenes.length === 0 && !loadError ? (
          <p className="m-0 text-xs text-soft" data-screen-compositions-empty>
            No compositions yet. Create one below.
          </p>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0" data-screen-compositions>
            {scenes.map((scene) => (
              <li
                key={scene.id}
                data-screen-composition={scene.id}
                className={scene.id === activeId ? "rounded-md outline-2 outline-solid outline-brand" : undefined}
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    data-screen-composition-open={scene.id}
                    aria-current={scene.id === activeId ? "true" : undefined}
                    onClick={() => onSelect(scene.id)}
                    className="min-w-0 flex-1 cursor-pointer bg-transparent p-1 text-left"
                  >
                    <span className="block truncate text-sm font-semibold">{scene.name}</span>
                    <span className="block text-xs text-soft">
                      {scene.width} × {scene.height} px · {scene.placements.length} label
                      {scene.placements.length === 1 ? "" : "s"}
                    </span>
                  </button>
                  <TooltipHint content="Delete this composition">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      data-screen-composition-delete={scene.id}
                      aria-label={`Delete composition ${scene.name}`}
                      onClick={() =>
                        void onDelete(scene).catch((failure: unknown) => {
                          setError(failure instanceof Error ? failure.message : "Couldn’t delete the composition.");
                        })
                      }
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </TooltipHint>
                </div>
              </li>
            ))}
          </ul>
        )}
        {scenes !== null && loadError && <ListLoadError message={loadError} loading={loading} onRetry={onRetry} />}
        <div className="flex flex-col gap-1">
          <Label htmlFor="composition-name">New composition</Label>
          <div className="flex gap-2">
            <Input
              id="composition-name"
              data-screen-composition-create-name
              value={name}
              maxLength={120}
              autoComplete="off"
              spellCheck={false}
              disabled={creating || !profilesLoaded}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void create();
              }}
            />
            <Button data-screen-composition-create disabled={creating || !profilesLoaded} onClick={() => void create()}>
              {creating ? (
                "Creating…"
              ) : (
                <>
                  <Plus aria-hidden="true" className="size-3 shrink-0" />
                  Add
                </>
              )}
            </Button>
          </div>
        </div>
        {error && (
          <p role="alert" className="m-0 text-xs" data-screen-compositions-error>
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
