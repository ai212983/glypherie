import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  FontCanvasDiagnosticsStory,
  canvasArgTypes,
  defaultCanvasArgs,
  fontCanvasSnippet,
  type CanvasStoryArgs,
} from "./font-canvas-story.js";

// Failure and lifecycle simulations for the shared canvas live here so the
// main FontCanvas page stays focused on real rendering. Selecting a state
// writes its full deterministic bundle (scenario, ready, text, mode); the
// raw JSON editor writes the actual palette arg. The state selector
// lives only in the inline Diagnostic tools panel: the Controls table lists
// real FontCanvas props, so the hidden diagnostic arg below is just the
// initial selection. Anything else already set stays, and the provider only
// remounts when the scenario itself changes (error/unavailable keep the
// deterministic fixture, everything else renders for real).
const meta = {
  title: "Renderer/FontCanvasDiagnostics",
  render: FontCanvasDiagnosticsStory,
  tags: ["!autodocs"],
  parameters: {
    docs: {
      description: {
        component: [
          "Failure modes for the shared canvas. Only render errors and unavailable services use the",
          "simulating fixture; everything else renders for real.",
        ].join("\n"),
      },
    },
  },
  argTypes: canvasArgTypes,
  args: {
    ...defaultCanvasArgs,
    diagnostic: "ready",
  },
} satisfies Meta<CanvasStoryArgs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const States: Story = {
  parameters: { docs: { source: { code: fontCanvasSnippet() } } },
};
