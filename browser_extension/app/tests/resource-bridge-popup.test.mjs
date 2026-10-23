import assert from "node:assert/strict";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import {build} from "esbuild";

test("routeBrowserDownload does not open the popup when disabled", async () => {
  let popupOpens = 0;
  globalThis.chrome = {
    action: {openPopup: async () => { popupOpens += 1; }},
    runtime: {getManifest: () => ({version: "2.2.0"})},
    i18n: {getMessage: (key) => key},
    storage: {session: {}},
  };
  const bundled = await build({
    entryPoints: [fileURLToPath(new URL("../src/background/resource-bridge.ts", import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "browser",
    write: false,
  });
  const {createResourceBridge} = await import(
    `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`
  );
  const requests = [];
  const bridge = createResourceBridge({
    shouldOpenPopupOnSent: () => false,
    sendDesktopRequest: async (request) => {
      requests.push(request);
      return {ok: true};
    },
  });

  await bridge.routeBrowserDownload({url: "https://example.com/clip.mp4", filename: "clip.mp4"});

  assert.deepEqual(requests, [{
    type: "create_task",
    source: "download",
    title: "clip.mp4",
    payload: {
      url: "https://example.com/clip.mp4",
      headers: {},
      filename: "clip.mp4",
      size: 0,
      supportsRange: false,
    },
  }]);
  assert.equal(popupOpens, 0);
});
