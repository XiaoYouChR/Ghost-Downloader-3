// Strategies see only URL + content-type so they can't reach into background-only fields.

import {isCatCatchM3u8, isCatCatchMedia, isCatCatchMpd} from "../shared/cat-catch";
import {dashTrackRoleOf, fileExtension, filenameFromUrl, mimeFromUrl} from "../shared/utils";

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

// Douyin tags track role in the URL path; the "prime" muxed-MP4 has no marker but stays
// on douyinvod.com with __vid in the query.
export function douyinKindOf(url: string): "video" | "audio" | "muxed" | "" {
  if (url.includes("/media-audio-")) { return "audio"; }
  if (url.includes("/media-video-")) { return "video"; }
  if (hostEndsWith(url, "douyinvod.com") && url.includes("__vid=")) { return "muxed"; }
  return "";
}

export function classifyTrackRole(url: string, contentType: string): TrackRole {
  const douyin = douyinKindOf(url);
  if (douyin === "muxed") { return "muxed"; }
  if (douyin === "video") { return "video"; }
  if (douyin === "audio") { return "audio"; }

  const mime = (contentType || mimeFromUrl(url) || "").toLowerCase();

  // SourceBuffer mime (`codecs=...`) wins outright: Bilibili's da3 format puts both
  // video (30016) and audio (30216) in the same trackId range that the heuristic uses,
  // and only the MSE-side mime tells them apart.
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
