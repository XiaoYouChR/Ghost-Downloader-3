import type {Resource} from "../shared/types";
import {
  HEADER_EXPIRATION_MS,
  HEADER_SNAPSHOT_LIMIT,
  RESOURCE_LIMIT,
} from "./constants";

export type HeaderSnapshot = {
  url: string;
  headers: Record<string, string>;
  capturedAt: number;
  tabId: number | null;
  supportsRange: boolean;
};

// Forwarded to desktop on resource handoff. Cookies/auth/sec-* are needed for gated CDNs;
// the rest are dropped to keep storage small and avoid leaking irrelevant headers.
const HEADER_WHITELIST = new Set([
  "accept",
  "accept-language",
  "authorization",
  "cookie",
  "origin",
  "referer",
  "sec-ch-ua",
  "sec-ch-ua-arch",
  "sec-ch-ua-bitness",
  "sec-ch-ua-full-version",
  "sec-ch-ua-full-version-list",
  "sec-ch-ua-mobile",
  "sec-ch-ua-model",
  "sec-ch-ua-platform",
  "sec-ch-ua-platform-version",
  "sec-fetch-dest",
  "sec-fetch-mode",
  "sec-fetch-site",
  "user-agent",
  "priority",
]);

export type ResourceCacheSnapshot = {
  resources: Record<string, Resource[]>;
  headers: HeaderSnapshot[];
};

export function selectAllowedHeaders(headers: Record<string, string> | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers ?? {})) {
    const name = key.trim().toLowerCase();
    if (!HEADER_WHITELIST.has(name)) {
      continue;
    }
    const text = value.trim();
    if (!text) {
      continue;
    }
    result[name] = text;
  }
  return result;
}

export function urlWithoutHash(value: string, allowBlob = false): string {
  if (!value) {
    return "";
  }
  if (allowBlob && value.startsWith("blob:")) {
    return value;
  }
  try {
    const url = new URL(value);
    url.hash = "";
    return url.toString();
  } catch {
    return value.split("#", 1)[0] ?? value;
  }
}

function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

function sortResources(resources: Iterable<Resource>): Resource[] {
  return [...resources].sort((left, right) => right.capturedAt - left.capturedAt);
}

function resourceFromStorage(resource: Resource): Resource {
  return {...resource, requestHeaders: selectAllowedHeaders(resource.requestHeaders)};
}

function headerSnapshotFromStorage(snapshot: HeaderSnapshot): HeaderSnapshot {
  return {...snapshot, headers: selectAllowedHeaders(snapshot.headers)};
}

// Pure in-memory cache for captured resources + request-header snapshots. No chrome deps,
// so it unit-tests cleanly. The bridge owns persistence (toSnapshot/load) and wires
// `onChange` to a debounced save. clearTab clears both resources and headers because tab
// close and navigation always need both gone together.
export class ResourceCache {
  private resourcesByTab = new Map<number, Map<string, Resource>>();
  private resourcesById = new Map<string, Resource>();
  private headerSnapshotsByUrl = new Map<string, HeaderSnapshot>();
  private awaiters = new Map<string, Set<(resource: Resource) => void>>();
  private readonly onChange: () => void;

  constructor(onChange: () => void) {
    this.onChange = onChange;
  }

  add(resource: Resource): void {
    let resourceMap = this.resourcesByTab.get(resource.tabId);
    if (!resourceMap) {
      resourceMap = new Map<string, Resource>();
      this.resourcesByTab.set(resource.tabId, resourceMap);
    }
    const existing = resourceMap.get(resource.id);
    const merged: Resource = existing
      ? {
          ...existing,
          ...resource,
          pageTitle: resource.pageTitle || existing.pageTitle,
          pageUrl: resource.pageUrl || existing.pageUrl,
          filename: resource.filename || existing.filename,
          mime: resource.mime || existing.mime,
          size: resource.size > 0 ? resource.size : existing.size,
          supportsRange: resource.supportsRange || existing.supportsRange,
          referer: resource.referer || existing.referer,
          // Fresh cookies/auth/sec-* override stale ones (per-key, like every field above).
          requestHeaders: {
            ...existing.requestHeaders,
            ...resource.requestHeaders,
          },
          capturedAt: Math.max(existing.capturedAt, resource.capturedAt),
          sentToDesktopAt: existing.sentToDesktopAt ?? resource.sentToDesktopAt,
        }
      : resource;

    resourceMap.set(merged.id, merged);
    this.resourcesById.set(merged.id, merged);

    const awaiterSet = this.awaiters.get(merged.id);
    if (awaiterSet && awaiterSet.size > 0) {
      this.awaiters.delete(merged.id);
      for (const resolver of awaiterSet) {
        try {
          resolver(merged);
        } catch {
          // Awaiter callback failed — swallow so a bad consumer can't break capture.
        }
      }
    }

    // A late webRequest event can carry real size/headers for a row an earlier click
    // synthesised. Propagate the enrichment to every row sharing this URL.
    const mergedUrl = urlWithoutHash(merged.url, true);
    if (mergedUrl && (merged.size > 0 || merged.mime || merged.supportsRange)) {
      for (const related of this.resourcesById.values()) {
        if (related.id === merged.id || !related.id.endsWith(`:${mergedUrl}`)) {
          continue;
        }
        related.size = merged.size > 0 ? merged.size : related.size;
        related.mime = merged.mime || related.mime;
        related.filename = related.filename && related.filename !== "resource" ? related.filename : merged.filename;
        related.supportsRange = merged.supportsRange || related.supportsRange;
      }
    }

    this.removeOverflow(resource.tabId);
    this.onChange();
  }

