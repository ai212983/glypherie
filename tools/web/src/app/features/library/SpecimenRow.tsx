import * as React from "react";
import { Slot } from "radix-ui";
import { Trash2Icon } from "lucide-react";
import { cn } from "utils";
import type { CanvasFrame } from "./canvas-palettes.js";

type DataAttributes = { [key: `data-${string}`]: string | number | boolean | undefined };

interface SpecimenRowProps {
  frame: CanvasFrame;
  action: React.ReactElement;
  name: string;
  caption: React.ReactNode;
  selected?: boolean;
  tintAttributes?: DataAttributes;
  deleteButton?: Omit<React.ComponentProps<"button">, "children" | "title"> & DataAttributes;
  deleteError?: React.ReactNode;
  children?: React.ReactNode;
}

export function SpecimenRow({
  frame, action, name, caption, selected = false, tintAttributes, deleteButton, deleteError, children,
}: SpecimenRowProps): React.JSX.Element {
  return (
    <div className="group flow-root relative">
      <Slot.Root
        className="relative -mx-2 block w-[calc(100%+1rem)] min-w-0 cursor-pointer rounded-[6px] px-2 py-1 text-left no-underline focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2"
        style={{ outlineColor: frame.inkCss }}
      >
        <Slot.Slottable>{action}</Slot.Slottable>
        <span
          {...tintAttributes}
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-0 z-20 rounded-[6px] bg-[color-mix(in_srgb,var(--specimen-ink)_6%,transparent)]",
            selected ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
          )}
        />
        <div className={cn("flex min-h-5 w-full min-w-0 items-center gap-2 font-studio text-[9px] leading-4", deleteButton && "pr-7")}>
          <span className="min-w-0 flex-1 text-left [overflow-wrap:anywhere]" style={{ color: frame.inkCss }}>{name}</span>
          <span className="shrink-0" style={{ color: frame.mutedCss }}>{caption}</span>
        </div>
        {children}
      </Slot.Root>
      {deleteButton && (
        <div className="absolute top-1 right-0 z-10 flex h-5 items-center">
          <button
            type="button"
            {...deleteButton}
            className={cn(
              "flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded-[4px] border-0 bg-transparent p-0 text-[var(--specimen-ink)] outline-none hover:bg-[color-mix(in_srgb,var(--specimen-ink)_12%,transparent)] focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--specimen-ink)] disabled:pointer-events-none disabled:opacity-50",
              deleteButton.className,
            )}
          >
            <Trash2Icon className="size-3" aria-hidden="true" />
          </button>
        </div>
      )}
      {deleteError}
    </div>
  );
}
