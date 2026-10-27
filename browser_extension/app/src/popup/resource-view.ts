import type {Resource, ResourceKind, ResourceSort} from "../shared/types";
import {fileExtension, filenameFromUrl, isDashSegment, kindOf} from "../shared/utils";

export interface ResourceQuery {
  kind: ResourceKind | "all";
  text: string;
  sort: ResourceSort;
}

export interface ResourceView {
  kindCounts: Array<{ kind: ResourceKind | "all"; count: number }>;
  resources: Resource[];
  dashSegments: Resource[];
  hlsSegments: Resource[];
}

const KIND_ORDER: ResourceKind[] = ["video", "audio", "pdf", "image", "archive", "document", "spreadsheet", "other"];

function nameOf(resource: Resource): string {
  return resource.filename || filenameFromUrl(resource.url);
}

function byNewest(left: Resource, right: Resource): number {
  return right.capturedAt - left.capturedAt;
}

const COMPARATORS: Record<ResourceSort, (left: Resource, right: Resource) => number> = {
  time: byNewest,
  // Unknown size (0) ranks below every known size.
  size: (left, right) => (right.size || -1) - (left.size || -1) || byNewest(left, right),
  name: (left, right) =>
    nameOf(left).localeCompare(nameOf(right), undefined, { numeric: true, sensitivity: "base" }) || byNewest(left, right),
};

function matchWords(resource: Resource, words: string[]): boolean {
  const text = `${nameOf(resource)} ${resource.url} ${resource.pageTitle}`.toLowerCase();
  return words.every((word) => text.includes(word));
}

/** kindCounts counts after the text search; the queried kind stays listed even at 0. */
export function buildResourceView(resources: Resource[], query: ResourceQuery): ResourceView {
  const words = query.text.toLowerCase().split(/\s+/).filter(Boolean);
  const matched = resources
    .filter((resource) => matchWords(resource, words))
    .map((resource) => ({ resource, kind: kindOf(resource) }));

  const counts = new Map<ResourceKind, number>();
  for (const { kind } of matched) {
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  const kindCounts: ResourceView["kindCounts"] = [
    { kind: "all", count: matched.length },
    ...KIND_ORDER
      .filter((kind) => counts.has(kind) || kind === query.kind)
      .map((kind) => ({ kind, count: counts.get(kind) ?? 0 })),
  ];

  const visible = matched
    .filter(({ kind }) => query.kind === "all" || kind === query.kind)
    .map(({ resource }) => resource)
    .sort(COMPARATORS[query.sort]);

  // Bare .ts files only count as HLS segments when a playlist is around to own them.
  const hasPlaylist = visible.some((resource) => {
    const extension = fileExtension(nameOf(resource));
    return extension === "m3u8" || extension === "mpd";
  });
  const view: ResourceView = { kindCounts, resources: [], dashSegments: [], hlsSegments: [] };
  for (const resource of visible) {
    if (isDashSegment(resource)) {
      view.dashSegments.push(resource);
    } else if (hasPlaylist && fileExtension(nameOf(resource)) === "ts") {
      view.hlsSegments.push(resource);
    } else {
      view.resources.push(resource);
    }
  }
  return view;
}
