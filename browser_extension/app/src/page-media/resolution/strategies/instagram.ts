import {fbCdnBitrate, instagramAssetId, instagramKindOf, isInstagramCdnUrl, stripRangeParams} from "../url-classify";
import {postBindAttributedUrls} from "../strategy";
import type {AttributedUrlView, FindUrlsByIdHint, ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

function selectBestPair(
  urls: ReadonlyArray<AttributedUrlView>,
): { video: string; audio: string } | null {
  let bestVideo: { url: string; bitrate: number } | null = null;
  let bestAudio: { url: string; bitrate: number } | null = null;
  for (const entry of urls) {
    const kind = instagramKindOf(entry.url);
    const bitrate = fbCdnBitrate(entry.url);
    if (kind === "video" && (!bestVideo || bitrate > bestVideo.bitrate)) {
      bestVideo = { url: entry.url, bitrate };
    } else if (kind === "audio" && (!bestAudio || bitrate > bestAudio.bitrate)) {
      bestAudio = { url: entry.url, bitrate };
    }
  }
  return bestVideo && bestAudio ? { video: bestVideo.url, audio: bestAudio.url } : null;
}

// Group by xpv_asset_id, try each group by segment count (the actively playing video
// has the most fetched segments), then by highest video bitrate as tiebreaker.
function matchPairByAssetId(
  post: ReadonlyArray<AttributedUrlView>,
): { video: string; audio: string } | null {
  const byAsset = new Map<string, AttributedUrlView[]>();
  for (const entry of post) {
    const id = instagramAssetId(entry.url);
    if (!id) { continue; }
    let group = byAsset.get(id);
    if (!group) { group = []; byAsset.set(id, group); }
    group.push(entry);
  }
  if (byAsset.size <= 1) { return selectBestPair(post); }
  const maxVideoBitrate = (urls: ReadonlyArray<AttributedUrlView>) =>
    urls.reduce((max, e) => Math.max(max, instagramKindOf(e.url) === "video" ? fbCdnBitrate(e.url) : 0), 0);
  const groups = [...byAsset.values()].sort((a, b) =>
    b.length - a.length || maxVideoBitrate(b) - maxVideoBitrate(a));
  for (const group of groups) {
    const pair = selectBestPair(group);
    if (pair) { return pair; }
  }
  return null;
}

export function selectMeta(ctx: ResolveContext, findUrlsByIdHint: FindUrlsByIdHint): Resolution {
  const post = postBindAttributedUrls(ctx.clicked).filter((r) => isInstagramCdnUrl(r.url));

  if (ctx.clicked.formKind === "dash") {
    const pair = matchPairByAssetId(post) ?? findPairByAssetId(post, findUrlsByIdHint);
    if (pair) {
      return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForInstagramSeparateTracks") };
  }

  if (post.length === 0) {
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }
  const pair = matchPairByAssetId(post);
  if (pair) {
    return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
  }
  return { kind: "pending", reason: chrome.i18n.getMessage("waitingForInstagramSeparateTracks") };
}

// Extract xpv_asset_id from any URL we already have, then search all sessions for
// sibling tracks with the same asset ID — rescues prefetched URLs still owned by a
// sibling session.
function findPairByAssetId(
  post: ReturnType<typeof postBindAttributedUrls>,
  findUrlsByIdHint: FindUrlsByIdHint,
): { video: string; audio: string } | null {
  let assetId = "";
  for (const entry of post) {
    assetId = instagramAssetId(entry.url);
    if (assetId) { break; }
  }
  if (!assetId) { return null; }
  const matches = findUrlsByIdHint(`xpv_asset_id=${assetId}`);
  return selectBestPair(matches);
}
