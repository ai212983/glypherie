import * as React from "react";
import { curveLevels, curvePath, type GrayCurve } from "./response-curve";

const WIDTH = 760;
const HEIGHT = 320;
const LEFT = 48;
const TOP = 24;
const PLOT_HEIGHT = HEIGHT - TOP - 48;
const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

interface ResponseCurveProps {
  curve: GrayCurve;
  selected: number;
  editable: boolean;
  onSelect: (index: number) => void;
  onChange: (index: number, value: number) => void;
  onPin: (index: number) => void;
  onUnpin: (index: number) => void;
}

export function ResponseCurve({ curve, selected, editable, onSelect, onChange, onPin, onUnpin }: ResponseCurveProps): React.JSX.Element {
  const levels = curveLevels(curve);
  const svg = React.useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = React.useState(WIDTH);
  const points = React.useRef<(SVGCircleElement | null)[]>([]);
  const dragging = React.useRef<{ index: number; pointer: number; startX: number; startY: number; startValue: number; wasPinned: boolean; moved: boolean } | null>(null);
  React.useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const measure = (): void => setWidth(Math.max(160, element.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const plotWidth = width - LEFT - 24;
  const x = (index: number): number => LEFT + index * plotWidth / (levels.length - 1);
  const y = (gray: number): number => TOP + (1 - gray / 255) * PLOT_HEIGHT;
  const ticks = levels.length <= Math.max(2, Math.floor(plotWidth / 32)) ? levels.map((_, index) => index)
    : [0, 1, 2, 3, 4].map((tick) => Math.round(tick * (levels.length - 1) / 4));

  const position = (event: React.PointerEvent<SVGSVGElement>): { x: number; y: number } => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: (event.clientX - rect.left) * width / rect.width, y: (event.clientY - rect.top) * HEIGHT / rect.height };
  };
  const dragValue = (event: React.PointerEvent<SVGSVGElement>): void => {
    const drag = dragging.current;
    if (!drag || drag.pointer !== event.pointerId) return;
    const at = position(event);
    if (!drag.moved && Math.hypot(at.x - drag.startX, at.y - drag.startY) < 3) return;
    drag.moved = true;
    onChange(drag.index, clamp(Math.round(drag.startValue + (drag.startY - at.y) * 255 / PLOT_HEIGHT), 0, 255));
  };
  const endDrag = (event: React.PointerEvent<SVGSVGElement>, toggle = false): void => {
    const drag = dragging.current;
    if (drag?.pointer !== event.pointerId) return;
    dragging.current = null;
    if (toggle && !drag.moved && drag.wasPinned) onUnpin(drag.index);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <div className="min-w-0">
      <svg
        ref={svg} viewBox={`0 0 ${width} ${HEIGHT}`} preserveAspectRatio="none"
        role="group" aria-label="Gray response graph"
        className={`block h-80 w-full overflow-visible text-card-foreground ${editable ? "touch-none cursor-crosshair" : ""}`}
        onPointerDown={(event) => {
          if (!editable || event.button !== 0 || dragging.current) return;
          const at = position(event);
          if (at.x < LEFT - 8 || at.x > LEFT + plotWidth + 8 || at.y < TOP - 8 || at.y > TOP + PLOT_HEIGHT + 8) return;
          event.preventDefault();
          const index = clamp(Math.round((at.x - LEFT) * (levels.length - 1) / plotWidth), 0, levels.length - 1);
          const wasPinned = curve[index]?.pinned ?? false;
          dragging.current = { index, pointer: event.pointerId, startX: at.x, startY: at.y, startValue: levels[index] ?? 0, wasPinned, moved: false };
          event.currentTarget.setPointerCapture(event.pointerId);
          onSelect(index);
          if (!wasPinned) onPin(index);
          points.current[index]?.focus();
        }}
        onPointerMove={dragValue} onPointerUp={(event) => endDrag(event, true)} onPointerCancel={(event) => endDrag(event)}
        onLostPointerCapture={() => { dragging.current = null; }}
      >
        <g aria-hidden="true" className="text-muted-foreground" fontSize="12" fill="currentColor">
          {[0, 64, 128, 192, 255].map((gray) => (
            <g key={gray}>
              <line x1={LEFT} y1={y(gray)} x2={LEFT + plotWidth} y2={y(gray)} stroke="currentColor" strokeOpacity=".15" vectorEffect="non-scaling-stroke" />
              <text x={LEFT - 10} y={y(gray) + 4} textAnchor="end">{gray}</text>
            </g>
          ))}
          {ticks.map((index) => (
            <g key={index}>
              <line x1={x(index)} y1={TOP} x2={x(index)} y2={TOP + PLOT_HEIGHT} stroke="currentColor" strokeOpacity=".12" vectorEffect="non-scaling-stroke" />
              <text x={x(index)} y={TOP + PLOT_HEIGHT + 20} textAnchor="middle">{index}</text>
            </g>
          ))}
          <text x={LEFT} y={13}>Gray value</text>
          <text x={LEFT} y={HEIGHT - 5}>Paper</text>
          <text x={LEFT + plotWidth / 2} y={HEIGHT - 5} textAnchor="middle">Level</text>
          <text x={LEFT + plotWidth} y={HEIGHT - 5} textAnchor="end">Full ink</text>
          <line x1={LEFT} y1={TOP} x2={LEFT + plotWidth} y2={TOP + PLOT_HEIGHT} stroke="currentColor" strokeOpacity=".45" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
        </g>
        <path aria-hidden="true" d={curvePath(curve, (position) => LEFT + position * plotWidth, y)} fill="none" className="stroke-primary" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {levels.map((gray, index) => (
          <circle
            key={index} ref={(element) => { points.current[index] = element; }}
            cx={x(index)} cy={y(curve[index]!.value)} r={selected === index ? 7 : curve[index]?.pinned ? 5 : levels.length > 32 ? 2 : 3}
            data-curve-level={index} data-pinned={curve[index]?.pinned}
            className={`${curve[index]?.pinned ? "fill-primary" : "fill-card"} stroke-primary outline-none focus-visible:stroke-ring focus-visible:stroke-[4]`}
            strokeWidth="2" vectorEffect="non-scaling-stroke"
            role={editable ? "slider" : undefined} tabIndex={editable ? (selected === index ? 0 : -1) : undefined}
            aria-label={`Level ${index} gray value`} aria-orientation={editable ? "vertical" : undefined}
            aria-valuemin={editable ? 0 : undefined} aria-valuemax={editable ? 255 : undefined} aria-valuenow={editable ? gray : undefined}
            aria-valuetext={editable ? `${gray}, ${curve[index]?.pinned ? "pinned handle" : "follows the curve"}` : undefined}
            onKeyDown={(event) => {
              if (!editable) return;
              const step = event.shiftKey ? 10 : 1;
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                event.preventDefault();
                const next = clamp(index + (event.key === "ArrowLeft" ? -1 : 1), 0, levels.length - 1);
                onSelect(next);
                points.current[next]?.focus();
              } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                if (curve[index]?.pinned) onUnpin(index);
                else onPin(index);
              } else if (event.key === "Delete" || event.key === "Backspace") {
                event.preventDefault();
                onUnpin(index);
              } else if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                const next = event.key === "Home" ? 0 : event.key === "End" ? 255 : gray + (event.key === "ArrowUp" ? step : -step);
                onChange(index, clamp(next, 0, 255));
              }
            }}
          />
        ))}
      </svg>
    </div>
  );
}
