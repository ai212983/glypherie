import * as React from "react";
import { cn } from "utils";
import { SelectTrigger } from "../../../components/ui/select";
import { specimenControlClassName } from "./SpecimenButton";
import type { CanvasFrame } from "./canvas-palettes.js";

export function SpecimenSelectTrigger({
  frame, className, style, ...props
}: React.ComponentProps<typeof SelectTrigger> & { frame: CanvasFrame }): React.JSX.Element {
  return (
    <SelectTrigger
      {...props}
      className={cn(specimenControlClassName, "py-0 shadow-none focus-visible:ring-0 focus-visible:border-[var(--specimen-ink)] dark:bg-[var(--specimen-paper)] dark:hover:bg-[var(--specimen-ink)] [&>svg]:size-3", className)}
      style={{
        "--specimen-paper": frame.paperCss,
        "--specimen-ink": frame.inkCss,
        "--specimen-border": frame.borderCss,
        ...style,
      } as React.CSSProperties}
    />
  );
}
