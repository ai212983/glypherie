import type { Meta, StoryObj } from "@storybook/react-vite";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

function FormControls({ disabled, invalid }: { disabled: boolean; invalid: boolean }) {
  return (
    <div className="grid w-80 gap-4">
      <div className="grid gap-2">
        <Label htmlFor="variant-name">Variant name</Label>
        <Input id="variant-name" placeholder="Reading size" disabled={disabled} aria-invalid={invalid} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="output-profile">Output profile</Label>
        <Select defaultValue="mono" disabled={disabled}>
          <SelectTrigger id="output-profile" aria-invalid={invalid} className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mono">Monochrome</SelectItem>
            <SelectItem value="gray">Grayscale</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="specimen-text">Specimen text</Label>
        <Textarea
          id="specimen-text"
          defaultValue="The quick brown fox jumps over the lazy dog."
          disabled={disabled}
          aria-invalid={invalid}
        />
      </div>
    </div>
  );
}

const meta = {
  title: "UI/Form controls",
  component: FormControls,
  args: { disabled: false, invalid: false },
} satisfies Meta<typeof FormControls>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Disabled: Story = { args: { disabled: true } };
export const Invalid: Story = { args: { invalid: true } };
