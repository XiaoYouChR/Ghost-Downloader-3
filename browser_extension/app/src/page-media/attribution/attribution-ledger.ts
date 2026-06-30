import type {AttributionTier} from "../types";

// Single arbiter of URL → session ownership. Claims before MSE bind are provisional
// (lockedByMse=false); reclaimUrls moves them to whichever session's MSE later proves
// ownership. This is the structural fix for the Douyin v-2 prefetch case.

export type LedgerEntry = {
  sessionId: string;
  attributedAt: number;
  tier: AttributionTier;
  lockedByMse: boolean;
};

export type ReclaimResult = {
  urls: string[];
};

export type ClaimResult = {
  ownerId: string;
  moved: boolean; // true if this claim replaced a prior (provisional) owner
};

export class AttributionLedger {
  private readonly entries = new Map<string, LedgerEntry>();

  // Locked entries never move. Provisional entries only move on a locked claim — late
  // tier-2/3 claims don't churn ownership.
  claim(url: string, sessionId: string, tier: AttributionTier, attributedAt: number, locked: boolean): ClaimResult {
    const existing = this.entries.get(url);
    if (existing && existing.lockedByMse) {
      return { ownerId: existing.sessionId, moved: false };
    }
    if (existing && !locked) {
      return { ownerId: existing.sessionId, moved: false };
    }
    this.entries.set(url, { sessionId, attributedAt, tier, lockedByMse: locked });
    return {
      ownerId: sessionId,
      moved: existing != null && existing.sessionId !== sessionId,
    };
  }

  lookup(url: string): LedgerEntry | null {
    return this.entries.get(url) ?? null;
  }

  // idHintsForUrl is a callback so the ledger stays free of URL parsing.
  reclaimUrls(
    newSessionId: string,
    newIdHints: ReadonlySet<string>,
    idHintsForUrl: (url: string) => ReadonlySet<string>,
    now: number,
  ): ReclaimResult {
    if (newIdHints.size === 0) { return { urls: [] }; }
    const moved: string[] = [];
    for (const [url, entry] of this.entries) {
      if (entry.lockedByMse) { continue; }
      if (entry.sessionId === newSessionId) { continue; }
      const urlIdHints = idHintsForUrl(url);
      let intersects = false;
      for (const d of urlIdHints) {
        if (newIdHints.has(d)) { intersects = true; break; }
      }
      if (!intersects) { continue; }
      this.entries.set(url, {
        sessionId: newSessionId,
        attributedAt: now,
        tier: "mse",
        lockedByMse: true,
      });
      moved.push(url);
    }
    return { urls: moved };
  }

  // Pins URLs that were already correctly attributed before MSE bind.
  lockAllFor(sessionId: string): void {
    for (const [url, entry] of this.entries) {
      if (entry.sessionId === sessionId && !entry.lockedByMse) {
        this.entries.set(url, { ...entry, lockedByMse: true, tier: "mse" });
      }
    }
  }

  release(sessionId: string): string[] {
    const released: string[] = [];
    for (const [url, entry] of this.entries) {
      if (entry.sessionId === sessionId) {
        this.entries.delete(url);
        released.push(url);
      }
    }
    return released;
  }

  size(): number {
    return this.entries.size;
  }
}
