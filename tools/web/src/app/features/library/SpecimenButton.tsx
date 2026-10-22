import * as React from "react";
import { cn } from "utils";

export const specimenControlClassName = cn(
  "inline-flex h-7 shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-[5px] border px-2.5 font-studio text-[10px] leading-4 font-bold whitespace-nowrap transition-colors outline-none",
  "border-[var(--specimen-border)] bg-[var(--specimen-paper)] text-[var(--specimen-ink)]",
  "hover:border-[var(--specimen-ink)] hover:bg-[var(--specimen-ink)] hover:text-[var(--specimen-paper)]",
  "active:translate-y-px",
  "focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--specimen-ink)]",
  "disabled:pointer-events-none disabled:opacity-50",
);

export function SpecimenButton({
  className,
  ...props
}: React.ComponentProps<"button">): React.JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        specimenControlClassName,
        className,
      )}
      {...props}
    />
  );
}
