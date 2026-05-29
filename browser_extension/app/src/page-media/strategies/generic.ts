import {classifyTrackRole, isDashSegmentUrl, isStreamUrl, stripRangeParams} from "../url-classify";
import {newestBy, postBindResources} from "../strategy";
import type {MediaStrategy, ResolveContext} from "../strategy";
import type {Resolution} from "../types";

// Fallback; matches() always true, so it must be registered last.
export class GenericStrategy implements MediaStrategy {
  readonly id = "generic";

  matches(_pageUrl: URL): boolean {
    return true;
  }

  resolve(ctx: ResolveContext): Resolution {
    const post = postBindResources(ctx.clicked);

    const stream = newestBy(post.filter((r) => isStreamUrl(r.url, r.contentType)), (r) => r.capturedAt);
    if (stream) {
      return { kind: "selection", selection: { kind: "stream", url: stream.url } };
    }

    if (ctx.clicked.formKind === "muxed") {
      const muxed = newestBy(post.filter((r) => !isDashSegmentUrl(r.url)), (r) => r.capturedAt);
      if (muxed) {
        return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed.url), formKind: "muxed" } };
      }
      return { kind: "pending", reason: "等待嗅探到当前视频资源" };
    }

    if (ctx.clicked.formKind === "dash") {
      const video = newestBy(post.filter((r) => classifyTrackRole(r.url, r.contentType) === "video"), (r) => r.capturedAt);
      const audio = newestBy(post.filter((r) => classifyTrackRole(r.url, r.contentType) === "audio"), (r) => r.capturedAt);
      if (video && audio) {
        return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(video.url), audio: stripRangeParams(audio.url) } };
      }
      return { kind: "pending", reason: "等待音视频分轨齐全" };
    }

    if (post.length === 0) {
      return { kind: "pending", reason: "等待嗅探到当前视频资源" };
    }
    if (post.length === 1) {
      const only = post[0];
      if (isDashSegmentUrl(only.url)) {
        // The sibling track may still be in flight pre-MSE-ack.
        return { kind: "pending", reason: "等待音视频分轨齐全" };
      }
      return { kind: "selection", selection: { kind: "single", url: stripRangeParams(only.url), formKind: "unknown" } };
    }
    return { kind: "refused", message: "找到多个媒体资源，请在资源嗅探页选择" };
  }
}
