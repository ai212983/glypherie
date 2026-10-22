import * as React from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { FontSizeControl } from "./FontSizeControl";

const meta = {
  title: "Controls/Font size",
  component: FontSizeControl,
  args: { sizePx: 16, disabled: false, onSize: () => {} },
  render: (args) => {
    const [size, setSize] = React.useState(args.sizePx);
    React.useEffect(() => setSize(args.sizePx), [args.sizePx]);
    return <div className="w-72"><FontSizeControl {...args} sizePx={size} onSize={setSize} /></div>;
  },
} satisfies Meta<typeof FontSizeControl>;

export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Custom: Story = { args: { sizePx: 20.5 } };
export const Disabled: Story = { args: { disabled: true } };
