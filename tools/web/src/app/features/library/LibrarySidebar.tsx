import * as React from "react";
import { MAX_TEXT_LENGTH, TEXT_DEFAULT } from "../../renderer/render-spec";
import { Input } from "../../../components/ui/input";
import { FontSizeControl } from "../../../components/FontSizeControl";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import specimenIcon from "../../../components/ui/assets/glypherie/specimen.svg";
import importFontIcon from "../../../components/ui/assets/glypherie/import-font.svg";
import type { LibraryBaseSize } from "./preferences";
import { SampleTextControl } from "./SampleTextControl";
import "./LibrarySidebar.css";

interface LibrarySidebarProps {
  sampleText: string;
  sampleBaseSize: LibraryBaseSize;
  importStatus: string;
  onSampleText: (text: string) => void;
  onSampleBaseSize: (size: LibraryBaseSize) => void;
  onImport: (files: FileList | null) => void;
}

export function LibrarySidebar({
  sampleText, sampleBaseSize, importStatus,
  onSampleText, onSampleBaseSize, onImport,
}: LibrarySidebarProps): React.JSX.Element {
  return (
    <aside
      aria-labelledby="library-controls-heading"
      className="library-sidebar studio-card flex w-full shrink-0 flex-col gap-5 border-b border-studio-border bg-font-card p-4 lg:h-full lg:min-h-0 lg:w-96 lg:overflow-y-auto lg:border-r lg:border-b-0"
    >
      <Card>
        <CardHeader>
          <CardTitle asChild>
            <h2 id="library-controls-heading">
              <span aria-hidden="true" className="library-title-icon h-[10px] w-[11.25px]" style={{ maskImage: `url(${specimenIcon})` }} />
              Preview
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <SampleTextControl
            id="index-sample"
            data-index-text
            maxLength={MAX_TEXT_LENGTH}
            placeholder={TEXT_DEFAULT}
            value={sampleText}
            onValueChange={onSampleText}
          />
          <FontSizeControl id="library-font-size" sizePx={sampleBaseSize} onSize={onSampleBaseSize} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild>
            <h2>
              <span aria-hidden="true" className="library-title-icon h-[13.3333px] w-[10.6667px]" style={{ maskImage: `url(${importFontIcon})` }} />
              Import fonts
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="font-import m-0 flex flex-col items-start gap-2">
          <Input
            type="file"
            accept=".ttf,.otf"
            multiple
            data-import-font
            aria-label="Import font files"
            className="h-auto w-full rounded-lg border-border bg-background p-2 text-[10px] leading-4 font-normal shadow-studio-inset file:mr-2 file:rounded file:bg-accent file:px-2 file:text-[10px] file:font-bold file:text-accent-foreground md:text-[10px] dark:bg-background"
            onChange={(event) => { onImport(event.target.files); event.target.value = ""; }}
          />
          {importStatus && <span className="text-[10px] leading-4 font-normal text-muted-foreground [overflow-wrap:anywhere]" role="status" data-import-status>{importStatus}</span>}
        </CardContent>
      </Card>
    </aside>
  );
}
