import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL("./pages", import.meta.url)),
  base: process.env.PAGES_BASE_PATH || "/OpenVMA/",
  plugins: [react()],
  // Only the project's first-party brand assets enter the public showcase.
  publicDir: "public",
  build: {
    outDir: "../dist-pages",
    emptyOutDir: true,
  },
  preview: { host: "127.0.0.1", port: 4175, strictPort: true },
});
