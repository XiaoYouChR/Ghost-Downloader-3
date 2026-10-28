// Strategies see only URL + content-type so they can't reach into background-only fields.

import {isCatCatchM3u8, isCatCatchMedia, isCatCatchMpd} from "../../shared/cat-catch";
import {dashTrackRoleOf, fileExtension, filenameFromUrl, mimeFromUrl} from "../../shared/utils";

export type TrackRole = "video" | "audio" | "muxed" | "unknown";

export function hostEndsWith(url: string, suffix: string): boolean {
  try {
    return new URL(url).hostname.endsWith(suffix);
  } catch {
    return false;
  }
}

// Instagram serves DASH segments as byte-ranges over one signed URL; bytestart/byteend
// rotate per chunk, so stripping them gets the full track in one request. `_nc_rmd` is
// FB/IG's chunk-routing hint that changes per chunk without affecting auth.
const RANGE_PARAM_KEYS = ["bytestart", "byteend", "_nc_rmd"];

export function stripRangeParams(url: string): string {
  try {
    const parsed = new URL(url);
    let modified = false;
    for (const key of RANGE_PARAM_KEYS) {
      if (parsed.searchParams.has(key)) {
        parsed.searchParams.delete(key);
        modified = true;
      }
    }
    return modified ? parsed.toString() : url;
  } catch {
    return url;
  }
}

export function isStreamUrl(url: string, contentType: string): boolean {
  const ext = fileExtension(filenameFromUrl(url));
  return isCatCatchM3u8(ext, contentType) || isCatCatchMpd(ext, contentType);
}

export function isDashSegmentUrl(url: string): boolean {
  if (url.includes("/media-audio-") || url.includes("/media-video-")) { return true; }
  return fileExtension(filenameFromUrl(url)) === "m4s";
}

// ByteDance CDNs (Douyin, TikTok) tag track role in the URL path.
function trackRoleFromPath(url: string): "video" | "audio" | "" {
  if (url.includes("/media-audio-")) { return "audio"; }
  if (url.includes("/media-video-")) { return "video"; }
  return "";
}

export function isInstagramCdnUrl(url: string): boolean {
  return hostEndsWith(url, "cdninstagram.com") || hostEndsWith(url, "fbcdn.net");
}

function parseEfg(url: string): Record<string, unknown> | null {
  try {
    const efg = new URL(url).searchParams.get("efg");
    if (!efg) { return null; }
    return JSON.parse(atob(efg));
  } catch {
    return null;
  }
}

export function instagramVencodeTag(url: string): string {
  const efg = parseEfg(url);
  if (!efg || typeof efg !== "object") { return ""; }
  const tag = (efg as Record<string, unknown>).vencode_tag;
  return typeof tag === "string" ? tag : "";
}

export function instagramAssetId(url: string): string {
  const efg = parseEfg(url);
  if (!efg || typeof efg !== "object") { return ""; }
  const id = (efg as Record<string, unknown>).xpv_asset_id;
  if (typeof id === "string") { return id; }
  if (typeof id === "number") { return String(id); }
  return "";
}

export function fbCdnBitrate(url: string): number {
  const efg = parseEfg(url);
  if (!efg || typeof efg !== "object") { return 0; }
  const br = (efg as Record<string, unknown>).bitrate;
  return typeof br === "number" && br > 0 ? br : 0;
}

export function fbCdnDuration(url: string): number {
  const efg = parseEfg(url);
  if (!efg || typeof efg !== "object") { return 0; }
  const dur = (efg as Record<string, unknown>).duration_s;
  return typeof dur === "number" && dur > 0 ? dur : 0;
}

export function instagramKindOf(url: string): "video" | "audio" | "" {
  const tag = instagramVencodeTag(url);
  if (!tag) { return ""; }
  if (tag.includes("_audio")) { return "audio"; }
  if (tag.includes("dash_")) { return "video"; }
  return "";
}

