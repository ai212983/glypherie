/// <reference types="vite/client" />

declare const __APP_SITE_URL__: string;

declare const __APP_BUILD__: {
  readonly version: string;
  readonly build: string;
  readonly builtAt: string;
  readonly commit: string | null;
  readonly localFingerprint: string | null;
  readonly renderer: string | null;
  readonly devServer: boolean;
};
