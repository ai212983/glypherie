// Scenes list: minimal usable create/delete over saved domain scenes.
// Saved variants are text styles semantically; scenes arrange labels that
// use those styles, they never redefine fonts.
import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import { NavLink } from "../../../components/NavLink";
import { readRouteSearch } from "../../navigation/snapshot";
import { scenePath } from "../../navigation/router";
import { DEFAULT_CHARACTER_COVERAGE, type CharacterCoverage } from "../../domain/coverage";
import { CoverageControl } from "../preview/CoverageControl";
import type { DomainOutputProfileView, DomainSceneView } from "./service";
import { createScene, deleteScene, listOutputProfiles, listScenes, subscribeDomain } from "./service";

function domainError(error: unknown, fallback: string): { message: string; conflict: boolean } {
  const code = (error as { code?: unknown }).code;
  const conflict = code === "conflict"
    || (error instanceof Error && /conflict|another tab|expected revision/i.test(error.message));
  return {
    message: conflict ? "The scene changed in another tab; it was reloaded." : error instanceof Error ? error.message : fallback,
    conflict,
  };
}

export function ScenesPage({ onOpenScene }: { onOpenScene: (id: string) => void }): React.JSX.Element {
  const [scenes, setScenes] = React.useState<DomainSceneView[] | null>(null);
  const [profiles, setProfiles] = React.useState<DomainOutputProfileView[] | null>(null);
  const [error, setError] = React.useState("");
  const [name, setName] = React.useState("");
  const [width, setWidth] = React.useState("400");
  const [height, setHeight] = React.useState("240");
  const [profileId, setProfileId] = React.useState("");
  const [coverage, setCoverage] = React.useState<CharacterCoverage>(DEFAULT_CHARACTER_COVERAGE);
  const [creating, setCreating] = React.useState(false);

  const reload = React.useCallback(async () => {
    try {
      const [nextScenes, nextProfiles] = await Promise.all([listScenes(), listOutputProfiles()]);
      setScenes(nextScenes);
      setProfiles(nextProfiles);
      setProfileId((current) => current || nextProfiles[0]?.id || "");
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn’t load scenes.");
    }
  }, []);

  React.useEffect(() => {
    void reload();
    return subscribeDomain(() => { void reload(); });
  }, [reload]);

  const create = async (): Promise<void> => {
    if (creating) return;
    setCreating(true);
    setError("");
    try {
      const parsedWidth = Math.round(Number(width));
      const parsedHeight = Math.round(Number(height));
      if (!name.trim()) throw new Error("Scene names must be non-empty text.");
      if (!Number.isInteger(parsedWidth) || parsedWidth < 1 || parsedWidth > 4096) {
        throw new Error("Scene width must be a whole number within 1..4096.");
      }
      if (!Number.isInteger(parsedHeight) || parsedHeight < 1 || parsedHeight > 4096) {
        throw new Error("Scene height must be a whole number within 1..4096.");
      }
      if (!profileId) throw new Error("Choose an output profile for the scene.");
      const created = await createScene({
        name: name.trim(), width: parsedWidth, height: parsedHeight, outputProfileId: profileId, exportCoverage: coverage,
      });
      setName("");
      setCoverage(DEFAULT_CHARACTER_COVERAGE);
      onOpenScene(created.id);
    } catch (failure) {
      setError(domainError(failure, "Couldn’t create the scene.").message);
    } finally {
      setCreating(false);
    }
  };

  const remove = async (scene: DomainSceneView): Promise<void> => {
    setError("");
    try {
      await deleteScene(scene.id, scene.revision);
      await reload();
    } catch (failure) {
      const mapped = domainError(failure, "Couldn’t delete the scene.");
      setError(mapped.message);
      if (mapped.conflict) await reload();
    }
  };

  return (
    <div className="flex min-w-0 flex-col gap-4" data-scenes-page>
      <Card>
        <CardHeader>
          <CardTitle asChild><h2><Plus aria-hidden="true" className="size-3 shrink-0" />New scene</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="scene-name">Name</Label>
            <Input id="scene-name" data-scene-create-name value={name} maxLength={120} autoComplete="off"
              spellCheck={false} disabled={creating} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="scene-width">Width (px)</Label>
              <Input id="scene-width" data-scene-create-width type="number" min={1} max={4096} value={width}
                disabled={creating} onChange={(event) => setWidth(event.target.value)} className="w-28" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="scene-height">Height (px)</Label>
              <Input id="scene-height" data-scene-create-height type="number" min={1} max={4096} value={height}
                disabled={creating} onChange={(event) => setHeight(event.target.value)} className="w-28" />
            </div>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="scene-profile">Output profile</Label>
              <Select value={profileId} disabled={creating || !profiles} onValueChange={setProfileId}>
                <SelectTrigger id="scene-profile" data-scene-create-profile className="w-full">
                  <SelectValue placeholder="Choose a profile" />
                </SelectTrigger>
                <SelectContent>
                  {(profiles ?? []).map((profile) => (
                    <SelectItem key={profile.id} value={profile.id}>{profile.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <CoverageControl coverage={coverage} onCoverage={setCoverage} disabled={creating} />
          <div>
            <Button data-scene-create disabled={creating || !profiles} onClick={() => void create()}>
              {creating ? "Creating…" : "Create scene"}
            </Button>
          </div>
        </CardContent>
      </Card>
      {error && <p role="alert" className="m-0 text-xs" data-scenes-error>{error}</p>}
      {scenes === null ? (
        <p role="status" className="m-0 text-xs">Loading scenes…</p>
      ) : scenes.length === 0 ? (
        <p className="m-0 text-xs text-soft" data-scenes-empty>No scenes yet. Create one above.</p>
      ) : (
        <ul className="m-0 grid list-none gap-3 p-0" data-scenes-list>
          {scenes.map((scene) => (
            <li key={scene.id}>
              <Card data-scene-card={scene.id}>
                <CardContent className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <NavLink href={scenePath(scene.id, readRouteSearch() || window.location.search)} data-scene-open={scene.id}
                      onNavigate={() => onOpenScene(scene.id)}>
                      {scene.name}
                    </NavLink>
                    <p className="m-0 text-xs text-soft">
                      {scene.width} × {scene.height} px · {scene.placements.length} label{scene.placements.length === 1 ? "" : "s"}
                    </p>
                  </div>
                  <TooltipHint content="Delete this scene">
                    <Button type="button" variant="ghost" size="icon-xs" data-scene-delete={scene.id}
                      aria-label={`Delete scene ${scene.name}`} onClick={() => void remove(scene)}>
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </TooltipHint>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
