import { userError } from "../../user-error";
import * as React from "react";
import { Type } from "lucide-react";
import type { StoredFont } from "../../fonts/storage.js";
import type { FontVariant } from "../../variants/model.js";
import { VariantStorageError } from "../../variants/repository.js";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import { FontEditor } from "../preview/FontEditor";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { indexPath, variantPath } from "../../navigation/router.js";
import { readRouteSearch } from "../../navigation/snapshot";
import { NavLink } from "../../../components/NavLink";
import { SiteHeader } from "../../shell/SiteHeader";
import { useLiveVariant } from "../../variants/useFontVariants.js";
import { useVariantDraft } from "../../variants/useVariantDraft.js";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { VariantList } from "./VariantList";
import type { LibraryBaseSize } from "../library/preferences";
import "./VariantPage.css";

interface VariantPageProps {
  nav?: React.ReactNode;
  font: StoredFont | null;
  variantId: string;
  baseSize: LibraryBaseSize;
  rootSampleText: string;
  library: FontLibrary;
  onIndex: () => void;
  onOpenVariantId: (fontId: string, variantId: string) => void;
  onVariantDeleted: (name: string) => void;
  onAddVariant: (font: StoredFont) => Promise<void>;
}

interface VariantEditorProps {
  font: StoredFont;
  variant: FontVariant;
  library: FontLibrary;
  sidebar: React.ReactNode;
  rootSampleText: string;
}

