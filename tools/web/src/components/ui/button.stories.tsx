import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

const meta = {
  title: "UI/Button",
  component: Button,
  args: { children: "Add variant", onClick: fn() },
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "secondary", "outline", "ghost", "destructive", "link"],
    },
    size: {
      control: "select",
      options: ["default", "xs", "sm", "lg", "icon", "icon-xs", "icon-sm", "icon-lg"],
    },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Secondary: Story = { args: { variant: "secondary" } };
export const Outline: Story = { args: { variant: "outline" } };
export const Destructive: Story = { args: { variant: "destructive", children: "Delete variant" } };
export const Disabled: Story = { args: { disabled: true } };
export const Icon: Story = {
  args: { size: "icon", "aria-label": "Add variant", children: <Plus /> },
};
