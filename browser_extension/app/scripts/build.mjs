import { cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const outDir = path.resolve(appRoot, "../chromium");
const upstreamDir = path.resolve(appRoot, "../upstream");

await viteBuild({
  configFile: path.resolve(appRoot, "vite.config.ts"),
  mode: "production",
});

await esbuild({
  entryPoints: [path.resolve(appRoot, "src/background.ts")],
  bundle: true,
  format: "esm",
  target: "chrome114",
  platform: "browser",
  outfile: path.resolve(outDir, "background.js"),
});

await esbuild({
  entryPoints: [path.resolve(appRoot, "src/content-script.ts")],
  bundle: true,
  format: "iife",
  target: "chrome114",
  platform: "browser",
  outfile: path.resolve(outDir, "content-script.js"),
});

await mkdir(outDir, { recursive: true });
await cp(path.resolve(upstreamDir, "catch-script"), path.resolve(outDir, "catch-script"), { recursive: true });
