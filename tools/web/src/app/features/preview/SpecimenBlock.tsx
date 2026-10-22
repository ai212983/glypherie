import * as React from "react";
import { cn } from "utils";
import { ResetButton } from "../../../components/ResetButton";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import specimenIcon from "../../../components/ui/assets/glypherie/specimen.svg";
import { SpecimenControls } from "./controls/SpecimenControls";
import "./SpecimenBlock.css";

interface SpecimenBlockProps extends React.ComponentProps<typeof SpecimenControls> {
  onReset?: () => void;
  resetDisabled?: boolean;
  appearance?: "classic" | "studio";
  title?: string;
  status?: React.ReactNode;
  children?: React.ReactNode;
}

export function SpecimenBlock({
  onReset, resetDisabled, appearance = "studio", title = "Specimen", status, children, ...controls
}: SpecimenBlockProps): React.JSX.Element {
  const headingId = React.useId();
  const studio = appearance === "studio";
  return (
    <Card variant={studio ? "default" : "plain"}
      className={cn("specimen-block min-w-0", !studio && "interactive-preview gap-0 overflow-hidden py-0")}
      role="group" aria-labelledby={headingId} data-control-layer="specimen">
      <CardHeader className={studio ? "items-center" : "items-center px-4 pt-[.85rem]"}>
        <CardTitle asChild className={studio ? undefined : "flex items-center gap-[6px] pb-[.35rem] text-[1rem] text-studio-heading"}>
          <h2 id={headingId}>
            <span aria-hidden="true" className="block h-[10px] w-[11.25px] shrink-0 bg-current [mask-position:center] [mask-repeat:no-repeat]" style={{ maskImage: `url(${specimenIcon})` }} />
            {title}
          </h2>
        </CardTitle>
        {onReset && <CardAction className="row-span-1 self-center">
          <ResetButton data-reset aria-label="Reset specimen" disabled={resetDisabled} onClick={onReset} />
        </CardAction>}
        {status}
      </CardHeader>
      <CardContent className={studio ? "flex min-w-0 flex-col gap-3" : "px-4"}>
        <SpecimenControls {...controls} />
      </CardContent>
      {children}
    </Card>
  );
}
