import {classifyTrackRole, isDashSegmentUrl, isStreamUrl, stripRangeParams} from "../url-classify";
import {newestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

// Fallback strategy — runs when no per-site strategy matches the hostname.
export function selectGeneric(ctx: ResolveContext): Resolution {
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
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }

  if (ctx.clicked.formKind === "dash") {
    const pair = selectMergePair(post, classifyTrackRole);
    if (pair) {
      return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForSeparateTracks") };
  }

  if (post.length === 0) {
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }
  if (post.length === 1) {
    const only = post[0];
    if (isDashSegmentUrl(only.url)) {
      // The sibling track may still be in flight pre-MSE-ack.
      return { kind: "pending", reason: chrome.i18n.getMessage("waitingForSeparateTracks") };
    }
    return { kind: "selection", selection: { kind: "single", url: stripRangeParams(only.url), formKind: "unknown" } };
  }
  return { kind: "refused", message: chrome.i18n.getMessage("errorMultipleMediaFound") };
}
