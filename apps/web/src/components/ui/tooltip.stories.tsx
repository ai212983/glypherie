import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "./button";
import { TooltipHint } from "../TooltipHint";

function TooltipExample({ content }: { content: string }) {
  return <TooltipHint content={content}><Button variant="outline">Hover or focus</Button></TooltipHint>;
}

const meta = {
  title: "UI/Tooltip",
  component: TooltipExample,
  args: { content: "Helpful information." },
  parameters: { layout: "centered" },
} satisfies Meta<typeof TooltipExample>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
