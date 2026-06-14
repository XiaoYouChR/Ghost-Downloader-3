import {isCatCatchMedia} from "../shared/cat-catch";
import {fileExtension, filenameFromUrl, mimeFromUrl} from "../shared/utils";

import {AttributionLedger} from "./attribution-ledger";
import {pickStrategy} from "./strategy-registry";
import {isMediaSignal} from "./signals";
import type {AttributedUrlView, MediaStrategy, SessionSnapshot, ResolveContext, ResolveHints} from "./strategy";
import type {
  AttributionTier,
  MseAttributionSignal,
  Resolution,
  VideoSession,
  VideoSessionFormKind,
  AttributedUrlMeta,
  VideoSessionState,
} from "./types";

const LOG_PREFIX = "[GD3 Media]";
const VIDEO_ID_QUERY_KEYS = ["__vid", "v", "modal_id", "video_id", "id", "bvid", "aid"];
// Budget from the FIRST Pending — not per re-eval.
const WAIT_FOR_TIMEOUT_MS = 8000;
// Matches the overlay status toast — auto-reset and toast fade on the same clock.
const TERMINAL_RESET_MS = 1600;

type ResolveStateListener = (state: VideoSessionState, reason: string) => void;

// mse_buffer_appended usually follows fetch_completed within tens of ms; slow CPUs stretch.
const FETCH_BUFFER_CORRELATION_MS = 2500;
const RECENT_FETCHES_CAP = 16;

function looksLikeVideoIdSegment(segment: string): boolean {
  if (segment.length < 10) { return false; }
  if (!/^[A-Za-z0-9_-]+$/.test(segment)) { return false; }
  let longestRun = 0;
  for (const run of segment.split(/[-_]+/)) {
    if (run.length > longestRun) { longestRun = run.length; }
  }
  return longestRun >= 10;
}

function urlIdHints(url: string): Set<string> {
  const result = new Set<string>();
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return result;
  }
  for (const segment of parsed.pathname.split("/")) {
    if (looksLikeVideoIdSegment(segment)) { result.add(segment); }
  }
  for (const key of VIDEO_ID_QUERY_KEYS) {
    const value = parsed.searchParams.get(key);
    if (value && value.length >= 4) { result.add(`${key}=${value}`); }
  }
  return result;
}

function toFormKind(mimeTypes: Set<string>): VideoSessionFormKind {
  if (mimeTypes.size === 0) { return "unknown"; }

  if (mimeTypes.size === 1) {
    const [mime] = mimeTypes;
    const codecsMatch = /codecs\s*=\s*"([^"]*)"|codecs\s*=\s*([^;]*)/i.exec(mime);
    const codecsText = codecsMatch?.[1] ?? codecsMatch?.[2] ?? "";
    const codecs = codecsText.split(",").map((part) => part.trim()).filter(Boolean);
    return codecs.length >= 2 ? "muxed" : "unknown";
  }

  let hasVideo = false;
  let hasAudio = false;
  for (const mime of mimeTypes) {
    if (mime.startsWith("video/")) { hasVideo = true; }
    if (mime.startsWith("audio/")) { hasAudio = true; }
  }
  return hasVideo && hasAudio ? "dash" : "unknown";
}

// Per-site strategies are extension points; bubbling their exceptions to the overlay
// would crash the click pipeline.
function tryResolve(strategy: MediaStrategy, ctx: ResolveContext): Resolution {
  try {
    return strategy.resolve(ctx);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`${LOG_PREFIX} strategy "${strategy.id}" threw`, error);
    return { kind: "refused", message: `策略异常: ${message}` };
  }
}

function toSessionSnapshot(session: VideoSession): SessionSnapshot {
  const attributedUrls: SessionSnapshot["attributedUrls"] = Object.freeze(
    [...session.attributedUrls.entries()].map(([url, meta]) => Object.freeze({
      url,
      contentType: meta.contentType,
      capturedAt: meta.capturedAt,
    })),
  );
  return Object.freeze({
    formKind: session.formKind,
    lastBoundAt: session.lastBoundAt,
    attributedUrls,
  });
}


