import type {
  CapturedResource,
  DesktopConnectionState,
  GenericTaskSummary,
  ResourceFilter,
} from "./types";

const ACTIVE_STATUSES = new Set(["running", "waiting", "paused", "failed"]);
const VIDEO_EXTENSIONS = new Set(["mp4", "mkv", "webm", "mov", "avi", "flv", "m4s", "ts"]);
const AUDIO_EXTENSIONS = new Set(["mp3", "m4a", "flac", "wav", "aac", "opus", "ogg"]);
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
type ResourceDeliveryTarget = "gd3" | "browser_download";

interface ResourcePresentation {
  extension: string;
  parserHint: ResourceParserHint;
  deliveryTarget: ResourceDeliveryTarget;
  category: ResourceFilter;
  primaryBadge: string;
  statusText: string;
  actionLabel: string;
  needsDesktop: boolean;
  tags: string[];
  visual: {
    kind: VisualKind;
  };
}

export function sortTasks(tasks: GenericTaskSummary[]): GenericTaskSummary[] {
  return [...tasks].sort((left, right) => {
    const leftActive = ACTIVE_STATUSES.has(left.status);
    const rightActive = ACTIVE_STATUSES.has(right.status);
    if (leftActive !== rightActive) {
      return leftActive ? -1 : 1;
    }
    return right.createdAt - left.createdAt;
  });
}

