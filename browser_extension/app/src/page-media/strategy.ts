import type {Resolution, VideoSessionFormKind} from "./types";

// One attributed URL as the strategies see it — also the element type of
// SessionSnapshot.attributedUrls and of findUrlsByDiscriminator's return.
export type AttributedUrlView = {
  readonly url: string;
  readonly contentType: string;
  readonly capturedAt: number;
};

// Strategies see only this — they MUST NOT reach back into the controller.
export type SessionSnapshot = {
  readonly formKind: VideoSessionFormKind;
  readonly lastBoundAt: number;
  readonly attributedUrls: ReadonlyArray<AttributedUrlView>;
};

export type ResolveHints = {
  readonly poster: string;
};

// findUrlsByDiscriminator is the escape hatch for Douyin's prefetch case where the URL
// is provisionally owned by v-1 but carries v-2's __vid.
export type ResolveContext = {
  readonly clicked: SessionSnapshot;
  readonly pageUrl: URL;
  readonly hints: ResolveHints;
  findUrlsByDiscriminator(discriminator: string): ReadonlyArray<AttributedUrlView>;
};

export interface MediaStrategy {
  readonly id: string;
  matches(pageUrl: URL): boolean;
  resolve(ctx: ResolveContext): Resolution;
}

// Belt-and-suspenders against pre-bind leakage that survived the ledger.
export function postBindAttributedUrls(view: SessionSnapshot): SessionSnapshot["attributedUrls"] {
  if (view.lastBoundAt <= 0) { return view.attributedUrls; }
  return view.attributedUrls.filter((r) => r.capturedAt >= view.lastBoundAt);
}

export function newestBy<T>(items: ReadonlyArray<T>, key: (item: T) => number): T | undefined {
  if (items.length === 0) { return undefined; }
  let best = items[0];
  let bestKey = key(best);
  for (let i = 1; i < items.length; i += 1) {
    const k = key(items[i]);
    if (k > bestKey) { best = items[i]; bestKey = k; }
  }
  return best;
}

// The freshest attributed URL whose url/contentType matches — the shared shape behind every
// "pick the newest stream / muxed / track" line the strategies used to spell out by hand.
export function newestMatching(
  urls: SessionSnapshot["attributedUrls"],
  predicate: (url: string, contentType: string) => boolean,
): string | undefined {
  return newestBy(urls.filter((entry) => predicate(entry.url, entry.contentType)), (entry) => entry.capturedAt)?.url;
}

// The freshest video + audio track for a DASH merge, or null if either side is missing.
// The caller decides whether to strip range params off the returned URLs.
export function selectMergePair(
  urls: SessionSnapshot["attributedUrls"],
  classify: (url: string, contentType: string) => string,
): { video: string; audio: string } | null {
  const video = newestMatching(urls, (url, contentType) => classify(url, contentType) === "video");
  const audio = newestMatching(urls, (url, contentType) => classify(url, contentType) === "audio");
  return video && audio ? { video, audio } : null;
}
