import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: mode === "admin" ? 5274 : 5273,
    host: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: mode === "admin" ? "dist-admin" : "dist",
    rollupOptions: {
      input: mode === "admin" ? path.resolve(__dirname, "admin.html") : path.resolve(__dirname, "index.html"),
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("react") || id.includes("scheduler")) return "react-vendor";
          if (id.includes("@tanstack")) return "query-vendor";
          if (id.includes("lucide-react")) return "icons-vendor";
          if (id.includes("read-excel-file")) return "spreadsheet-vendor";
          return "vendor";
        },
      },
    },
  },
}));
