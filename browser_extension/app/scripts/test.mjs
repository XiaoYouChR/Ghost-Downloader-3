import {execFileSync} from "node:child_process";
import {mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {build} from "esbuild";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputDir = mkdtempSync(path.join(tmpdir(), "ghost-extension-tests-"));
try {
  const output = path.join(outputDir, "site-rules.test.mjs");
  await build({
    entryPoints: [path.join(root, "tests/site-rules.test.ts")],
    bundle: true,
    platform: "node",
    format: "esm",
    outfile: output,
  });
  execFileSync(process.execPath, ["--test", output], {stdio: "inherit"});
} finally {
  rmSync(outputDir, {recursive: true, force: true});
}
