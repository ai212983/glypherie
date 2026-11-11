// Centered drawing viewport: the logical device canvas aperture stays
// centered in the scrollport (below the header, beside the rulers), fixed
// pixel rulers share the same scroll origin, and one scroll state drives
// both. Zoom/body/panel changes preserve the centered native point; only a
// device, orientation or dimension change recenters.
import * as React from "react";
import { ScrollArea } from "../../../components/ui/scroll-area.js";
import { Button } from "../../../components/ui/button.js";
import { TooltipHint } from "../../../components/TooltipHint.js";
import { useTheme } from "../../../components/theme/ThemeProvider.js";
import { useLiveRatio } from "../../renderer/live-ratio.js";
import { PixelRuler } from "./PixelRuler.js";
import {
  RULER_SIZE,
  centeredContent,
  centerNative,
  rulerScrollPos,
  rulerUnitForScale,
  scrollToCenterNative,
  type ApertureBox,
} from "./canvas-viewport-geometry.js";

// Label insets into the 22px strip (stable identities: new arrays would
// recreate the ruler instances every render). The painter anchors tick lines
// toward the canvas and text baselines outside the strip, so each axis shifts
// only its labels' cross axis back inside; tick coordinates never move.
const HORIZONTAL_TEXT_OFFSET: readonly [number, number] = [0, 13];
const VERTICAL_TEXT_OFFSET: readonly [number, number] = [8, 0];

export interface CanvasViewportProps extends ApertureBox {
  // Screen px per native device px; the single ruler zoom.
  cssScale: number;
  // Device/orientation/dimension identity; a change recenters the aperture.
  centerKey: string;
  // The body (shell or bare canvas) with the painted stage inside.
  body: React.ReactNode;
}

function rulerTheme(theme: string): { background: string; line: string; text: string; font: string } {
  const font = `10px "Glypherie Mono", ui-monospace, monospace`;
  if (theme === "dark") {
    return { background: "#1c2026", line: "#282e38", text: "#859399", font };
  }
  return { background: "#ffffff", line: "#cdd3db", text: "#647078", font };
}

