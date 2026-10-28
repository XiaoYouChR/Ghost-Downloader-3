import {classifyTrackRole, isDashSegmentUrl, isStreamUrl, stripRangeParams} from "../url-classify";
import {bestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {ResolveContext, SessionSnapshot} from "../strategy";
import type {Resolution, Selection} from "../../types";

const isMuxedUrl = (url: string) => !isDashSegmentUrl(url);
// TikTok declares its audio SourceBuffer as video/mp4, so the codec is what tells.
const isAudioTrack = (mimeType: string) => /^audio\/|codecs="?(mp4a|opus|vorbis|flac|[ae]c-3)/i.test(mimeType);

// Source Files hold the samples being played, so they settle the form whatever their URLs look like.
function selectBySourceFiles({ tracks, formKind }: SessionSnapshot): Selection | undefined {
  if (tracks.length === 1 && tracks[0].sourceUrls.length === 1) {
    return { kind: "single", url: stripRangeParams(tracks[0].sourceUrls[0]), formKind };
  }
  const video = tracks.find((track) => !isAudioTrack(track.mimeType))?.sourceUrls;
  const audio = tracks.find((track) => isAudioTrack(track.mimeType))?.sourceUrls;
  if (tracks.length !== 2 || video?.length !== 1 || !audio) { return undefined; }
  // The video's file holding the played audio too makes it the whole video, even when other files share the sound.
  if (audio.includes(video[0])) {
    return { kind: "single", url: stripRangeParams(video[0]), formKind: "muxed" };
  }
  if (audio.length === 1) {
    return { kind: "merge", video: stripRangeParams(video[0]), audio: stripRangeParams(audio[0]) };
  }
  return undefined;
}

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

  const bySourceFiles = selectBySourceFiles(ctx.clicked);
  if (bySourceFiles) {
    return { kind: "selection", selection: bySourceFiles };
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
  const onlyMuxed = post.length === 1 && isMuxedUrl(post[0].url) ? post[0].url : undefined;
  const muxed = evidencedMuxed.length === 1 ? evidencedMuxed[0].url : onlyMuxed;
  if (muxed) {
    return { kind: "selection", selection: { kind: "single", url: stripRangeParams(muxed), formKind: "unknown" } };
  }
  // An mp4 beside an unrelated mp3 is no pair, so without evidence only URLs naming themselves as tracks are paired.
  const isTrackPair = post.length === 2 && post.every((r) => isDashSegmentUrl(r.url));
  const pair = selectMergePair(evidenced, classifyTrackRole) ?? (isTrackPair ? selectMergePair(post, classifyTrackRole) : null);
  if (pair) {
    return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
  }
  if (post.length === 1) {
    // The sibling track may still be in flight pre-MSE-ack.
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForSeparateTracks") };
  }
  return { kind: "refused", message: chrome.i18n.getMessage("errorMultipleMediaFound") };
}
