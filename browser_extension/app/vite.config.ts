import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const browserTarget = process.env.GD4B_BROWSER_TARGET === "firefox" ? "firefox" : "chromium";
const outDir = path.resolve(__dirname, `../${browserTarget}`);
const buildTarget = browserTarget === "firefox" ? "firefox113" : "chrome114";

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
