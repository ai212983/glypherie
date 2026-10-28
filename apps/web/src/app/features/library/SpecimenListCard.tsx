import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { SampleTextControl } from "./SampleTextControl";
import { SpecimenFrame, SpecimenFooter } from "./SpecimenFrame";
import type { CanvasFrame } from "./canvas-palettes";

interface SpecimenListCardProps {
  title: React.ReactNode;
  label: string;
  frame: CanvasFrame;
  text: string;
  onText: (text: string) => void;
  frameProps?: Omit<React.ComponentProps<typeof SpecimenFrame>, "frame" | "children"> & { [key: `data-${string}`]: string | number | boolean | undefined };
  footer: React.ReactNode;
  children: React.ReactNode;
}

export function SpecimenListCard({ title, label, frame, text, onText, frameProps, footer, children }: SpecimenListCardProps): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle asChild><h2>{title}</h2></CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <SampleTextControl data-specimen-list-text value={text} maxLength={512} onValueChange={onText} />
        <SpecimenFrame {...frameProps} frame={frame}>
          <div role="group" aria-label={label}>
            <ul className="m-0 flex min-w-0 list-none flex-col p-0">{children}</ul>
          </div>
          <SpecimenFooter frame={frame}>{footer}</SpecimenFooter>
        </SpecimenFrame>
      </CardContent>
    </Card>
  );
}

export function SpecimenListItem({ frame, children }: { frame: CanvasFrame; children: React.ReactNode }): React.JSX.Element {
  return <li className="border-t py-1 first:border-t-0" style={{ borderColor: frame.dividerCss }}>{children}</li>;
}