class PageMediaController {
  private readonly elementsWithListeners = new WeakSet<HTMLMediaElement>();
  private readonly sessionsByElement = new WeakMap<HTMLMediaElement, VideoSession>();
  private readonly sessionsById = new Map<string, VideoSession>();
  private readonly sessionByMediaSourceId = new Map<string, VideoSession>();
  private readonly mediaSourceIdByObjectUrl = new Map<string, string>();
  private readonly resolveListenerByElement = new WeakMap<HTMLMediaElement, ResolveStateListener>();
  private readonly ledger = new AttributionLedger();
  private mutationObserver: MutationObserver | null = null;
  private performanceObserver: PerformanceObserver | null = null;
  private lastBoundSession: VideoSession | null = null;
  private sessionCounter = 0;
  // The only way to definitively bind a URL to a specific <video>: lock the most recent
  // unlocked fetch to whichever session consumed it via appendBuffer.
  private readonly recentFetches: Array<{ url: string; capturedAt: number }> = [];

  start(): void {
    document.querySelectorAll<HTMLMediaElement>("video, audio").forEach((element) => {
      this.trackMediaElement(element);
    });

    this.mutationObserver = new MutationObserver(this.onMutations);
    this.mutationObserver.observe(document.documentElement, { childList: true, subtree: true });

    try {
      this.performanceObserver = new PerformanceObserver(this.onResourceTimingEntries);
      this.performanceObserver.observe({ type: "resource", buffered: true });
    } catch {
      // mse-probe.ts covers attribution if PerformanceObserver throws.
    }

    window.addEventListener("message", this.onMessage);
    console.log(`${LOG_PREFIX} controller started in frame ${location.href}`);
  }

