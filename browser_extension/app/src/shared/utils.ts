import type {Resource, DesktopConnectionState, TaskSummary, ResourceKind,} from "./types";
import {
    CAT_CATCH_AUDIO_EXTENSIONS,
    CAT_CATCH_VIDEO_EXTENSIONS,
    isCatCatchM3u8,
    isCatCatchMedia,
    isCatCatchMpd,
} from "./cat-catch";

const ACTIVE_STATUSES = new Set(["running", "waiting", "paused", "failed"]);
const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "avif", "heic"]);
const ARCHIVE_EXTENSIONS = new Set(["zip", "7z", "rar", "tar", "gz", "bz2", "xz"]);
const PDF_EXTENSIONS = new Set(["pdf"]);
const SPREADSHEET_EXTENSIONS = new Set(["xls", "xlsx", "csv", "tsv", "ods", "numbers"]);
const DOCUMENT_EXTENSIONS = new Set([
  "txt",
  "md",
  "rtf",
  "doc",
  "docx",
  "ppt",
  "pptx",
  "pages",
  "key",
  "epub",
]);

export type AccentTone = "neutral" | "success" | "info" | "warning" | "danger";
export type VisualKind =
  | "download"
  | "video"
  | "audio"
  | "archive"
  | "document"
  | "pdf"
  | "spreadsheet"
  | "image"
  | "stream";
type ResourceParserHint = "m3u8" | "mpd" | "media" | "download" | "other";
type ResourceDeliveryTarget = "desktop" | "browser_download";
type ResourceMediaKind = "video" | "audio" | "";

interface ResourcePresentation {
  extension: string;
  parserHint: ResourceParserHint;
  deliveryTarget: ResourceDeliveryTarget;
  primaryBadge: string;
  statusText: string;
  actionLabel: string;
  needsDesktop: boolean;
  tags: string[];
  visual: {
    kind: VisualKind;
  };
}

export function sortTasks(tasks: TaskSummary[]): TaskSummary[] {
  return [...tasks].sort((left, right) => {
    const leftActive = ACTIVE_STATUSES.has(left.status);
    const rightActive = ACTIVE_STATUSES.has(right.status);
    if (leftActive !== rightActive) {
      return leftActive ? -1 : 1;
    }
    return right.createdAt - left.createdAt;
  });
}

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 100 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatTaskStatus(status: string): string {
  switch (status) {
    case "running":
      return chrome.i18n.getMessage("downloading");
    case "waiting":
      return chrome.i18n.getMessage("waiting");
    case "paused":
      return chrome.i18n.getMessage("paused");
    case "completed":
      return chrome.i18n.getMessage("completed");
    case "failed":
      return chrome.i18n.getMessage("failed");
    default:
      return status;
  }
}

export function formatTaskMetric(task: TaskSummary): string {
  if (task.speed > 0) {
    return `${formatBytes(task.speed)}/s`;
  }
  return `${formatBytes(task.receivedBytes)} / ${task.fileSize > 0 ? formatBytes(task.fileSize) : "--"}`;
}

export function formatProgress(task: TaskSummary): string {
  if (task.fileSize > 0) {
    return `${formatBytes(task.receivedBytes)} / ${formatBytes(task.fileSize)}`;
  }
  return `${formatBytes(task.receivedBytes)} / --`;
}

