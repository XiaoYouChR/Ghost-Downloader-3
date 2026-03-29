import { cp, mkdir, copyFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const outDir = path.resolve(appRoot, "../firefox");
const upstreamDir = path.resolve(appRoot, "../upstream");

// Create output directory
await mkdir(outDir, { recursive: true });

// Build Vite popup
await viteBuild({
  configFile: path.resolve(appRoot, "vite.config.ts"),
  mode: "production",
  build: {
    outDir,
    emptyOutDir: false,
  },
});

// Build background script for Firefox (IIFE format for better compatibility)
await esbuild({
  entryPoints: [path.resolve(appRoot, "src/background.ts")],
  bundle: true,
  format: "iife",
  target: "firefox109",
  platform: "browser",
  outfile: path.resolve(outDir, "background.js"),
});

// Build content script
await esbuild({
  entryPoints: [path.resolve(appRoot, "src/content-script.ts")],
  bundle: true,
  format: "iife",
  target: "firefox109",
  platform: "browser",
  outfile: path.resolve(outDir, "content-script.js"),
});

// Copy resources
await cp(
  path.resolve(upstreamDir, "catch-script"),
  path.resolve(outDir, "catch-script"),
  { recursive: true }
).catch(() => {
  // upstream resources might not exist, that's okay
});

// Copy Firefox-specific manifest
await copyFile(
  path.resolve(appRoot, "public/manifest-firefox.json"),
  path.resolve(outDir, "manifest.json")
);

console.log(`✓ Firefox extension built successfully to: ${outDir}`);

