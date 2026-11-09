// Inspector for the selected scene label: typography reference (saved
// variant style or direct font) and position. Reference changes only relink
// the label to another saved style or direct font and never mutate shared
// state. Weight and Size for a variant label show the style's saved values
// read-only; a direct label carries its own editable size and wght override
// (null means the selected font's default). Wrap width stays internal: the
// resize gesture owns it, never the typography panel.
import * as React from "react";
import { Move, Plus, Type } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui/select";
import type { StoredFont } from "../../fonts/storage.js";
import type { VariantSettings } from "../../variants/model.js";
import type { DomainPlacementView, DomainTextStyleView, SceneLabelPatch } from "../scenes/service.js";
import { directWghtAxis, effectiveDirectWeight } from "./direct-label.js";

function styleLabel(style: DomainTextStyleView): string {
  return `${style.name} — ${style.fontSize}px`;
}

function targetOf(placement: DomainPlacementView): string {
  return placement.textStyleId !== null ? `style:${placement.textStyleId}` : `font:${placement.fontId}`;
}

export function LabelInspector({
  placement,
  styles,
  fonts,
  variantSettings,
  sceneWidth,
  saving,
  onPatch,
}: {
  placement: DomainPlacementView;
  styles: DomainTextStyleView[];
  fonts: StoredFont[];
  // Resolved render settings for a variant-backed label; absent while the
  // style still resolves or failed to resolve.
  variantSettings?: VariantSettings;
  sceneWidth: number;
  saving: boolean;
  onPatch: (patch: SceneLabelPatch) => void;
}): React.JSX.Element {
  const directFont =
    placement.textStyleId === null ? (fonts.find((font) => font.id === placement.fontId) ?? null) : null;
  const directAxis = directWghtAxis(directFont);
  const directWeight = directFont ? (effectiveDirectWeight(directFont, placement.fontWeight) ?? null) : null;
  const directWeightFallback =
    directFont && !directAxis
      ? typeof directFont.metadata.style?.weight_class === "number" &&
        Number.isFinite(directFont.metadata.style.weight_class)
        ? String(directFont.metadata.style.weight_class)
        : null
      : null;
  const [x, setX] = React.useState(String(placement.x));
  const [y, setY] = React.useState(String(placement.y));
  const [size, setSize] = React.useState(placement.fontSize === null ? "" : String(placement.fontSize));
  const [weight, setWeight] = React.useState(directWeight === null ? "" : String(directWeight));
  // A background position save can commit new coordinates while the user
  // types here; committed values adopt only into fields without focus, so
  // an in-flight draft survives the re-render until commit or selection change.
  const placementIdRef = React.useRef(placement.id);
  React.useEffect(() => {
    const focusedId = document.activeElement instanceof HTMLElement ? document.activeElement.id : "";
    const switched = placement.id !== placementIdRef.current;
    if (switched || focusedId !== `inspector-x-${placement.id}`) setX(String(placement.x));
    if (switched || focusedId !== `inspector-y-${placement.id}`) setY(String(placement.y));
    if (switched || focusedId !== `inspector-size-${placement.id}`) {
      setSize(placement.fontSize === null ? "" : String(placement.fontSize));
    }
    if (switched || focusedId !== `inspector-weight-${placement.id}`) {
      setWeight(directWeight === null ? "" : String(directWeight));
    }
    placementIdRef.current = placement.id;
  }, [
    placement.x,
    placement.y,
    placement.fontSize,
    placement.fontId,
    placement.fontWeight,
    placement.id,
    directWeight,
  ]);

  const commitPosition = (): void => {
    const parsedX = Math.round(Number(x));
    const parsedY = Math.round(Number(y));
    if (!Number.isInteger(parsedX) || !Number.isInteger(parsedY)) return;
    if (parsedX === placement.x && parsedY === placement.y) return;
    onPatch({ x: parsedX, y: parsedY });
  };

  const commitSize = (): void => {
    if (placement.textStyleId !== null) return;
    const parsed = Math.round(Number(size));
    if (!Number.isInteger(parsed) || parsed === placement.fontSize) return;
    onPatch({ fontSize: parsed });
  };

  const commitWeight = (): void => {
    if (placement.textStyleId !== null || !directAxis) return;
    const parsed = Number(weight);
    if (!Number.isFinite(parsed) || parsed < 1 || parsed > 1000) {
      setWeight(directWeight === null ? "" : String(directWeight));
      return;
    }
    const clamped = Math.min(directAxis.max, Math.max(directAxis.min, parsed));
    if (clamped === directWeight) {
      if (String(clamped) !== weight) setWeight(String(clamped));
      return;
    }
    onPatch({ fontWeight: clamped });
  };

  const onReferenceChange = (target: string): void => {
    if (target === targetOf(placement)) return;
    if (target.startsWith("style:")) {
      onPatch({ textStyleId: target.slice("style:".length) });
      return;
    }
    if (target.startsWith("font:")) {
      const fontId = target.slice("font:".length);
      // A variant-to-font switch keeps the painted size and wrap so the
      // label does not jump; the new reference stays fully editable after.
      const fontSize =
        placement.textStyleId !== null
          ? Math.round(
              variantSettings?.sizePx ?? styles.find((style) => style.id === placement.textStyleId)?.fontSize ?? 16,
            )
          : (placement.fontSize ?? 16);
      const wrap =
        placement.textStyleId !== null
          ? Math.max(1, sceneWidth - placement.x)
          : (placement.width ?? Math.max(1, sceneWidth - placement.x));
      // A variant-to-font switch preserves the style's resolved wght inside
      // the destination font's support; the domain carries it when the patch
      // carries none (for example while the style still resolves).
      const resolvedWght = placement.textStyleId !== null ? variantSettings?.axes["wght"] : placement.fontWeight;
      const destination = fonts.find((font) => font.id === fontId) ?? null;
      const destinationAxis = directWghtAxis(destination);
      const preserved =
        destinationAxis !== null && typeof resolvedWght === "number" && Number.isFinite(resolvedWght)
          ? Math.min(destinationAxis.max, Math.max(destinationAxis.min, resolvedWght))
          : undefined;
      onPatch(
        preserved === undefined
          ? { fontId, fontSize, width: wrap }
          : { fontId, fontSize, width: wrap, fontWeight: preserved },
      );
    }
  };

  const isVariant = placement.textStyleId !== null;
  const savedWeight = variantSettings?.axes["wght"];
  const savedSize = variantSettings?.sizePx ?? styles.find((style) => style.id === placement.textStyleId)?.fontSize;

  return (
    <>
      <Card data-scene-typography={placement.id}>
        <CardHeader>
          <CardTitle asChild>
            <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-widest text-soft uppercase">
              <Type aria-hidden="true" className="size-3.5 shrink-0" />
              Typography
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Select
              value={targetOf(placement)}
              disabled={saving || (styles.length === 0 && fonts.length === 0)}
              onValueChange={onReferenceChange}
            >
              <SelectTrigger
                id={`inspector-style-${placement.id}`}
                data-scene-inspector-style
                aria-label="Label font or text style"
                className="w-full min-w-0"
              >
                <SelectValue placeholder="Choose a text style or font" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Variants</SelectLabel>
                  {styles.map((style) => (
                    <SelectItem key={style.id} value={`style:${style.id}`}>
                      {styleLabel(style)}
                    </SelectItem>
                  ))}
                </SelectGroup>
                <SelectGroup>
                  <SelectLabel>Fonts</SelectLabel>
                  {fonts.map((font) => (
                    <SelectItem key={font.id} value={`font:${font.id}`}>
                      {font.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              data-scene-typography-plus
              aria-label="Add font or variant"
              disabled={saving}
              onClick={() => undefined}
            >
              <Plus aria-hidden="true" />
            </Button>
          </div>
          {isVariant ? (
            <div className="flex flex-wrap gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Label htmlFor={`inspector-weight-${placement.id}`} className="shrink-0 text-soft">
                  Weight
                </Label>
                <Input
                  id={`inspector-weight-${placement.id}`}
                  data-scene-typography-weight
                  value={
                    typeof savedWeight === "number" && Number.isFinite(savedWeight)
                      ? String(Math.round(savedWeight))
                      : "—"
                  }
                  readOnly
                  disabled={saving}
                  className="min-w-0 flex-1 text-right"
                />
              </div>
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Label htmlFor={`inspector-size-${placement.id}`} className="shrink-0 text-soft">
                  Size
                </Label>
                <Input
                  id={`inspector-size-${placement.id}`}
                  data-scene-typography-size
                  value={savedSize === undefined ? "—" : String(savedSize)}
                  readOnly
                  disabled={saving}
                  className="min-w-0 flex-1 text-right"
                />
                <span aria-hidden="true" className="shrink-0 text-xs text-soft">
                  px
                </span>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Label htmlFor={`inspector-size-${placement.id}`} className="shrink-0 text-soft">
                  Size
                </Label>
                <Input
                  id={`inspector-size-${placement.id}`}
                  data-scene-typography-size
                  type="number"
                  min={1}
                  max={512}
                  value={size}
                  disabled={saving}
                  className="min-w-0 flex-1 text-right"
                  onChange={(event) => setSize(event.target.value)}
                  onBlur={commitSize}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                  }}
                />
                <span aria-hidden="true" className="shrink-0 text-xs text-soft">
                  px
                </span>
              </div>
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Label htmlFor={`inspector-weight-${placement.id}`} className="shrink-0 text-soft">
                  Weight
                </Label>
                <Input
                  id={`inspector-weight-${placement.id}`}
                  data-scene-typography-weight
                  type={directAxis ? "number" : undefined}
                  min={directAxis?.min}
                  max={directAxis?.max}
                  step={directAxis ? 1 : undefined}
                  value={directAxis ? weight : (directWeightFallback ?? "—")}
                  readOnly={!directAxis}
                  disabled={saving || !directAxis}
                  className="min-w-0 flex-1 text-right"
                  onChange={(event) => setWeight(event.target.value)}
                  onBlur={commitWeight}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                  }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      <Card data-scene-inspector={placement.id}>
        <CardHeader>
          <CardTitle asChild>
            <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-widest text-soft uppercase">
              <Move aria-hidden="true" className="size-3.5 shrink-0" />
              Position
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Label htmlFor={`inspector-x-${placement.id}`} className="shrink-0 text-soft">
                X
              </Label>
              <Input
                id={`inspector-x-${placement.id}`}
                data-scene-inspector-x
                type="number"
                value={x}
                disabled={saving}
                className="min-w-0 flex-1 text-right"
                onChange={(event) => setX(event.target.value)}
                onBlur={commitPosition}
                onKeyDown={(event) => {
                  if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                }}
              />
              <span aria-hidden="true" className="shrink-0 text-xs text-soft">
                px
              </span>
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Label htmlFor={`inspector-y-${placement.id}`} className="shrink-0 text-soft">
                Y
              </Label>
              <Input
                id={`inspector-y-${placement.id}`}
                data-scene-inspector-y
                type="number"
                value={y}
                disabled={saving}
                className="min-w-0 flex-1 text-right"
                onChange={(event) => setY(event.target.value)}
                onBlur={commitPosition}
                onKeyDown={(event) => {
                  if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                }}
              />
              <span aria-hidden="true" className="shrink-0 text-xs text-soft">
                px
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
