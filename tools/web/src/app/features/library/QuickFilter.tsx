import * as React from "react";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import searchIcon from "../../../components/ui/assets/glypherie/search.svg";

interface QuickFilterProps {
  value: string;
  onChange: (value: string) => void;
}

export function QuickFilter({ value, onChange }: QuickFilterProps): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-1 justify-end sm:flex-none">
      <Label htmlFor="library-filter" className="sr-only">Filter fonts</Label>
      <div className="relative w-full min-w-0 sm:w-[219px]">
        <span
          aria-hidden="true"
          className="library-title-icon pointer-events-none absolute top-1/2 left-[14px] h-3 w-3 -translate-y-1/2 text-studio-muted"
          style={{ maskImage: `url(${searchIcon})` }}
        />
        <Input
          id="library-filter"
          data-library-filter
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="Filter fonts…"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-[30px] w-full rounded-full border-studio-border bg-studio-inset pr-3 pl-[37px] font-studio text-[12px] text-muted-foreground shadow-studio-inset md:text-[12px]"
        />
      </div>
    </div>
  );
}
