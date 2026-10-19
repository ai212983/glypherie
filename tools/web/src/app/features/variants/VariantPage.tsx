import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import { defaultVariantSettings, type FontVariant } from "../../variants/model.js";
import { deleteVariant, VariantStorageError } from "../../variants/repository.js";
import { TEXT_DEFAULT } from "../../renderer/render-spec";
import { displayName } from "../../fonts/metadata";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import { FontEditor } from "../preview/FontEditor";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { indexHash, variantHash } from "../../navigation/router.js";
import { readHashSearch } from "../../navigation/snapshot";
import { NavLink } from "../../../components/NavLink";
import { SiteHeader } from "../../shell/SiteHeader";
import { useLiveVariant } from "../../variants/useFontVariants.js";
import { useVariantDraft } from "../../variants/useVariantDraft.js";

interface VariantPageProps {
  font: StoredFont | null;
  variantId: string;
  library: FontLibrary;
  ratio: number;
  onIndex: () => void;
  onOpenVariantId: (fontId: string, variantId: string) => void;
  onVariantDeleted: (name: string) => void;
}

interface VariantEditorProps {
  font: StoredFont;
  variant: FontVariant;
  library: FontLibrary;
  ratio: number;
  onVariantDeleted: (name: string) => void;
}

// Hydrated editor, keyed by variant id so each variant owns its draft and
// view state. The persisted domain is the FontVariant row edited through the
// shared FontEditor; cross-tab changes surface as an ordinary save error with
// an explicit reload that discards local edits.
function VariantEditor({ font, variant, library, ratio, onVariantDeleted }: VariantEditorProps): React.JSX.Element {
  const { draft, status, error, update, retry, reload } = useVariantDraft(variant);
  const [zoom, setZoom] = React.useState(1);
  const [pixelAccurate, setPixelAccurate] = React.useState(false);
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [deleting, setDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState("");
  const ready = library.rendererAvailable === true && library.loadedIds.has(font.id);
  const fontLoadError = library.loadStatus(font.id).state === "error"
    ? library.loadStatus(font.id).error
    : "";
  const conflict = error instanceof VariantStorageError && error.code === "conflict";

  const saveLabel = status === "saving" ? "Saving…" : status === "saved" ? "Saved" : (error?.message ?? "");

  const onDelete = (): void => {
    if (deleting) return;
    setDeleting(true);
    setDeleteError("");
    void deleteVariant(variant.id)
      .then(() => onVariantDeleted(draft.name))
      .catch((failure: unknown) => {
        setDeleteError(failure instanceof Error ? failure.message : String(failure ?? ""));
      })
      .finally(() => setDeleting(false));
  };

  return (
    <main id="main" className="mx-auto w-[min(100%-3rem,1440px)]" data-variant-editor={variant.id}>
      <div className="mt-5 flex flex-wrap items-end gap-x-5 gap-y-3" data-variant-bar>
        <div className="flex min-w-52 flex-1 flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor={`variant-name-${variant.id}`}>Variant name</Label>
          <Input
            id={`variant-name-${variant.id}`}
            data-variant-name
            type="text"
            autoComplete="off"
            spellCheck={false}
            maxLength={120}
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
          />
        </div>
        <p className="m-0 text-[.8rem] text-soft" role="status" data-save-status>{saveLabel}</p>
        <Button data-delete-variant={variant.id} variant="destructive" size="sm" onClick={onDelete} disabled={deleting}>
          {deleting ? "Deleting…" : "Delete variant"}
        </Button>
      </div>
      {status === "error" && error && (
        <section className="content-state my-6 max-w-[45rem] leading-[1.6]" role="alert" data-variant-error={variant.id}>
          <h2>{conflict ? "Another tab changed this variant." : "This variant could not be saved."}</h2>
          {conflict ? (
            <p>Another tab saved this variant first. Reloading replaces your unsaved edits with the saved version.</p>
          ) : (
            <p>{error.message} Changes haven&apos;t been saved.</p>
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
      {(deleteError || previewStatus) && (
        <p className="mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="alert" data-editor-error>
          {deleteError || previewStatus}
        </p>
      )}
      <FontEditor
        font={font}
        settings={draft.settings}
        sampleText={draft.sampleText}
        onSettings={(settings) => update({ settings })}
        onSampleText={(sampleText) => update({ sampleText })}
        onReset={() => update({ settings: defaultVariantSettings(font), sampleText: TEXT_DEFAULT })}
        zoom={zoom}
        pixelAccurate={pixelAccurate}
        onZoom={setZoom}
        onPixelAccurate={setPixelAccurate}
        fontReady={ready}
        fontLoadError={fontLoadError}
        ratio={ratio}
        previewStatus={previewStatus}
        onStatus={setPreviewStatus}
      />
    </main>
  );
}

// Thin route host: loading, error, missing, and wrong-font recovery around
// the keyed editor. Navigation is plain route identity; the database owns the
// settings, so leaving never needs a flush gate.
export function VariantPage({
  font, variantId, library, ratio, onIndex, onOpenVariantId, onVariantDeleted,
}: VariantPageProps): React.JSX.Element {
  const live = useLiveVariant(variantId);

  React.useEffect(() => {
    if (font) library.ensureLoaded(font.id);
  }, [font, library]);

  const base = readHashSearch() || window.location.search;
  const indexHref = `${window.location.pathname}${indexHash(base)}`;
  const header = (title: string): React.JSX.Element => (
    <SiteHeader
      eyebrow={<NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>← All fonts</NavLink>}
      title={title}
    />
  );

  if (!font) {
    return (
      <>
        {header("Font preview")}
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-missing>
            <h2>This font is no longer in the library.</h2>
            <p>It may have been removed in another tab. Return to{" "}
              <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>{" "}
              to pick another.
            </p>
          </section>
        </main>
      </>
    );
  }

  if (live.status === "loading") {
    return (
      <>
        {header(displayName(font))}
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          <p role="status" data-variant-editor={variantId}>Loading variant…</p>
        </main>
      </>
    );
  }

  if (live.status === "error") {
    return (
      <>
        {header(displayName(font))}
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-error={variantId}>
            <h2>This variant could not be loaded.</h2>
            <p>{live.message}{" "}
              <button type="button" className="underline" data-variant-retry={variantId} onClick={live.retry}>
                Retry
              </button>{" "}
              or return to{" "}
              <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>.
            </p>
          </section>
        </main>
      </>
    );
  }

  if (live.status === "missing") {
    return (
      <>
        {header(displayName(font))}
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-deleted={variantId}>
            <h2>This variant no longer exists.</h2>
            <p>It may have been deleted in another tab. Return to{" "}
              <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>{" "}
              to pick another.
            </p>
          </section>
        </main>
      </>
    );
  }

  const saved = live.variant;
  if (saved.fontId !== font.id) {
    return (
      <>
        {header(displayName(font))}
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <section className="content-state my-12 leading-[1.6]" role="alert" data-variant-wrong-font={variantId}>
            <h2>This variant belongs to a different font.</h2>
            <p>
              <NavLink
                href={`${window.location.pathname}${variantHash(saved.fontId, saved.id)}`}
                data-variant-correct={saved.id}
                onNavigate={() => onOpenVariantId(saved.fontId, saved.id)}
              >
                Open it under its own font
              </NavLink>{" "}
              or return to{" "}
              <NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink>.
            </p>
          </section>
        </main>
      </>
    );
  }

  return (
    <>
      {header(displayName(font))}
      <VariantEditor
        key={saved.id}
        font={font}
        variant={saved}
        library={library}
        ratio={ratio}
        onVariantDeleted={onVariantDeleted}
      />
    </>
  );
}
