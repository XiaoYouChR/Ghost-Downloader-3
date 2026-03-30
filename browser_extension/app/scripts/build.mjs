import { access, cp, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const upstreamDir = path.resolve(appRoot, "../upstream");
const catchScriptDir = path.resolve(upstreamDir, "catch-script");
const manifestTemplate = JSON.parse(
  await readFile(path.resolve(appRoot, "public/manifest.json"), "utf8"),
);

const buildTargets = {
  chromium: {
    outDir: path.resolve(appRoot, "../chromium"),
    runtimeTarget: "chrome114",
  },
  firefox: {
    outDir: path.resolve(appRoot, "../firefox"),
    runtimeTarget: "firefox113",
  },
};

function createManifest(target) {
  const manifest = structuredClone(manifestTemplate);

  if (target === "firefox") {
    manifest.background = {
      scripts: ["background.js"],
      type: "module",
    };
    manifest.browser_specific_settings = {
      gecko: {
        strict_min_version: "113.0",
      },
    };
    delete manifest.minimum_chrome_version;
    return manifest;
  }

  manifest.background = {
    service_worker: "background.js",
    type: "module",
  };
  manifest.minimum_chrome_version = "114";
  delete manifest.browser_specific_settings;
  return manifest;
}

try {
  await access(catchScriptDir);
} catch {
  throw new Error(
    "Missing browser_extension/upstream/catch-script. Run `git submodule update --init --recursive browser_extension/upstream` first.",
  );
}

for (const [target, config] of Object.entries(buildTargets)) {
  process.env.GD4B_BROWSER_TARGET = target;

  await viteBuild({
    configFile: path.resolve(appRoot, "vite.config.ts"),
    mode: "production",
    build: {
      outDir: config.outDir,
      emptyOutDir: true,
      target: config.runtimeTarget,
    },
  });

  await esbuild({
    entryPoints: [path.resolve(appRoot, "src/background.ts")],
    bundle: true,
    format: "esm",
    target: config.runtimeTarget,
    platform: "browser",
    outfile: path.resolve(config.outDir, "background.js"),
  });

  await esbuild({
    entryPoints: [path.resolve(appRoot, "src/content-script.ts")],
    bundle: true,
    format: "iife",
    target: config.runtimeTarget,
    platform: "browser",
    outfile: path.resolve(config.outDir, "content-script.js"),
  });

  await mkdir(config.outDir, { recursive: true });
  await cp(catchScriptDir, path.resolve(config.outDir, "catch-script"), { recursive: true });
  await writeFile(
    path.resolve(config.outDir, "manifest.json"),
    `${JSON.stringify(createManifest(target), null, 2)}\n`,
  );
}

delete process.env.GD4B_BROWSER_TARGET;
