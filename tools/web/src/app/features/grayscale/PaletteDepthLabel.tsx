import * as React from "react";
import { cn } from "utils";

export function paletteDepthLabel(count: number, sizePx?: number): string {
  const bits = Math.log2(count);
  const depth = Number.isInteger(bits) ? `${bits}-bit · ${count} levels` : `${count} levels`;
  return sizePx === undefined ? depth : `${sizePx} px / ${depth}`;
}

export function PaletteDepthLabel({ count, sizePx, className, ...props }: {
  count: number;
  sizePx?: number;
} & React.ComponentProps<"span">): React.JSX.Element {
  return <span {...props} data-palette-depth={count}
    className={cn("inline-block max-w-full font-studio text-[9px] leading-4 font-normal whitespace-normal text-balance normal-case", className)}>
    {paletteDepthLabel(count, sizePx)}
  </span>;
}
