import {selectGeneric} from "./strategies/generic";
import {selectMeta} from "./strategies/instagram";
import {selectYouTube} from "./strategies/youtube";
import {isStreamUrl} from "./url-classify";
import type {ClickedVideoMatch} from "./url-classify";
import type {Resolution, VideoSessionFormKind} from "../types";

// One attributed URL as the strategies see it — also the element type of
// SessionSnapshot.attributedUrls and of a FindUrlsByIdHint return.
export type AttributedUrlView = {
  readonly url: string;
  readonly contentType: string;
  readonly capturedAt: number;
  readonly isMaster?: boolean;
  readonly isLockedByMse: boolean;
  // Whether the URL holds the video the user clicked, judged by the Attribution Engine.
  readonly clickedVideo: ClickedVideoMatch;
};

// Strategies see only this — they MUST NOT reach back into the controller.
export type SessionSnapshot = {
  readonly formKind: VideoSessionFormKind;
  readonly lastBoundAt: number;
  readonly attributedUrls: ReadonlyArray<AttributedUrlView>;
  // One per SourceBuffer, with its Source Files (empty until the probe finds one).
  readonly tracks: ReadonlyArray<{ readonly mimeType: string; readonly sourceUrls: ReadonlyArray<string> }>;
};

export type ResolveHints = {
  readonly poster: string;
  readonly linkUrl: string;
};

export type ResolveContext = {
  readonly clicked: SessionSnapshot;
  readonly pageUrl: URL;
  readonly hints: ResolveHints;
  // Rescues a prefetched URL still provisionally owned by the previous reel's session.
  readonly clickedVideoUrls: ReadonlyArray<AttributedUrlView>;
};

// Cross-session ledger lookup by a `key=value` id hint (Instagram's xpv_asset_id).
export type FindUrlsByIdHint = (idHint: string) => ReadonlyArray<AttributedUrlView>;

// The whole dispatch: pick the strategy by hostname, Generic being the fallback. Strategies
// are pure functions of the context; Instagram also takes the ledger lookup.
export function selectMediaForPage(ctx: ResolveContext, findUrlsByIdHint: FindUrlsByIdHint): Resolution {
  const host = ctx.pageUrl.hostname;
  // Instagram and Facebook share the same CDN format (fbcdn.net, efg/vencode_tag/xpv_asset_id).
  if (host === "www.instagram.com" || host.endsWith(".instagram.com")
    || host === "www.facebook.com" || host.endsWith(".facebook.com")) {
    return selectMeta(ctx, findUrlsByIdHint);
  }
  if (host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be") {
    return selectYouTube(ctx);
  }
  return selectGeneric(ctx);
}

// Belt-and-suspenders against pre-bind leakage that survived the ledger.
// Stream manifests represent "what to download", not attribution data — exempt from time filter.
export function postBindAttributedUrls(view: SessionSnapshot): SessionSnapshot["attributedUrls"] {
  if (view.lastBoundAt <= 0) { return view.attributedUrls; }
  return view.attributedUrls.filter((r) =>
    r.capturedAt >= view.lastBoundAt || isStreamUrl(r.url, r.contentType),
  );
}

// A prefetched sibling is fetched after the clicked video's own URL, so freshness ranks last.
function isBetter(candidate: AttributedUrlView, best: AttributedUrlView): boolean {
  if ((candidate.clickedVideo === "same") !== (best.clickedVideo === "same")) { return candidate.clickedVideo === "same"; }
  if (candidate.isLockedByMse !== best.isLockedByMse) { return candidate.isLockedByMse; }
  return candidate.capturedAt > best.capturedAt;
}

// The most trusted attributed URL whose url/contentType matches.
export function bestMatching(
  urls: SessionSnapshot["attributedUrls"],
  predicate: (url: string, contentType: string) => boolean,
): string | undefined {
  let best: AttributedUrlView | undefined;
  for (const entry of urls) {
    if (!predicate(entry.url, entry.contentType)) { continue; }
    if (!best || isBetter(entry, best)) { best = entry; }
  }
  return best?.url;
}

// The most trusted video + audio track for a DASH merge, or null if either side is missing.
// The caller decides whether to strip range params off the returned URLs.
export function selectMergePair(
  urls: SessionSnapshot["attributedUrls"],
  classify: (url: string, contentType: string) => string,
): { video: string; audio: string } | null {
  const video = bestMatching(urls, (url, contentType) => classify(url, contentType) === "video");
  const audio = bestMatching(urls, (url, contentType) => classify(url, contentType) === "audio");
  return video && audio ? { video, audio } : null;
}
