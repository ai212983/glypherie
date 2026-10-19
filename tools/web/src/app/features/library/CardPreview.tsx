import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import { controlAxes, defaultAxesValue } from "../../fonts/metadata";
import { FontCanvas } from "../../renderer/FontCanvas.js";

const CARD_SIZE_PX = 16;

interface CardPreviewProps {
  font: StoredFont;
  text: string;
  zoom: number;
  loaded: boolean;
  loadError: string;
}

// Library card preview: candidate Mono at the constant card size and the
// font's default axes over the shared FontCanvas. Markup, diagnostics and
// canvas data hooks stay exactly as the card browser coverage expects.
export function CardPreview({ font, text, zoom, loaded, loadError }: CardPreviewProps): React.JSX.Element {
  const [error, setError] = React.useState("");
  const [missing, setMissing] = React.useState(0);
  const [truncated, setTruncated] = React.useState(false);
  const axes = React.useMemo(() => defaultAxesValue(controlAxes(font.metadata)), [font.metadata]);
  const empty = text.length === 0;

  React.useEffect(() => {
    if (empty) {
      setError("");
      setMissing(0);
      setTruncated(false);
    }
  }, [empty]);

  // Empty-sample visibility is this card's policy: it unmounts the canvas
  // (cancelling pending work) instead of asking FontCanvas to hide itself.
  return (
    <>
      {!empty && (
        <FontCanvas
          fontId={font.id}
          text={text}
          sizePx={CARD_SIZE_PX}
          axes={axes}
          profile="mono_1bit"
          role="candidate"
          spacing={0}
          kerning
          stemFitting="font_hints_first"
          zoom={zoom}
          mode="normal"
          ready={loaded && !loadError}
          debounceMs={0}
          clearOnError
          viewportProps={{ "data-card-preview": font.id, "aria-hidden": true, className: "block min-w-0" }}
          canvasProps={{ "data-card-canvas": font.id, className: "block h-auto w-full [image-rendering:pixelated]" }}
          debugIdentity={(width) => ({ font: font.id, width, zoom, text, axes })}
          exposeFullHeight
          onPaint={(diagnostics) => {
            setMissing(diagnostics.missing);
            setTruncated(diagnostics.truncated);
            setError("");
          }}
          onError={(message) => {
            setMissing(0);
            setTruncated(false);
            setError(message);
          }}
        />
      )}
      {(loadError || error) && (
        <p data-card-error={font.id} className="px-4 pb-2 text-[.75rem] text-soft">{loadError || error}</p>
      )}
      {!loadError && !error && !empty && truncated && (
        <p data-card-limit={font.id} className="px-4 pb-2 text-[.75rem] text-soft">
          Text too long to preview fully. Shorten the sample or reduce zoom.
        </p>
      )}
      {!loadError && !error && !empty && missing > 0 && (
        <p data-card-glyphs={font.id} className="px-4 pb-2 text-[.75rem] text-soft">
          {`${missing} character${missing === 1 ? "" : "s"} not in this font.`}
        </p>
      )}
    </>
  );
}
