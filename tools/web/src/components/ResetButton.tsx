import * as React from "react";
import { RotateCcwIcon } from "lucide-react";
import { cn } from "utils";
import { Button } from "./ui/button";

export function ResetButton({ className, ...props }: React.ComponentProps<"button">): React.JSX.Element {
  return (
    <Button type="button" size="icon-sm" variant="outline"
      className={cn("size-7 bg-background text-muted-foreground shadow-studio-inset hover:bg-accent hover:text-accent-foreground disabled:border-transparent disabled:bg-transparent disabled:opacity-25 disabled:shadow-none dark:bg-background dark:hover:bg-accent dark:disabled:border-transparent dark:disabled:bg-transparent", className)}
      {...props}>
      <RotateCcwIcon className="size-3.5" aria-hidden="true" />
    </Button>
  );
}
