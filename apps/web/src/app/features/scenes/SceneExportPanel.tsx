// Scene ZIP export panel: bitmap fonts for the supplied text styles with the
// scene's output profile and saved export coverage. Failures name the
// style and abort the archive; missing ranges stay visible, never silently
// truncated.
import * as React from "react";
import { Download } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { useRenderer } from "../../renderer/renderer-context";
import { getFont } from "../../fonts/storage";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import { coverageCount, formatCustomRange, resolveCoverage } from "../../domain/coverage";
import {
  exportTextStylesToZip,
  FontExportError,
  type FontExportServices,
  type FontExportStyleSnapshot,
} from "../../domain/font-export";
import type { DomainSceneView, DomainTextStyleView } from "./service";
import { resolveTextStyles } from "./service";
import { isConflict } from "./conflict";

export function SceneExportPanel({
  scene,
  textStyles,
  directFonts,
  library,
}: {
  scene: DomainSceneView;
  textStyles: DomainTextStyleView[];
  // Direct-font labels resolved by the workspace with the same settings as
  // the preview; exported alongside the text styles in one archive.
  directFonts?: FontExportStyleSnapshot[];
  library: FontLibrary;
}): React.JSX.Element {
  const { service } = useRenderer();
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState("");
  const [error, setError] = React.useState("");
  const [completed, setCompleted] = React.useState<string[]>([]);
  const [missingNote, setMissingNote] = React.useState("");
  const readyRef = React.useRef<ReadonlySet<string>>(new Set());
  readyRef.current = library.loadedIds;

  const extras = directFonts ?? [];
  const fontIds = React.useMemo(
    () => [...new Set([...textStyles.map((style) => style.fontId), ...extras.map((snapshot) => snapshot.fontId)])],
    [textStyles, extras],
  );
  React.useEffect(() => {
    library.ensureLoaded(fontIds);
  }, [library, fontIds]);
  const pendingFonts = fontIds.filter((fontId) => !library.loadedIds.has(fontId));
  const failedStyles = textStyles.filter((style) => library.loadStatus(style.fontId).state === "error");
  const failedFontIds = new Set(failedStyles.map((style) => style.fontId));
  const loadingFonts = pendingFonts.filter((fontId) => !failedFontIds.has(fontId));
  const coverageScalars = coverageCount(resolveCoverage(scene.exportCoverage));

  const download = async (): Promise<void> => {
    if (!service || busy) return;
    const renderer = service;
    setBusy(true);
    setError("");
    setCompleted([]);
    setMissingNote("");
    try {
      const services: FontExportServices = {
        resolveTextStyles: (textStyleIds, outputProfileId) => resolveTextStyles(textStyleIds, outputProfileId),
        fontCoverage: async (fontId) => {
          const stored = await getFont(fontId);
          const ranges = stored?.metadata.coverage?.ranges;
          return ranges ? ranges.map(([start, end]) => ({ start, end })) : null;
        },
        ensureFontReady: async (fontId) => {
          library.ensureLoaded(fontId);
          if (!readyRef.current.has(fontId)) {
            throw new Error("is still loading into the renderer; try again once it is ready.");
          }
        },
        exportPlaydate: (fontId, request) => renderer.exportPlaydate(fontId, request),
      };
      const result = await exportTextStylesToZip(
        {
          textStyleIds: textStyles.map((style) => style.id),
          outputProfileId: scene.outputProfileId,
          coverage: scene.exportCoverage,
          format: "playdate",
          extraSnapshots: extras,
        },
        services,
        ({ done, total, name }) => setProgress(`Exporting ${name} (${done + 1} of ${total})…`),
      );
      const copy = result.bytes.slice();
      const url = URL.createObjectURL(new Blob([copy.buffer as ArrayBuffer], { type: "application/zip" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = result.fileName;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setProgress("");
      setCompleted(result.files);
      if (result.missing.length > 0) {
        setMissingNote(
          result.missing.map((entry) => `${entry.name}: ${entry.ranges.map(formatCustomRange).join(", ")}`).join("; "),
        );
      }
    } catch (failure) {
      setProgress("");
      if (failure instanceof FontExportError) {
        setError(failure.failures.map((entry) => `"${entry.name}": ${entry.message}`).join(" "));
      } else if (isConflict(failure)) {
        setError("The scene changed in another tab. Reload it before exporting again.");
      } else {
        setError(failure instanceof Error ? failure.message : String(failure));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Scene export" data-scene-export className="flex min-w-0 flex-col gap-2">
      <p className="m-0 text-xs text-soft">
        Exports all {textStyles.length + extras.length} text styles
        {extras.length === 0 ? "" : ` (including ${extras.length} direct font${extras.length === 1 ? "" : "s"})`} as
        Playdate bitmap fonts ({coverageScalars} characters) in one ZIP.
      </p>
      {loadingFonts.length > 0 && (
        <p className="m-0 text-xs text-soft">
          Loading {loadingFonts.length} font{loadingFonts.length === 1 ? "" : "s"}…
        </p>
      )}
      {failedStyles.length > 0 && (
        <p role="alert" className="m-0 text-xs" data-scene-export-font-error>
          Couldn’t load {failedStyles.map((style) => style.name).join(", ")} into the renderer.
        </p>
      )}
      <div>
        <Button
          data-scene-export-zip
          disabled={busy || !service || pendingFonts.length > 0 || textStyles.length + extras.length === 0}
          onClick={() => void download()}
        >
          <Download aria-hidden="true" className="size-3 shrink-0" />
          {busy ? "Exporting…" : "Export ZIP"}
        </Button>
      </div>
      {progress && (
        <p role="status" className="m-0 text-xs" data-scene-export-progress>
          {progress}
        </p>
      )}
      {error && (
        <p role="alert" className="m-0 text-xs" data-scene-export-error>
          {error}
        </p>
      )}
      {completed.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1">
          <p role="status" className="m-0 text-xs" data-scene-export-success>
            Downloaded {completed.length} font{completed.length === 1 ? "" : "s"}: {completed.join(", ")}
          </p>
          {missingNote && (
            <p className="m-0 text-xs text-soft" data-scene-export-missing>
              Missing from fonts: {missingNote}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
