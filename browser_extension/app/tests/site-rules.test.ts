import assert from "node:assert/strict";
import test from "node:test";
import {selectGeneric} from "../src/page-media/resolution/strategies/generic";
import type {ResolveContext} from "../src/page-media/resolution/strategy";

globalThis.chrome = {i18n: {getMessage: (key: string) => key}} as typeof chrome;

function context(enabled: boolean): ResolveContext {
  return {
    clicked: {
      formKind: "unknown",
      lastBoundAt: 10,
      attributedUrls: [
        {url: "https://cdn.test/advert/master.m3u8", contentType: "application/vnd.apple.mpegurl", capturedAt: 20, isMaster: true},
        {url: "https://cdn.test/main/master.m3u8", contentType: "application/vnd.apple.mpegurl", capturedAt: 30, isMaster: true},
      ],
    },
    pageUrl: new URL("https://hdsex.org/shemale/video/776062386"),
    hints: {
      poster: "",
      siteRules: [{id: "hdsex", name: "HDSex", hosts: ["hdsex.org"], action: "prefer_latest_hls", enabled}],
    },
  };
}

test("HDSex rule skips the older pre-roll HLS", () => {
  const result = selectGeneric(context(true));
  assert.equal(result.kind, "selection");
  if (result.kind === "selection" && result.selection.kind === "stream") {
    assert.equal(result.selection.url, "https://cdn.test/main/master.m3u8");
  }
});

test("disabling HDSex rule preserves generic first-master behavior", () => {
  const result = selectGeneric(context(false));
  assert.equal(result.kind, "selection");
  if (result.kind === "selection" && result.selection.kind === "stream") {
    assert.equal(result.selection.url, "https://cdn.test/advert/master.m3u8");
  }
});
