import type {Resolution, VideoSessionFormKind, VideoSessionState} from "./types";

// Strategies see only this — they MUST NOT reach back into the controller.
export type SessionSnapshot = {
  readonly id: string;
  readonly state: VideoSessionState;
  readonly formKind: VideoSessionFormKind;
  readonly lastBoundAt: number;
  readonly resources: ReadonlyArray<{
    readonly url: string;
    readonly contentType: string;
    readonly capturedAt: number;
  }>;
  readonly discriminators: ReadonlySet<string>;
};

export type ResolveHints = {
  readonly poster: string;
  readonly title: string;
};

export type AttributedUrlMatch = {
  readonly url: string;
  readonly contentType: string;
  readonly capturedAt: number;
  readonly lockedByMse: boolean;
};

// findUrlsByDiscriminator is the escape hatch for Douyin's prefetch case where the URL
// is provisionally owned by v-1 but carries v-2's __vid.
export type ResolveContext = {
  readonly clicked: SessionSnapshot;
  readonly pageUrl: URL;
  readonly hints: ResolveHints;
  readonly now: number;
  findUrlsByDiscriminator(discriminator: string): ReadonlyArray<AttributedUrlMatch>;
};

export interface MediaStrategy {
  readonly id: string;
  matches(pageUrl: URL): boolean;
  resolve(ctx: ResolveContext): Resolution;
}

// Belt-and-suspenders against pre-bind leakage that survived the ledger.
export function postBindResources(view: SessionSnapshot): SessionSnapshot["resources"] {
  if (view.lastBoundAt <= 0) { return view.resources; }
  return view.resources.filter((r) => r.capturedAt >= view.lastBoundAt);
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
