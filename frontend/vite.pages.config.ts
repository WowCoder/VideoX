import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL("./pages", import.meta.url)),
  base: process.env.PAGES_BASE_PATH || "/VideoX/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // Keep homepage assets separate from user uploads and workspace media.
  publicDir: "public",
  build: {
    outDir: "../dist-pages",
    emptyOutDir: true,
  },
  preview: { host: "127.0.0.1", port: 4175, strictPort: true },
});
