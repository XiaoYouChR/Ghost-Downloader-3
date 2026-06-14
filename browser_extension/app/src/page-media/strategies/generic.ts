import {classifyTrackRole, isDashSegmentUrl, isStreamUrl, stripRangeParams} from "../url-classify";
import {newestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {MediaStrategy, ResolveContext} from "../strategy";
import type {Resolution} from "../types";

// Fallback; matches() always true, so it must be registered last.
export class GenericStrategy implements MediaStrategy {
  readonly id = "generic";

  matches(_pageUrl: URL): boolean {
    return true;
  }

  resolve(ctx: ResolveContext): Resolution {
    const post = postBindAttributedUrls(ctx.clicked);

    const stream = newestMatching(post, isStreamUrl);
    if (stream) {
      return { kind: "selection", selection: { kind: "stream", url: stream } };
    }

    if (ctx.clicked.formKind === "muxed") {
      const muxed = newestMatching(post, (url) => !isDashSegmentUrl(url));
      if (muxed) {
        return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed), formKind: "muxed" } };
      }
      return { kind: "pending", reason: "等待嗅探到当前视频资源" };
    }

    if (ctx.clicked.formKind === "dash") {
      const pair = selectMergePair(post, classifyTrackRole);
      if (pair) {
        return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
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
