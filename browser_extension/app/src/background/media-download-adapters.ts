import type {CapturedResource} from "../shared/types";
import {describeResource, mimeFromUrl} from "../shared/utils";

export type PageMediaPayload = {
  url: string;
  href?: string;
  poster?: string;
  resourceUrls?: string[];
};

export type MediaAdapterSelection = {
  resources: CapturedResource[];
  exclusive?: boolean;
  message?: string;
};

type MediaAdapter = {
  matches: (pageUrl: URL) => boolean;
  pick: (resources: CapturedResource[], payload: PageMediaPayload, pageUrl: URL) => MediaAdapterSelection;
};

const TWITTER_MEDIA_ID = /\/(?:amplify_video(?:_thumb)?|ext_tw_video|tweet_video)\/(\d+)\//i;

function hostEndsWith(url: string, suffix: string): boolean {
  try {
    return new URL(url).hostname.endsWith(suffix);
  } catch {
    return false;
  }
}

function sameResource(left: string, right: string): boolean {
  try {
    const leftUrl = new URL(left);
    const rightUrl = new URL(right);
    leftUrl.hash = "";
    rightUrl.hash = "";
    return leftUrl.toString() === rightUrl.toString();
  } catch {
    return left === right;
  }
}

function payloadResourceSet(payload: PageMediaPayload): Set<string> {
  return new Set([payload.url, ...(payload.resourceUrls ?? [])].filter(Boolean));
}

function matchesPayloadResource(resource: CapturedResource, payloadUrls: Set<string>): boolean {
  for (const url of payloadUrls) {
    if (sameResource(resource.url, url)) {
      return true;
    }
  }
  return false;
}

function mediaIdFromUrl(url: string): string {
  return TWITTER_MEDIA_ID.exec(url)?.[1] ?? "";
}

function isStream(resource: CapturedResource): boolean {
  const hint = describeResource(resource).parserHint;
  return hint === "m3u8" || hint === "mpd";
}

function douyinKind(resource: CapturedResource): "audio" | "video" | "" {
  const mime = mimeFromUrl(resource.url) || resource.mime.toLowerCase();
  if (mime.startsWith("audio/")) {
    return "audio";
  }
  if (mime.startsWith("video/")) {
    return "video";
  }
  const category = describeResource(resource).category;
  return category === "audio" || category === "video" ? category : "";
}

function pickDouyinTrack(
  resources: CapturedResource[],
  kind: "audio" | "video",
  payloadUrls: Set<string>,
  videoId: string,
): CapturedResource | undefined {
  const rank = (resource: CapturedResource) => (
    (matchesPayloadResource(resource, payloadUrls) ? 2 : 0)
    + (videoId && resource.url.includes(`__vid=${videoId}`) ? 1 : 0)
  );

  return resources
    .filter((resource) => douyinKind(resource) === kind)
    .sort((left, right) => (
      rank(right) - rank(left)
      || right.size - left.size
      || right.capturedAt - left.capturedAt
    ))[0];
}

const adapters: MediaAdapter[] = [
  {
    matches: (pageUrl) => pageUrl.hostname === "x.com" || pageUrl.hostname.endsWith(".x.com"),
    pick: (resources, payload) => {
      const mediaId = mediaIdFromUrl(payload.poster ?? "") || mediaIdFromUrl(payload.url);
      const streams = resources.filter((resource) => (
        isStream(resource)
        && hostEndsWith(resource.url, "video.twimg.com")
        && (!mediaId || resource.url.includes(`/${mediaId}/`))
      ));
      return {
        exclusive: true,
        resources: streams.slice(0, 1),
        message: "X 当前媒体只捕获到分片时不能一键发送，请先在资源嗅探页选择完整清单",
      };
    },
  },
  {
    matches: (pageUrl) => pageUrl.hostname === "www.douyin.com" || pageUrl.hostname.endsWith(".douyin.com"),
    pick: (resources, payload, pageUrl) => {
      const videoId = pageUrl.searchParams.get("modal_id") ?? "";
      const payloadUrls = payloadResourceSet(payload);
      const douyinResources = resources.filter((resource) => hostEndsWith(resource.url, "douyinvod.com"));
      const video = pickDouyinTrack(douyinResources, "video", payloadUrls, videoId);
      const audio = pickDouyinTrack(douyinResources, "audio", payloadUrls, videoId);
      return {
        exclusive: true,
        resources: video && audio ? [video, audio] : [],
        message: "Douyin 当前媒体需要同时捕获视频和音频后才能一键合并，请播放几秒后重试",
      };
    },
  },
];

export function pickSiteMediaResources(
  resources: CapturedResource[],
  payload: PageMediaPayload,
): MediaAdapterSelection | null {
  try {
    const pageUrl = new URL(payload.href || "");
    const adapter = adapters.find((item) => item.matches(pageUrl));
    return adapter ? adapter.pick(resources, payload, pageUrl) : null;
  } catch {
    return null;
  }
}
