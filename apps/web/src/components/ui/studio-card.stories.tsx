import { useId, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import specimenIcon from "./assets/glypherie/specimen.svg";
import fontLicense from "./assets/glypherie/OFL-JetBrainsMono.txt?url";

const presets = {
  pangram: "The quick brown fox jumps over 0123456789",
  alphabet: "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz",
  digits: "0123456789 !@#$%^&*()",
};

function LiveSpecimenCard(args: React.ComponentProps<typeof Card>) {
  const id = useId();
  const [text, setText] = useState(presets.pangram);
  const [preset, setPreset] = useState<keyof typeof presets>("pangram");
  const [size, setSize] = useState(16);
  const [gamma, setGamma] = useState(1.8);
  const [polarity, setPolarity] = useState("paper");
  const labelClass = "text-[9px] leading-4 font-semibold text-muted-foreground uppercase";

  return (
    <Card {...args}>
      <CardHeader>
        <CardTitle asChild>
          <h2>
            <img src={specimenIcon} alt="" className="shrink-0" />
            1. Live specimen input
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1 rounded-lg border border-primary/40 bg-background px-2 pt-2 pb-3 shadow-studio-inset focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
          <Label htmlFor={`${id}-buffer`} className={labelClass}>Test buffer text</Label>
          <Textarea
            id={`${id}-buffer`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="h-[39px] min-h-0 resize-none rounded-none border-0 bg-transparent p-0 text-[12px] leading-[19.5px] shadow-none focus-visible:outline-none focus-visible:ring-0 md:text-[12px] dark:bg-transparent"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-preset`} className={labelClass}>Quick presets</Label>
          <Select
            value={preset}
            onValueChange={(value) => {
              const next = value as keyof typeof presets;
              setPreset(next);
              setText(presets[next]);
            }}
          >
            <SelectTrigger id={`${id}-preset`} className="h-[38px] w-full rounded-lg bg-background px-[10px] py-[6px] text-[11px] leading-6 shadow-none dark:bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="studio-card bg-card font-studio text-card-foreground shadow-studio-card">
              <SelectItem value="pangram">Pangram + Digits (0-9)</SelectItem>
              <SelectItem value="alphabet">Uppercase + Lowercase</SelectItem>
              <SelectItem value="digits">Digits + Symbols</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div role="group" aria-label="Base specimen size" className="flex flex-col gap-[6px]">
          <span className="text-[10px] leading-4 font-semibold text-muted-foreground uppercase">Base specimen size:</span>
          <div className="flex gap-1">
            {[8, 10, 12, 16, 24, 32, 48].map((value) => (
              <Button
                key={value}
                size="xs"
                variant={size === value ? "default" : "outline"}
                aria-pressed={size === value}
                onClick={() => setSize(value)}
                className={`h-[26px] min-w-0 flex-1 rounded px-0 text-[10px] leading-4 font-bold ${
                  size === value ? "shadow-xs" : "bg-background text-muted-foreground shadow-studio-inset dark:bg-background"
                }`}
              >
                {value}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 py-1">
          <div className="flex items-center justify-between gap-2 text-[10px] leading-4">
            <span id={`${id}-gamma-label`} className="font-semibold text-muted-foreground uppercase">Electrophoretic gamma:</span>
            <output className="font-bold text-studio-info">{gamma.toFixed(2)} γ</output>
          </div>
          <Slider
            aria-labelledby={`${id}-gamma-label`}
            aria-valuetext={`${gamma.toFixed(2)} gamma`}
            min={0.5}
            max={3}
            step={0.05}
            value={[gamma]}
            onValueChange={([value]) => { if (value !== undefined) setGamma(value); }}
            className="h-4 cursor-pointer [--ring:var(--accent)] [&_[data-slot=slider-track]]:h-1 [&_[data-slot=slider-track]]:bg-background [&_[data-slot=slider-range]]:bg-transparent [&_[data-slot=slider-thumb]]:size-3 [&_[data-slot=slider-thumb]]:border-accent [&_[data-slot=slider-thumb]]:bg-accent"
          />
        </div>
      </CardContent>
      <CardFooter className="flex-wrap justify-between gap-[6px]">
        <span className="text-[10px] leading-4 font-semibold text-muted-foreground uppercase">Polarity</span>
        <div role="group" aria-label="Polarity" className="flex w-[213.48px] max-w-full rounded-full border border-border bg-background p-[2px] shadow-studio-inset">
          {([['paper', <>Dark / Light<br />Paper</>], ['dark', <>Light /<br />Dark</>]] as const).map(([value, label]) => (
            <Button
              key={value}
              size="xs"
              variant={polarity === value ? "default" : "ghost"}
              aria-pressed={polarity === value}
              onClick={() => setPolarity(value)}
              className={`h-9 rounded-full py-[2px] text-[10px] leading-4 font-bold ${value === "paper" ? "px-[24.24px]" : "px-[22.5px]"} ${
                polarity === value ? "" : "text-muted-foreground"
              }`}
            >
              <span>{label}</span>
            </Button>
          ))}
        </div>
      </CardFooter>
    </Card>
  );
}

const meta = {
  title: "UI/Studio Card",
  component: Card,
  args: { className: "w-[351px] max-w-full" },
  argTypes: {
    variant: { control: "select", options: ["default", "studio", "plain"] },
  },
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component: `Glypherie's sidebar card, composed with the default shadcn Card slots. Use the toolbar theme switch for light/dark. Dark follows the [Figma reference](https://www.figma.com/design/a3qw2VZeu6oWTBtZqcmVZD/Glove80-UI?node-id=483-1092); light is an adapted palette. Colors and elevation use scoped theme tokens. Example controls are local to this story. [JetBrains Mono license](${fontLicense}).`,
      },
    },
  },
  decorators: [(Story) => <div className="max-w-full bg-studio-backdrop p-4"><Story /></div>],
  render: (args) => <LiveSpecimenCard {...args} />,
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
