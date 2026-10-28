import {classifyTrackRole, isDashSegmentUrl, isStreamUrl, stripRangeParams} from "../url-classify";
import {bestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

const isMuxedUrl = (url: string) => !isDashSegmentUrl(url);

// Fallback strategy — runs when no per-site strategy matches the hostname.
export function selectGeneric(ctx: ResolveContext): Resolution {
  const post = postBindAttributedUrls(ctx.clicked).filter((r) => r.clickedVideo !== "other");
  const pick = (predicate: (url: string, contentType: string) => boolean) =>
    bestMatching(post, predicate) ?? bestMatching(ctx.clickedVideoUrls, predicate);

  const master = post.find((r) => r.isMaster);
  if (master) {
    return { kind: "selection", selection: { kind: "stream", url: master.url } };
  }

  const stream = bestMatching(post, isStreamUrl);
  if (stream) {
    return { kind: "selection", selection: { kind: "stream", url: stream } };
  }

  if (ctx.clicked.formKind === "muxed") {
    const muxed = pick(isMuxedUrl);
    if (muxed) {
      return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed), formKind: "muxed" } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }

  if (ctx.clicked.formKind === "dash") {
    const video = pick((url, contentType) => classifyTrackRole(url, contentType) === "video");
    const audio = pick((url, contentType) => classifyTrackRole(url, contentType) === "audio");
    if (video && audio) {
      return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(video), audio: stripRangeParams(audio) } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForSeparateTracks") };
  }

  // formKind unknown: a guess between unrelated videos is worse than asking, so only evidence or uniqueness picks.
  if (post.length === 0) {
    const muxed = pick(isMuxedUrl);
    if (muxed) {
      return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed), formKind: "unknown" } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }
  const evidenced = post.filter((r) => r.clickedVideo === "same");
  // Two evidenced files are a duration collision between reels, not a choice.
  const evidencedMuxed = evidenced.filter((r) => isMuxedUrl(r.url));
  const muxed = evidencedMuxed.length === 1 ? evidencedMuxed[0].url : (post.length === 1 && isMuxedUrl(post[0].url) ? post[0].url : undefined);
  if (muxed) {
    return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed), formKind: "unknown" } };
  }
  const pair = selectMergePair(evidenced, classifyTrackRole) ?? (post.length === 2 ? selectMergePair(post, classifyTrackRole) : null);
  if (pair) {
    return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
  }
  if (post.length === 1) {
    // The sibling track may still be in flight pre-MSE-ack.
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForSeparateTracks") };
  }
  return { kind: "refused", message: chrome.i18n.getMessage("errorMultipleMediaFound") };
}
