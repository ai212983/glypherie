import * as React from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export function TooltipHint({ content, children }: { content?: React.ReactNode; children: React.ReactElement }): React.JSX.Element {
  if (!content) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{content}</TooltipContent>
    </Tooltip>
  );
}