export function formatDuration(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return "00:00";
  }

  const totalSeconds = Math.floor(value);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const hours = Math.floor(totalSeconds / 3600);

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function formatCapturedAt(timestamp: number): string {
  const date = new Date(timestamp);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function truncate(text: string, max = 44): string {
  if (!text || text.length <= max) {
    return text;
  }
  return `${text.slice(0, Math.max(0, max - 3))}...`;
}

export function connectionTone(state: DesktopConnectionState): AccentTone {
  switch (state) {
    case "connected":
      return "success";
    case "connecting":
    case "authenticating":
      return "info";
    case "missing_token":
      return "warning";
    case "unauthorized":
    case "disconnected":
      return "danger";
    default:
      return "neutral";
  }
}

export function connectionLabel(state: DesktopConnectionState, fallback: string): string {
  if (fallback?.trim()) {
    return fallback;
  }
  switch (state) {
    case "connected":
      return chrome.i18n.getMessage("connected");
    case "connecting":
      return chrome.i18n.getMessage("connecting");
    case "authenticating":
      return chrome.i18n.getMessage("authenticating");
    case "missing_token":
      return chrome.i18n.getMessage("awaitingPairing");
    case "unauthorized":
      return chrome.i18n.getMessage("tokenInvalid");
    default:
      return chrome.i18n.getMessage("disconnected");
  }
}

export function domainFromUrl(value: string): string {
  try {
    return new URL(value).hostname;
  } catch {
    return "";
  }
}

export function isPdf(extension: string, mime = ""): boolean {
  return PDF_EXTENSIONS.has(extension) || mime.toLowerCase() === "application/pdf";
}

export function isCapturable(extension: string, mime = ""): boolean {
  return isCatCatchMedia(extension, mime) || isPdf(extension, mime);
}

export function mimeFromUrl(value: string): string {
  try {
    const mime = new URL(value).searchParams.get("mime_type")?.replace(/_/g, "/").toLowerCase() ?? "";
    return isCatCatchMedia("", mime) ? mime : "";
  } catch {
    return "";
  }
}

export function filenameFromUrl(value: string): string {
  try {
    const url = new URL(value);
    return decodeURIComponent(url.pathname.split("/").pop() || "");
  } catch {
    return "";
  }
}

export function fileExtension(name: string): string {
  const dotIndex = name.lastIndexOf(".");
  return dotIndex < 0 ? "" : name.slice(dotIndex + 1).toLowerCase();
}

function parserHintOf(url: string, mime: string, extension: string): ResourceParserHint {
  const loweredUrl = url.toLowerCase();
  const loweredMime = mime.toLowerCase();
  const loweredExt = extension.toLowerCase();

  if (isCatCatchM3u8(loweredExt, loweredMime) || loweredUrl.includes(".m3u8")) {
    return "m3u8";
  }
  if (isCatCatchMpd(loweredExt, loweredMime) || loweredUrl.includes(".mpd")) {
    return "mpd";
  }
  if (isCatCatchMedia(loweredExt, loweredMime)) {
    return "media";
  }
  if (["zip", "7z", "rar", "pdf", "exe", "msi", "dmg", "pkg", "apk", "iso"].includes(loweredExt)) {
    return "download";
  }
  return "other";
}

// Fallback when no SourceBuffer mime is around: explicit video/audio markers in the URL.
export function dashTrackRoleOf(filename: string, url: string): ResourceMediaKind {
  const name = filename || filenameFromUrl(url);
  const lowered = `${name} ${url}`.toLowerCase();

  if (/(^|[-_.\\/])(video)([-_.\\/]|$)/i.test(lowered)) {
    return "video";
  }
  if (/(^|[-_.\\/])(audio)([-_.\\/]|$)/i.test(lowered)) {
    return "audio";
  }
  return "";
}

// Container mime can't tell DASH tracks apart (Bilibili serves audio as video/mp4), so DASH
// segments only trust a SourceBuffer mime with codecs or explicit URL markers.
export function trackRoleOf(resource: Resource): ResourceMediaKind {
  const mime = resource.mime.toLowerCase();
  if (mime.includes("codecs")) {
    if (mime.startsWith("video/")) { return "video"; }
    if (mime.startsWith("audio/")) { return "audio"; }
  }
  if (isDashSegment(resource)) {
    return dashTrackRoleOf(resource.filename, resource.url);
  }

  if (mime.startsWith("video/")) { return "video"; }
  if (mime.startsWith("audio/")) { return "audio"; }
  const extension = fileExtension(resource.filename || filenameFromUrl(resource.url));
  if (CAT_CATCH_VIDEO_EXTENSIONS.has(extension) && !CAT_CATCH_AUDIO_EXTENSIONS.has(extension)) { return "video"; }
  if (CAT_CATCH_AUDIO_EXTENSIONS.has(extension) && !CAT_CATCH_VIDEO_EXTENSIONS.has(extension)) { return "audio"; }
  return "";
}

function visualKindOf({
  extension,
  mime,
  parserHint,
  trackRole,
}: {
  extension: string;
  mime?: string;
  parserHint?: ResourceParserHint;
  trackRole?: ResourceMediaKind;
}): VisualKind {
  const loweredMime = mime?.toLowerCase() ?? "";
  const loweredExtension = extension.toLowerCase();

  if (parserHint === "m3u8" || parserHint === "mpd") {
    return "stream";
  }
  if (trackRole) {
    return trackRole;
  }
  if (loweredMime.startsWith("video/") || CAT_CATCH_VIDEO_EXTENSIONS.has(loweredExtension)) {
    return "video";
  }
  if (loweredMime.startsWith("audio/") || CAT_CATCH_AUDIO_EXTENSIONS.has(loweredExtension)) {
    return "audio";
  }
  if (loweredMime.startsWith("image/") || IMAGE_EXTENSIONS.has(loweredExtension)) {
    return "image";
  }
  if (ARCHIVE_EXTENSIONS.has(loweredExtension)) {
    return "archive";
  }
  if (isPdf(loweredExtension, loweredMime)) {
    return "pdf";
  }
  if (
    SPREADSHEET_EXTENSIONS.has(loweredExtension)
    || loweredMime.includes("spreadsheet")
    || loweredMime.includes("excel")
    || loweredMime.includes("csv")
  ) {
    return "spreadsheet";
  }
  if (DOCUMENT_EXTENSIONS.has(loweredExtension) || loweredMime.startsWith("text/")) {
    return "document";
  }
  return "download";
}

function resourcePresentationParts(resource: Resource): {
  extension: string;
  parserHint: ResourceParserHint;
  deliveryTarget: ResourceDeliveryTarget;
} {
  const extension = fileExtension(resource.filename || filenameFromUrl(resource.url));
  return {
    extension,
    parserHint: parserHintOf(resource.url, resource.mime, extension),
    deliveryTarget: resource.url.startsWith("blob:") ? "browser_download" : "desktop",
  };
}

function resourcePrimaryBadge(resource: Resource, parts = resourcePresentationParts(resource)): string {
  if (parts.parserHint === "m3u8") {
    return "M3U8";
  }
  if (parts.parserHint === "mpd") {
    return "MPD";
  }

  if (parts.extension) {
    return parts.extension.slice(0, 6).toUpperCase();
  }
  if (resource.mime.startsWith("audio/")) {
    return chrome.i18n.getMessage("audio");
  }
  if (resource.mime.startsWith("video/")) {
    return chrome.i18n.getMessage("video");
  }
  return chrome.i18n.getMessage("resource");
}

function resourceVisualKindOf(resource: Resource, parts = resourcePresentationParts(resource)): VisualKind {
  return visualKindOf({
    extension: parts.extension,
    mime: resource.mime,
    parserHint: parts.parserHint,
    trackRole: trackRoleOf(resource),
  });
}

export function kindOf(resource: Resource): ResourceKind {
  const kind = resourceVisualKindOf(resource);
  if (kind === "stream") {
    return "video";
  }
  if (kind === "download") {
    return "other";
  }
  return kind;
}

export function describeResource(resource: Resource): ResourcePresentation {
  const parts = resourcePresentationParts(resource);

  const primaryBadge = resourcePrimaryBadge(resource, parts);
  const needsDesktop = parts.deliveryTarget === "desktop";
  const statusText = resource.sentToDesktopAt
    ? needsDesktop
      ? chrome.i18n.getMessage("sentToDesktop")
      : chrome.i18n.getMessage("sentToBrowserDownload")
    : needsDesktop
      ? chrome.i18n.getMessage("sendToDesktop")
      : chrome.i18n.getMessage("browserDownload");

  const tags = [primaryBadge];
  if (parts.deliveryTarget === "browser_download") {
    tags.push(chrome.i18n.getMessage("browserDownload"));
  }
  if (isDashSegment(resource)) {
    const role = trackRoleOf(resource);
    if (role === "video") { tags.push(chrome.i18n.getMessage("videoTrack")); }
    else if (role === "audio") { tags.push(chrome.i18n.getMessage("audioTrack")); }
  }
  const visual: ResourcePresentation["visual"] = {
    kind: resourceVisualKindOf(resource, parts),
  };

  return {
    extension: parts.extension,
    parserHint: parts.parserHint,
    deliveryTarget: parts.deliveryTarget,
    primaryBadge,
    statusText,
    actionLabel: needsDesktop ? chrome.i18n.getMessage("sendToDesktop") : chrome.i18n.getMessage("browserDownload"),
    needsDesktop,
    tags,
    visual,
  };
}

// A DASH segment can't stand alone — either the path carries /media-(audio|video)-
// (Douyin packagers) or it's .m4s (Bilibili/generic CMAF).
export function isDashSegment(resource: Resource): boolean {
  const url = resource.url;
  if (url.includes("/media-audio-") || url.includes("/media-video-")) {
    return true;
  }
  const extension = fileExtension(resource.filename || filenameFromUrl(url));
  return extension === "m4s";
}

export function canUseOnlineMerge(resource: Resource): boolean {
  const parts = resourcePresentationParts(resource);
  if (parts.deliveryTarget !== "desktop") {
    return false;
  }

  const mime = resource.mime.toLowerCase();
  return (
    parts.parserHint === "m3u8"
    || parts.parserHint === "mpd"
    || isCatCatchMedia(parts.extension, mime)
    || mime.endsWith("octet-stream")
  );
}

export function canUseOnlineMergeSelection(resources: Resource[]): boolean {
  return resources.length === 2 && resources.every(canUseOnlineMerge);
}

export function sortResourcesForOnlineMerge(resources: Resource[]): Resource[] {
  return [...resources].sort((left, right) => {
    const leftRole = trackRoleOf(left);
    const rightRole = trackRoleOf(right);
    if (leftRole === rightRole) {
      return 0;
    }
    if (leftRole === "video") {
      return -1;
    }
    if (rightRole === "video") {
      return 1;
    }
    return 0;
  });
}

export function taskActionLabel(task: TaskSummary): string {
  if (task.status === "running") {
    return chrome.i18n.getMessage("pause");
  }
  if (task.status === "paused" || task.status === "waiting" || task.status === "failed") {
    return chrome.i18n.getMessage("resume");
  }
  return "";
}

export function taskVisual(task: TaskSummary): { kind: VisualKind } {
  const extension = fileExtension(task.fileExt || task.name);
  return {
    kind: visualKindOf({
      extension,
      parserHint:
        task.packName.includes("m3u8") || extension === "m3u8" || extension === "mpd"
          ? "m3u8"
          : undefined,
    }),
  };
}
