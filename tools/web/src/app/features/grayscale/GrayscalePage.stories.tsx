import type { Meta, StoryObj } from "@storybook/react-vite";
import { GrayscalePage } from "./GrayscalePage";
import { DisplayPreferencesProvider } from "../../shell/DisplayPreferences";

const meta = {
  title: "Pages/E-ink grayscale",
  component: GrayscalePage,
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <DisplayPreferencesProvider>
        <Story />
      </DisplayPreferencesProvider>
    ),
  ],
} satisfies Meta<typeof GrayscalePage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
