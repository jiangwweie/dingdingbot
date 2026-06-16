/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OWNER_USE_MOCK?: "true" | "false";
  readonly VITE_OWNER_PRODUCT_PROJECTION_URL?: string;
  readonly VITE_OWNER_MOCK_SCENARIO?: "normal" | "processing" | "paused" | "intervention" | "stale" | "empty" | "error";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
