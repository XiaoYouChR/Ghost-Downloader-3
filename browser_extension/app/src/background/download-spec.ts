import type {Resource} from "../shared/types";
import {fileExtension, filenameFromUrl} from "../shared/utils";

// ResourceTaskOptions 的权威。Per ADR-0001, the extension — not the desktop — decides
// the filename/size/supportsRange for a browser-sourced task, because only the browser has
// the page context (title/poster) and the media's real response. This module is that
// authority: pure functions turning a captured 资源 (Resource) into the options the desktop
// trusts. The two exported entry points are the test surface; the helpers stay internal.

export interface ResourceTaskOptions {
  url: string;
  headers: Record<string, string>;
  filename: string;
  size: number;
  supportsRange: boolean;
}

// Minimal shape resourceNameFromCapture reads; CapturePayload (cat-catch addMedia path)
// structurally satisfies it.
export interface ResourceNameInput {
  url: string;
  filename?: string;
  mime?: string;
  ext?: string;
}

const MIME_EXTENSIONS: Record<string, string> = {
  "application/dash+xml": "mpd",
  "application/mpegurl": "m3u8",
  "application/vnd.apple.mpegurl": "m3u8",
  "application/x-mpegurl": "m3u8",
  "audio/aac": "aac",
  "audio/flac": "flac",
  "audio/mp4": "m4a",
  "audio/mpeg": "mp3",
  "audio/ogg": "ogg",
  "audio/wav": "wav",
  "audio/webm": "webm",
  "video/mp2t": "ts",
  "video/mp4": "mp4",
  "video/quicktime": "mov",
  "video/webm": "webm",
  "video/x-flv": "flv",
  "video/x-m4v": "m4v",
  "video/x-ms-wmv": "wmv",
};

function cleanFilename(value?: string): string {
  return (value ?? "")
    .trim()
    .replace(/[<>:"/\\|?*\x00-\x1f]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/[. ]+$/g, "")
    .trim()
    .slice(0, 160);
}

function extensionFromMime(mime?: string): string {
  const type = mime?.split(";")[0]?.trim().toLowerCase() ?? "";
  return MIME_EXTENSIONS[type] ?? "";
}

function filenameWithExtension(baseName: string, extension: string): string {
  const trimmedBaseName = cleanFilename(baseName) || "resource";
  const normalizedExt = extension.trim().replace(/^\./, "").toLowerCase();
  if (!normalizedExt) {
    return trimmedBaseName;
  }
  if (fileExtension(trimmedBaseName) === normalizedExt) {
    return trimmedBaseName;
  }
  return `${trimmedBaseName}.${normalizedExt}`;
}

// Capture-time name for a resource discovered via cat-catch's addMedia path.
export function resourceNameFromCapture(payload: ResourceNameInput): string {
  const ext = payload.ext?.trim() || extensionFromMime(payload.mime);
  const explicit = cleanFilename(payload.filename);
  if (explicit) {
    return ext && !fileExtension(explicit) ? filenameWithExtension(explicit, ext) : explicit;
  }

  const fromUrl = cleanFilename(filenameFromUrl(payload.url));
  if (fromUrl) {
    return ext ? filenameWithExtension(fromUrl, ext) : fromUrl;
  }

  return ext ? filenameWithExtension("resource", ext) : "resource";
}

// Task name derived from a captured resource; prefers the page title.
export function taskNameForResource(resource: Resource): string {
  const urlFilename = filenameFromUrl(resource.url);
  const current = cleanFilename(resource.filename || urlFilename);
  const extension = fileExtension(current)
    || fileExtension(urlFilename)
    || extensionFromMime(resource.mime);
  const title = cleanFilename(resource.pageTitle);
  const baseName = title || current || "resource";
  return filenameWithExtension(baseName, extension);
}

// 资源 → ResourceTaskOptions.
export function toResourceTaskOptions(resource: Resource): ResourceTaskOptions {
  return {
    url: resource.url,
    headers: resource.requestHeaders,
    filename: taskNameForResource(resource),
    size: resource.size,
    supportsRange: resource.supportsRange,
  };
}