  private onMutations = (mutations: MutationRecord[]): void => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node instanceof HTMLMediaElement) {
          this.trackMediaElement(node);
          return;
        }
        if (node instanceof Element) {
          node.querySelectorAll<HTMLMediaElement>("video, audio").forEach((element) => {
            this.trackMediaElement(element);
          });
        }
      });
    }
  };

  private trackMediaElement(element: HTMLMediaElement): void {
    if (this.elementsWithListeners.has(element)) { return; }
    this.elementsWithListeners.add(element);

    element.addEventListener("loadstart", () => this.onMediaLoadStart(element));
    element.addEventListener("loadedmetadata", () => this.onMediaLoadedMetadata(element));
    element.addEventListener("emptied", () => this.onMediaEmptied(element));

    const initialSrc = element.currentSrc || element.src || "";
    if (initialSrc) {
      this.openSessionFor(element);
    }
  }

  private onMediaLoadStart(element: HTMLMediaElement): void {
    const src = element.currentSrc || element.src || "";
    if (!src) { return; }
    const existing = this.sessionsByElement.get(element);
    if (!existing) {
      this.openSessionFor(element);
      return;
    }
    if (existing.src !== src) {
      console.log(`${LOG_PREFIX} ${existing.id} src changed → new session`, { from: existing.src, to: src });
      this.openSessionFor(element);
    }
  }

  private onMediaLoadedMetadata(element: HTMLMediaElement): void {
    let session = this.sessionsByElement.get(element);
    if (!session) {
      const src = element.currentSrc || element.src || "";
      if (!src) { return; }
      session = this.openSessionFor(element);
    }
    this.transition(session, "armed", "loadedmetadata");
    const src = element.currentSrc || element.src || "";
    console.log(`${LOG_PREFIX} ${session.id} loadedmetadata`, { state: session.state, src });
    this.bindBlobToMediaSource(session, src);
  }

  private onMediaEmptied(element: HTMLMediaElement): void {
    const previous = this.sessionsByElement.get(element);
    if (!previous) { return; }
    console.log(`${LOG_PREFIX} ${previous.id} emptied — releasing`);

    // Unblock any inflight click before teardown, otherwise it sits orphaned for 8s.
    this.notifyResolveListener(previous, "refused", "媒体已释放");

    // Without release, Douyin/X feeds accumulate one session per swipe forever.
    this.ledger.release(previous.id);
    this.sessionsByElement.delete(element);
    this.sessionsById.delete(previous.id);
    for (const mediaSourceId of previous.mediaSourceIds) {
      this.sessionByMediaSourceId.delete(mediaSourceId);
    }
    for (const [objectUrl, mediaSourceId] of this.mediaSourceIdByObjectUrl) {
      if (previous.mediaSourceIds.has(mediaSourceId)) {
        this.mediaSourceIdByObjectUrl.delete(objectUrl);
      }
    }
    if (this.lastBoundSession?.id === previous.id) {
      this.lastBoundSession = null;
    }
  }

  private openSessionFor(element: HTMLMediaElement): VideoSession {
    this.sessionCounter += 1;
    const src = element.currentSrc || element.src || "";
    const session: VideoSession = {
      id: `v-${this.sessionCounter}`,
      elementRef: new WeakRef(element),
      src,
      state: "inert",
      startedAt: performance.now(),
      lastBoundAt: 0,
      attributedUrls: new Map(),
      mimeTypes: new Set(),
      mediaSourceIds: new Set(),
      idHints: new Set(),
      formKind: "unknown",
    };
    this.sessionsByElement.set(element, session);
    this.sessionsById.set(session.id, session);
    console.log(`${LOG_PREFIX} ${session.id} opened`, { tag: element.tagName.toLowerCase(), src });

    if (src) {
      this.bindBlobToMediaSource(session, src);
      if (!src.startsWith("blob:")) {
        // Direct <video src=...>, no MSE — provisional until something else confirms.
        this.attribute(session, src, mimeFromUrl(src), 2, false);
      }
    }
    return session;
  }

  private bindBlobToMediaSource(session: VideoSession, src: string): void {
    if (!src.startsWith("blob:")) { return; }
    const mediaSourceId = this.mediaSourceIdByObjectUrl.get(src);
    if (!mediaSourceId) { return; }
    if (session.mediaSourceIds.has(mediaSourceId)) { return; }
    session.mediaSourceIds.add(mediaSourceId);
    this.sessionByMediaSourceId.set(mediaSourceId, session);
    this.lastBoundSession = session;
    session.lastBoundAt = performance.now();
    console.log(`${LOG_PREFIX} ${session.id} bound to ${mediaSourceId}`);

    // Reclaim URLs the prior session provisionally grabbed during prefetch (Douyin v-2).
    const reclaimed = this.ledger.reclaimUrls(
      session.id,
      session.idHints,
      (url) => urlIdHints(url),
      performance.now(),
    );
    if (reclaimed.urls.length > 0) {
      for (const url of reclaimed.urls) {
        this.handoffUrl(url, session);
      }
      console.log(`${LOG_PREFIX} ${session.id} reclaimed ${reclaimed.urls.length} url(s)`);
    }
    // Pins re-fetches (rebuffering) to this session even after lastBoundSession changes.
    this.ledger.lockAllFor(session.id);
  }

  // capturedAt is reset so newSession's post-bind filter sees the URL as fresh.
  // trackMime, when present, beats the inherited container mime — Instagram's URLs have
  // no audio/video marker, so the SourceBuffer's `codecs=...` is the only way to know.
  private handoffUrl(url: string, newSession: VideoSession, trackMime: string = ""): void {
    let oldSession: VideoSession | null = null;
    let inheritedContentType = "";
    for (const session of this.sessionsById.values()) {
      if (session.id === newSession.id) { continue; }
      const meta = session.attributedUrls.get(url);
      if (meta) { oldSession = session; inheritedContentType = meta.contentType; break; }
    }

    const meta: AttributedUrlMeta = {
      contentType: trackMime || inheritedContentType,
      capturedAt: performance.now(),
      tier: "mse",
      lockedByMse: true,
    };

    if (oldSession) {
      oldSession.attributedUrls.delete(url);
      // Only locked attributed URLs contribute to idHints (see recordAttribution).
      const recomputed = new Set<string>();
      for (const [remainingUrl, remainingMeta] of oldSession.attributedUrls) {
        if (!remainingMeta.lockedByMse) { continue; }
        for (const d of urlIdHints(remainingUrl)) { recomputed.add(d); }
      }
      oldSession.idHints = recomputed;
    }

    newSession.attributedUrls.set(url, meta);
    for (const d of urlIdHints(url)) { newSession.idHints.add(d); }
    this.notifyResolveListener(newSession, newSession.state, "url-handoff");

    if (newSession.state === "inert" || newSession.state === "armed" || newSession.state === "waiting") {
      this.transition(newSession, "ready", `attributed ${url}`);
    }
  }

  // Media-only — analytics fetches landing right before appendBuffer would otherwise
  // get spuriously locked to the active session.
  private recordFetch(url: string, contentType: string): void {
    if (!this.isMediaUrl(url, contentType)) { return; }
    this.recentFetches.push({ url, capturedAt: performance.now() });
    if (this.recentFetches.length > RECENT_FETCHES_CAP) {
      this.recentFetches.shift();
    }
  }

  // Whichever session's MSE consumed the bytes is the URL's true owner — the network
  // mime alone can't distinguish DASH audio from DASH video when they share a container.
  private attributeBufferAppend(mediaSourceId: string, sourceBufferMime: string): void {
    const session = this.sessionByMediaSourceId.get(mediaSourceId);
    if (!session) { return; }
    const now = performance.now();
    for (let i = this.recentFetches.length - 1; i >= 0; i -= 1) {
      const entry = this.recentFetches[i];
      if (now - entry.capturedAt > FETCH_BUFFER_CORRELATION_MS) { break; }
      const ledgerEntry = this.ledger.lookup(entry.url);
      if (ledgerEntry?.lockedByMse) {
        const owner = this.sessionsById.get(ledgerEntry.sessionId);
        const meta = owner?.attributedUrls.get(entry.url);
        if (meta) { this.upgradeTrackMime(meta, sourceBufferMime); }
        continue;
      }
      const claim = this.ledger.claim(entry.url, session.id, "mse", now, true);
      if (claim.moved || claim.ownerId === session.id) {
        if (!session.attributedUrls.has(entry.url)) {
          this.handoffUrl(entry.url, session, sourceBufferMime);
        } else {
          const meta = session.attributedUrls.get(entry.url);
          if (meta) { this.upgradeTrackMime(meta, sourceBufferMime); }
          for (const d of urlIdHints(entry.url)) { session.idHints.add(d); }
        }
        console.log(`${LOG_PREFIX} ${session.id} attributed buffer-append → ${entry.url} via ${sourceBufferMime}`);
      }
      // Consume the entry so repeated appendBuffer events don't lock it to multiple sessions.
      this.recentFetches.splice(i, 1);
      return;
    }
  }

  // SourceBuffer mime (with `codecs=...`) is always more specific than the container mime
  // it would overwrite, so once it's in place we leave it.
  private upgradeTrackMime(meta: AttributedUrlMeta, sourceBufferMime: string): void {
    if (!sourceBufferMime) { return; }
    if (meta.contentType.includes("codecs")) { return; }
    meta.contentType = sourceBufferMime;
  }

  private onMessage = (event: MessageEvent): void => {
    if (isMediaSignal(event.data)) {
      this.onSignal(event.data);
    }
  };

  private onSignal(signal: MseAttributionSignal): void {
    switch (signal.kind) {
      case "mse_objecturl": {
        this.mediaSourceIdByObjectUrl.set(signal.objectUrl, signal.mediaSourceId);
        for (const session of this.sessionsById.values()) {
          if (session.src === signal.objectUrl) {
            this.bindBlobToMediaSource(session, signal.objectUrl);
          }
        }
        return;
      }

      case "mse_source_buffer_added": {
        const session = this.sessionByMediaSourceId.get(signal.mediaSourceId);
        if (!session) { return; }
        if (session.mimeTypes.has(signal.mimeType)) { return; }
        session.mimeTypes.add(signal.mimeType);
        console.log(`${LOG_PREFIX} ${session.id} mime += ${signal.mimeType}`);
        const formKind = toFormKind(session.mimeTypes);
        if (formKind !== session.formKind) {
          session.formKind = formKind;
          console.log(`${LOG_PREFIX} ${session.id} formKind = ${formKind}`);
          this.notifyResolveListener(session, session.state, "formKind-changed");
        }
        return;
      }

      case "mse_buffer_appended":
        this.attributeBufferAppend(signal.mediaSourceId, signal.mimeType);
        return;

      case "request_completed":
        this.recordFetch(signal.url, signal.contentType);
        this.attributeFetch(signal.url, signal.contentType);
        return;
    }
  }

  private onResourceTimingEntries = (list: PerformanceObserverEntryList): void => {
    for (const entry of list.getEntries() as PerformanceResourceTiming[]) {
      this.attributeFetch(entry.name, "");
    }
  };

  private attributeFetch(url: string, contentType: string): void {
    if (!this.isMediaUrl(url, contentType)) { return; }

    const existingEntry = this.ledger.lookup(url);
    if (existingEntry?.lockedByMse) {
      const owner = this.sessionsById.get(existingEntry.sessionId);
      if (owner && !owner.attributedUrls.has(url)) {
        this.recordAttribution(owner, url, contentType, "mse", true);
      }
      return;
    }

    const { session, tier } = this.pickSessionAndTier(url);
    if (!session) {
      console.log(`${LOG_PREFIX} orphan resource`, { url, contentType });
      return;
    }
    if (session.attributedUrls.has(url)) { return; }
    this.attribute(session, url, contentType, tier, false);
  }

  private pickSessionAndTier(url: string): { session: VideoSession | null; tier: AttributionTier } {
    const incoming = urlIdHints(url);

    if (incoming.size > 0) {
      for (const session of this.sessionsById.values()) {
        for (const d of incoming) {
          if (session.idHints.has(d)) {
            return { session, tier: 1 };
          }
        }
      }
    }

    // Provisional — recordAttribution will refuse to add prefetch URLs to
    // lastBoundSession.idHints so they don't poison tier-1 for the next session.
    if (this.lastBoundSession && this.sessionsById.has(this.lastBoundSession.id)) {
      return { session: this.lastBoundSession, tier: 2 };
    }

    if (this.sessionsById.size === 1) {
      for (const session of this.sessionsById.values()) {
        return { session, tier: 3 };
      }
    }

    return { session: null, tier: 3 };
  }

  private attribute(session: VideoSession, url: string, contentType: string, tier: AttributionTier, locked: boolean): void {
    const claim = this.ledger.claim(url, session.id, tier, performance.now(), locked);
    const ownerSession = claim.ownerId === session.id ? session : this.sessionsById.get(claim.ownerId);
    if (!ownerSession) { return; }
    if (ownerSession.attributedUrls.has(url)) { return; }
    this.recordAttribution(ownerSession, url, contentType, tier, locked || claim.ownerId !== session.id);
  }

  private recordAttribution(session: VideoSession, url: string, contentType: string, tier: AttributionTier, locked: boolean): void {
    session.attributedUrls.set(url, {
      contentType,
      capturedAt: performance.now(),
      tier,
      lockedByMse: locked,
    });
    // Provisional claims do NOT update idHints — a v-2 prefetch URL provisionally
    // attributed to lastBoundSession=v-1 would otherwise add v-2's __vid to v-1's set,
    // and v-2's own later URLs would forever tier-1 match v-1.
    if (locked || tier === 0 || tier === 1 || tier === "mse") {
      for (const d of urlIdHints(url)) { session.idHints.add(d); }
    }
    if (session.state === "inert" || session.state === "armed" || session.state === "waiting") {
      this.transition(session, "ready", `attributed ${url}`);
    } else {
      this.notifyResolveListener(session, session.state, `attributed ${url}`);
    }
    console.log(`${LOG_PREFIX} ${session.id} += ${url}`, { hint: contentType, count: session.attributedUrls.size, tier, locked, state: session.state });
  }

  private isMediaUrl(url: string, contentType: string): boolean {
    if (!/^https?:/i.test(url)) { return false; }
    const extension = fileExtension(filenameFromUrl(url));
    return isCatCatchMedia(extension, contentType);
  }

  private transition(session: VideoSession, next: VideoSessionState, reason: string): void {
    const changed = session.state !== next;
    if (changed) {
      const previous = session.state;
      session.state = next;
      console.log(`${LOG_PREFIX} ${session.id} state ${previous} → ${next}`, { reason });
    }
    this.notifyResolveListener(session, next, reason);
    if (changed && (next === "dispatched" || next === "failed" || next === "refused")) {
      // Re-arm so the user can click again without reloading.
      setTimeout(() => {
        if (session.state === next) {
          this.transition(session, session.attributedUrls.size > 0 ? "ready" : "armed", "terminal-reset");
        }
      }, TERMINAL_RESET_MS);
    }
  }

  private notifyResolveListener(session: VideoSession, state: VideoSessionState, reason: string): void {
    const element = session.elementRef.deref();
    if (!element) { return; }
    const listener = this.resolveListenerByElement.get(element);
    if (!listener) { return; }
    try { listener(state, reason); } catch { /* swallow */ }
  }

  attributedUrlsFor(element: HTMLMediaElement | null): string[] {
    if (!element) { return []; }
    const session = this.sessionsByElement.get(element);
    return session ? [...session.attributedUrls.keys()] : [];
  }

  async resolveForElement(
    element: HTMLMediaElement | null,
    hints: ResolveHints,
    onStateChange?: ResolveStateListener,
  ): Promise<Resolution> {
    if (!element) {
      return { kind: "refused", message: "未识别媒体来源" };
    }
    const session = this.sessionsByElement.get(element);
    if (!session) {
      return { kind: "refused", message: "未识别媒体来源" };
    }
    const pageUrl = new URL(location.href);
    const strategy: MediaStrategy = pickStrategy(pageUrl);

    const buildCtx = (): ResolveContext => ({
      clicked: toSessionSnapshot(session),
      pageUrl,
      hints,
      findUrlsByIdHint: (idHint) => this.lookupByIdHint(idHint),
    });

    const initial = tryResolve(strategy, buildCtx());
    if (initial.kind !== "pending") {
      this.applyResolutionToState(session, initial);
      return initial;
    }

    this.transition(session, "waiting", initial.reason);
    let lastPendingReason = initial.reason;

    return new Promise<Resolution>((resolve) => {
      let settled = false;
      const finish = (result: Resolution) => {
        if (settled) { return; }
        settled = true;
        this.resolveListenerByElement.delete(element);
        clearTimeout(timer);
        this.applyResolutionToState(session, result);
        resolve(result);
      };

      this.resolveListenerByElement.set(element, (state, reason) => {
        onStateChange?.(state, reason);
        // onMediaEmptied fires "refused" through this channel; don't run strategy on a torn-down snapshot.
        if (state === "refused" || state === "failed") {
          finish({ kind: "refused", message: reason });
          return;
        }
        const next = tryResolve(strategy, buildCtx());
        if (next.kind === "pending") {
          lastPendingReason = next.reason;
          return;
        }
        finish(next);
      });

      const timer = setTimeout(() => {
        finish({ kind: "refused", message: `${lastPendingReason}（已等待 ${Math.round(WAIT_FOR_TIMEOUT_MS / 1000)}s）` });
      }, WAIT_FOR_TIMEOUT_MS);
    });
  }

  // Douyin uses this to reach across sessions for a prefetched URL claimed by a sibling
  // before the new <video> existed.
  private lookupByIdHint(idHint: string): ReadonlyArray<AttributedUrlView> {
    const matches: AttributedUrlView[] = [];
    for (const session of this.sessionsById.values()) {
      for (const [url, meta] of session.attributedUrls) {
        if (urlIdHints(url).has(idHint)) {
          matches.push({
            url,
            contentType: meta.contentType,
            capturedAt: meta.capturedAt,
          });
        }
      }
    }
    return matches;
  }

  private applyResolutionToState(session: VideoSession, resolution: Resolution): void {
    if (resolution.kind === "selection") {
      this.transition(session, "resolving", "selection-dispatch");
      return;
    }
    if (resolution.kind === "refused") {
      this.transition(session, "refused", resolution.message);
    }
  }

  markDispatchResult(element: HTMLMediaElement | null, ok: boolean, message: string): void {
    if (!element) { return; }
    const session = this.sessionsByElement.get(element);
    if (!session) { return; }
    this.transition(session, ok ? "dispatched" : "failed", message);
  }
}

declare global {
  interface Window {
    __gd3PageMedia?: {
      attributedUrlsForElement(element: HTMLMediaElement | null): string[];
      resolveForElement(
        element: HTMLMediaElement | null,
        hints: ResolveHints,
        onStateChange?: (state: VideoSessionState, reason: string) => void,
      ): Promise<Resolution>;
      markDispatchResult(element: HTMLMediaElement | null, ok: boolean, message: string): void;
    };
  }
}

let controllerInstance: PageMediaController | null = null;

export function startPageMediaController(): void {
  if (controllerInstance) { return; }
  controllerInstance = new PageMediaController();
  controllerInstance.start();
  window.__gd3PageMedia = {
    attributedUrlsForElement: (element) => controllerInstance?.attributedUrlsFor(element) ?? [],
    resolveForElement: (element, hints, onStateChange) =>
      controllerInstance?.resolveForElement(element, hints, onStateChange) ?? Promise.resolve({ kind: "refused" as const, message: "controller not ready" }),
    markDispatchResult: (element, ok, message) =>
      controllerInstance?.markDispatchResult(element, ok, message),
  };
}
