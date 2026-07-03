import {douyinKindOf, hostEndsWith} from "../url-classify";
import {newestMatching, postBindAttributedUrls, selectMergePair} from "../strategy";
import type {FindUrlsByIdHint, ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

// Until the next reel's MSE binds and correlation locks the URL, the prefetched URL is
// still provisionally owned by the previous reel's session. modal_id is what survives
// that window.
export function selectDouyin(ctx: ResolveContext, findUrlsByIdHint: FindUrlsByIdHint): Resolution {
  const post = postBindAttributedUrls(ctx.clicked).filter((r) => hostEndsWith(r.url, "douyinvod.com"));

  if (ctx.clicked.formKind === "muxed") {
    const muxed = newestMatching(post, (url) => douyinKindOf(url) === "muxed") ?? findByModalId(ctx, findUrlsByIdHint, "muxed");
    if (muxed) {
      return { kind: "selection", selection: { kind: "single", url: muxed, formKind: "muxed" } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForDouyinMuxedUrl") };
  }

  if (ctx.clicked.formKind === "dash") {
    const pair = selectMergePair(post, douyinKindOf);
    if (pair) {
      return { kind: "selection", selection: { kind: "merge", video: pair.video, audio: pair.audio } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForDouyinSeparateTracks") };
  }

  // formKind unknown — MSE hasn't reported yet.
  if (post.length === 0) {
    const fromModalId = findByModalId(ctx, findUrlsByIdHint, "muxed");
    if (fromModalId) {
      return { kind: "selection", selection: { kind: "single", url: fromModalId, formKind: "unknown" } };
    }
    return { kind: "pending", reason: chrome.i18n.getMessage("waitingForVideoResource") };
  }
  const muxed = newestMatching(post, (url) => douyinKindOf(url) === "muxed");
  if (muxed) {
    return { kind: "selection", selection: { kind: "single", url: muxed, formKind: "unknown" } };
  }
  const pair = selectMergePair(post, douyinKindOf);
  if (pair) {
    return { kind: "selection", selection: { kind: "merge", video: pair.video, audio: pair.audio } };
  }
  return { kind: "refused", message: chrome.i18n.getMessage("errorCannotDetermineDouyinMediaForm") };
}

// Ledger query crosses session boundaries — that's what lets us pick the prefetched
// URL even when it's still provisionally owned by the previous reel.
function findByModalId(ctx: ResolveContext, findUrlsByIdHint: FindUrlsByIdHint, kind: "muxed" | "video" | "audio"): string | undefined {
  const modalId = ctx.pageUrl.searchParams.get("modal_id");
  if (!modalId || modalId.length < 4) { return undefined; }
  const matches = findUrlsByIdHint(`__vid=${modalId}`);
  return newestMatching(matches, (url) => douyinKindOf(url) === kind);
}
