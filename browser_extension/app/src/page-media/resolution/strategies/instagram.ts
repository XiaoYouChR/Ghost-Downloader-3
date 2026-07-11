import {instagramAssetId, instagramKindOf, isInstagramCdnUrl, stripRangeParams} from "../url-classify";
import {newestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {FindUrlsByIdHint, ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

export function selectInstagram(ctx: ResolveContext, findUrlsByIdHint: FindUrlsByIdHint): Resolution {
  const post = postBindAttributedUrls(ctx.clicked).filter((r) => isInstagramCdnUrl(r.url));

  if (ctx.clicked.formKind === "dash") {
    const pair = selectMergePair(post, instagramKindOf) ?? findPairByAssetId(post, findUrlsByIdHint);
    if (pair) {
      return { kind: "selection", selection: { kind: "merge", video: stripRangeParams(pair.video), audio: stripRangeParams(pair.audio) } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForInstagramSeparateTracks") };
  }

  if (post.length === 0) {
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }
  const pair = selectMergePair(post, instagramKindOf);
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
  const video = newestMatching(matches, (url) => instagramKindOf(url) === "video");
  const audio = newestMatching(matches, (url) => instagramKindOf(url) === "audio");
  return video && audio ? { video, audio } : null;
}
