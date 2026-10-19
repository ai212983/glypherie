import type { Meta, StoryObj } from "@storybook/react-vite";
import { Controls, Primary, Stories, Title } from "@storybook/addon-docs/blocks";
import {
  FontCanvasStory,
  canvasArgTypes,
  defaultCanvasArgs,
  fontCanvasSnippet,
  type CanvasStoryArgs,
} from "./font-canvas-story.js";
import type { RGBA } from "./renderer-types.js";

// Concise docs entry: one short intro with example navigation, then the
// live stories. Each story canvas carries its own compact panels, so this
// page never repeats full control walls.
function FontCanvasDocs() {
  return (
    <div data-fc-docs>
      <Title />
      <p>Render text with editable palettes, transparency, and pixel scaling.</p>
      <nav aria-label="FontCanvas examples">
        <ul>
          <li>
            <a href="./?path=/story/renderer-fontcanvas--playground" target="_top">
              Playground
            </a>
          </li>
          <li>
            <a href="./?path=/story/renderer-fontcanvas--pixel-accurate" target="_top">
              Pixel accurate
            </a>
          </li>
          <li>
            <a href="./?path=/story/renderer-fontcanvas--palette-and-transparency" target="_top">
              Palette &amp; transparency
            </a>
          </li>
          <li>
            <a href="./?path=/story/renderer-fontcanvasdiagnostics--states" target="_top">
              Diagnostics
            </a>
          </li>
        </ul>
      </nav>
      <Primary />
      <details data-api-reference>
        <summary>Component API</summary>
        <Controls />
      </details>
      <h3>More examples</h3>
      <Stories includePrimary={false} />
    </div>
  );
}

const meta = {
  title: "Renderer/FontCanvas",
  render: FontCanvasStory,
  tags: ["autodocs"],
  parameters: {
    docs: {
      description: {
        component: [
          "Shared font rendering canvas behind the library cards and the interactive specimen.",
          "The Controls table lists real FontCanvas props only; inline panels configure the preview.",
          "Entry 0 is the paper, every other entry paints its own color. Failure simulations live in",
          "the diagnostics story linked above.",
        ].join("\n"),
      },
      page: FontCanvasDocs,
    },
  },
  argTypes: canvasArgTypes,
  args: defaultCanvasArgs,
} satisfies Meta<CanvasStoryArgs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {
  parameters: { docs: { source: { code: fontCanvasSnippet() } } },
};

export const PixelAccurate: Story = {
  args: { mode: "exact", zoom: 2 },
  parameters: { docs: { source: { code: fontCanvasSnippet({ mode: "exact", zoom: 2 }) } } },
};

// One shared constant feeds both the story args and its source snippet, so
// the documented usage can never drift from the painted values. Entry 0 is
// the translucent paper the uncovered pixels show.
const TRANSPARENCY_PALETTE: RGBA[] = [
  [70, 130, 180, 110],
  [30, 60, 200, 36],
  [30, 90, 200, 72],
  [30, 120, 200, 108],
  [30, 150, 200, 144],
  [30, 180, 200, 180],
  [30, 210, 200, 216],
  [30, 240, 200, 252],
];

export const PaletteAndTransparency: Story = {
  args: {
    profile: "gray_3bit",
    palette: TRANSPARENCY_PALETTE,
    checkerboard: true,
  },
  parameters: {
    docs: {
      source: {
        code: fontCanvasSnippet({
          profile: "gray_3bit",
          palette: TRANSPARENCY_PALETTE,
        }),
      },
    },
  },
};
