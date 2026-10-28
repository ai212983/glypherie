import * as React from "react";
import { cn } from "utils";
import type { CanvasFrame } from "./canvas-palettes.js";

interface SpecimenFrameProps extends React.ComponentProps<"div"> {
  frame: CanvasFrame;
}

export function SpecimenFrame({ frame, className, style, ...props }: SpecimenFrameProps): React.JSX.Element {
  return (
    <div
      {...props}
      className={cn("rounded-[12px] border p-4 shadow-[inset_0_2px_4px_rgb(0_0_0/5%)]", className)}
      style={{
        backgroundColor: frame.paperCss,
        borderColor: frame.borderCss,
        "--specimen-paper": frame.paperCss,
        "--specimen-ink": frame.inkCss,
        "--specimen-border": frame.borderCss,
        ...style,
      } as React.CSSProperties}
    />
  );
}

interface SpecimenFooterProps extends React.ComponentProps<"div"> {
  frame: CanvasFrame;
  bordered?: boolean;
}

export function SpecimenFooter({ frame, bordered = true, className, style, ...props }: SpecimenFooterProps): React.JSX.Element {
  return (
    <div
      {...props}
      className={cn("flex flex-col items-end gap-1.5", bordered && "border-t pt-4", className)}
      style={{ borderColor: frame.dividerCss, ...style }}
    />
  );
}