// Hydrated editor, keyed by variant id so each variant owns its draft and
// view state. The persisted domain is the FontVariant row edited through the
// shared FontEditor; cross-tab changes surface as an ordinary save error with
// an explicit reload that discards local edits.
function VariantEditor({ font, variant, library, sidebar, rootSampleText }: VariantEditorProps): React.JSX.Element {
  const { draft, status, error, update, retry, reload } = useVariantDraft(variant);
  const [previewStatus, setPreviewStatus] = React.useState("");
  const ready = library.rendererAvailable === true && library.loadedIds.has(font.id);
  const fontLoadError = library.loadStatus(font.id).state === "error"
    ? library.loadStatus(font.id).error
    : "";
  const conflict = error instanceof VariantStorageError && error.code === "conflict";

  const saveError = React.useMemo(() => error ? userError(error, "Couldn’t save changes.") : "", [error]);
  const saveLabel = status === "saving" ? "Saving…" : status === "saved" ? "Saved" : "";

  const sidebarHead = (
    <Card className="gap-5 p-4 sm:p-6">
      <CardHeader>
        <CardTitle asChild>
          <Label htmlFor={`variant-name-${variant.id}`}><Type aria-hidden="true" className="size-3 shrink-0" />Name</Label>
        </CardTitle>
        <CardAction className="self-center text-[10px] leading-4 text-muted-foreground">
          <span role="status" data-save-status>{saveLabel}</span>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2" data-variant-bar>
          <Input
            id={`variant-name-${variant.id}`}
            data-variant-name
            type="text"
            autoComplete="off"
            spellCheck={false}
            maxLength={120}
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
            className="bg-background text-[12px] shadow-studio-inset md:text-[12px]"
          />
        </div>
        {status === "error" && error && (
          <section className="content-state leading-[1.6]" role="alert" data-variant-error={variant.id}>
            <h2>{conflict ? "Another tab changed this variant." : "Couldn’t save changes."}</h2>
            {conflict ? (
              <p>Reloading discards your unsaved changes.</p>
            ) : saveError !== "Couldn’t save changes." && (
              <p>{saveError}</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {conflict ? (
                <Button data-error-reload={variant.id} size="sm" onClick={() => reload()}>
                  Reload saved version
                </Button>
              ) : (
                <Button data-error-retry={variant.id} size="sm" onClick={() => retry()}>
                  Retry save
                </Button>
              )}
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );

  return (
    <FontEditor
      appearance="studio"
      sidebarHead={sidebarHead}
      sidebarStart={sidebar}
      font={font}
      settings={draft.settings}
      sampleText={draft.inheritSampleText ? rootSampleText : draft.sampleText}
      specimenInheritance={{ active: !!draft.inheritSampleText, onInherit: () => update({ inheritSampleText: true }) }}
      onSettings={(settings) => update({ settings })}
      onSampleText={(sampleText) => update({ sampleText, inheritSampleText: false })}
      onReset={() => update({ inheritSampleText: true })}
      resetDisabled={!!draft.inheritSampleText}
      fontReady={ready}
      fontLoadError={fontLoadError}
      previewStatus={previewStatus}
      onStatus={setPreviewStatus}
    />
  );
}

// Thin route host: loading, error, missing, and wrong-font recovery around
// the keyed editor. Navigation is plain route identity; the database owns the
// settings, so leaving never needs a flush gate.
function VariantRoute({
  nav, font, variantId, baseSize, rootSampleText, library, onIndex, onOpenVariantId, onVariantDeleted, onAddVariant, listText, onListText,
}: VariantPageProps & { listText: string; onListText: (text: string) => void }): React.JSX.Element {
  const live = useLiveVariant(variantId);

  React.useEffect(() => {
    if (font) library.ensureLoaded(font.id);
  }, [font, library]);

  const base = readRouteSearch() || window.location.search;
  const indexHref = indexPath(base);
  const header = (): React.JSX.Element => (
    <div className="sticky top-0 z-40 shrink-0">
      <SiteHeader
        title="Glypherie"
        variant="brand"
        nav={nav}

      />
    </div>
  );
  const recovery = (content: React.JSX.Element): React.JSX.Element => (
    <div className="variant-studio flex flex-col lg:h-dvh lg:overflow-hidden">
      {header()}
      <main id="main" className="w-full flex-1 lg:min-h-0 lg:overflow-y-auto">
        <div className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <Card>
            <CardContent>
              {content}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );

  if (!font) {
    return recovery(
      <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-missing>
        <h2>Font not found</h2>
        <p>
          <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>{" "}
        </p>
      </section>,
    );
  }

  if (live.status === "loading") {
    return recovery(
      <p role="status" data-variant-editor={variantId}>Loading variant…</p>,
    );
  }

  if (live.status === "error") {
    return recovery(
      <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-error={variantId}>
        <h2>Couldn’t load variant.</h2>
        <p>{live.message}{" "}
          <button type="button" className="underline" data-variant-retry={variantId} onClick={live.retry}>
            Retry
          </button>{" "}
          or return to{" "}
          <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>.
        </p>
      </section>,
    );
  }

  if (live.status === "missing") {
    return recovery(
      <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-deleted={variantId}>
        <h2>Variant not found</h2>
        <p>
          <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>{" "}
        </p>
      </section>,
    );
  }

  const saved = live.variant;
  if (saved.fontId !== font.id) {
    return recovery(
      <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-wrong-font={variantId}>
        <h2>Variant belongs to another font.</h2>
        <p>
          <NavLink
            href={variantPath(saved.fontId, saved.id)}
            data-variant-correct={saved.id}
            onNavigate={() => onOpenVariantId(saved.fontId, saved.id)}
          >
            Open variant
          </NavLink>{" "}
          or return to{" "}
          <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>.
        </p>
      </section>,
    );
  }

  return (
    <div className="variant-studio flex flex-col lg:h-dvh lg:overflow-hidden">
      {header()}
      <main id="main" data-variant-editor={saved.id} className="w-full flex-1 lg:flex lg:min-h-0 lg:flex-col">
        <div className="flex min-h-[calc(100dvh-56px)] flex-col lg:min-h-0 lg:flex-1 lg:flex-row lg:overflow-hidden">
          <VariantEditor
            key={saved.id}
            font={font}
            variant={saved}
            rootSampleText={rootSampleText}
            library={library}
            sidebar={<VariantList font={font} variantId={saved.id} library={library}
              text={listText} baseSize={baseSize} onText={onListText} onAdd={onAddVariant}
              onOpen={onOpenVariantId} onLastDeleted={onVariantDeleted} />}
          />
        </div>
      </main>
    </div>
  );
}

// Keep the list's comparison text across variant switches; route hydration and
// editor drafts still remount for each variant identity.
export function VariantPage(props: VariantPageProps): React.JSX.Element {
  const [listText, setListText] = React.useState("Aa 0123");
  return <VariantRoute key={props.variantId} {...props} listText={listText} onListText={setListText} />;
}
