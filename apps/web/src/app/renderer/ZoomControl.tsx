import * as React from "react";
import { PREVIEW_ZOOM_STOPS } from "./display-scaling.js";
import "./ZoomControl.css";

interface ZoomControlProps {
  id?: string;
  zoom: number;
  disabled?: boolean;
  onZoom: (value: number) => void;
}
export function ZoomControl({ id = "zoom", zoom, disabled = false, onZoom }: ZoomControlProps): React.JSX.Element {
  return (
    <div className="zoom-control" data-zoom-control>
      <fieldset id={id} className="zoom-control__stops" data-preview-zoom data-value={zoom} disabled={disabled}>
        <legend className="sr-only">Zoom</legend>
        {PREVIEW_ZOOM_STOPS.map((value) => (
          <label key={value} className="zoom-control__stop">
            <input type="radio" name={id} value={value} checked={zoom === value} onChange={() => onZoom(value)} />
            <span>{value}×</span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}
