import { MAX_TEXT_LENGTH, TEXT_DEFAULT } from "../../renderer/render-spec.ts";

export interface TextPreset {
  id: string;
  title: string;
  content: string;
}

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789";

export const TEXT_PRESETS: TextPreset[] = [
  { id: "pangram", title: "Pangram", content: TEXT_DEFAULT },
  { id: "alphabet", title: "Alphabet", content: ALPHABET },
  { id: "custom", title: "Custom", content: "" },
];

export function presetForText(text: string): string {
  return TEXT_PRESETS.find((preset) => preset.id !== "custom" && preset.content === text)?.id ?? "custom";
}

export { MAX_TEXT_LENGTH };
