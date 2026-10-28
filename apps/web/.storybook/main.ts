import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  // Lifecycle test fixtures live under tests/ and load only with
  // STORYBOOK_TEST_HARNESSES=1, so normal Storybook never sees them.
  stories: [
    "../src/**/*.stories.@(ts|tsx)",
    ...(process.env.STORYBOOK_TEST_HARNESSES === "1" ? ["../tests/fixtures/**/*.stories.@(ts|tsx)"] : []),
  ],
  addons: ["@storybook/addon-docs", "@storybook/addon-themes"],
  core: {
    allowedHosts: process.env.STORYBOOK_ALLOWED_HOSTS?.split(",").map((host) => host.trim()).filter(Boolean) ?? [],
  },
  framework: {
    name: "@storybook/react-vite",
    options: {
      builder: {
        // Component previews share the UI setup without the app's PWA build.
        viteConfigPath: ".storybook/vite.config.ts",
      },
    },
  },
  viteFinal(config) {
    if (config.server?.hmr && typeof config.server.hmr === "object") {
      // Storybook already supplies the HTTP server for WebSockets. Let Vite's
      // client use the page's port, including through HTTPS reverse proxies.
      delete config.server.hmr.port;
    }
    return config;
  },
};

export default config;
