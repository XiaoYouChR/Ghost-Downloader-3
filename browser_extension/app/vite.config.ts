import path from "node:path";
import {fileURLToPath} from "node:url";

import react from "@vitejs/plugin-react";
import {defineConfig} from "vite";

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
    rolldownOptions: {
      input: {
        popup: path.resolve(__dirname, "popup.html"),
      },
      output: {
        codeSplitting: {
          groups: [
            {name: "fluent-vendor", test: /node_modules[\\/]@(fluentui|griffel)[\\/]/, priority: 30},
            {name: "react-vendor", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 20},
            {name: "vendor", test: /node_modules[\\/]/, priority: 10},
          ],
        },
      },
    },
  },
});
