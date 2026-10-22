import * as React from "react";
import { Download, ListOrdered } from "lucide-react";
import { useRenderer } from "../../renderer/renderer-context";
import type { VariantSettings } from "../../variants/model";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
import { Label } from "../../../components/ui/label";
import { TooltipHint } from "../../../components/TooltipHint";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { PLAYDATE_ASCII, playdateFileName, playdateRequest } from "./playdate-export";

export function PlaydateExport({ fontId, name, settings, ready }: {
  fontId: string; name: string; settings: VariantSettings; ready: boolean;
}): React.JSX.Element {
  const { service, available } = useRenderer();
  const id = React.useId();
  const [characters, setCharacters] = React.useState(PLAYDATE_ASCII);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [completed, setCompleted] = React.useState(false);
  const mounted = React.useRef(true);
  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  React.useEffect(() => { setError(""); setCompleted(false); }, [characters, settings]);
  const count = new Set(characters).size;
  const mono = settings.profile === "mono_1bit";
  const download = async (): Promise<void> => {
    if (!service || busy) return;
    setBusy(true);
    setError("");
    setCompleted(false);
    try {
      const bytes = await service.exportPlaydate(fontId, playdateRequest(settings, characters));
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
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor={id}>{count} characters</Label>
          <TooltipHint content="Sort characters and remove duplicates">
            <Button type="button" variant="ghost" size="icon-xs" aria-label="Sort characters and remove duplicates"
              disabled={busy || count === 0}
              onClick={() => setCharacters((current) => [...new Set(current)]
                .sort((left, right) => left.codePointAt(0)! - right.codePointAt(0)!).join(""))}>
              <ListOrdered aria-hidden="true" />
            </Button>
          </TooltipHint>
        </div>
        <Textarea id={id} data-export-characters value={characters} maxLength={8192} disabled={busy}
          spellCheck={false} onChange={(event) => setCharacters(event.target.value)} />
        {!mono && <p className="m-0 text-xs text-soft">Select Monochrome output to export for Playdate.</p>}
        <Button data-export-playdate className="self-start" disabled={busy || !ready || available !== true || !mono || count < 1 || count > 1024}
          onClick={() => void download()}>
          {busy ? "Exporting…" : "Playdate .fnt"}
        </Button>
        {error && <p role="alert" className="m-0 text-xs" data-export-error>{error}</p>}
        {completed && <p role="status" className="m-0 text-xs">Playdate font downloaded.</p>}
      </CardContent>
    </Card>
  );
}
