// Upstream cat-catch media/script rules, with existing GD3 extension coverage kept compatible.
const CAT_CATCH_HLS_TYPES = new Set([
  "application/vnd.apple.mpegurl",
  "application/x-mpegurl",
  "application/mpegurl",
  "application/octet-stream-m3u8",
]);

const CAT_CATCH_MPD_TYPES = new Set(["application/dash+xml"]);

export const CAT_CATCH_VIDEO_EXTENSIONS = new Set([
  "3gp",
  "asf",
  "avi",
  "divx",
  "f4v",
  "flv",
  "hlv",
  "m4s",
  "mkv",
  "mov",
  "mp4",
  "mpeg",
  "mpeg4",
  "movie",
  "ogv",
  "ts",
  "vid",
  "webm",
  "wmv",
]);

export const CAT_CATCH_AUDIO_EXTENSIONS = new Set([
  "aac",
  "acc",
  "flac",
  "m4s",
  "m4a",
  "mp3",
  "ogg",
  "opus",
  "wav",
  "weba",
  "wma",
]);

const CAT_CATCH_MEDIA_EXTENSIONS = new Set([
  ...CAT_CATCH_VIDEO_EXTENSIONS,
  ...CAT_CATCH_AUDIO_EXTENSIONS,
  "m3u",
  "m3u8",
  "mpd",
]);

export function isCatCatchM3u8(extension: string, mime = ""): boolean {
  const type = String(mime || "").toLowerCase();
  return (
    extension === "m3u8"
    || extension === "m3u"
    || CAT_CATCH_HLS_TYPES.has(type)
    || type.endsWith("/vnd.apple.mpegurl")
    || type.endsWith("/x-mpegurl")
    || type.endsWith("/mpegurl")
    || type.endsWith("/octet-stream-m3u8")
  );
}

export function isCatCatchMpd(extension: string, mime = ""): boolean {
  return extension === "mpd" || CAT_CATCH_MPD_TYPES.has(String(mime || "").toLowerCase());
}

export function isCatCatchMedia(extension: string, mime = ""): boolean {
  const type = mime.toLowerCase();
  return (
    CAT_CATCH_MEDIA_EXTENSIONS.has(extension)
    || type.startsWith("video/")
    || type.startsWith("audio/")
    || isCatCatchM3u8(extension, type)
    || isCatCatchMpd(extension, type)
  );
}

export const CAT_CATCH_SCRIPT_FEATURES = {
  recorder: { script: "recorder.js", i18n: true, allFrames: true, world: "MAIN", reloadRequired: false },
  webrtc: { script: "webrtc.js", i18n: true, allFrames: true, world: "MAIN", reloadRequired: true },
  recorder2: { script: "recorder2.js", i18n: true, allFrames: false, world: "ISOLATED", reloadRequired: false },
  search: { script: "search.js", i18n: false, allFrames: true, world: "MAIN", reloadRequired: true },
  catch: { script: "catch.js", i18n: true, allFrames: true, world: "MAIN", reloadRequired: true },
} as const;

export const MOBILE_USER_AGENT =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1";
