import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const upstreamDir = path.resolve(appRoot, "../upstream");
const baseManifestPath = path.resolve(appRoot, "public/manifest.json");

const buildTargets = [
  {
    name: "chromium",
    buildTarget: "chrome114",
    outDir: path.resolve(appRoot, "../chromium"),
  },
  {
    name: "firefox",
    buildTarget: "firefox113",
    outDir: path.resolve(appRoot, "../firefox"),
  },
];

function createManifest(baseManifest, targetName) {
  const manifest = structuredClone(baseManifest);

  if (targetName === "firefox") {
    delete manifest.minimum_chrome_version;
    manifest.background = {
      scripts: ["background.js"],
      type: "module",
    };
    manifest.content_security_policy = {
      extension_pages:
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:;",
    };
    manifest.browser_specific_settings = {
      gecko: {
        id: "ghost-downloader-browser@ghost-downloader.local",
        strict_min_version: "113.0",
      },
    };
    return manifest;
  }

  manifest.background = {
    service_worker: "background.js",
    type: "module",
  };
  delete manifest.content_security_policy;
  delete manifest.browser_specific_settings;
  return manifest;
}

const baseManifest = JSON.parse(await readFile(baseManifestPath, "utf8"));
const originalBuildTarget = process.env.GD4B_BUILD_TARGET;
const originalOutDir = process.env.GD4B_OUT_DIR;

try {
  for (const target of buildTargets) {
    process.env.GD4B_BUILD_TARGET = target.buildTarget;
    process.env.GD4B_OUT_DIR = path.relative(appRoot, target.outDir);

    await viteBuild({
      configFile: path.resolve(appRoot, "vite.config.ts"),
      mode: "production",
    });

    await esbuild({
      entryPoints: [path.resolve(appRoot, "src/background.ts")],
      bundle: true,
      format: "esm",
      target: target.buildTarget,
      platform: "browser",
      outfile: path.resolve(target.outDir, "background.js"),
    });

    await esbuild({
      entryPoints: [path.resolve(appRoot, "src/content-script.ts")],
      bundle: true,
      format: "iife",
      target: target.buildTarget,
      platform: "browser",
      outfile: path.resolve(target.outDir, "content-script.js"),
    });

    await mkdir(target.outDir, { recursive: true });
    await cp(path.resolve(upstreamDir, "catch-script"), path.resolve(target.outDir, "catch-script"), { recursive: true });
    await writeFile(
      path.resolve(target.outDir, "manifest.json"),
      `${JSON.stringify(createManifest(baseManifest, target.name), null, 2)}\n`,
      "utf8",
    );
  }
} finally {
  if (originalBuildTarget === undefined) {
    delete process.env.GD4B_BUILD_TARGET;
  } else {
    process.env.GD4B_BUILD_TARGET = originalBuildTarget;
  }

  if (originalOutDir === undefined) {
    delete process.env.GD4B_OUT_DIR;
  } else {
    process.env.GD4B_OUT_DIR = originalOutDir;
  }
}
