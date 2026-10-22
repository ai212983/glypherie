import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import { licenseBadge } from "../../fonts/metadata";
import { Card } from "../../../components/ui/card";

function InfoBox({ label, value, danger = false, hook, hookValue, ariaLabel }: {
  label: string;
  value: React.ReactNode;
  danger?: boolean;
  hook?: string;
  hookValue?: string;
  ariaLabel?: string;
}): React.JSX.Element {
  return (
    <Card variant="plain"
      className="min-w-0 gap-0 rounded-lg border-studio-border bg-studio-inset p-2 font-studio shadow-studio-inset"
      aria-label={ariaLabel}
      {...(hook && hookValue ? { [hook]: hookValue } : {})}
    >
      <dt className="text-[9px] leading-4 font-normal text-studio-muted uppercase">{label}</dt>
      <dd className={`m-0 wrap-anywhere text-[10px] leading-4 font-bold ${danger ? "text-destructive/80" : "text-studio-foreground"}`}>{value}</dd>
    </Card>
  );
}

export function FontInfoBoxes({ font }: { font: StoredFont }): React.JSX.Element {
  const horizontalKerning = font.metadata.kerning?.horizontal;
  const characterCount = font.metadata.coverage?.character_count;
  const license = licenseBadge(font.metadata);

  const slope = font.metadata.style?.slope;
  const style = slope && slope !== "upright"
    ? slope.charAt(0).toUpperCase() + slope.slice(1)
    : null;

  return (
    <dl className={`m-0 grid w-full gap-2 grid-cols-[repeat(auto-fit,minmax(min(100%,7rem),1fr))] ${style ? "max-w-[728px]" : "max-w-[544px]"}`} data-font-info={font.id}>
      <InfoBox label="Characters" value={characterCount?.toLocaleString("en-US") ?? "Unavailable"} />
      <InfoBox label="Kerning" value={horizontalKerning === true ? "YES" : horizontalKerning === false ? "NO" : "Unavailable"}
        danger={horizontalKerning === false} />
      {style && <InfoBox label="Style" value={style} />}
      <InfoBox label="License" value={license.label}
        hook="data-font-license" hookValue={font.id} ariaLabel={`License: ${license.label}`} />
    </dl>
  );
}
