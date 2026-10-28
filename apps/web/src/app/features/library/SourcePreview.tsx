import { userError } from "../../user-error";
import * as React from "react";
import type { StoredFont } from "../../fonts/storage";
import { controlAxes } from "../../fonts/metadata";

interface SourcePreviewProps {
  font: StoredFont;
  text: string;
  sizePx: number;
  zoom: number;
  ink: string;
}

// FontFace consumes the original bytes. CSS axes override size-dependent
// optical selection, and synthesis is disabled so the source design is used.
// https://www.w3.org/TR/css-font-loading-3/#fontface-interface
export function SourcePreview({ font, text, sizePx, zoom, ink }: SourcePreviewProps): React.JSX.Element {
  const family = `source-${font.id}`;
  const axes = React.useMemo(() => controlAxes(font.metadata)
    .map((axis) => `${JSON.stringify(axis.tag)} ${axis.defaultValue}`).join(", ") || "normal", [font.metadata]);
  const [load, setLoad] = React.useState<{ font: StoredFont; error?: string } | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    const face = new FontFace(family, font.bytes.slice(0));
    void face.load().then(() => {
      if (cancelled) return;
      document.fonts.add(face);
      setLoad({ font });
    }).catch((failure: unknown) => {
      if (!cancelled) setLoad({ font, error: userError(failure, "Couldn’t load font.") });
    });
    return () => { cancelled = true; document.fonts.delete(face); };
  }, [font, family]);

  // Do not silently substitute another font for encoded-character gaps.
  const ranges = font.metadata.coverage?.ranges;
  const missing = ranges ? [...text].filter((character) => {
    if (character === "\n" || character === "\r" || character === "\t") return false;
    const codepoint = character.codePointAt(0)!;
    return !ranges.some(([start, end]) => codepoint >= start && codepoint <= end);
  }).length : 0;
  const error = missing > 0 ? `${missing} character${missing === 1 ? "" : "s"} not in this font.`
    : load?.font === font ? load.error : undefined;
  const ready = load?.font === font && !error;
  return (
    <div data-card-preview={font.id} className="min-w-0 pt-1">
      {error ? <p data-card-error={font.id} className="m-0 text-[12px]" style={{ color: ink }}>{error}</p>
        : ready ? (
          <div data-source-preview={font.id} data-rendered="true"
            style={{
              fontFamily: `"${family}"`, fontVariationSettings: axes, fontOpticalSizing: "none",
              fontSynthesis: "none", fontKerning: "normal", fontVariantLigatures: "none",
              fontSize: sizePx * zoom, lineHeight: 1.4, letterSpacing: 0,
              whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: ink,
            }}>{text}</div>
        ) : <p role="status" className="m-0 text-[12px]" style={{ color: ink }}>Loading source font…</p>}
    </div>
  );
}