  resourceById(id: string): Resource | undefined {
    return this.resourcesById.get(id);
  }

  resourceByUrl(url: string, tabId?: number): Resource | null {
    const resourceIdSuffix = `:${urlWithoutHash(url, true)}`;
    let matched: Resource | null = null;
    const resources = tabId == null
      ? this.resourcesById.values()
      : (this.resourcesByTab.get(tabId)?.values() ?? []);
    for (const resource of resources) {
      if (!resource.id.endsWith(resourceIdSuffix)) {
        continue;
      }
      if (matched == null || resource.capturedAt > matched.capturedAt) {
        matched = resource;
      }
    }
    return matched;
  }

  resourcesForTab(tabId: number): Resource[] {
    return sortResources(this.resourcesByTab.get(tabId)?.values() ?? []);
  }

  otherResources(activeTabId: number | null): Resource[] {
    const result: Resource[] = [];
    for (const [tabId, resourceMap] of this.resourcesByTab.entries()) {
      if (activeTabId != null && tabId === activeTabId) {
        continue;
      }
      result.push(...resourceMap.values());
    }
    return sortResources(result);
  }

  enrichResource(urls: string[], meta: {
    duration?: number;
    videoWidth?: number;
    videoHeight?: number;
    posterUrl?: string;
  }): void {
    let changed = false;
    for (const url of urls) {
      const normalizedUrl = urlWithoutHash(url, true);
      for (const resource of this.resourcesById.values()) {
        if (!resource.id.endsWith(`:${normalizedUrl}`)) { continue; }
        if (meta.duration != null && meta.duration > 0) { resource.duration = meta.duration; }
        if (meta.videoWidth != null && meta.videoWidth > 0) { resource.videoWidth = meta.videoWidth; }
        if (meta.videoHeight != null && meta.videoHeight > 0) { resource.videoHeight = meta.videoHeight; }
        if (meta.posterUrl) { resource.posterUrl = meta.posterUrl; }
        changed = true;
      }
    }
    if (changed) { this.onChange(); }
  }

  enrichTabPoster(tabId: number, posterUrl: string): void {
    const resourceMap = this.resourcesByTab.get(tabId);
    if (!resourceMap || !posterUrl) { return; }
    let changed = false;
    for (const resource of resourceMap.values()) {
      if (!resource.posterUrl) {
        resource.posterUrl = posterUrl;
        changed = true;
      }
    }
    if (changed) { this.onChange(); }
  }

  setSent(id: string): void {
    const resource = this.resourcesById.get(id);
    if (!resource) {
      return;
    }
    resource.sentToDesktopAt = Date.now();
    this.onChange();
  }

  clearTab(tabId: number): void {
    const resourceMap = this.resourcesByTab.get(tabId);
    if (resourceMap) {
      for (const resourceId of resourceMap.keys()) {
        this.resourcesById.delete(resourceId);
      }
      this.resourcesByTab.delete(tabId);
    }

    let headersChanged = false;
    for (const [url, snapshot] of this.headerSnapshotsByUrl.entries()) {
      if (snapshot.tabId === tabId) {
        this.headerSnapshotsByUrl.delete(url);
        headersChanged = true;
      }
    }

    if (resourceMap || headersChanged) {
      this.onChange();
    }
  }

  headerSnapshotByUrl(url: string): HeaderSnapshot | null {
    this.removeStaleHeaders();
    return this.headerSnapshotsByUrl.get(url) ?? null;
  }

  setHeaderSnapshot(
    url: string,
    headers: Record<string, string>,
    tabId: number | null,
    supportsRange: boolean,
  ): void {
    const existing = this.headerSnapshotsByUrl.get(url);
    const mergedHeaders = {
      ...(existing?.headers ?? {}),
      ...headers,
    };
    const mergedSupportsRange = supportsRange || Boolean(existing?.supportsRange);
    if (Object.keys(mergedHeaders).length === 0 && !mergedSupportsRange) {
      return;
    }
    this.headerSnapshotsByUrl.set(url, {
      url,
      headers: mergedHeaders,
      capturedAt: Date.now(),
      tabId: tabId ?? existing?.tabId ?? null,
      supportsRange: mergedSupportsRange,
    });
    this.removeStaleHeaders();
    this.onChange();
  }

