import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const buildTarget = process.env.GD4B_BUILD_TARGET ?? "chrome114";
const outDir = process.env.GD4B_OUT_DIR
  ? path.resolve(__dirname, process.env.GD4B_OUT_DIR)
  : path.resolve(__dirname, "../chromium");

export default defineConfig({
  root: path.resolve(__dirname),
  publicDir: path.resolve(__dirname, "public"),
  plugins: [react()],
  build: {
    outDir,
    emptyOutDir: true,
    target: buildTarget,
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        popup: path.resolve(__dirname, "popup.html"),
      },
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }

          if (
            id.includes("/@fluentui/")
            || id.includes("\\@fluentui\\")
            || id.includes("/@griffel/")
            || id.includes("\\@griffel\\")
          ) {
            return "fluent-vendor";
          }

          if (
            id.includes("/react/")
            || id.includes("\\react\\")
            || id.includes("/react-dom/")
            || id.includes("\\react-dom\\")
            || id.includes("/scheduler/")
            || id.includes("\\scheduler\\")
          ) {
            return "react-vendor";
          }

          return "vendor";
        },
      },
    },
  },
});
