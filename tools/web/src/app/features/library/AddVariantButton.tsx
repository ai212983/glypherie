import * as React from "react";
import type { StoredFont } from "../../fonts/storage";
import { userError } from "../../user-error";
import { SpecimenButton } from "./SpecimenButton";

export function AddVariantButton({ font, onAdd }: { font: StoredFont; onAdd: (font: StoredFont) => Promise<void> }): React.JSX.Element {
  const [adding, setAdding] = React.useState(false);
  const [error, setError] = React.useState("");
  return (
    <>
      <SpecimenButton data-add-variant={font.id} disabled={adding} onClick={() => {
        if (adding) return;
        setAdding(true);
        setError("");
        void onAdd(font)
          .catch((failure: unknown) => setError(userError(failure, "Couldn’t add variant.")))
          .finally(() => setAdding(false));
      }}>{adding ? "Adding…" : "Add variant"}</SpecimenButton>
      {error && <p className="m-0 font-studio text-[10px] leading-4 text-destructive" role="alert" data-add-variant-error={font.id}>{error}</p>}
    </>
  );
}