function sortResources(resources: CapturedResource[]): CapturedResource[] {
  return [...resources].sort((left, right) => right.capturedAt - left.capturedAt);
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
      return "下载中";
    case "waiting":
      return "等待中";
    case "paused":
      return "已暂停";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

export function formatTaskMetric(task: GenericTaskSummary): string {
  if (task.speed > 0) {
    return `${formatBytes(task.speed)}/s`;
  }
  return `${formatBytes(task.receivedBytes)} / ${task.fileSize > 0 ? formatBytes(task.fileSize) : "--"}`;
}

export function formatProgress(task: GenericTaskSummary): string {
  if (task.fileSize > 0) {
    return `${formatBytes(task.receivedBytes)} / ${formatBytes(task.fileSize)}`;
  }
  return `${formatBytes(task.receivedBytes)} / --`;
}

export function formatShortTime(value: number): string {
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

export function shorten(value: string, max = 44): string {
  if (!value || value.length <= max) {
    return value;
  }
  return `${value.slice(0, Math.max(0, max - 3))}...`;
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
      return "已连接";
    case "connecting":
      return "正在连接";
    case "authenticating":
      return "正在校验";
    case "missing_token":
      return "待配对";
    case "unauthorized":
      return "令牌无效";
    default:
      return "未连接";
  }
}

export function domainFromUrl(value: string): string {
  try {
    return new URL(value).hostname;
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
  const trimmed = String(name || "").trim();
  const dotIndex = trimmed.lastIndexOf(".");
  if (dotIndex < 0) {
    return "";
  }
  return trimmed.slice(dotIndex + 1).toLowerCase();
}

function inferParserHint(rawUrl: string, mime: string, extension: string): ResourceParserHint {
  const loweredUrl = String(rawUrl || "").toLowerCase();
  const loweredMime = String(mime || "").toLowerCase();
  const loweredExt = String(extension || "").toLowerCase();

  if (loweredExt === "m3u8" || loweredExt === "m3u" || loweredUrl.includes(".m3u8") || loweredMime.includes("mpegurl")) {
    return "m3u8";
  }
  if (loweredExt === "mpd" || loweredUrl.includes(".mpd") || loweredMime === "application/dash+xml") {
    return "mpd";
  }
  if (loweredMime.startsWith("video/") || loweredMime.startsWith("audio/")) {
    return "media";
  }
  if (VIDEO_EXTENSIONS.has(loweredExt) || AUDIO_EXTENSIONS.has(loweredExt)) {
    return "media";
  }
  if (["zip", "7z", "rar", "pdf", "exe", "msi", "dmg", "pkg", "apk", "iso"].includes(loweredExt)) {
    return "download";
  }
  return "other";
}

function inferDeliveryTarget(url: string): ResourceDeliveryTarget {
  return String(url || "").startsWith("blob:") ? "browser_download" : "gd3";
}

function inferVisualKind({
  extension,
  mime,
  parserHint,
}: {
  extension: string;
  mime?: string;
  parserHint?: ResourceParserHint;
}): VisualKind {
  const loweredMime = String(mime || "").toLowerCase();
  const loweredExtension = String(extension || "").toLowerCase();

  if (parserHint === "m3u8" || parserHint === "mpd") {
    return "stream";
  }
  if (loweredMime.startsWith("video/") || VIDEO_EXTENSIONS.has(loweredExtension)) {
    return "video";
  }
  if (loweredMime.startsWith("audio/") || AUDIO_EXTENSIONS.has(loweredExtension)) {
    return "audio";
  }
  if (loweredMime.startsWith("image/") || IMAGE_EXTENSIONS.has(loweredExtension)) {
    return "image";
  }
  if (ARCHIVE_EXTENSIONS.has(loweredExtension)) {
    return "archive";
  }
  if (PDF_EXTENSIONS.has(loweredExtension) || loweredMime === "application/pdf") {
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

function resourceDerivedState(resource: CapturedResource): {
  extension: string;
  parserHint: ResourceParserHint;
  deliveryTarget: ResourceDeliveryTarget;
} {
  const extension = fileExtension(resource.filename || filenameFromUrl(resource.url));
  return {
    extension,
    parserHint: inferParserHint(resource.url, resource.mime, extension),
    deliveryTarget: inferDeliveryTarget(resource.url),
  };
}

function resourcePrimaryBadge(resource: CapturedResource, derived = resourceDerivedState(resource)): string {
  if (derived.parserHint === "m3u8") {
    return "M3U8";
  }
  if (derived.parserHint === "mpd") {
    return "MPD";
  }

  if (derived.extension) {
    return derived.extension.slice(0, 6).toUpperCase();
  }
  if (resource.mime.startsWith("audio/")) {
    return "音频";
  }
  if (resource.mime.startsWith("video/")) {
    return "视频";
  }
  return "资源";
}

export function describeResource(resource: CapturedResource): ResourcePresentation {
  const derived = resourceDerivedState(resource);
  const mime = String(resource.mime || "").toLowerCase();

  let category: ResourceFilter = "all";
  if (derived.parserHint === "m3u8" || derived.parserHint === "mpd") {
    category = "streaming";
  } else if (mime.startsWith("audio/") || AUDIO_EXTENSIONS.has(derived.extension)) {
    category = "audio";
  } else if (mime.startsWith("video/") || VIDEO_EXTENSIONS.has(derived.extension)) {
    category = "video";
  }

  const primaryBadge = resourcePrimaryBadge(resource, derived);
  const needsDesktop = derived.deliveryTarget === "gd3";
  const statusText = resource.sentToDesktopAt
    ? needsDesktop
      ? "已发送到 Ghost Downloader"
      : "已交给浏览器下载"
    : needsDesktop
      ? "发送到 Ghost Downloader"
      : "浏览器下载";

  const tags = [primaryBadge];
  tags.push(derived.deliveryTarget === "browser_download" ? "浏览器下载" : "GD3");
  if (!resource.sentToDesktopAt && (derived.parserHint === "m3u8" || derived.parserHint === "mpd")) {
    tags.push("流媒体");
  }
  if (
    !resource.sentToDesktopAt
    && resource.requestHeaders
    && Object.keys(resource.requestHeaders).length > 0
    && (derived.parserHint === "m3u8" || derived.parserHint === "mpd")
  ) {
    tags.push("需请求头");
  }
  if (!resource.sentToDesktopAt && (derived.parserHint === "download" || derived.parserHint === "media")) {
    tags.push("可直接下载");
  }
  const visual: ResourcePresentation["visual"] = {
    kind: inferVisualKind({
      extension: derived.extension,
      mime,
      parserHint: derived.parserHint,
    }),
  };

  return {
    extension: derived.extension,
    parserHint: derived.parserHint,
    deliveryTarget: derived.deliveryTarget,
    category,
    primaryBadge,
    statusText,
    actionLabel: needsDesktop ? "发送到 Ghost Downloader" : "浏览器下载",
    needsDesktop,
    tags,
    visual,
  };
}

export function filterResources(resources: CapturedResource[], filter: ResourceFilter): CapturedResource[] {
  const sorted = sortResources(resources);
  if (filter === "all") {
    return sorted;
  }
  return sorted.filter((resource) => describeResource(resource).category === filter);
}

export function taskActionLabel(task: GenericTaskSummary): string {
  if (task.status === "running") {
    return "暂停";
  }
  if (task.status === "paused" || task.status === "waiting" || task.status === "failed") {
    return "继续";
  }
  return "";
}

export function taskVisual(task: GenericTaskSummary): { kind: VisualKind } {
  const extension = fileExtension(task.fileExt || task.title);
  return {
    kind: inferVisualKind({
      extension,
      parserHint:
        task.packName.includes("m3u8") || extension === "m3u8" || extension === "mpd"
          ? "m3u8"
          : undefined,
    }),
  };
}