export function CanvasViewport(props: CanvasViewportProps): React.JSX.Element {
  const { cssScale, centerKey, body, bodyWidth, bodyHeight, apertureX, apertureY, apertureWidth, apertureHeight } =
    props;
  const content = React.useMemo(
    () => centeredContent({ bodyWidth, bodyHeight, apertureX, apertureY, apertureWidth, apertureHeight }),
    [bodyWidth, bodyHeight, apertureX, apertureY, apertureWidth, apertureHeight],
  );
  const { theme } = useTheme();
  const palette = rulerTheme(theme);
  const density = useLiveRatio();

  const viewportElRef = React.useRef<HTMLDivElement | null>(null);
  const [viewport, setViewport] = React.useState({ width: 0, height: 0 });
  const [scroll, setScroll] = React.useState({ x: 0, y: 0 });
  // Synchronous scroll mirror: the browser clamps scrolled content before
  // layout effects run, so the preserve path reads this instead of the
  // already-clamped DOM value. Updated on every scroll event and every
  // programmatic write below.
  const scrollPosRef = React.useRef({ x: 0, y: 0 });
  const geomRef = React.useRef<{
    centerKey: string;
    cssScale: number;
    viewportWidth: number;
    viewportHeight: number;
    canvasX: number;
    canvasY: number;
    contentWidth: number;
    contentHeight: number;
  } | null>(null);

  const setViewportRef = React.useCallback((element: HTMLDivElement | null) => {
    viewportElRef.current = element;
  }, []);

  React.useLayoutEffect(() => {
    const element = viewportElRef.current;
    if (!element) return undefined;
    const measure = (): void =>
      setViewport((current) => {
        const width = element.clientWidth;
        const height = element.clientHeight;
        return current.width === width && current.height === height ? current : { width, height };
      });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const onScroll = React.useCallback((event: React.UIEvent<HTMLDivElement>): void => {
    const target = event.currentTarget;
    scrollPosRef.current = { x: target.scrollLeft, y: target.scrollTop };
    setScroll((current) =>
      current.x === target.scrollLeft && current.y === target.scrollTop
        ? current
        : { x: target.scrollLeft, y: target.scrollTop },
    );
  }, []);

  const unit = rulerUnitForScale(cssScale);
  const scrollPosX = rulerScrollPos(scroll.x, viewport.width, content.contentWidth, content.canvasX, cssScale);
  const scrollPosY = rulerScrollPos(scroll.y, viewport.height, content.contentHeight, content.canvasY, cssScale);
  // Explicit pixel box: Radix wraps scroll content in a display:table div that
  // sizes to its children, so percentage min-width/height and margin:auto
  // cannot center within the viewport. The same centering offsets the rulers
  // assume are baked into the box and anchor instead.
  const areaWidth = Math.max(content.contentWidth, viewport.width);
  const areaHeight = Math.max(content.contentHeight, viewport.height);
  const anchorX = Math.max(0, (areaWidth - content.contentWidth) / 2) + content.bodyX;
  const anchorY = Math.max(0, (areaHeight - content.contentHeight) / 2) + content.bodyY;

  // Preserve the centered native point, or recenter a new device/orientation.
  // Layout-timed so the scroll lands before paint; scroll events never run it.
  React.useLayoutEffect(() => {
    const element = viewportElRef.current;
    if (!element || viewport.width === 0 || viewport.height === 0) return;
    const previous = geomRef.current;
    const maxX = element.scrollWidth - element.clientWidth;
    const maxY = element.scrollHeight - element.clientHeight;
    let nextX: number;
    let nextY: number;
    if (!previous || previous.centerKey !== centerKey) {
      nextX = scrollToCenterNative(
        apertureWidth / cssScale / 2,
        viewport.width,
        content.contentWidth,
        content.canvasX,
        cssScale,
        maxX,
      );
      nextY = scrollToCenterNative(
        apertureHeight / cssScale / 2,
        viewport.height,
        content.contentHeight,
        content.canvasY,
        cssScale,
        maxY,
      );
    } else {
      const nativeX = centerNative(
        scrollPosRef.current.x,
        previous.viewportWidth,
        previous.contentWidth,
        previous.canvasX,
        previous.cssScale,
      );
      const nativeY = centerNative(
        scrollPosRef.current.y,
        previous.viewportHeight,
        previous.contentHeight,
        previous.canvasY,
        previous.cssScale,
      );
      nextX = scrollToCenterNative(nativeX, viewport.width, content.contentWidth, content.canvasX, cssScale, maxX);
      nextY = scrollToCenterNative(nativeY, viewport.height, content.contentHeight, content.canvasY, cssScale, maxY);
    }
    geomRef.current = {
      centerKey,
      cssScale,
      viewportWidth: viewport.width,
      viewportHeight: viewport.height,
      canvasX: content.canvasX,
      canvasY: content.canvasY,
      contentWidth: content.contentWidth,
      contentHeight: content.contentHeight,
    };
    if (element.scrollLeft !== nextX) element.scrollLeft = nextX;
    if (element.scrollTop !== nextY) element.scrollTop = nextY;
    scrollPosRef.current = { x: element.scrollLeft, y: element.scrollTop };
    // Geometry only: scroll, paint, selection and inspector renders never run
    // this; the preserve path above is idempotent when nothing moved.
    // apertureWidth/Height ride with content but are listed for the hook lint.
  }, [centerKey, cssScale, content, viewport.width, viewport.height, apertureWidth, apertureHeight]);

  const rulerWidth = Math.max(0, viewport.width);
  const rulerHeight = Math.max(0, viewport.height);
  const rulerProps = {
    zoom: cssScale,
    unit,
    backgroundColor: palette.background,
    lineColor: palette.line,
    textColor: palette.text,
    font: palette.font,
  };

  return (
    <div data-canvas-viewport className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-row">
        <TooltipHint content="Pixel rulers: origin 0 is the canvas top-left, values are native device pixels.">
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="About pixel rulers"
            data-canvas-corner
            className="flex items-center justify-center rounded-none p-0 font-studio"
            style={{
              width: RULER_SIZE,
              height: RULER_SIZE,
              flexShrink: 0,
              backgroundColor: palette.background,
              color: palette.text,
              fontSize: 9,
            }}
          >
            px
          </Button>
        </TooltipHint>
        {rulerWidth > 0 ? (
          <PixelRuler
            key={`h-${density}`}
            type="horizontal"
            width={rulerWidth}
            height={RULER_SIZE}
            scrollPos={scrollPosX}
            textOffset={HORIZONTAL_TEXT_OFFSET}
            {...rulerProps}
          />
        ) : (
          <div style={{ width: 0, height: RULER_SIZE }} />
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-row">
        {rulerHeight > 0 ? (
          <PixelRuler
            key={`v-${density}`}
            type="vertical"
            width={RULER_SIZE}
            height={rulerHeight}
            scrollPos={scrollPosY}
            textOffset={VERTICAL_TEXT_OFFSET}
            {...rulerProps}
          />
        ) : (
          <div style={{ width: RULER_SIZE, height: 0 }} />
        )}
        <ScrollArea
          type="always"
          viewportRef={setViewportRef}
          viewportProps={{ onScroll, "data-screen-stage-scroll": true }}
          className="flex-1"
          data-canvas-scroll
          data-ruler-scroll-x={Math.round(scrollPosX * 1000) / 1000}
          data-ruler-scroll-y={Math.round(scrollPosY * 1000) / 1000}
          data-ruler-unit={unit}
        >
          <div className="relative" style={{ width: areaWidth, height: areaHeight }}>
            <div
              className="absolute"
              style={{
                left: anchorX,
                top: anchorY,
                width: bodyWidth,
                height: bodyHeight,
              }}
            >
              {body}
            </div>
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