  // SPA watch URLs often have no snapshot of their own; fall back to the freshest same-host
  // request that carried a cookie. Only cookie + user-agent are forwarded.
  headersForPage(pageUrl: string): Record<string, string> {
    const host = hostOf(pageUrl);
    if (host === null) {
      return {};
    }

    let snapshot = this.headerSnapshotByUrl(pageUrl);
    if (!snapshot?.headers.cookie) {
      let freshest: HeaderSnapshot | null = null;
      for (const candidate of this.headerSnapshotsByUrl.values()) {
        if (!candidate.headers.cookie || hostOf(candidate.url) !== host) {
          continue;
        }
        if (!freshest || candidate.capturedAt > freshest.capturedAt) {
          freshest = candidate;
        }
      }
      snapshot = freshest;
    }

    const headers: Record<string, string> = {};
    if (snapshot?.headers.cookie) {
      headers.cookie = snapshot.headers.cookie;
    }
    if (snapshot?.headers["user-agent"]) {
      headers["user-agent"] = snapshot.headers["user-agent"];
    }
    return headers;
  }

  // Lets resourceForMediaUrl wait when a click races ahead of webRequest (SW restart).
  waitForResource(id: string, timeoutMs: number): Promise<Resource | null> {
    return new Promise((resolve) => {
      let set = this.awaiters.get(id);
      if (!set) {
        set = new Set();
        this.awaiters.set(id, set);
      }
      let settled = false;
      const finish = (value: Resource | null) => {
        if (settled) {
          return;
        }
        settled = true;
        set?.delete(resolver);
        if (set && set.size === 0) {
          this.awaiters.delete(id);
        }
        clearTimeout(timer);
        resolve(value);
      };
      const resolver = (resource: Resource) => finish(resource);
      set.add(resolver);
      const timer = setTimeout(() => finish(null), timeoutMs);
    });
  }

  toSnapshot(): ResourceCacheSnapshot {
    this.removeStaleHeaders();
    const resources: Record<string, Resource[]> = {};
    for (const [tabId, resourceMap] of this.resourcesByTab.entries()) {
      resources[String(tabId)] = sortResources(resourceMap.values()).slice(0, RESOURCE_LIMIT);
    }
    return {
      resources,
      headers: [...this.headerSnapshotsByUrl.values()],
    };
  }

  load(snapshot: ResourceCacheSnapshot): void {
    this.resourcesByTab.clear();
    this.resourcesById.clear();
    for (const [tabIdText, resources] of Object.entries(snapshot.resources ?? {})) {
      const tabId = Number(tabIdText);
      if (!Number.isInteger(tabId) || tabId <= 0 || !Array.isArray(resources)) {
        continue;
      }
      const resourceMap = new Map<string, Resource>();
      for (const resource of sortResources(resources.map(resourceFromStorage)).slice(0, RESOURCE_LIMIT)) {
        resourceMap.set(resource.id, resource);
        this.resourcesById.set(resource.id, resource);
      }
      this.resourcesByTab.set(tabId, resourceMap);
    }

    this.headerSnapshotsByUrl.clear();
    for (const snapshotHeader of snapshot.headers ?? []) {
      const normalized = headerSnapshotFromStorage(snapshotHeader);
      if (!normalized.url) {
        continue;
      }
      this.headerSnapshotsByUrl.set(normalized.url, normalized);
    }
    this.removeStaleHeaders();
  }

  private removeOverflow(tabId: number): void {
    const resourceMap = this.resourcesByTab.get(tabId);
    if (!resourceMap || resourceMap.size <= RESOURCE_LIMIT) {
      return;
    }
    const keepIds = new Set(sortResources(resourceMap.values()).slice(0, RESOURCE_LIMIT).map((resource) => resource.id));
    for (const resourceId of resourceMap.keys()) {
      if (keepIds.has(resourceId)) {
        continue;
      }
      resourceMap.delete(resourceId);
      this.resourcesById.delete(resourceId);
    }
  }

  private removeStaleHeaders(): void {
    const now = Date.now();
    const snapshots = [...this.headerSnapshotsByUrl.values()]
      .filter((snapshot) => snapshot.url && now - snapshot.capturedAt <= HEADER_EXPIRATION_MS)
      .sort((left, right) => right.capturedAt - left.capturedAt)
      .slice(0, HEADER_SNAPSHOT_LIMIT);

    this.headerSnapshotsByUrl.clear();
    for (const snapshot of snapshots) {
      this.headerSnapshotsByUrl.set(snapshot.url, snapshot);
    }
  }
}
