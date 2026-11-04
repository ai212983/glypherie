import * as React from "react";
import { Download } from "lucide-react";
import { useRenderer } from "../../renderer/renderer-context";
import type { VariantSettings } from "../../variants/model";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { DEFAULT_CHARACTER_COVERAGE, coverageCount, type CharacterCoverage, type CodepointRange } from "../../domain/coverage";
import { PLAYDATE_EXPORT_MAX_SCALARS } from "../../domain/font-export";
import { CoverageControl } from "./CoverageControl";
import { playdateCoveredRequest, playdateFileName, splitPlaydateCoverage } from "./playdate-export";

export function PlaydateExport({ fontId, name, settings, ready, availableRanges }: {
  fontId: string; name: string; settings: VariantSettings; ready: boolean;
  availableRanges?: readonly CodepointRange[];
}): React.JSX.Element {
  const { service, available } = useRenderer();
  const [coverage, setCoverage] = React.useState<CharacterCoverage>(DEFAULT_CHARACTER_COVERAGE);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [completed, setCompleted] = React.useState(false);
  const mounted = React.useRef(true);
  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  React.useEffect(() => { setError(""); setCompleted(false); }, [coverage, settings]);
  // The 1024 cap applies to the actual covered set, never the full preset
  // union; unknown font coverage generates the full requested set.
  const split = React.useMemo(() => splitPlaydateCoverage(coverage, availableRanges), [coverage, availableRanges]);
  const count = coverageCount(split.supported);
  const mono = settings.profile === "mono_1bit";
  const overLimit = count > PLAYDATE_EXPORT_MAX_SCALARS;
  const download = async (): Promise<void> => {
    if (!service || busy) return;
    setBusy(true);
    setError("");
    setCompleted(false);
    try {
      const bytes = await service.exportPlaydate(fontId, playdateCoveredRequest(settings, coverage, availableRanges));
      if (!mounted.current) return;
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = playdateFileName(name, settings.sizePx);
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setCompleted(true);
    } catch (failure) {
      if (mounted.current) setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <Card data-playdate-export>
      <CardHeader>
        <CardTitle asChild><h2><Download aria-hidden="true" className="size-3 shrink-0" />Export</h2></CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <CoverageControl coverage={coverage} onCoverage={setCoverage} disabled={busy} availableRanges={availableRanges} />
        {!mono && <p className="m-0 text-xs text-soft">Select Monochrome output to export for Playdate.</p>}
        {overLimit && <p className="m-0 text-xs text-soft">Coverage exceeds the 1024-character Playdate limit.</p>}
        <Button data-export-playdate className="self-start" disabled={busy || !ready || available !== true || !mono || count < 1 || overLimit}
          onClick={() => void download()}>
          {busy ? "Exporting…" : "Playdate .fnt"}
        </Button>
        {error && <p role="alert" className="m-0 text-xs" data-export-error>{error}</p>}
        {completed && <p role="status" className="m-0 text-xs">Playdate font downloaded.</p>}
      </CardContent>
    </Card>
  );
}
