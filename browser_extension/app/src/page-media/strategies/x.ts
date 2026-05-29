import {hostEndsWith, isStreamUrl} from "../url-classify";
import {newestBy, postBindResources} from "../strategy";
import type {MediaStrategy, ResolveContext} from "../strategy";
import type {Resolution} from "../types";

const TWITTER_MEDIA_ID = /\/(?:amplify_video(?:_thumb)?|ext_tw_video|tweet_video)\/(\d+)\//i;

function mediaIdOf(url: string): string {
  return TWITTER_MEDIA_ID.exec(url)?.[1] ?? "";
}

// Master playlist sits one segment under /pl/; variants nest a codec sub-segment
// (avc1/hevc/av01/mp4a). Variants are single-track downloads.
function isMasterTwitterPlaylist(url: string): boolean {
  try {
    const parts = new URL(url).pathname.split("/").filter(Boolean);
    const plIdx = parts.indexOf("pl");
    return plIdx !== -1 && plIdx === parts.length - 2;
  } catch {
    return false;
  }
}

// Master m3u8 only — variants are single-track and dropping one would give silent video.
// posterMediaId pins to this tweet so adjacent tweets' streams don't leak in.
export class XStrategy implements MediaStrategy {
  readonly id = "x";

  matches(pageUrl: URL): boolean {
    return pageUrl.hostname === "x.com" || pageUrl.hostname.endsWith(".x.com");
  }

  resolve(ctx: ResolveContext): Resolution {
    const posterMediaId = mediaIdOf(ctx.hints.poster ?? "");
    const allStreams = postBindResources(ctx.clicked).filter((r) =>
      hostEndsWith(r.url, "video.twimg.com")
      && isStreamUrl(r.url, r.contentType),
    );

    const candidates = posterMediaId
      ? allStreams.filter((r) => mediaIdOf(r.url) === posterMediaId)
      : allStreams;

    const masters = candidates.filter((r) => isMasterTwitterPlaylist(r.url));
    const pick = newestBy(masters, (r) => r.capturedAt);
    if (pick) {
      return { kind: "selection", selection: { kind: "stream", url: pick.url } };
    }

    return { kind: "pending", reason: "等待 X 主播放清单" };
  }
}