const VIDEO_ID_QUERY_KEYS = ["__vid", "v", "modal_id", "video_id", "id", "bvid", "aid"];

function looksLikeVideoIdSegment(segment: string): boolean {
  if (segment.length < 10) { return false; }
  if (!/^[A-Za-z0-9_-]+$/.test(segment)) { return false; }
  let longestRun = 0;
  for (const run of segment.split(/[-_]+/)) {
    if (run.length > longestRun) { longestRun = run.length; }
  }
  return longestRun >= 10;
}

export function urlIdHints(url: string): Set<string> {
  const result = new Set<string>();
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return result;
  }
  for (const segment of parsed.pathname.split("/")) {
    if (looksLikeVideoIdSegment(segment)) { result.add(segment); }
  }
  for (const key of VIDEO_ID_QUERY_KEYS) {
    const value = parsed.searchParams.get(key);
    if (value && value.length >= 4) { result.add(`${key}=${value}`); }
  }
  if (isInstagramCdnUrl(url)) {
    const assetId = instagramAssetId(url);
    if (assetId) { result.add(`xpv_asset_id=${assetId}`); }
  }
  return result;
}

// CDN path segments are storage hashes and v/id/aid also carry cache busters, so neither can prove "other".
const OTHER_PROVING_QUERY_KEYS = ["__vid", "modal_id", "video_id", "bvid"];

function queryIdValues(parsed: URL, keys: string[]): Set<string> {
  const values = new Set<string>();
  for (const key of keys) {
    const value = parsed.searchParams.get(key);
    if (value && value.length >= 4) { values.add(value); }
  }
  return values;
}

function pathIdValues(parsed: URL): Set<string> {
  return new Set(parsed.pathname.split("/").filter(looksLikeVideoIdSegment));
}

export type ClickedVideoMatch = "same" | "other" | "unknown";

// By value, not key: Douyin's page says modal_id=X where its CDN says __vid=X.
export function matchClickedVideoById(url: string, pageUrl: URL): ClickedVideoMatch {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return "unknown";
  }
  const pageIds = new Set([...queryIdValues(pageUrl, VIDEO_ID_QUERY_KEYS), ...pathIdValues(pageUrl)]);
  if (pageIds.size === 0) { return "unknown"; }
  for (const id of [...queryIdValues(parsed, VIDEO_ID_QUERY_KEYS), ...pathIdValues(parsed)]) {
    if (pageIds.has(id)) { return "same"; }
  }
  const isProvable = queryIdValues(parsed, OTHER_PROVING_QUERY_KEYS).size > 0 && queryIdValues(pageUrl, OTHER_PROVING_QUERY_KEYS).size > 0;
  return isProvable ? "other" : "unknown";
}

export function classifyTrackRole(url: string, contentType: string): TrackRole {
  const pathRole = trackRoleFromPath(url);
  if (pathRole) { return pathRole; }

  const mime = (contentType || mimeFromUrl(url) || "").toLowerCase();

  // SourceBuffer mime (`codecs=...`) wins outright: CDNs serve DASH audio as video/mp4 (Bilibili).
  if (mime.includes("codecs")) {
    if (mime.startsWith("video/")) { return "video"; }
    if (mime.startsWith("audio/")) { return "audio"; }
  }

  if (mime.startsWith("video/") && !isDashSegmentUrl(url)) { return "video"; }
  if (mime.startsWith("audio/")) { return "audio"; }

  const ext = fileExtension(filenameFromUrl(url));

  // m4s never defaults to muxed — a lone audio segment would otherwise dispatch as a
  // video file. Returning "unknown" makes the strategy wait for a sibling track.
  if (ext === "m4s") {
    const dashRole = dashTrackRoleOf(filenameFromUrl(url), url);
    if (dashRole === "video" || dashRole === "audio") { return dashRole; }
    return "unknown";
  }

  if (isCatCatchMedia(ext, mime)) {
    return "muxed";
  }
  return "unknown";
}
