import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Shared by the app and Storybook so component imports and styling stay aligned.
export default defineConfig({
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(import.meta.dirname, "src") },
      // Exact match only: the bare "utils" specifier is the shadcn cn helper.
      { find: /^utils$/, replacement: path.resolve(import.meta.dirname, "src", "utils.ts") },
    ],
  },
  plugins: [react(), tailwindcss()],
});
