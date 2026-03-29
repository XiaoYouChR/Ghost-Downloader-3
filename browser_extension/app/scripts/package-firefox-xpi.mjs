#!/usr/bin/env node

/**
 * Firefox XPI Packager
 * Generates a Firefox extension package from the built Firefox extension directory
 */

import { createReadStream, createWriteStream } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import archiver from "archiver";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const firefoxBuildDir = path.resolve(appRoot, "../firefox");
const outputDir = path.resolve(appRoot, "../..");
const xpiPath = path.resolve(outputDir, "firefox_extension.xpi");

async function createXPI() {
  const output = createWriteStream(xpiPath);
  const archive = archiver("zip", {
    zlib: { level: 9 },
  });

  return new Promise((resolve, reject) => {
    output.on("close", () => {
      console.log(`✓ Firefox extension packaged: ${xpiPath}`);
      console.log(`  Size: ${(archive.pointer() / 1024).toFixed(2)} KB`);
      resolve(xpiPath);
    });

    archive.on("error", (err) => {
      reject(err);
    });

    archive.pipe(output);

    // Add all files from the firefox build directory
    archive.directory(firefoxBuildDir, false);

    archive.finalize();
  });
}

async function main() {
  try {
    // Check if firefox build directory exists
    const stats = await stat(firefoxBuildDir).catch(() => null);
    if (!stats?.isDirectory()) {
      throw new Error(
        `Firefox build directory not found: ${firefoxBuildDir}\n` +
        "Please run 'npm run build:firefox' first"
      );
    }

    console.log("Building Firefox XPI extension...");
    const xpiFile = await createXPI();
    console.log(`\n✅ Firefox extension ready at: ${xpiFile}`);
    return 0;
  } catch (error) {
    console.error("❌ Error creating Firefox extension:", error);
    return 1;
  }
}

process.exit(await main());
